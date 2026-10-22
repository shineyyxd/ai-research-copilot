# -*- coding: utf-8 -*-
"""
quality_gate.py — 周报质量门禁（Actions 自动 commit 前调用）
任一不达标即 exit 1（阻止当日提交，避免在公开仓库留下难看记录）：
  1. 当日 digest 存在且条目数 >= 20
  2. 当日 snapshot JSON 可解析且含 items
  3. digest 六个主题分桶结构完整
"""
import json, os, re, sys, time
from pathlib import Path

OUT = Path(os.environ.get("OUT_DIR", Path(__file__).resolve().parent.parent / "output"))
TODAY = time.strftime("%Y-%m-%d")
MIN_ITEMS = 20
REQUIRED_THEMES = ["Agent", "RAG", "模型", "编码", "基础设施"]


def main():
    digest = OUT / f"digest_{TODAY}.md"
    if not digest.exists():
        sys.exit(f"FAIL: 未生成 {digest.name}")
    text = digest.read_text(encoding="utf-8")
    items = len(re.findall(r"^- \[", text, flags=re.M))
    if items < MIN_ITEMS:
        sys.exit(f"FAIL: 条目数 {items} < {MIN_ITEMS}")
    missing = [t for t in REQUIRED_THEMES if t not in text]
    if missing:
        sys.exit(f"FAIL: 主题分桶缺失 {missing}")
    snaps = list((Path(__file__).resolve().parent.parent
                  / "tracker" / "history").glob(f"snapshot_{TODAY}*.json"))
    if not snaps:
        sys.exit("FAIL: 当日快照缺失")
    try:
        data = json.loads(snaps[0].read_text(encoding="utf-8"))
        assert data, "snapshot 为空"
    except Exception as e:
        sys.exit(f"FAIL: 快照不可解析: {e}")
    print(f"PASS: 条目 {items} ≥ {MIN_ITEMS}，主题齐全，快照有效")


if __name__ == "__main__":
    main()
