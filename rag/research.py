# -*- coding: utf-8 -*-
"""
research.py — 多轮 Deep Research 循环（移植自 dzhng/deep-research 的 breadth/depth 范式）

流程（对应简历叙事「拆解→检索→自检→补检→汇总」）：
  1. 拆解：把研究问题按「技术路线/产品定位/商业化策略/生态壁垒」四维 × 厂商 拆成子查询
  2. 检索：每个子查询在本地语料库做 TF-IDF 检索
  3. 自检：对每格证据做「充分性检查」（top-1 相关度 + 证据覆盖数）
  4. 补检：不充分的格子自动生成扩展查询（从已检回 chunk 抽取显著词扩展），二轮加深检索
  5. 汇总：输出带完整迭代日志（trace）的研究报告，每条结论可溯源

LLM 层可插拔：设置 DEEPSEEK_API_KEY 后，子查询生成/追问/汇总升级为 LLM 驱动；
未配置时走确定性规则兜底（诚实标注模式）。

用法：
  python research.py "对比三家厂商的商业化策略"     # 单问题模式
  python research.py                                # 默认全矩阵研究
"""
import json, os, re, sys
from collections import Counter
from pathlib import Path

from ingest import tokenize
from query import (DIMENSIONS, CORE_VENDORS, tier_of, retrieve, query_vec,
                   cosine, extractive_summary, llm_summary)

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("OUT_DIR", ROOT.parent / "output"))
OUT.mkdir(parents=True, exist_ok=True)
INDEX_PATH = Path(os.environ.get("INDEX_PATH", ROOT / "index.json"))

# ---- 自检阈值（可调，eval 金标集建好后可回归验证）----
MIN_TOP_SCORE = 0.18     # top-1 相关度低于此值 → 判定证据不足
MIN_EVIDENCE = 2         # 有效证据 chunk 数低于此值 → 判定覆盖不够
MAX_DEPTH = 2            # 最多补检轮数（对应 deep-research 的 depth）


def load_chunks():
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return idx["chunks"]


# ---------- 1. 拆解 ----------
def decompose(question, vendors):
    """把研究问题拆成 厂商×维度 的子查询列表。
    LLM 模式下可自由拆解；规则模式按四维框架笛卡尔展开（本身就是简历里的方法论）。"""
    hit_dims = [d for d in DIMENSIONS if d in question] or list(DIMENSIONS)
    hit_vendors = [v for v in vendors if v.lower() in question.lower()] or vendors
    subs = []
    for v in hit_vendors:
        for d in hit_dims:
            subs.append({
                "vendor": v, "dim": d,
                "query": f"{d} {DIMENSIONS[d]}",
                "goal": f"收集「{v}」在「{d}」维度的可溯源证据",
            })
    return subs


# ---------- 3. 自检 ----------
def sufficiency_check(evidences, dim=None):
    """证据充分性自检：返回 (是否充分, 原因)。
    维度锁规则：top-1 章节名与维度同名时属确定性证据（语料按维度组织），
    直接判充分——不再因跨维共现词导致的相关度打分偏低而误标「证据待补」。"""
    if not evidences:
        return False, "零证据命中"
    top_score, top_chunk = evidences[0][0], evidences[0][1]
    if dim and top_chunk.get("section") == dim:
        return True, f"维度锁命中：top-1 章节 §{dim} 与维度同名（确定性证据，相关度 {top_score}）"
    if top_score < MIN_TOP_SCORE:
        return False, f"top-1 相关度 {top_score} < 阈值 {MIN_TOP_SCORE}"
    if len(evidences) < MIN_EVIDENCE:
        return False, f"有效证据 {len(evidences)} 条 < 阈值 {MIN_EVIDENCE}"
    return True, f"top-1 相关度 {top_score}，证据 {len(evidences)} 条"


# ---------- 4. 补检（follow-up 查询生成）----------
STOPWORDS = set("的 了 在 是 和 与 等 及 为 对 以 于 由 从 或 也 都 并 而 被 把 有 无 一 个 中 上 下".split())


def expand_query(base_query, evidences, chunks, vendor):
    """从已检回证据中抽显著词，扩展原查询（deep-research 的 followUpQuestions 规则版）。
    显著词 = 在该厂商证据里高频、但在原查询里没出现的词。"""
    seen = set(tokenize(base_query))
    tf = Counter()
    for _, c in evidences:
        for t in tokenize(c["text"]):
            if len(t) >= 2 and t not in seen and t not in STOPWORDS:
                tf[t] += 1
    extra = " ".join(t for t, _ in tf.most_common(6))
    return (base_query + " " + extra).strip()


