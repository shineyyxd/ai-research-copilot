# -*- coding: utf-8 -*-
"""
build_corpus_v2.py — 用真实数据源（天眼查/Wind）组装 L2 模型层 v2 语料
每条事实携带六元组证据信封：[trust_tier | as_of | caliber | source]
输入：data/tianyancha/*.csv、data/wind/*.json、Wind 缓存 CSV、rag/corpus/（v1）
输出：rag/corpus_v2/*.md（YAML 头：market/layer/depth_tier/as_of）
"""
import csv, glob, json, os, re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYC = ROOT / "data" / "tianyancha"
WIND = ROOT / "data" / "wind"
V1 = ROOT / "rag" / "corpus"
OUT = ROOT / "rag" / "corpus_v2"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = Path.home() / ".cache" / "wind-allskill" / "csv"
TODAY = "2026-10-23"

# vendor_key -> (显示名, market, v1语料文件名或None, 天眼查名, wind名)
VENDORS = {
    "zhipu":        ("智谱", "港股", "zhipu.md", "智谱", "智谱"),
    "minimax":      ("MiniMax", "港股", "minimax.md", "MiniMax", "MiniMax"),
    "moonshot-kimi":("月之暗面（Kimi）", "未上市", "moonshot-kimi.md", "月之暗面", None),
    "deepseek":     ("DeepSeek", "未上市", "deepseek.md", "DeepSeek", None),
    "stepfun":      ("阶跃星辰", "未上市", "stepfun.md", "阶跃星辰", None),
    "01ai":         ("零一万物", "未上市", "01ai.md", "零一万物", None),
    "alibaba-qwen": ("阿里通义（Qwen）", "港股", "alibaba-qwen.md", None, "阿里巴巴"),
    "baidu":        ("百度文心", "港股", None, None, "百度集团"),
    "iflytek":      ("科大讯飞（星火）", "A股", None, None, "科大讯飞"),
    "tencent":      ("腾讯（混元）", "港股", None, None, "腾讯控股"),
    "bytedance-doubao": ("字节豆包", "未上市", "bytedance-doubao.md", "字节豆包", None),
    "google-gemini":("Google Gemini", "美股", "google-gemini.md", None, "Google"),
    "meta-llama":   ("Meta（Llama）", "美股", "meta-llama.md", None, "Meta"),
}

def env(tier, as_of, caliber, source):
    return f"[{tier}|as_of={as_of}|caliber={caliber}|src={source}]"

def ts2date(ms):
    try:
        return time.strftime("%Y-%m-%d", time.localtime(int(ms) / 1000))
    except Exception:
        return ""

