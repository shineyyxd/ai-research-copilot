# -*- coding: utf-8 -*-
"""
report.py — 《国内大模型公司梯队研判》主报告生成器
基于本地语料（全部真实公开数据，带来源）按「获利模式」分梯队：
  通用基座 / 出海应用 / 混合业态 / 大厂生态 / 转型掉队
每家厂商给出：梯队归属依据 + 四维证据（可溯源）+ 风险提示。
附录：海外对标映射表（研判性质，非事实陈述，均附映射理由）。
输出 output/tier_report.md + tier_report.json
"""
import json
from pathlib import Path
from query import DIMENSIONS, retrieve, tier_of, CORE_VENDORS, extractive_summary

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "output"
OUT.mkdir(exist_ok=True)

# ---- 梯队定义（获利模式框架，来源：21财经 2026-06 / 南方周末 WAIC 报道的分化叙事）----
# 归属判断为分析研判，依据 = 语料中的真实数据（每条可溯源）
TIERS = [
    {
        "name": "第一梯队 · 通用基座（吃估值红利）",
        "vendors": ["智谱", "DeepSeek"],
        "logic": "以基座模型能力本身作为核心资产，估值锚定「中国 SOTA 看涨期权」。"
                 "特征：研发投入极重、收入高增长但普遍未盈利、资本市场给予最高溢价。",
        "risk": "估值高度依赖模型迭代节奏；一旦基座能力被开源/大厂追平，估值逻辑塌缩。",
    },
    {
        "name": "第一梯队 · 出海应用（吃增速红利）",
        "vendors": ["MiniMax", "月之暗面（Kimi）"],
        "logic": "以海外 C 端/开发者市场为主要增长引擎，ARR 增速为第一定价指标。"
                 "特征：用户规模全球化、收入弹性大，但亏损与获客成本同样巨大。",
        "risk": "海外监管与支付通道风险；增速一旦放缓，卖方目标价与二级市场定价的背离会快速收敛（向下）。",
    },
    {
        "name": "第二梯队 · 混合业态（吃稳健红利）",
        "vendors": ["阶跃星辰"],
        "logic": "「AI+终端」B+C 折中路线：模型预装进手机/汽车终端换确定性收入，"
                 "牺牲部分想象力换取报表稳健性，被二级市场视为风险偏好较低的标的。",
        "risk": "终端厂商议价权强，单机授权费有天花板；开发者生态存在感弱。",
    },
    {
        "name": "第二梯队 · 大厂生态（吃流量与云红利）",
        "vendors": ["阿里通义（Qwen）", "字节豆包"],
        "logic": "背靠母公司流量与云基础设施，大模型是云业务/广告业务的引流器而非独立盈利单元。"
                 "特征：用户规模最大、价格战主导者，但不单独证明商业模式。",
        "risk": "不独立上市则无独立估值；组织优先级随母公司战略摇摆。",
    },
    {
        "name": "第三梯队 · 转型掉队（对照样本）",
        "vendors": ["零一万物"],
        "logic": "已公开退出基座竞赛，转向企业级应用（「中国版 Palantir」路线）。"
                 "作为对照样本价值极高：验证了「无持续算力资本开支能力 → 必须离开基座桌」的分化逻辑。",
        "risk": "企业级订单的交付重、复制慢；品牌从「基座玩家」降级后的人才流失。",
    },
]

# ---- 海外对标映射（研判，非事实；理由必须来自语料真实数据）----
MAPPINGS = [
    {"cn": "智谱", "overseas": "OpenAI",
     "why": "同为「基座旗舰 + 全栈产品矩阵」定位：智谱以 GLM 系列对标 GPT 系列，"
            "均以 API/订阅双轮商业化，且都处于「高增长高亏损、靠资本市场定价」阶段。"},
    {"cn": "月之暗面（Kimi）", "overseas": "Anthropic",
     "why": "同为「后发但以模型质量逆袭」的路径：Kimi K 系列在代码/长文本基准登顶的打法，"
            "与 Anthropic 靠 Claude 编码能力吃下企业市场类似；两家都以 ARR 三级跳作为融资叙事核心。"},
    {"cn": "MiniMax", "overseas": "xAI",
     "why": "同为「多模态内容消费 + 全球 C 端」：MiniMax 2.36 亿用户、200+ 国家的出海盘，"
            "与 xAI 借 X 平台做大众分发的逻辑同构；两家亏损体量在同梯队中也最重。"},
    {"cn": "阿里通义（Qwen）", "overseas": "Google Gemini",
     "why": "同为「云厂商附属旗舰」：模型服务于云收入（阿里云 / GCP），"
            "开源(权重)策略 + 全家桶集成，均不需要模型单独盈利。"},
    {"cn": "DeepSeek", "overseas": "Meta（Llama）",
     "why": "同为「开源心智代表」：以开放权重换全球开发者生态；"
            "区别在 DeepSeek 拟独立 IPO，Meta 则将 Llama 完全内化为战略成本项。"},
    {"cn": "阶跃星辰", "overseas": "—（无严格对标）",
     "why": "「模型预装终端」在海外无对应上市叙事；勉强类比苹果自研模型路线，但苹果非独立模型公司。"},
    {"cn": "字节豆包", "overseas": "Google Gemini / Meta 混合",
     "why": "流量分发像 Meta（超级 App 内嵌），云 MaaS 市占像 Google；本质是大厂生态模式的中国极端版。"},
    {"cn": "零一万物", "overseas": "—（对照样本）",
     "why": "海外基座玩家尚无「公开认输转企业应用」的同级案例（Inflection 被微软收编最接近，但非独立转型）。"},
]

