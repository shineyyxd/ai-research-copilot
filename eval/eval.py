# -*- coding: utf-8 -*-
"""
eval.py — RAG 检索评测 harness（金标集驱动）
对 goldset.json 中每条人工标注问答，跑两种检索模式并量化：

  A. 全库开放检索（不给厂商、不给维度锁）—— 模拟真实用户提问
     - Vendor Hit@1 / Hit@3：top-k 命中期望厂商
     - Section Hit@1：top-1 章节 == 期望维度
     - Fact Recall@3：金标事实出现在 top-3 证据文本中（每组 any-of，组间 all-of）
  B. 维度锁定检索（厂商+维度已知，走 lock_section）—— 模拟矩阵组格
     - Fact Recall@3

输出 output/eval_report.md + eval_report.json。零 LLM 依赖、可复现。
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # eval/
RAG = ROOT.parent / "rag"
OUT = Path(os.environ.get("OUT_DIR", ROOT.parent / "output"))
INDEX_PATH = Path(os.environ.get("INDEX_PATH", RAG / "index.json"))
sys.path.insert(0, str(RAG))

from query import query_vec, cosine, retrieve, DIMENSIONS, route_vendor  # noqa: E402

TOP_K = 3


def open_retrieve(chunks, question, top_k=TOP_K, use_router=False):
    """全库开放检索。use_router=True 时先做确定性厂商路由再排序。"""
    pool = chunks
    if use_router:
        v = route_vendor(question)
        if v:
            routed = [c for c in chunks if c["vendor"] == v]
            if routed:
                pool = routed
    qv = query_vec(question)
    scored = sorted(((cosine(qv, c["vec"]), c) for c in pool), key=lambda x: -x[0])
    return [(round(s, 4), c) for s, c in scored[:top_k] if s > 0]


def fact_recall(fact_groups, texts):
    """组间 all-of、组内 any-of：每组至少一个子串命中任一证据文本。"""
    blob = "\n".join(texts)
    hit = sum(1 for group in fact_groups if any(alt in blob for alt in group))
    return hit, len(fact_groups)


def main():
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    chunks = idx["chunks"]
    gold = json.loads((ROOT / "goldset.json").read_text(encoding="utf-8"))
    items = gold["items"]

    rows = []
    agg = {k: 0 for k in ["r_v1", "r_v3", "r_s1", "r_f_hit", "r_f_tot", "r_full",   # raw baseline
                          "v1", "v3", "s1", "fa_hit", "fa_tot", "fa_full",           # routed
                          "fb_hit", "fb_tot", "fb_full"]}                            # locked

    for it in items:
        q, v_exp, d_exp = it["question"], it["vendor"], it["dim"]
        q_full = q + " " + DIMENSIONS.get(d_exp, "")

        # --- A0. 无路由 baseline（修复前）---
        ev_r = open_retrieve(chunks, q_full, use_router=False)
        vr = [c["vendor"] for _, c in ev_r]
        agg["r_v1"] += bool(vr and vr[0] == v_exp)
        agg["r_v3"] += v_exp in vr
        agg["r_s1"] += bool(ev_r and ev_r[0][1]["section"] == d_exp and vr[0] == v_exp)
        rf_h, rf_t = fact_recall(it["facts"], [c["text"] for _, c in ev_r])
        agg["r_f_hit"] += rf_h; agg["r_f_tot"] += rf_t; agg["r_full"] += (rf_h == rf_t)

        # --- A. 开放检索 + 厂商路由器（修复后）---
        ev_a = open_retrieve(chunks, q_full, use_router=True)
        vendors_a = [c["vendor"] for _, c in ev_a]
        v1 = bool(vendors_a and vendors_a[0] == v_exp)
        v3 = v_exp in vendors_a
        s1 = bool(ev_a and ev_a[0][1]["section"] == d_exp and vendors_a[0] == v_exp)
        fa_h, fa_t = fact_recall(it["facts"], [c["text"] for _, c in ev_a])

        # --- B. 维度锁定检索 ---
        ev_b = retrieve(chunks, v_exp, d_exp + " " + DIMENSIONS[d_exp],
                        top_k=TOP_K, lock_section=d_exp)
        fb_h, fb_t = fact_recall(it["facts"], [c["text"] for _, c in ev_b])

        agg["v1"] += v1; agg["v3"] += v3; agg["s1"] += s1
        agg["fa_hit"] += fa_h; agg["fa_tot"] += fa_t; agg["fa_full"] += (fa_h == fa_t)
        agg["fb_hit"] += fb_h; agg["fb_tot"] += fb_t; agg["fb_full"] += (fb_h == fb_t)

        # v2：按 stable / time-sensitive 分组统计（金标防腐化）
        tp = it.get("type", "stable")
        agg.setdefault(f"{tp}_n", 0)
        agg.setdefault(f"{tp}_full", 0)
        agg[f"{tp}_n"] += 1
        agg[f"{tp}_full"] += (fa_h == fa_t)

        rows.append({"id": it["id"], "question": q, "vendor": v_exp, "dim": d_exp,
                     "open": {"vendor_hit@1": v1, "vendor_hit@3": v3, "section_hit@1": s1,
                              "fact_recall": f"{fa_h}/{fa_t}",
                              "top1": f"{vendors_a[0]}§{ev_a[0][1]['section']}" if ev_a else "—"},
                     "locked": {"fact_recall": f"{fb_h}/{fb_t}"}})

    n = len(items)
    summary = {
        "date": __import__("time").strftime("%Y-%m-%d"), "goldset_size": n, "top_k": TOP_K,
        "baseline_no_router": {
            "vendor_hit@1": round(agg["r_v1"] / n, 3),
            "vendor_hit@3": round(agg["r_v3"] / n, 3),
            "section_hit@1": round(agg["r_s1"] / n, 3),
            "fact_recall@3": round(agg["r_f_hit"] / agg["r_f_tot"], 3),
            "full_fact_items": f"{agg['r_full']}/{n}",
        },
        "open_retrieval": {
            "vendor_hit@1": round(agg["v1"] / n, 3),
            "vendor_hit@3": round(agg["v3"] / n, 3),
            "section_hit@1": round(agg["s1"] / n, 3),
            "fact_recall@3": round(agg["fa_hit"] / agg["fa_tot"], 3),
            "full_fact_items": f"{agg['fa_full']}/{n}",
        },
        "locked_retrieval": {
            "fact_recall@3": round(agg["fb_hit"] / agg["fb_tot"], 3),
            "full_fact_items": f"{agg['fb_full']}/{n}",
        },
        "by_type": {
            "stable": f"{agg.get('stable_full',0)}/{agg.get('stable_n',0)}",
            "time-sensitive": f"{agg.get('time-sensitive_full',0)}/{agg.get('time-sensitive_n',0)}",
        },
    }

    OUT.mkdir(exist_ok=True)
    (OUT / "eval_report.json").write_text(
        json.dumps({"summary": summary, "detail": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    sb, so, sl = summary["baseline_no_router"], summary["open_retrieval"], summary["locked_retrieval"]
    lines = [
        "# RAG 检索评测报告（金标集驱动）", "",
        f"> 金标集 {n} 条人工标注问答 ｜ 事实均已验证存在于语料 ｜ Top-K={TOP_K} ｜ 评测日期 {summary['date']}", "",
        "## 汇总指标（评测驱动迭代：baseline → +厂商路由器 → +维度锁）", "",
        "| 指标 | 无路由 baseline | 开放检索+厂商路由 | 维度锁定（矩阵组格） |",
        "|---|---|---|---|",
        f"| 厂商命中 Hit@1 | {sb['vendor_hit@1']:.0%} | **{so['vendor_hit@1']:.0%}** | —（厂商已知） |",
        f"| 厂商命中 Hit@3 | {sb['vendor_hit@3']:.0%} | **{so['vendor_hit@3']:.0%}** | — |",
        f"| 维度章节命中 Hit@1 | {sb['section_hit@1']:.0%} | **{so['section_hit@1']:.0%}** | 100%（确定性锁） |",
        f"| 事实召回 Recall@3 | {sb['fact_recall@3']:.0%} | **{so['fact_recall@3']:.0%}** | **{sl['fact_recall@3']:.0%}** |",
        f"| 全事实命中条目 | {sb['full_fact_items']} | **{so['full_fact_items']}** | {sl['full_fact_items']} |",
        "",
        f"> 金标防腐化（v2）：稳定型 {summary['by_type']['stable']} 全命中 ｜ 时效型 {summary['by_type']['time-sensitive']} 全命中",
        "> 时效型题目（收入/月活/估值等）已标注 as_of 快照日期，语料更新后需同步刷新对应金标事实。",
        "",
        "> 迭代记录：初版评测发现厂商名在跨厂商语料中交叉出现（如 minimax.md 含「增速高于智谱」），",
        "> TF-IDF 将厂商名当普通词稀释，Hit@1 仅 35%。加入确定性厂商路由器（别名表→先路由再排序）后修复。",
        ">",
        "> ⚠️ 如实标注：本集为**开发集**——路由器与维度锁均在本集上迭代调参，100% 是调参后的",
        "> 过拟合预期，不代表对未见过问题的泛化能力；且金标事实反向出卷自语料（必存在于库中）。",
        "> 本集的正确定位是 **CI 回归测试**（防退化）；真实泛化能力见 heldout_report.md（留出集，只测不调）。",
        "",
        "## 逐条明细", "",
        "| ID | 问题 | 期望 | 开放Top-1 | 厂商@1 | 章节@1 | 事实(开放) | 事实(锁定) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        o = r["open"]
        lines.append(
            f"| {r['id']} | {r['question']} | {r['vendor']}·{r['dim']} | {o['top1']} | "
            f"{'✅' if o['vendor_hit@1'] else '❌'} | {'✅' if o['section_hit@1'] else '❌'} | "
            f"{o['fact_recall']} | {r['locked']['fact_recall']} |")
    lines += [
        "", "## 方法说明", "",
        "- **金标集**：20 条问答由人工标注，金标事实为语料中真实存在的可验证子串（组间 all-of、组内 any-of），",
        "  标注前已逐条 grep 验证，杜绝『评测集本身编造』。",
        "- **开放检索** = 全库 TF-IDF 排序（不给厂商/维度提示），衡量真实用户提问下的路由能力；",
        "  **锁定检索** = 已知厂商+维度、启用维度锁，衡量矩阵组格的证据质量上限。",
        "- 零 LLM 依赖，任何人克隆后一条命令即可复现：`python eval/eval.py`。",
        "- **已知边界（如实记录）**：g14 为跨维度问题（装机量∈产品定位、Pre-IPO∈商业化策略），",
        "  维度锁定模式按定义只在单一维度内检索，故锁定事实召回 1/2；开放检索+路由模式下该条为满召回。",
        "  这说明锁定检索适合矩阵组格，跨维问题应走开放路由通道——评测本身发现了这条路由规则。", "",
    ]
    (OUT / "eval_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"输出：{OUT/'eval_report.md'} / eval_report.json")


if __name__ == "__main__":
    main()
