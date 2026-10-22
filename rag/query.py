# -*- coding: utf-8 -*-
"""
query.py — 四维检索 + 对比矩阵生成
对每个厂商 × 四个维度（技术路线/产品定位/商业化策略/生态壁垒）逐项检索证据，
有 DEEPSEEK_API_KEY 时用 LLM 按 JSON Schema 汇总；没有时用抽取式摘要兜底。
输出 output/matrix.json + output/matrix.md
"""
import json, os, re, sys, urllib.request
from pathlib import Path
from ingest import tokenize

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("OUT_DIR", ROOT.parent / "output"))
OUT.mkdir(parents=True, exist_ok=True)
INDEX_PATH = Path(os.environ.get("INDEX_PATH", ROOT / "index.json"))

DIMENSIONS = {
    "技术路线": "自研 预训练 模型架构 开源 多模态 长上下文 推理 MoE 技术栈 算力",
    "产品定位": "定位 C端 B端 用户 场景 产品矩阵 助手 平台 客户 行业",
    "商业化策略": "收入 融资 商业化 变现 订阅 API计费 客单价 上市 IPO 估值",
    "生态壁垒": "壁垒 生态 护城河 社区 心智 留存 风险 竞争 数据飞轮",
}

TOP_K = 3

# ---- 厂商分层：国内核心（A/H 已上市或拟 IPO 的大模型公司）vs 海外对标 ----
CORE_VENDORS = ["智谱", "月之暗面（Kimi）", "MiniMax", "DeepSeek",
                "阿里通义（Qwen）", "字节豆包", "阶跃星辰", "零一万物",
                "百度文心", "科大讯飞（星火）", "腾讯（混元）"]

# ---- 厂商路由器：问题中的厂商名/别名 → 确定性路由到该厂商的 chunk ----
# 背景：eval 金标集发现厂商名会在其他厂商语料中交叉出现（如 minimax.md 里
# 「增速高于智谱」），TF-IDF 将厂商名当普通词稀释，开放检索 Hit@1 仅 35%。
# 修复：先做确定性别名匹配路由，再在该厂商范围内排序（metadata routing）。
VENDOR_ALIASES = {
    "智谱": ["智谱", "GLM", "02513", "清华 KEG"],
    "月之暗面（Kimi）": ["月之暗面", "Kimi", "kimi", "K3", "杨植麟", "Moonshot"],
    "MiniMax": ["MiniMax", "minimax", "稀宇", "海螺", "Talkie", "00100"],
    "DeepSeek": ["DeepSeek", "deepseek", "深度求索", "幻方", "梁文锋"],
    "阿里通义（Qwen）": ["通义", "Qwen", "qwen", "阿里云", "千问"],
    "字节豆包": ["豆包", "字节", "火山引擎", "抖音"],
    "阶跃星辰": ["阶跃", "StepFun", "Step 3", "Step-3"],
    "零一万物": ["零一万物", "零一", "01.AI", "李开复", "万物智能"],
    "OpenAI": ["OpenAI", "openai", "GPT", "ChatGPT", "奥特曼", "Altman"],
    "Anthropic": ["Anthropic", "anthropic", "Claude", "claude"],
    "Google Gemini": ["Gemini", "gemini", "谷歌", "Google", "DeepMind"],
    "xAI（Grok）": ["xAI", "Grok", "grok", "马斯克"],
    "Meta（Llama）": ["Meta", "Llama", "llama", "扎克伯格"],
    "百度文心": ["百度", "文心", "ERNIE", "Ernie", "Baidu"],
    "科大讯飞（星火）": ["科大讯飞", "讯飞", "星火", "SparkDesk", "iFlytek"],
    "腾讯（混元）": ["腾讯", "混元", "Hunyuan", "hunyuan"],
    "Mistral AI": ["Mistral", "mistral", "米斯特拉尔"],
}


def route_vendor(question):
    """确定性厂商路由：按别名最长匹配优先，命中即返回厂商名，未命中返回 None。"""
    hits = []
    for vendor, aliases in VENDOR_ALIASES.items():
        for a in aliases:
            if a in question:
                hits.append((len(a), vendor))
    return max(hits)[1] if hits else None


def tier_of(vendor):
    return "国内核心" if vendor in CORE_VENDORS else "海外对标"


def cosine(q_vec, d_vec):
    if len(q_vec) > len(d_vec):
        q_vec, d_vec = d_vec, q_vec
    return sum(w * d_vec.get(t, 0.0) for t, w in q_vec.items())


def query_vec(text):
    toks = tokenize(text)
    from collections import Counter
    tf = Counter(toks)
    norm = sum(v * v for v in tf.values()) ** 0.5 or 1.0
    return {t: v / norm for t, v in tf.items()}


