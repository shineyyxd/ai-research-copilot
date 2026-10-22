# -*- coding: utf-8 -*-
"""
research_graph.py — 节点式 Deep Research（harness 版，替代 v1 单脚本循环）

图结构（与 LangGraph 语义对齐）：
  supervisor（意图识别：锁定厂商池与维度）
    → planner（四维×厂商拆解子查询）
    → [interrupt：人工审批计划，REQUIRE_APPROVAL=1 时启用]
    → researcher（工具循环：检索→自检→补检，每格带审计）
    → critic（全矩阵证据充分性复核，标 ⚠️证据待补）
    → reporter（汇总渲染，数字程序渲染自证据）

用法：
  python rag/research_graph.py                          # 全矩阵
  python rag/research_graph.py "对比三家厂商的商业化策略"   # 单问题
  REQUIRE_APPROVAL=1 python rag/research_graph.py       # 带人工审批点
  # 中断后直接重跑同命令即可从断点恢复（thread 由问题文本哈希确定）
"""
import hashlib, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from harness import Graph, audit, OUT                                   # noqa: E402
from research import (decompose, sufficiency_check, expand_query,       # noqa: E402
                      llm_followup, render_report, MAX_DEPTH, load_chunks)
from query import (DIMENSIONS, CORE_VENDORS, tier_of, retrieve,          # noqa: E402
                   extractive_summary, llm_summary)

APPROVE_REQUIRED = os.environ.get("REQUIRE_APPROVAL") == "1"


# ---------- 节点定义 ----------
def supervisor(state):
    """意图识别：确定本次研究的厂商池与维度范围。"""
    chunks = load_chunks()
    all_vendors = sorted({c["vendor"] for c in chunks})
    vendors = [v for v in CORE_VENDORS if v in all_vendors] + \
              sorted(v for v in all_vendors if v not in CORE_VENDORS)
    state["vendors"] = vendors
    state["tiers"] = {v: tier_of(v) for v in vendors}
    state["trace"] = [{"step": "supervisor",
                       "detail": f"锁定 {len(vendors)} 家厂商（国内核心 "
                                 f"{sum(1 for v in vendors if tier_of(v) == '国内核心')} 家）"}]
    return state


def planner(state):
    subs = decompose(state["question"], state["vendors"])
    state["subs"] = subs
    state["trace"].append({"step": "planner",
                           "detail": f"拆解为 {len(subs)} 个子查询"
                                     f"（{len(set(s['vendor'] for s in subs))} 厂商 × "
                                     f"{len(set(s['dim'] for s in subs))} 维度）"})
    return state


def researcher(state):
    """工具循环：逐格子查询 检索→自检→补检（≤MAX_DEPTH 轮），每次检索写审计。"""
    chunks = load_chunks()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    cells, stats = {}, {"initial_pass": 0, "refined": 0, "refine_success": 0}
    for sub in state["subs"]:
        v, d = sub["vendor"], sub["dim"]
        q = sub["query"]
        history = []
        evidences = retrieve(chunks, v, q, top_k=4, lock_section=d)
        audit("retrieve", {"vendor": v, "dim": d, "query": q, "round": 1},
              {"hits": len(evidences), "top_score": evidences[0][0] if evidences else 0})
        ok, reason = sufficiency_check(evidences, dim=d)
        history.append({"round": 1, "query": q, "hits": len(evidences),
                        "sufficient": ok, "reason": reason})
        depth = 1
        while not ok and depth < MAX_DEPTH + 1:
            depth += 1
            if api_key:
                try:
                    q = llm_followup(state["question"], sub, evidences, api_key)
                except Exception:
                    q = expand_query(q, evidences, chunks, v)
            else:
                q = expand_query(q, evidences, chunks, v)
            merged = {id(c): (s, c) for s, c in evidences}
            for s, c in retrieve(chunks, v, q, top_k=4, lock_section=d):
                if id(c) not in merged or s > merged[id(c)][0]:
                    merged[id(c)] = (s, c)
            evidences = sorted(merged.values(),
                               key=lambda x: (-(x[1]["section"] == d), -x[0]))[:4]
            audit("retrieve", {"vendor": v, "dim": d, "query": q, "round": depth},
                  {"hits": len(evidences), "top_score": evidences[0][0] if evidences else 0})
            ok, reason = sufficiency_check(evidences, dim=d)
            history.append({"round": depth, "query": q, "hits": len(evidences),
                            "sufficient": ok, "reason": reason})
        if history[0]["sufficient"]:
            stats["initial_pass"] += 1
        else:
            stats["refined"] += 1
            stats["refine_success"] += bool(ok)
        if api_key and evidences:
            try:
                summary = llm_summary(v, d, evidences, api_key).get("summary", "")
            except Exception:
                summary = extractive_summary(evidences)
        else:
            summary = extractive_summary(evidences)
        cells[f"{v}|{d}"] = {"vendor": v, "dim": d, "summary": summary, "sufficient": ok,
                             "evidence": [{"score": s, "source": c["source"],
                                           "section": c["section"]} for s, c in evidences],
                             "rounds": history}
    state["cells"] = cells
    state["stats"] = stats
    return state


def critic(state):
    """全矩阵复核：统计证据充分率，不足格显式标注（诚实 > 完整）。"""
    cells = state["cells"]
    insufficient = [k for k, c in cells.items() if not c["sufficient"]]
    total = len(cells)
    state["trace"].append({"step": "critic",
                           "detail": f"证据充分率 {total - len(insufficient)}/{total}；"
                                     f"不足格 {len(insufficient)} 个已标注⚠️证据待补"
                                     + (f"：{', '.join(insufficient[:6])}…" if insufficient else "")})
    return state


def reporter(state):
    """渲染报告：复用 v1 render（cells 键换回 (vendor, dim) 元组）。"""
    cells = {(c["vendor"], c["dim"]): c for c in state["cells"].values()}
    res = {"question": state["question"],
           "mode": "harness图执行(零依赖)" + ("+LLM(deepseek)" if os.environ.get("DEEPSEEK_API_KEY") else ""),
           "vendors": state["vendors"], "cells": cells,
           "trace": state["trace"], "stats": state["stats"]}
    report = render_report(res)
    (OUT / "research_report.md").write_text(report, encoding="utf-8")
    (OUT / "research_trace.json").write_text(json.dumps(
        {"question": res["question"], "mode": res["mode"],
         "stats": res["stats"], "trace": res["trace"]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    state["report_path"] = str(OUT / "research_report.md")
    return state


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else \
        "系统评估各厂商在技术路线、产品定位、商业化策略、生态壁垒四个维度的竞争力"
    thread_id = hashlib.md5(question.encode()).hexdigest()[:10]
    g = Graph(
        nodes={"supervisor": supervisor, "planner": planner,
               "researcher": researcher, "critic": critic, "reporter": reporter},
        order=["supervisor", "planner", "researcher", "critic", "reporter"],
        interrupt_before={"researcher"} if APPROVE_REQUIRED else set(),
    )
    state, done = g.run(thread_id, {"question": question})
    if not done:
        print("[harness] 已暂停在审批点，断点已保存。")
        return
    st = state["stats"]
    print(f"完成：子查询 {st['initial_pass']+st['refined']} ｜ 首轮充分 {st['initial_pass']} ｜ "
          f"补检 {st['refined']}（成功 {st['refine_success']}）")
    print(f"报告：{state['report_path']} ｜ 审计：{OUT/'audit_log.jsonl'} ｜ 断点：{OUT/'checkpoints.db'}")


if __name__ == "__main__":
    main()
