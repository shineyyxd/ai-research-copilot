# -*- coding: utf-8 -*-
"""
heldout_eval.py — 留出/对抗评测（v2 新增）

与 goldset.json（开发集，路由器在其上迭代过，100% 是过拟合预期）不同，
本集在路由器冻结后编写，**只测不调**，用于估计真实泛化能力：
  - 隐式指代：问题不含厂商名，路由器失效，考验纯检索
  - 跨厂商比较：多厂商共现，考验路由与排序
  - 库外否定题：答案不在语料中，期望系统"说不知道"而非硬答
    （判定：top-1 相关度 < MIN_TOP_SCORE 或 显式证据不足 → 视为正确拒答）
  - v2新数据题：答案只存在于 v2 实时数据层，防"吃老本"

输出 heldout_report.md/json。零 LLM 依赖。
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJ = ROOT.parent
OUT = Path(os.environ.get("OUT_DIR", PROJ / "output"))
sys.path.insert(0, str(PROJ / "rag"))
sys.path.insert(0, str(ROOT))

from eval import open_retrieve, fact_recall      # noqa: E402
from research import MIN_TOP_SCORE                # noqa: E402


def main():
    idx = json.loads((PROJ / os.environ.get("INDEX_PATH", "rag/index_v2.json")).read_text(encoding="utf-8"))
    chunks = idx["chunks"]
    items = json.loads((ROOT / "heldout.json").read_text(encoding="utf-8"))["items"]

    rows, agg = [], {}
    for it in items:
        ev = open_retrieve(chunks, it["question"], use_router=True)
        top_vendor = ev[0][1]["vendor"] if ev else None
        top_score = ev[0][0] if ev else 0.0
        if it.get("expect_insufficient"):
            # 否定题：期望"证据不足"。top-1 低于自检阈值 → 正确拒答
            ok = (not ev) or top_score < MIN_TOP_SCORE
            detail = f"top-1={top_vendor}({top_score}) → {'拒答✅' if ok else '硬答❌'}"
        else:
            hit_v = top_vendor == it["expect_vendor"]
            fh, ft = fact_recall(it["facts"], [c["text"] for _, c in ev])
            ok = hit_v and fh == ft
            detail = f"top-1={top_vendor}({top_score}) 厂商{'✅' if hit_v else '❌'} 事实{fh}/{ft}"
        rows.append({"id": it["id"], "kind": it["kind"], "question": it["question"],
                     "ok": ok, "detail": detail})
        k = it["kind"]
        agg.setdefault(k, [0, 0])
        agg[k][1] += 1
        agg[k][0] += ok

    n = len(items)
    total_ok = sum(r["ok"] for r in rows)
    summary = {"date": "2026-10-23", "size": n, "pass": total_ok,
               "pass_rate": round(total_ok / n, 3),
               "by_kind": {k: f"{v[0]}/{v[1]}" for k, v in agg.items()}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "heldout_report.json").write_text(
        json.dumps({"summary": summary, "detail": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    lines = [
        "# 留出/对抗评测报告（真实泛化能力）", "",
        f"> 评测日期 {summary['date']} ｜ 本集在路由器冻结后编写，只测不调",
        "> 与开发集（goldset 20 条，100% 为调参后的过拟合结果）相区分", "",
        f"## 汇总：{total_ok}/{n} 通过（{total_ok / n:.0%}）", "",
        "| 题型 | 通过 |", "|---|---|",
    ] + [f"| {k} | {v} |" for k, v in summary["by_kind"].items()] + [
        "", "## 逐条明细", "",
        "| ID | 题型 | 问题 | 结果 | 明细 |", "|---|---|---|---|---|",
    ] + [f"| {r['id']} | {r['kind']} | {r['question'][:28]}… | {'✅' if r['ok'] else '❌'} | {r['detail']} |"
         for r in rows] + [
        "", "## 解读", "",
        "- 隐式指代题考察路由器失效时的纯检索能力，是本集最有信息量的部分；",
        "- 库外否定题考察系统是否会『硬答』——正确行为是低置信拒答（对应报告的⚠️证据待补机制）；",
        "- 本集任何失败项只记录、不调参（调参请回开发集），否则本集也会退化为开发集。", "",
    ]
    (OUT / "heldout_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in rows:
        print(f"  {r['id']} {r['kind']:　<6} {'✅' if r['ok'] else '❌'} {r['detail']}")


if __name__ == "__main__":
    main()
