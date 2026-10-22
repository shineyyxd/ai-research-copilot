# -*- coding: utf-8 -*-
"""
ingest.py — 竞品研究 RAG 的入库脚本
把 corpus/ 下的 .md/.txt（可扩展 pdf）切块、建 TF-IDF 倒排索引，存成 index.json。
零外部依赖：中文用字符 bigram 分词，英文按单词，纯标准库实现。
"""
import json, math, os, re, sys
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
CORPUS = Path(os.environ.get("CORPUS_DIR", ROOT / "corpus"))
INDEX_FILE = Path(os.environ.get("INDEX_PATH", ROOT / "index.json"))


def parse_front_matter(text):
    """解析 v2 语料的 YAML 头（---...---），返回 metadata dict；无头返回 {}。"""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def tokenize(text: str):
    """中文 → 字符bigram；英文/数字 → 小写单词。混合文本两者都出。"""
    tokens = []
    for word in re.findall(r"[A-Za-z0-9_\-\.]+", text):
        tokens.append(word.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    for seg in cjk:
        if len(seg) == 1:
            tokens.append(seg)
        for i in range(len(seg) - 1):
            tokens.append(seg[i:i + 2])
    return tokens


def chunk_markdown(text: str, source: str, meta: dict = None):
    """按 ## 标题切块；块内再按 ~400 字二次切分，保留出处。
    meta（v2 YAML 头）中的 market/layer/depth_tier/as_of 会写入每个 chunk。"""
    meta = meta or {}
    chunks = []
    vendor = meta.get("vendor")
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        vendor = m.group(1).strip()
    sections = re.split(r"^##\s+", text, flags=re.M)
    for sec in sections[1:]:
        lines = sec.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        body = re.sub(r"^>.*$", "", body, flags=re.M).strip()  # 去掉引用说明行
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        buf = ""
        for p in paras:
            if len(buf) + len(p) > 400 and buf:
                chunks.append({"vendor": vendor, "section": heading, "text": buf, "source": source})
                buf = p
            else:
                buf = (buf + "\n" + p).strip()
        if buf:
            chunks.append({"vendor": vendor, "section": heading, "text": buf, "source": source})
    return chunks


def build_index():
    all_chunks = []
    for f in sorted(CORPUS.glob("*")):
        if f.suffix.lower() in (".md", ".txt"):
            raw = f.read_text(encoding="utf-8")
            meta = parse_front_matter(raw)
            chunks = chunk_markdown(raw, f.name, meta)
            for c in chunks:  # v2 元数据落 chunk（检索/矩阵可按层过滤）
                for k in ("market", "layer", "depth_tier", "as_of"):
                    if meta.get(k):
                        c[k] = meta[k]
            all_chunks += chunks
        elif f.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
                text = "\n".join((p.extract_text() or "") for p in PdfReader(str(f)).pages)
                all_chunks += chunk_markdown("# " + f.stem + "\n## 全文\n" + text, f.name)
            except Exception as e:
                print(f"[warn] 跳过 {f.name}: {e}")

    # TF-IDF
    df = Counter()
    doc_tokens = []
    for c in all_chunks:
        toks = tokenize(c["text"] + " " + c["section"])
        doc_tokens.append(toks)
        df.update(set(toks))
    n = len(all_chunks)
    index = []
    for c, toks in zip(all_chunks, doc_tokens):
        tf = Counter(toks)
        vec = {t: (1 + math.log(cnt)) * math.log(n / (1 + df[t])) for t, cnt in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        c["vec"] = {t: round(v / norm, 6) for t, v in vec.items()}
        index.append(c)

    INDEX_FILE.write_text(json.dumps({"n_chunks": n, "chunks": index}, ensure_ascii=False), encoding="utf-8")
    vendors = sorted({c["vendor"] for c in index})
    print(f"入库完成：{len(list(CORPUS.glob('*')))} 个文档 → {n} 个chunk，厂商：{vendors}")


if __name__ == "__main__":
    build_index()