def load_tyc(name):
    """返回 (工商行列表, 融资行列表)"""
    basic, fin = [], []
    bf = TYC / f"{name}_工商基本信息.csv"
    if bf.exists():
        with open(bf, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows:
            r = rows[0]
            for k in ("legalPersonName", "regCapital", "estiblishTime", "regLocation", "companyOrgType"):
                if r.get(k):
                    label = {"legalPersonName": "法定代表人", "regCapital": "注册资本",
                             "estiblishTime": "成立日期", "regLocation": "注册地",
                             "companyOrgType": "企业类型"}[k]
                    v = r[k]
                    if k == "estiblishTime" and v.isdigit():
                        v = ts2date(v)
                    basic.append(f"{label}：{v}")
    ff = TYC / f"{name}_融资历史.csv"
    if ff.exists():
        with open(ff, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = ts2date(r.get("pubTime", ""))
                rd = r.get("round", "").strip()
                money = r.get("money", "").strip()
                inv = (r.get("investorName") or "").strip()
                val = (r.get("value") or "").strip()
                if rd or money:
                    s = f"{d} {rd}：{money}"
                    if inv: s += f"（投资方：{inv}）"
                    if val: s += f"，估值/投前：{val}"
                    fin.append(s)
    return basic, fin

def load_wind_fund(name):
    f = WIND / f"{name}_财务指标.json"
    if not f.exists():
        return None
    t = f.read_text(encoding="utf-8")
    # CLI 输出是双重转义的 JSON，先反转义再取 data_preview
    t = t.replace("\\\\n", "\n").replace('\\"', '"')
    m = re.search(r'data_preview":\s*"(wind_code,.*?)"\s*,\s*"notice', t, re.S)
    if not m:
        return None
    lines = [ln for ln in m.group(1).split("\n") if ln.strip()]
    if len(lines) < 2:
        return None
    hdr = lines[0].split(",")
    vals = lines[1].split(",")
    d = dict(zip(hdr, vals))
    keep = {"总市值2": "总市值", "市盈率PE_TTM": "PE_TTM", "市销率PS_TTM": "PS_TTM",
            "营业收入": "营业收入(亿)", "净利润": "净利润(亿)", "销售毛利率": "销售毛利率%"}
    return [f"{label} {d[k]}" for k, label in keep.items() if d.get(k)]

def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def load_wind_ann(name):
    """从 Wind 缓存 CSV 找该公司的公告（按标题关键词匹配）"""
    kw = {"智谱": "智譜|智谱", "MiniMax": "MINIMAX|MiniMax", "阿里巴巴": "阿里巴巴",
          "百度集团": "百度", "科大讯飞": "科大訊飛|科大讯飞", "腾讯控股": "騰訊|腾讯"}.get(name)
    if not kw:
        return []
    out = []
    for f in sorted(glob.glob(str(CACHE / "wind_get_company_announcements_*.csv")),
                    key=os.path.getmtime, reverse=True)[:20]:
        try:
            with open(f, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        except Exception:
            continue
        if rows and re.search(kw, rows[0].get("title", "") + rows[0].get("content", "")[:200]):
            for r in rows[:3]:
                title = r.get("title", "").strip()
                date = r.get("date", "").strip()
                excerpt = strip_html(r.get("content", ""))[:500]
                if title:
                    out.append((date, title, excerpt))
            break
    return out

def migrate_v1(fname):
    if not fname:
        return ""
    p = V1 / fname
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"^# .*\n", "", t, count=1)  # 去掉 v1 的一级标题，由 v2 头统一生成
    return t.strip()

def build():
    manifest = []
    for key, (disp, market, v1f, tyc_name, wind_name) in VENDORS.items():
        header = ["---", f"vendor: {disp}", f"market: {market}", "layer: L2",
                  "depth_tier: deep", f"as_of: {TODAY}",
                  "trust_note: T1审计财报/T2券商研报/T3工商榜单/T4媒体转述/T5前瞻估算",
                  "---", "", f"# {disp}", ""]
        body, stats = [], {"T1": 0, "T3": 0, "v1": 0}

        # —— 真实数据层（新）——
        real = []
        if wind_name:
            fund = load_wind_fund(wind_name)
            if fund:
                real.append(f"- {env('T3榜单', TODAY, 'TTM/最新收盘', 'Wind')} 市值与估值：" + "；".join(fund))
                stats["T3"] += 1
            anns = load_wind_ann(wind_name)
            for date, title, excerpt in anns:
                real.append(f"- {env('T1公告', date or TODAY, '公司公告', 'Wind公告')} 《{title}》：{excerpt}…")
                stats["T1"] += 1
        if tyc_name:
            basic, fin = load_tyc(tyc_name)
            if basic:
                real.append(f"- {env('T3工商', TODAY, '工商登记', '天眼查')} " + "；".join(basic))
                stats["T3"] += 1
            for s in fin:
                real.append(f"- {env('T3工商', TODAY, '融资事件', '天眼查')} {s}")
                stats["T3"] += 1
        if real:
            body += ["## 实时数据层（v2 接入，六元组信封）", ""] + real + [""]

        # —— v1 叙事层（迁移，标注快照时点）——
        v1 = migrate_v1(v1f)
        if v1:
            body += [f"> 以下为 2026-07-28 快照的叙事语料（v1 迁移，T4 媒体源为主），"
                     f"时效型数字以实时数据层为准", "", v1, ""]
            stats["v1"] = 1
        if not real and not v1:
            body += ["> ⚠️证据待补：该厂商尚未接入数据源（P1 补充 scholar/GitHub/媒体源）", ""]

        (OUT / f"{key}.md").write_text("\n".join(header + body), encoding="utf-8")
        manifest.append({"vendor": disp, "key": key, "market": market, **stats})
        print(f"{disp}: T1={stats['T1']} T3={stats['T3']} v1迁移={bool(stats['v1'])}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成：{len(manifest)} 家厂商 → {OUT}")

if __name__ == "__main__":
    build()
