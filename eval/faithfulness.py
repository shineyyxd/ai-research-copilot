# -*- coding: utf-8 -*-
"""
faithfulness.py — 端到端忠实性评测（v2 新增）

v1 的 eval.py 只测"检索层"（证据找得准不准）；本脚本测"生成层"：
  检查 1 · 数字回指率：汇总文本里的每个数字，必须能在证据原文中找到
          （LLM 不可编造、不做算术的机械化验证；抽取式模式下验证确定性路径）
  检查 2 · 信封完整率：corpus_v2 实时数据层的每条事实，必须携带
          [trust_tier|as_of|caliber|src] 四要素信封

输出 output_v2/faithfulness_report.md + .json。零 LLM 依赖、可复现。
"""
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # eval/
PROJ = ROOT.parent
OUT = Path(os.environ.get("OUT_DIR", PROJ / "output"))
CORPUS = Path(os.environ.get("CORPUS_DIR", PROJ / "rag" / "corpus_v2"))
sys.path.insert(0, str(PROJ / "rag"))

from query import DIMENSIONS, CORE_VENDORS, retrieve, extractive_summary  # noqa: E402

NUM_RE = re.compile(r"\d+(?:\.\d+)?(?:%|亿|万|万亿|千亿|百亿|港元|美元|人民币|亿元|倍)?")
ENVELOPE_RE = re.compile(r"^\-\s+\[T\d[^\]]*\|as_of=[^\]|]*\|caliber=[^\]|]*\|src=[^\]]*\]")


def extract_numbers(text):
    """抽取有业务意义的数字（≥2 位或带单位，过滤章节号等噪声）。"""
    nums = []
    for m in NUM_RE.finditer(text):
        s = m.group(0)
        core = re.match(r"\d+(?:\.\d+)?", s).group(0)
        if len(core) >= 2 or re.search(r"(%|亿|万|港元|美元|人民币|倍)", s):
            nums.append(s)
    return nums


def check_number_grounding(index_path):
    idx = json.loads(Path(index_path).read_text(encoding="utf-8"))
    chunks = idx["chunks"]
    vendors = [v for v in CORE_VENDORS if v in {c["vendor"] for c in chunks}]
    cells, tot_n, hit_n = [], 0, 0
    for v in vendors:
        for d in DIMENSIONS:
            ev = retrieve(chunks, v, d + " " + DIMENSIONS[d], top_k=4, lock_section=d)
            if not ev:
                continue
            summary = extractive_summary(ev)
            blob = "\n".join(c["text"] for _, c in ev)
            nums = extract_numbers(summary)
            if not nums:
                continue
            hits = sum(1 for n in nums if n in blob)
            tot_n += len(nums)
            hit_n += hits
            if hits < len(nums):
                cells.append({"vendor": v, "dim": d,
                              "missing": [n for n in nums if n not in blob][:5]})
    rate = hit_n / tot_n if tot_n else 1.0
    return rate, tot_n, hit_n, cells


def check_envelope_completeness():
    files, tot, ok = [], 0, 0
    for f in sorted(CORPUS.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r"## 实时数据层[^\n]*\n(.*?)(?=\n## |\Z)", text, re.S)
        if not m:
            files.append({"file": f.name, "facts": 0, "enveloped": 0, "rate": None})
            continue
        lines = [ln for ln in m.group(1).splitlines() if ln.startswith("- ")]
        good = sum(1 for ln in lines if ENVELOPE_RE.match(ln))
        tot += len(lines)
        ok += good
        files.append({"file": f.name, "facts": len(lines), "enveloped": good,
                      "rate": round(good / len(lines), 3) if lines else None})
    return (ok / tot if tot else 1.0), tot, ok, files


def self_check(chunks):
    """负对照自检：往汇总里注入一个假数字，检查器必须能抓到——
    证明 100% 不是检查器失效造成的假象（规则模式下本检查为恒真，
    其真正价值在 LLM 模式与 CI 防退化，报告需如实注明）。"""
    from query import CORE_VENDORS as CV
    v = CV[0]
    d = list(DIMENSIONS)[0]
    ev = retrieve(chunks, v, d + " " + DIMENSIONS[d], top_k=4, lock_section=d)
    if not ev:
        return False
    blob = "\n".join(c["text"] for _, c in ev)
    fake = extractive_summary(ev) + "公司估值已达9999亿美元。"
    missing = [n for n in extract_numbers(fake) if n not in blob]
    return "9999亿" in missing


def main():
    index_path = os.environ.get("INDEX_PATH", PROJ / "rag" / "index_v2.json")
    rate_n, tot_n, hit_n, bad_cells = check_number_grounding(index_path)
    rate_e, tot_e, ok_e, files = check_envelope_completeness()
    idx = json.loads(Path(index_path).read_text(encoding="utf-8"))
    sc = self_check(idx["chunks"])

    summary = {
        "date": "2026-10-23",
        "number_grounding": {"rate": round(rate_n, 4), "hit": hit_n, "total": tot_n,
                             "cells_with_missing": bad_cells[:10]},
        "envelope_completeness": {"rate": round(rate_e, 4), "ok": ok_e, "total": tot_e},
        "self_check_negative_control": sc,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "faithfulness_report.json").write_text(
        json.dumps({"summary": summary, "envelope_by_file": files},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 端到端忠实性评测报告（faithfulness）", "",
        f"> 评测日期 {summary['date']} ｜ 与检索层评测（eval.py）互补：本报告测生成层", "",
        "## 汇总", "",
        "| 检查项 | 指标 | 结果 |",
        "|---|---|---|",
        f"| 数字回指率（汇总数字 ↔ 证据原文） | {hit_n}/{tot_n} | **{rate_n:.1%}** |",
        f"| 信封完整率（实时数据层事实携带四要素） | {ok_e}/{tot_e} | **{rate_e:.1%}** |",
        f"| 负对照自检（注入假数字必须被抓到） | — | **{'通过' if sc else '失败'}** |", "",
        "> ⚠️ 如实标注：规则模式下汇总为证据原文的抽取式子串，数字回指恒真——",
        "> 该指标在 LLM 模式（DEEPSEEK_API_KEY）下才有信息量；规则模式下的价值是",
        "> CI 防代码退化（如截断逻辑被破坏），配合负对照自证检查器有效。", "",
        "## 方法说明", "",
        "- 数字回指：对每个 厂商×维度 格，复跑与生产完全相同的检索与确定性汇总，",
        "  抽取汇总中的业务数字（≥2 位或带单位），逐一验证其在证据原文中出现——",
        "  任何查无出处的数字都会被点名（cells_with_missing）。",
        "- 信封完整：corpus_v2 实时数据层的每条事实必须匹配",
        "  `[trust_tier|as_of|caliber|src]` 四要素，缺一项即计为不完整。",
        "- 零 LLM 依赖，一条命令复现：`python eval/faithfulness.py`。",
    ]
    if bad_cells:
        lines += ["", "## 数字未命中证据的格子（需人工复核）", ""]
        for c in bad_cells:
            lines.append(f"- {c['vendor']}·{c['dim']}：{', '.join(c['missing'])}")
    (OUT / "faithfulness_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