def retrieve(chunks, vendor, dim_query, top_k=TOP_K, lock_section=None):
    """检索该厂商的相关 chunk。

    lock_section（维度锁）：语料按「## 维度名」组织，章节名与维度同名的 chunk
    是该维度的确定性证据。加锁后这些 chunk 得到强先验加权，排在语义相似但
    章节错位的 chunk 之前——修复 TF-IDF 因跨维共现词（企业/客户/收入）抽串的问题。
    """
    qv = query_vec(dim_query)
    scored = []
    for c in chunks:
        if c["vendor"] != vendor:
            continue
        s = cosine(qv, c["vec"])
        locked = 1 if (lock_section and c["section"] == lock_section) else 0
        scored.append((locked, s, c))
    # 锁只影响排序（同名章节确定性优先），展示分数保持原始相关度不虚高
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [(round(s, 4), c) for locked, s, c in scored[:top_k] if s > 0 or locked]


def extractive_summary(evidences, max_sents=2):
    """无 LLM 时的兜底：取最相关 chunk 的前几句。"""
    if not evidences:
        return "（未检索到证据）"
    text = evidences[0][1]["text"]
    sents = re.split(r"(?<=[。；！])", text)
    return "".join(sents[:max_sents]).strip()


def llm_summary(vendor, dim, evidences, api_key):
    """有 Key 时：LLM 按 JSON Schema 汇总，带引用约束。"""
    evidence_text = "\n---\n".join(f"[{i+1}] ({s}) {c['text']}" for i, (s, c) in enumerate(evidences))
    prompt = f"""你是投研助理。仅基于以下证据，对厂商「{vendor}」在维度「{dim}」上做一句话总结（60字内），并列出关键点。
禁止编造证据之外的信息。输出 JSON：{{"summary": str, "key_points": [str], "evidence_ids": [int]}}

证据：
{evidence_text}"""
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.load(r)
    return json.loads(resp["choices"][0]["message"]["content"])


def main():
    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    chunks = idx["chunks"]
    all_vendors = sorted({c["vendor"] for c in chunks})
    # 分层排序：国内核心在前（按 CORE_VENDORS 顺序），海外对标在后
    vendors = [v for v in CORE_VENDORS if v in all_vendors] + \
              sorted(v for v in all_vendors if v not in CORE_VENDORS)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    mode = "LLM汇总(deepseek-chat)" if api_key else "抽取式摘要(未配置API Key)"

    matrix = {"mode": mode, "dimensions": list(DIMENSIONS),
              "tiers": {v: tier_of(v) for v in vendors}, "vendors": {}}
    for v in vendors:
        matrix["vendors"][v] = {}
        for dim, kw in DIMENSIONS.items():
            ev = retrieve(chunks, v, dim + " " + kw, lock_section=dim)
            cell = {"evidence": [{"score": s, "section": c["section"], "source": c["source"],
                                  "text": c["text"][:120] + "…"} for s, c in ev]}
            if api_key and ev:
                try:
                    cell.update(llm_summary(v, dim, ev, api_key))
                except Exception as e:
                    cell["summary"] = extractive_summary(ev)
                    cell["llm_error"] = str(e)
            else:
                cell["summary"] = extractive_summary(ev)
            matrix["vendors"][v][dim] = cell

    (OUT / "matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown 对比矩阵（分层：国内核心主表 + 海外对标附表）
    lines = ["# 大模型厂商四维对比矩阵", "",
             f"> 生成模式：{mode} ｜ 维度锁已启用（章节同名 chunk 确定性优先） ｜ 证据均来自本地语料库，可溯源到 chunk", ""]
    core = [v for v in vendors if tier_of(v) == "国内核心"]
    bench = [v for v in vendors if tier_of(v) == "海外对标"]
    for title, group in [("国内核心层（A/H 已上市或拟 IPO 大模型公司）", core),
                         ("海外对标层（映射基准）", bench)]:
        if not group:
            continue
        lines += [f"## {title}", ""]
        lines.append("| 维度 | " + " | ".join(group) + " |")
        lines.append("|---|" + "---|" * len(group))
        for dim in DIMENSIONS:
            row = [f"**{dim}**"]
            for v in group:
                row.append(matrix["vendors"][v][dim]["summary"].replace("\n", " "))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    lines += ["## 证据溯源（每格 top-1）", ""]
    for v in vendors:
        lines.append(f"### {v}")
        for dim in DIMENSIONS:
            evs = matrix["vendors"][v][dim]["evidence"]
            if evs:
                e = evs[0]
                lines.append(f"- **{dim}** ← `{e['source']}` §{e['section']}（相关度 {e['score']}）")
        lines.append("")
    (OUT / "matrix.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"完成：{len(vendors)} 厂商 × {len(DIMENSIONS)} 维度，模式={mode}")
    print(f"输出：{OUT/'matrix.md'} / matrix.json")


if __name__ == "__main__":
    main()
