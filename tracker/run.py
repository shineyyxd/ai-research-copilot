# -*- coding: utf-8 -*-
"""
run.py — Agent 赛道追踪器（真实数据）
1. 抓取：GitHub Search API（近14天新建的 agent/LLM 相关仓库，按 star 排序）
        + Hacker News Algolia API（近7天 agent/LLM 相关热帖）
2. 去重：按 URL 归一化去重，并与历史快照对比标记「新出现」
3. 聚类：关键词规则分桶（Agent框架 / RAG·知识库 / 模型发布 / 编码助手 / 基础设施 / 其他）
4. 产出：output/digest_YYYY-MM-DD.md 周报 + history/ 快照（支持"这个框架N周前什么样"回溯）
零依赖、无需 API Key。注意：本机代理已失效，运行时需 env -u http_proxy -u https_proxy。
"""
import json, re, ssl, urllib.request, urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HIST = ROOT / "history"
OUT = ROOT.parent / "output"
HIST.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
TODAY = date.today().isoformat()
CTX = ssl.create_default_context()

CLUSTERS = [
    ("Agent 框架/编排", r"agent|orchestrat|workflow|crew|autonomous|multi-agent|mcp\b|tool.?use"),
    ("RAG / 知识库", r"\brag\b|retrieval|vector|embedding|knowledge.?base|search"),
    ("模型发布/开源权重", r"\bllm\b|model|weights|open.?source.*model|qwen|llama|deepseek|kimi|glm|mistral"),
    ("编码助手/DevTool", r"code|coding|copilot|ide|developer|cli\b"),
    ("推理/部署基础设施", r"inference|serving|gpu|quantiz|deploy|runtime|kernel"),
]


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-research-copilot/0.1"})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.load(r)


def fetch_github():
    since = (date.today() - timedelta(days=14)).isoformat()
    q = urllib.parse.quote(f"agent OR llm created:>{since}")
    data = http_json(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=30")
    items = []
    for r in data.get("items", []):
        items.append({
            "src": "github", "title": r["full_name"], "url": r["html_url"],
            "desc": (r.get("description") or "")[:200], "stars": r["stargazers_count"],
            "lang": r.get("language"), "created": r["created_at"][:10],
        })
    return items


def fetch_hn():
    ts = int((datetime.now() - timedelta(days=7)).timestamp())
    items, seen = [], set()
    for q in ("agent", "LLM", "RAG"):
        data = http_json("https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote(q) +
                         f"&tags=story&numericFilters=created_at_i>{ts},points>40&hitsPerPage=20")
        for h in data.get("hits", []):
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
            if url in seen:
                continue
            seen.add(url)
            items.append({"src": "hn", "title": h["title"], "url": url,
                          "desc": "", "points": h["points"], "comments": h.get("num_comments", 0),
                          "created": h["created_at"][:10]})
    return items


def norm_url(u):
    u = re.sub(r"^https?://(www\.)?", "", u.lower())
    return u.rstrip("/")


def classify(item):
    text = (item["title"] + " " + item.get("desc", "")).lower()
    for name, pat in CLUSTERS:
        if re.search(pat, text):
            return name
    return "其他"


def main():
    gh, hn = fetch_github(), fetch_hn()
    raw = gh + hn
    # 去重
    seen, items = set(), []
    for it in raw:
        k = norm_url(it["url"])
        if k in seen:
            continue
        seen.add(k)
        items.append(it)

    # 与历史对比：标记新出现的条目 & star 变化
    prev_urls, prev_stars = set(), {}
    snaps = sorted(HIST.glob("snapshot_*.json"))
    if snaps:
        prev = json.loads(snaps[-1].read_text(encoding="utf-8"))
        for it in prev["items"]:
            prev_urls.add(norm_url(it["url"]))
            if it["src"] == "github":
                prev_stars[norm_url(it["url"])] = it.get("stars", 0)
    for it in items:
        k = norm_url(it["url"])
        it["is_new"] = k not in prev_urls
        if it["src"] == "github" and k in prev_stars:
            it["star_delta"] = it["stars"] - prev_stars[k]

    # 快照落盘（回溯用）
    (HIST / f"snapshot_{TODAY}.json").write_text(
        json.dumps({"date": TODAY, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 聚类 + 周报
    buckets = {}
    for it in items:
        buckets.setdefault(classify(it), []).append(it)

    lines = [f"# Agent 赛道周报 · {TODAY}", "",
             f"> 数据源：GitHub Search API（近14天新仓库 × star 排序，{len(gh)} 条）+ "
             f"Hacker News（近7天 >40 分热帖，{len(hn)} 条）；去重后 {len(items)} 条，"
             f"其中新出现 {sum(1 for i in items if i['is_new'])} 条。", ""]
    order = [n for n, _ in CLUSTERS] + ["其他"]
    for name in order:
        its = buckets.get(name)
        if not its:
            continue
        its.sort(key=lambda x: -(x.get("stars", 0) + x.get("points", 0) * 5))
        lines.append(f"## {name}（{len(its)}）")
        for it in its[:6]:
            flag = " 🆕" if it["is_new"] and snaps else ""
            if it["src"] == "github":
                delta = f"，+{it['star_delta']}⭐/期" if it.get("star_delta") else ""
                lines.append(f"- [{it['title']}]({it['url']}) ⭐{it['stars']}{delta} · {it['lang'] or '-'} · 建于{it['created']}{flag}")
                if it["desc"]:
                    lines.append(f"  - {it['desc']}")
            else:
                lines.append(f"- [HN] [{it['title']}]({it['url']}) ▲{it['points']} · 💬{it['comments']}{flag}")
        lines.append("")
    out = OUT / f"digest_{TODAY}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"抓取 GitHub {len(gh)} + HN {len(hn)} → 去重后 {len(items)} 条，分 {len(buckets)} 类")
    print(f"周报：{out}")
    print(f"快照：history/snapshot_{TODAY}.json（累计 {len(list(HIST.glob('snapshot_*.json')))} 期，可回溯）")


if __name__ == "__main__":
    main()