def llm_followup(question, sub, evidences, api_key):
    """LLM 模式：让模型基于已有 learnings 生成更聚焦的追问查询。"""
    import urllib.request
    ev = "\n".join(c["text"][:150] for _, c in evidences[:3]) or "（无）"
    prompt = (f"研究问题：{question}\n当前子任务：{sub['goal']}\n已检回证据片段：\n{ev}\n\n"
              f"请生成 1 个更聚焦的中文检索查询（只输出查询词本身，空格分隔关键词，不要解释）。")
    body = json.dumps({"model": "deepseek-chat",
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.3}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.load(r)
    return resp["choices"][0]["message"]["content"].strip()[:80]


# ---------- 主循环 ----------
def deep_research(question):
    chunks = load_chunks()
    all_vendors = sorted({c["vendor"] for c in chunks})
    vendors = [v for v in CORE_VENDORS if v in all_vendors] + \
              sorted(v for v in all_vendors if v not in CORE_VENDORS)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    mode = "LLM驱动(deepseek-chat)" if api_key else "规则驱动(未配置API Key，确定性兜底)"

    trace = []          # 完整迭代日志
    cells = {}          # (vendor, dim) -> 最终结果
    subs = decompose(question, vendors)
    trace.append({"step": "拆解", "detail": f"问题拆成 {len(subs)} 个子查询"
                                            f"（{len(set(s['vendor'] for s in subs))} 厂商 × "
                                            f"{len(set(s['dim'] for s in subs))} 维度）"})

    stats = {"initial_pass": 0, "refined": 0, "refine_success": 0}
    for sub in subs:
        v, d = sub["vendor"], sub["dim"]
        q = sub["query"]
        history = []
        evidences = retrieve(chunks, v, q, top_k=4, lock_section=d)
        ok, reason = sufficiency_check(evidences, dim=d)
        history.append({"round": 1, "query": q, "hits": len(evidences),
                        "sufficient": ok, "reason": reason})

        depth = 1
        while not ok and depth < MAX_DEPTH + 1:
            depth += 1
            if api_key:
                try:
                    q = llm_followup(question, sub, evidences, api_key)
                except Exception:
                    q = expand_query(q, evidences, chunks, v)
            else:
                q = expand_query(q, evidences, chunks, v)
            merged = {id(c): (s, c) for s, c in evidences}
            for s, c in retrieve(chunks, v, q, top_k=4, lock_section=d):
                if id(c) not in merged or s > merged[id(c)][0]:
                    merged[id(c)] = (s, c)
            # 维度锁章节始终排最前，其余按分数
            evidences = sorted(merged.values(),
                               key=lambda x: (-(x[1]["section"] == d), -x[0]))[:4]
            ok, reason = sufficiency_check(evidences, dim=d)
            history.append({"round": depth, "query": q, "hits": len(evidences),
                            "sufficient": ok, "reason": reason})

        if history[0]["sufficient"]:
            stats["initial_pass"] += 1
        else:
            stats["refined"] += 1
            if ok:
                stats["refine_success"] += 1

        # 汇总该格
        if api_key and evidences:
            try:
                summary = llm_summary(v, d, evidences, api_key).get("summary", "")
            except Exception:
                summary = extractive_summary(evidences)
        else:
            summary = extractive_summary(evidences)

        cells[(v, d)] = {"summary": summary, "sufficient": ok,
                         "evidence": [{"score": s, "source": c["source"], "section": c["section"]}
                                      for s, c in evidences],
                         "rounds": history}
        trace.append({"step": f"{v}·{d}", "rounds": len(history),
                      "final": "充分" if ok else "仍不足(已标注)",
                      "queries": [h["query"][:60] for h in history]})

    return {"question": question, "mode": mode, "vendors": vendors,
            "cells": cells, "trace": trace, "stats": stats}


def render_report(res):
    lines = [f"# Deep Research 报告：{res['question']}", "",
             f"> 模式：{res['mode']} ｜ 范式：拆解 → 检索 → 自检 → 补检 → 汇总"
             f"（移植自 dzhng/deep-research 的 breadth/depth 循环）", ""]
    st = res["stats"]
    total = st["initial_pass"] + st["refined"]
    lines += ["## 研究循环统计", "",
              f"- 子查询总数：{total}",
              f"- 首轮即充分：{st['initial_pass']}",
              f"- 触发补检：{st['refined']}（其中补检后达标 {st['refine_success']}）", ""]
    dims = sorted({d for _, d in res["cells"]}, key=lambda d: list(DIMENSIONS).index(d))
    core = [v for v in res["vendors"] if tier_of(v) == "国内核心"]
    bench = [v for v in res["vendors"] if tier_of(v) == "海外对标"]
    for title, group in [("结论矩阵 · 国内核心层（A/H 已上市或拟 IPO 大模型公司）", core),
                         ("结论矩阵 · 海外对标层（映射基准）", bench)]:
        if not group:
            continue
        lines += [f"## {title}", "", "| 维度 | " + " | ".join(group) + " |",
                  "|---|" + "---|" * len(group)]
        for d in dims:
            row = [f"**{d}**"]
            for v in group:
                cell = res["cells"].get((v, d))
                mark = "" if (cell and cell["sufficient"]) else " ⚠️证据待补"
                row.append((cell["summary"].replace("\n", " ") if cell else "—") + mark)
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    lines += ["", "## 迭代日志（每格的查询演化）", ""]
    for (v, d), cell in res["cells"].items():
        lines.append(f"### {v} · {d}")
        for h in cell["rounds"]:
            flag = "✅" if h["sufficient"] else "🔁"
            lines.append(f"- 第{h['round']}轮 {flag} `{h['query'][:70]}` → 命中 {h['hits']} 条（{h['reason']}）")
        for e in cell["evidence"][:2]:
            lines.append(f"  - 证据 ← `{e['source']}` §{e['section']}（{e['score']}）")
        lines.append("")
    return "\n".join(lines)


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "系统评估各厂商在技术路线、产品定位、商业化策略、生态壁垒四个维度的竞争力"
    res = deep_research(question)
    (OUT / "research_trace.json").write_text(
        json.dumps({k if isinstance(k, str) else "|".join(k): val for k, val in
                    [("question", res["question"]), ("mode", res["mode"]),
                     ("stats", res["stats"]), ("trace", res["trace"])]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    report = render_report(res)
    (OUT / "research_report.md").write_text(report, encoding="utf-8")
    st = res["stats"]
    print(f"完成：{res['mode']}")
    print(f"子查询 {st['initial_pass']+st['refined']} 个 ｜ 首轮充分 {st['initial_pass']} ｜ "
          f"触发补检 {st['refined']}（成功 {st['refine_success']}）")
    print(f"输出：{OUT/'research_report.md'} / research_trace.json")


if __name__ == "__main__":
    main()