FOCUS_DIMS = ["商业化策略", "技术路线", "生态壁垒"]  # 每家厂商展示的证据维度


def vendor_evidence(chunks, vendor):
    """取该厂商三个重点维度的 top-1 证据（走维度锁）。"""
    out = {}
    for dim in FOCUS_DIMS:
        ev = retrieve(chunks, vendor, dim + " " + DIMENSIONS[dim], top_k=2, lock_section=dim)
        if ev:
            s, c = ev[0]
            out[dim] = {"summary": extractive_summary(ev, max_sents=2),
                        "source": c["source"], "section": c["section"], "score": s}
    return out


def main():
    idx = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    chunks = idx["chunks"]
    have = {c["vendor"] for c in chunks}

    report = {"title": "国内大模型公司梯队研判", "date": "2026-07-28",
              "framework": "获利模式四分法（通用基座/出海应用/混合业态/大厂生态）+ 掉队对照",
              "tiers": [], "mappings": MAPPINGS}

    lines = [
        "# 国内大模型公司梯队研判",
        "",
        "> 研判日期：2026-07-28 ｜ 数据快照：2026-07-27/28 检索 ｜ 全部证据可溯源至本地语料 chunk",
        "> 数据可信度分层：审计财报 > 券商研报 > 工商/榜单 > 媒体转述 > 前瞻估算（详见各语料文件头部标注）",
        "",
        "## 核心研判",
        "",
        "2026 年中的国内大模型行业已完成从「百模大战」到「获利模式分化」的切换：",
        "**市场不再为参数买单，开始为收入结构定价。** 六小虎 + DeepSeek + 两家大厂模型",
        "分化为四种可持续获利模式与一类掉队样本，梯队间估值逻辑已不可比。",
        "关键信号：2026-07-17 港股 AI 板块回调中，智谱、MiniMax 领跌——二级市场开始",
        "区分「有真收入」与「有好故事」，本报告的分层框架正是对这一分化的结构化回应。",
        "",
    ]

    for tier in TIERS:
        lines += [f"## {tier['name']}", "", f"**归属逻辑**：{tier['logic']}", ""]
        t_out = {"name": tier["name"], "logic": tier["logic"], "risk": tier["risk"], "vendors": {}}
        for v in tier["vendors"]:
            if v not in have:
                continue
            evs = vendor_evidence(chunks, v)
            t_out["vendors"][v] = evs
            lines.append(f"### {v}")
            lines.append("")
            for dim in FOCUS_DIMS:
                if dim in evs:
                    e = evs[dim]
                    lines.append(f"- **{dim}**：{e['summary']}")
                    lines.append(f"  <sub>来源：`{e['source']}` §{e['section']}（相关度 {e['score']}）</sub>")
            lines.append("")
        lines += [f"**梯队风险**：{tier['risk']}", ""]
        report["tiers"].append(t_out)

    lines += [
        "## 附录 A · 海外对标映射表（研判性质）",
        "",
        "> 映射为分析师研判而非事实陈述；每条附映射理由，理由中的数据均来自语料（可溯源）。",
        "",
        "| 国内厂商 | 海外对标 | 映射理由 |",
        "|---|---|---|",
    ]
    for m in MAPPINGS:
        lines.append(f"| {m['cn']} | {m['overseas']} | {m['why']} |")

    lines += [
        "",
        "## 附录 B · 方法论与数据边界",
        "",
        "- **框架**：技术路线 / 产品定位 / 商业化策略 / 生态壁垒 四维检索 + 获利模式分层。",
        "- **检索**：TF-IDF + 中文 bigram + 维度锁（章节同名 chunk 确定性优先），每格证据可溯源到 chunk。",
        "- **数据边界**：真正有审计财报的仅智谱（HK.02513）、MiniMax（HK.00100）两家；",
        "  非上市公司数字来自券商研报、工商数据与媒体转述，前瞻数据仅作研判线索。",
        "- **免责**：本报告为方法论演示，数据为检索日快照，不构成投资建议。",
        "",
    ]

    (OUT / "tier_report.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "tier_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    n_vendors = sum(len(t["vendors"]) for t in report["tiers"])
    print(f"完成：{len(TIERS)} 个梯队 ｜ {n_vendors} 家厂商 ｜ {len(MAPPINGS)} 条海外映射")
    print(f"输出：{OUT/'tier_report.md'} / tier_report.json")


if __name__ == "__main__":
    main()
