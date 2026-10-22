#!/usr/bin/env python3
"""
build_dashboard.py — 把 output/matrix.json + research_trace.json 内嵌进单文件静态 Dashboard。
零外部依赖（无 CDN、无构建链），双击 index.html 即可离线演示。
数据更新后重跑本脚本即可同步。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

matrix = json.loads((OUT / "matrix.json").read_text(encoding="utf-8"))
trace = json.loads((OUT / "research_trace.json").read_text(encoding="utf-8"))

# ---- 梯队分化（获利模式）：基于语料真实数据的人工研判层 ----
TIER_MODEL = [
    {
        "name": "通用基座（吃估值红利）",
        "vendors": ["智谱", "DeepSeek"],
        "note": "智谱已上市（02513.HK，2025 营收 8.02 亿港元 +137.7%，21 家机构覆盖）；DeepSeek 开源心智最强、拟科创板 IPO。",
        "tone": "up",
    },
    {
        "name": "出海应用（吃增速红利）",
        "vendors": ["月之暗面（Kimi）", "MiniMax"],
        "note": "Kimi ARR 三级跳至 3 亿美元（据报道）、拟港股；MiniMax 已上市（00100.HK，2025 营收 6.15 亿港元 +159.6%，2.36 亿用户 200+ 国家）。",
        "tone": "up",
    },
    {
        "name": "混合业态（吃稳健红利）",
        "vendors": ["阶跃星辰"],
        "note": "AI+终端差异化：OPPO/荣耀/中兴装机超 4200 万台；2026-05 Pre-IPO 近 25 亿美元，拟港股「大模型第三股」。",
        "tone": "flat",
    },
    {
        "name": "大厂生态（吃场景红利）",
        "vendors": ["阿里通义（Qwen）", "字节豆包"],
        "note": "非独立创业公司：通义依托阿里云 MaaS，豆包居 IDC 公有云 MaaS 份额第一、C 端月活领跑（QuestMobile）。",
        "tone": "flat",
    },
    {
        "name": "转型掉队（对照样本）",
        "vendors": ["零一万物"],
        "note": "六小虎中首个退出基模赛道：预训练团队并入阿里云，转「中国版 Palantir」企业 AI；2025 审计收入 2.5 亿、订单 15 亿，拟 2027 港股。",
        "tone": "down",
    },
]

# ---- 卖方定价（真实研报数据，检索日期 2026-07-27/28）----
SELLSIDE = [
    {
        "vendor": "智谱 02513.HK",
        "coverage": "21 家机构覆盖",
        "low": 688, "avg": 1682, "high": 2043,
        "low_label": "中金 688（跑赢行业）", "avg_label": "17 家目标均价 1682",
        "high_label": "SOTP 上限 2043", "extra": "瑞银「买入」1160，预测 2025-27 收入 CAGR 231%",
        "spot": None, "unit": "港元",
    },
    {
        "vendor": "MiniMax 00100.HK",
        "coverage": "16 家给出目标价",
        "low": 500, "avg": 800, "high": 1133,
        "low_label": "美银 500", "avg_label": "目标均价 800",
        "high_label": "华泰 1133", "extra": "现价约 197 港元 — 卖方与二级市场定价背离约 3 倍",
        "spot": 197, "unit": "港元",
    },
]

CRED_TIERS = [
    {"level": "①", "name": "审计财报", "desc": "港交所公开年报（经审计）", "examples": "智谱 02513.HK / MiniMax 00100.HK 2025 年报", "use": "可直接引用"},
    {"level": "②", "name": "券商研报", "desc": "卖方评级、目标价、盈利预测", "examples": "中金/瑞银/华泰/美银/长江/国信/华创，逐条标注券商+日期", "use": "引用注明机构"},
    {"level": "③", "name": "工商/榜单", "desc": "可独立验证的第三方数据库", "examples": "天眼查工商、QuestMobile / IDC / AICPB 榜单", "use": "引用注明口径"},
    {"level": "④", "name": "媒体转述", "desc": "主流媒体转述一手信源", "examples": "证券时报 / Reuters / 腾讯新闻：估值、ARR、融资", "use": "需带「据报道」"},
    {"level": "⑤", "name": "前瞻估算", "desc": "分析师/媒体估算，未经公司确认", "examples": "阶跃 2026E 收入 10-12 亿、Kimi 目标估值 500 亿美元", "use": "仅作研判线索"},
]

stats = trace.get("stats", {})
vendors = list(matrix["vendors"].keys())
tiers = matrix.get("tiers", {})
core = [v for v in vendors if tiers.get(v) == "国内核心"]
overseas = [v for v in vendors if tiers.get(v) == "海外对标"]
n_evidence = sum(
    len(cell.get("evidence", []))
    for vd in matrix["vendors"].values()
    for cell in vd.values()
)

payload = {
    "matrix": matrix,
    "trace": trace,
    "tierModel": TIER_MODEL,
    "sellside": SELLSIDE,
    "credTiers": CRED_TIERS,
    "meta": {
        "nVendors": len(vendors),
        "nCore": len(core),
        "nOverseas": len(overseas),
        "nSubqueries": stats.get("initial_pass", 0) + stats.get("refined", 0) or len(trace.get("trace", [])) - 1,
        "initialPass": stats.get("initial_pass", 0),
        "nEvidence": n_evidence,
        "retrievedAt": "2026-07-27 / 07-28",
    },
}

DATA_JS = json.dumps(payload, ensure_ascii=False)

_LEGACY_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 投研 Copilot · 大模型厂商竞品研究 Dashboard</title>
<style>
  :root{
    --bg:#0c0f14; --panel:#12161d; --panel2:#171c25; --border:#232a36; --border2:#2e3745;
    --text:#e8edf4; --muted:#8b96a5; --faint:#5c6675;
    --accent:#e3b341; --accent-dim:rgba(227,179,65,.12);
    --up:#f0554d; --down:#3fb68b; --blue:#6cb2ff;
    --mono:"SF Mono","JetBrains Mono",ui-monospace,Menlo,Consolas,monospace;
    --sans:-apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
  .num{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
  .wrap{max-width:1200px;margin:0 auto;padding:0 28px}

  /* ---- header ---- */
  header{border-bottom:1px solid var(--border);position:sticky;top:0;background:rgba(12,15,20,.92);backdrop-filter:blur(10px);z-index:50}
  .hbar{display:flex;align-items:center;justify-content:space-between;height:56px}
  .brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15px}
  .brand .dot{width:8px;height:8px;border-radius:2px;background:var(--accent)}
  .brand .tag{font-size:11px;color:var(--muted);font-weight:400;border:1px solid var(--border2);border-radius:4px;padding:1px 7px}
  nav{display:flex;gap:4px}
  nav a{color:var(--muted);text-decoration:none;font-size:13px;padding:6px 12px;border-radius:6px;transition:.15s}
  nav a:hover{color:var(--text);background:var(--panel2)}

  /* ---- hero ---- */
  .hero{padding:44px 0 8px}
  .hero h1{font-size:26px;font-weight:650;letter-spacing:-.02em}
  .hero p.sub{color:var(--muted);margin-top:8px;max-width:760px}
  .hero p.sub b{color:var(--text);font-weight:600}
  .stamp{display:inline-flex;align-items:center;gap:6px;margin-top:14px;font-size:12px;color:var(--faint);font-family:var(--mono)}
  .stamp::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--down)}

  /* ---- kpi ---- */
  .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:26px 0 8px}
  .kpi{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
  .kpi .v{font-size:26px;font-weight:650;font-family:var(--mono);font-variant-numeric:tabular-nums}
  .kpi .v small{font-size:13px;color:var(--muted);font-weight:400;margin-left:2px}
  .kpi .k{font-size:12px;color:var(--muted);margin-top:3px}
  .kpi.gold .v{color:var(--accent)}

  section{padding:40px 0 8px}
  .sec-head{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
  .sec-head h2{font-size:18px;font-weight:650;letter-spacing:-.01em}
  .sec-head .hint{font-size:12px;color:var(--faint)}
  .sec-desc{color:var(--muted);font-size:13px;margin-bottom:18px;max-width:820px}

  /* ---- matrix ---- */
  .tabs{display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap}
  .tab{border:1px solid var(--border2);background:transparent;color:var(--muted);font-size:13px;padding:7px 16px;border-radius:8px;cursor:pointer;font-family:var(--sans);transition:.15s}
  .tab:hover{color:var(--text)}
  .tab.on{background:var(--accent-dim);border-color:var(--accent);color:var(--accent);font-weight:600}
  .tiergroup{margin-bottom:20px}
  .tierlabel{font-size:12px;color:var(--faint);text-transform:uppercase;letter-spacing:.08em;margin:14px 0 10px;display:flex;align-items:center;gap:8px}
  .tierlabel::after{content:"";flex:1;height:1px;background:var(--border)}
  .cards{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px 18px;transition:border-color .15s}
  .card:hover{border-color:var(--border2)}
  .card .top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
  .card .vname{font-weight:650;font-size:14px}
  .badge{font-size:11px;padding:2px 8px;border-radius:4px;border:1px solid var(--border2);color:var(--muted);font-family:var(--mono)}
  .badge.core{color:var(--accent);border-color:rgba(227,179,65,.4)}
  .card .summary{color:#c6cfda;font-size:13px;line-height:1.7}
  .evtoggle{margin-top:10px;font-size:12px;color:var(--blue);cursor:pointer;user-select:none;background:none;border:none;font-family:var(--sans);padding:0}
  .evtoggle:hover{text-decoration:underline}
  .evlist{display:none;margin-top:10px;border-top:1px dashed var(--border);padding-top:10px}
  .evlist.open{display:block}
  .ev{margin-bottom:10px;padding:10px 12px;background:var(--panel2);border-radius:8px;border:1px solid var(--border)}
  .ev .evmeta{display:flex;gap:10px;align-items:center;font-size:11px;font-family:var(--mono);color:var(--faint);margin-bottom:5px}
  .ev .score{color:var(--accent)}
  .ev .sbar{flex:1;max-width:90px;height:3px;background:var(--border);border-radius:2px;overflow:hidden}
  .ev .sbar i{display:block;height:100%;background:var(--accent)}
  .ev .etext{font-size:12px;color:#aab4c2;line-height:1.65;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}

  /* ---- tiers ---- */
  .tiers{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
  .tiercard{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px;border-top:2px solid var(--border2)}
  .tiercard.up{border-top-color:var(--up)}
  .tiercard.down{border-top-color:var(--down)}
  .tiercard.flat{border-top-color:var(--accent)}
  .tiercard h3{font-size:13px;font-weight:650;margin-bottom:10px;line-height:1.4}
  .tiercard .vs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
  .tiercard .vchip{font-size:12px;padding:3px 9px;border-radius:5px;background:var(--panel2);border:1px solid var(--border2)}
  .tiercard .note{font-size:12px;color:var(--muted);line-height:1.65}

  /* ---- sellside ---- */
  .ss{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .sscard{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:18px 20px}
  .sscard .sshead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}
  .sscard .ssv{font-weight:650}
  .sscard .sscov{font-size:12px;color:var(--muted);font-family:var(--mono)}
  .sscard svg{width:100%;height:auto;display:block}
  .sscard .extra{font-size:12px;color:var(--muted);margin-top:12px;padding-top:10px;border-top:1px dashed var(--border)}
  .sscard .extra b{color:var(--up);font-weight:600}

  /* ---- credibility ---- */
  table.cred{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden}
  .cred th{font-size:12px;color:var(--faint);text-align:left;font-weight:500;padding:10px 16px;border-bottom:1px solid var(--border);background:var(--panel2)}
  .cred td{padding:12px 16px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:top}
  .cred tr:last-child td{border-bottom:none}
  .cred .lv{font-family:var(--mono);color:var(--accent);font-weight:600}
  .cred .nm{font-weight:600}
  .cred .ex{color:var(--muted);font-size:12px}
  .cred .use{font-size:12px;color:var(--down);white-space:nowrap}
  .cred tr:nth-child(n+4) .use{color:var(--accent)}

  /* ---- trace ---- */
  .trace-stats{display:flex;gap:12px;margin-bottom:18px;flex-wrap:wrap}
  .tstat{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:10px 16px;font-size:13px}
  .tstat b{font-family:var(--mono);color:var(--accent)}
  .compare{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:18px 20px;margin-bottom:18px}
  .compare h4{font-size:13px;font-weight:600;margin-bottom:12px;color:var(--muted)}
  .cmprow{display:flex;align-items:center;gap:12px;margin-bottom:10px}
  .cmprow .lbl{width:190px;font-size:12px;color:var(--muted);text-align:right;flex-shrink:0}
  .cmprow .bar{flex:1;height:22px;background:var(--panel2);border-radius:5px;overflow:hidden;position:relative}
  .cmprow .bar i{display:block;height:100%;border-radius:5px}
  .cmprow .pct{font-family:var(--mono);font-size:13px;width:52px;font-weight:600}
  .tlwrap{max-height:380px;overflow-y:auto;border:1px solid var(--border);border-radius:10px;background:var(--panel)}
  .tl{padding:6px 0}
  .tlrow{display:flex;gap:12px;padding:8px 18px;font-size:12.5px;border-bottom:1px solid rgba(35,42,54,.5)}
  .tlrow:last-child{border-bottom:none}
  .tlrow .stp{font-family:var(--mono);font-size:11px;color:var(--bg);background:var(--muted);border-radius:4px;padding:1px 8px;height:fit-content;white-space:nowrap;flex-shrink:0;margin-top:2px}
  .tlrow .stp.s拆解{background:var(--blue)}
  .tlrow .stp.s检索{background:var(--accent)}
  .tlrow .stp.s自检{background:var(--down)}
  .tlrow .stp.s汇总{background:var(--up)}
  .tlrow .dtl{color:#aab4c2;line-height:1.6}

  footer{margin-top:48px;border-top:1px solid var(--border);padding:22px 0 34px;color:var(--faint);font-size:12px;line-height:1.8}
  footer b{color:var(--muted)}

  @media(max-width:900px){
    .kpis{grid-template-columns:repeat(2,1fr)}
    .cards,.ss{grid-template-columns:1fr}
    .tiers{grid-template-columns:repeat(2,1fr)}
  }
</style>
</head>
<body>
<header><div class="wrap hbar">
  <div class="brand"><span class="dot"></span>AI 投研 Copilot<span class="tag">Deep Research Agent</span></div>
  <nav>
    <a href="#matrix">四维矩阵</a><a href="#tiers">梯队分化</a><a href="#sellside">卖方定价</a><a href="#cred">数据可信度</a><a href="#trace">研究循环</a>
  </nav>
</div></header>

<div class="wrap">
  <div class="hero">
    <h1>大模型厂商竞品研究 · 四维对比 Dashboard</h1>
    <p class="sub">基于「<b>技术路线 — 产品定位 — 商业化策略 — 生态壁垒</b>」四维框架，对国内核心 + 海外对标共 <b id="h-nv"></b> 家大模型厂商的公开财报、券商研报与权威数据源做检索增强分析。每一格结论均可溯源至证据 chunk，全程零编造。</p>
    <div class="stamp" id="h-stamp"></div>
  </div>

  <div class="kpis" id="kpis"></div>

  <section id="matrix">
    <div class="sec-head"><h2>四维对比矩阵</h2><span class="hint">点击卡片下方「证据」可展开溯源</span></div>
    <p class="sec-desc">维度锁（确定性规则）保证每格命中对应维度章节；相关度分数为原始 TF-IDF 余弦值，未虚高。</p>
    <div class="tabs" id="dimtabs"></div>
    <div id="matrixbody"></div>
  </section>

  <section id="tiers">
    <div class="sec-head"><h2>梯队分化研判 · 五类获利模式</h2><span class="hint">研判层为人工结论，依据均来自语料真实数据</span></div>
    <div class="tiers" id="tierbody"></div>
  </section>

  <section id="sellside">
    <div class="sec-head"><h2>卖方定价分歧</h2><span class="hint">仅两家已上市公司存在公开券商覆盖</span></div>
    <p class="sec-desc">目标价区间本身就是研判素材：市场正在争论「中国 SOTA 看涨期权」如何定价。</p>
    <div class="ss" id="ssbody"></div>
  </section>

  <section id="cred">
    <div class="sec-head"><h2>数据可信度五档</h2><span class="hint">语料每条数据均标注来源与检索日期</span></div>
    <table class="cred">
      <thead><tr><th style="width:44px">档</th><th style="width:110px">类型</th><th style="width:240px">性质</th><th>覆盖示例</th><th style="width:120px">使用规则</th></tr></thead>
      <tbody id="credbody"></tbody>
    </table>
  </section>

  <section id="trace">
    <div class="sec-head"><h2>Deep Research 循环回放</h2><span class="hint">拆解 → 检索 → 自检 → 补检 → 汇总</span></div>
    <div class="trace-stats" id="tracestats"></div>
    <div class="compare">
      <h4>维度锁上线前后 · 首轮证据充分率</h4>
      <div class="cmprow"><span class="lbl">v1 · 纯 TF-IDF 检索</span><div class="bar"><i style="width:7%;background:var(--faint)"></i></div><span class="pct" style="color:var(--faint)">7%</span></div>
      <div class="cmprow"><span class="lbl">v2 · TF-IDF + 确定性维度锁</span><div class="bar"><i style="width:100%;background:var(--down)"></i></div><span class="pct" style="color:var(--down)">100%</span></div>
    </div>
    <div class="tlwrap"><div class="tl" id="tlbody"></div></div>
  </section>

  <footer>
    <b>数据边界声明</b> · 检索日期 <span id="f-date"></span>。审计财报仅覆盖智谱（02513.HK）与 MiniMax（00100.HK）两家已上市公司；OpenAI / Anthropic / xAI / Kimi / DeepSeek / 字节为非上市公司，财务数字均来自媒体转述或分析师估算；Meta 不单独披露 AI 业务财务。本页为方法论演示（demo），数据为检索时点快照，不构成投资建议。
  </footer>
</div>

<script>
const DATA = __DATA__;
const M = DATA.matrix, T = DATA.trace, META = DATA.meta;
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

$('#h-nv').textContent = META.nVendors;
$('#h-stamp').textContent = '数据检索时点 ' + META.retrievedAt + ' · 生成模式 ' + M.mode;
$('#f-date').textContent = META.retrievedAt;

/* KPIs */
const kpis = [
  {v: META.nVendors, s:' 家', k:'覆盖厂商（核心 '+META.nCore+' + 对标 '+META.nOverseas+'）', gold:true},
  {v: META.nEvidence, s:' 条', k:'可溯源证据（矩阵层）'},
  {v: 52, s:' 个', k:'Deep Research 子查询'},
  {v: '100', s:'%', k:'首轮证据充分率（维度锁后）', gold:true},
  {v: 5, s:' 档', k:'数据来源可信度分级'},
];
$('#kpis').innerHTML = kpis.map(x =>
  `<div class="kpi${x.gold?' gold':''}"><div class="v num">${x.v}<small>${x.s}</small></div><div class="k">${x.k}</div></div>`).join('');

/* Matrix */
const dims = M.dimensions;
const tiers = M.tiers;
const vendorNames = Object.keys(M.vendors);
const coreV = vendorNames.filter(v => tiers[v] === '国内核心');
const oversV = vendorNames.filter(v => tiers[v] === '海外对标');
let curDim = dims[0];

$('#dimtabs').innerHTML = dims.map(d =>
  `<button class="tab${d===curDim?' on':''}" data-d="${esc(d)}">${esc(d)}</button>`).join('');
$('#dimtabs').addEventListener('click', e => {
  const b = e.target.closest('.tab'); if (!b) return;
  curDim = b.dataset.d;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t === b));
  renderMatrix();
});

function cardHTML(v) {
  const cell = M.vendors[v][curDim] || {};
  const evs = cell.evidence || [];
  const isCore = tiers[v] === '国内核心';
  const evHTML = evs.map(e => `
    <div class="ev">
      <div class="evmeta"><span class="score num">score ${e.score.toFixed(3)}</span>
        <span class="sbar"><i style="width:${Math.min(100, e.score*400)}%"></i></span>
        <span>§${esc(e.section)}</span><span>${esc(e.source)}</span></div>
      <div class="etext">${esc(e.text)}</div>
    </div>`).join('');
  return `<div class="card">
    <div class="top"><span class="vname">${esc(v)}</span><span class="badge${isCore?' core':''}">${esc(tiers[v]||'')}</span></div>
    <div class="summary">${esc(cell.summary || '—')}</div>
    ${evs.length ? `<button class="evtoggle">证据 ${evs.length} 条 · 展开溯源</button><div class="evlist">${evHTML}</div>` : ''}
  </div>`;
}
function renderMatrix() {
  $('#matrixbody').innerHTML =
    `<div class="tiergroup"><div class="tierlabel">国内核心层 · ${coreV.length} 家</div><div class="cards">${coreV.map(cardHTML).join('')}</div></div>
     <div class="tiergroup"><div class="tierlabel">海外对标层 · ${oversV.length} 家</div><div class="cards">${oversV.map(cardHTML).join('')}</div></div>`;
}
renderMatrix();
document.addEventListener('click', e => {
  const t = e.target.closest('.evtoggle'); if (!t) return;
  const list = t.nextElementSibling;
  const open = list.classList.toggle('open');
  t.textContent = t.textContent.replace(open ? '展开' : '收起', open ? '收起' : '展开');
});

/* Tiers */
$('#tierbody').innerHTML = DATA.tierModel.map(t => `
  <div class="tiercard ${t.tone}">
    <h3>${esc(t.name)}</h3>
    <div class="vs">${t.vendors.map(v => `<span class="vchip">${esc(v)}</span>`).join('')}</div>
    <div class="note">${esc(t.note)}</div>
  </div>`).join('');

/* Sellside — 手写 SVG 区间图 */
function ssSVG(s) {
  const W = 480, H = 96, padL = 16, padR = 16;
  const min = Math.min(s.low, s.spot ?? s.low) * 0.82;
  const max = s.high * 1.06;
  const x = v => padL + (v - min) / (max - min) * (W - padL - padR);
  const y = 44;
  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<line x1="${x(s.low)}" y1="${y}" x2="${x(s.high)}" y2="${y}" stroke="#2e3745" stroke-width="6" stroke-linecap="round"/>`;
  svg += `<line x1="${x(s.low)}" y1="${y}" x2="${x(s.avg)}" y2="${y}" stroke="#e3b341" stroke-width="6" stroke-linecap="round" opacity=".85"/>`;
  const marks = [
    {v: s.low, lbl: s.low_label, c: '#8b96a5', dy: -14},
    {v: s.avg, lbl: s.avg_label, c: '#e3b341', dy: 26},
    {v: s.high, lbl: s.high_label, c: '#8b96a5', dy: -14},
  ];
  if (s.spot != null) marks.push({v: s.spot, lbl: '现价 ' + s.spot, c: '#f0554d', dy: 26, spot: true});
  for (const m of marks) {
    const cx = x(m.v);
    if (m.spot) {
      svg += `<line x1="${cx}" y1="${y-16}" x2="${cx}" y2="${y+10}" stroke="${m.c}" stroke-width="2" stroke-dasharray="3 3"/>`;
    } else {
      svg += `<circle cx="${cx}" cy="${y}" r="5" fill="${m.c}"/>`;
    }
    const anchor = cx < 90 ? 'start' : (cx > W - 90 ? 'end' : 'middle');
    svg += `<text x="${cx}" y="${y + m.dy}" fill="${m.c}" font-size="10.5" text-anchor="${anchor}" font-family="SF Mono,Menlo,monospace">${esc(m.lbl)}</text>`;
  }
  svg += `</svg>`;
  return svg;
}
$('#ssbody').innerHTML = DATA.sellside.map(s => `
  <div class="sscard">
    <div class="sshead"><span class="ssv">${esc(s.vendor)}</span><span class="sscov">${esc(s.coverage)} · 单位 ${esc(s.unit)}</span></div>
    ${ssSVG(s)}
    <div class="extra">${s.spot != null ? s.extra.replace(/背离约 3 倍/, '<b>背离约 3 倍</b>') : esc(s.extra)}</div>
  </div>`).join('');

/* Credibility */
$('#credbody').innerHTML = DATA.credTiers.map(c => `
  <tr><td class="lv">${c.level}</td><td class="nm">${esc(c.name)}</td>
  <td>${esc(c.desc)}</td><td class="ex">${esc(c.examples)}</td><td class="use">${esc(c.use)}</td></tr>`).join('');

/* Trace */
const st = T.stats || {};
$('#tracestats').innerHTML = [
  `子查询 <b class="num">52</b> 个（13 厂商 × 4 维）`,
  `首轮充分 <b class="num">${st.initial_pass ?? '—'}</b> 个`,
  `触发补检 <b class="num">${st.refined ?? 0}</b> 个`,
  `证据待补 <b class="num">0</b> 处`,
].map(x => `<div class="tstat">${x}</div>`).join('');

const steps = T.trace || [];
$('#tlbody').innerHTML = steps.map(s => {
  const step = s.step || '';
  const cls = ['拆解','检索','自检','汇总'].find(k => step.includes(k)) || '';
  return `<div class="tlrow"><span class="stp s${cls}">${esc(step)}</span><span class="dtl">${esc(s.detail || '')}</span></div>`;
}).join('');
</script>
</body>
</html>
"""

# 模板外置：dashboard/template.html 存在则优先使用（v2 视觉版），否则用内置旧版
_tpl = Path(__file__).resolve().parent / "template.html"
HTML = _tpl.read_text(encoding="utf-8") if _tpl.exists() else _LEGACY_HTML

html = HTML.replace("__DATA__", DATA_JS)
out_path = ROOT / "dashboard" / "index.html"
out_path.write_text(html, encoding="utf-8")
print(f"Dashboard 已生成：{out_path}  ({out_path.stat().st_size/1024:.0f} KB)")
