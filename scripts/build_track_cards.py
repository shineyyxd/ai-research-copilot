# -*- coding: utf-8 -*-
"""
build_track_cards.py — 跟踪层指标卡生成器（L1 算力层，21 家）
与 L2 深挖层不同：跟踪层不做四维矩阵，只做统一格式的轻量指标卡
（市值/估值/营收/净利/毛利率 + 产业链定位），每条数据带六元组信封。
输出：rag/track/L1/<key>.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_corpus_v2 import load_wind_fund, env, TODAY  # noqa: E402

OUT = ROOT / "rag" / "track" / "L1"
OUT.mkdir(parents=True, exist_ok=True)

# key -> (显示名, 代码, 市场, 产业链定位)
L3 = {
    "kingsoft-office": ("金山办公", "688111.SH", "A股", "办公 AI（WPS AI）"),
    "yonyou":     ("用友网络", "600588.SH", "A股", "企服 AI（ERP+Agent）"),
    "qihoo360":   ("三六零", "601360.SH", "A股", "C 端 AI 助手/安全"),
    "kunlun":     ("昆仑万维", "300418.SZ", "A股", "AI 出海应用（天工）"),
    "thundersoft":("中科创达", "300496.SZ", "A股", "终端 OS/边缘 AI"),
    "arcsoft":    ("虹软科技", "688088.SH", "A股", "视觉算法"),
    "cloudwalk":  ("云从科技-UW", "688327.SH", "A股", "视觉/行业 AI"),
    "intellifusion": ("云天励飞-U", "688343.SH", "A股", "视觉/芯片+应用"),
    "intsig":     ("合合信息", "688615.SH", "A股", "文档 AI（扫描全能王）"),
    "hikvision":  ("海康威视", "002415.SZ", "A股", "AIoT 视觉"),
    "sensetime":  ("商汤-W", "0020.HK", "港股", "视觉/大模型应用（日日新）"),
    "kuaishou":   ("快手-W", "1024.HK", "港股", "可灵视频生成"),
    "meituan":    ("美团-W", "3690.HK", "港股", "本地生活 AI/无人机"),
    "netease":    ("网易", "9999.HK", "港股", "游戏/有道 AI"),
    "bilibili":   ("哔哩哔哩-W", "9626.HK", "港股", "内容社区 AI"),
    "4paradigm":  ("第四范式", "6682.HK", "港股", "决策 AI（先知平台）"),
    "palantir":   ("Palantir", "PLTR.O", "美股", "政企 AI（AIP）"),
    "salesforce": ("Salesforce", "CRM.N", "美股", "Agent 企服（Agentforce）"),
    "adobe":      ("Adobe", "ADBE.O", "美股", "创作 AI（Firefly）"),
    "servicenow": ("ServiceNow", "NOW.N", "美股", "企业工作流 Agent"),
}

L4 = {
    "roborock":   ("石头科技", "688169.SH", "A股", "扫地机器人"),
    "ecovacs":    ("科沃斯", "603486.SH", "A股", "服务机器人"),
    "desay":      ("德赛西威", "002920.SZ", "A股", "智驾座舱"),
    "insta360":   ("影石创新", "688775.SH", "A股", "智能影像"),
    "goertek":    ("歌尔股份", "002241.SZ", "A股", "XR/声学零组件"),
    "xiaomi":     ("小米集团-W", "1810.HK", "港股", "AIoT/手机/汽车"),
    "lenovo":     ("联想集团", "0992.HK", "港股", "AI PC/服务器"),
    "horizon":    ("地平线机器人-W", "9660.HK", "港股", "智驾芯片"),
    "liauto":     ("理想汽车-W", "2015.HK", "港股", "智驾/端到端大模型"),
    "xpeng":      ("小鹏集团-W", "9868.HK", "港股", "智驾/机器人"),
    "apple":      ("苹果", "AAPL.O", "美股", "Apple Intelligence 终端"),
    "tesla":      ("特斯拉", "TSLA.O", "美股", "FSD/Optimus 机器人"),
}

# key -> (显示名, 代码, 市场, 产业链定位)
L1 = {
    "cambricon":  ("寒武纪", "688256.SH", "A股", "AI 训练/推理芯片"),
    "haiguang":   ("海光信息", "688041.SH", "A股", "CPU/DCU 加速卡"),
    "loongson":   ("龙芯中科", "688047.SH", "A股", "自主指令集 CPU"),
    "jingjiawei": ("景嘉微", "300474.SZ", "A股", "GPU（军工起家）"),
    "metax":      ("沐曦股份-U", "688802.SH", "A股", "GPGPU"),
    "verisilicon":("芯原股份", "688521.SH", "A股", "芯片 IP 授权"),
    "montage":    ("澜起科技", "688008.SH", "A股", "内存互连芯片"),
    "fudanmicro": ("复旦微电", "688385.SH", "A股", "FPGA"),
    "sugon":      ("中科曙光", "603019.SH", "A股", "服务器/算力服务"),
    "inspur":     ("浪潮信息", "000977.SZ", "A股", "AI 服务器"),
    "zhongji":    ("中际旭创", "300308.SZ", "A股", "光模块（800G/1.6T）"),
    "eoptolink":  ("新易盛", "300502.SZ", "A股", "光模块"),
    "smic":       ("中芯国际", "0981.HK", "港股", "晶圆代工"),
    "huahong":    ("华虹宏力", "1347.HK", "港股", "特色工艺代工"),
    "iluvatar":   ("天数智芯", "9903.HK", "港股", "GPGPU"),
    "nvidia":     ("英伟达", "NVDA.O", "美股", "GPU + CUDA 生态"),
    "amd":        ("AMD", "AMD.O", "美股", "GPU/CPU"),
    "broadcom":   ("博通", "AVGO.O", "美股", "定制 ASIC/网络芯片"),
    "tsmc":       ("台积电", "TSM.N", "美股", "先进制程代工"),
    "microsoft":  ("微软", "MSFT.O", "美股", "Azure 云 + OpenAI 生态"),
    "amazon":     ("亚马逊", "AMZN.O", "美股", "AWS 云 + 自研芯片"),
}

def build_layer(layer, companies, out_dir, deep_framework):
    out_dir.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, []
    for key, (disp, code, market, role) in companies.items():
        fund = load_wind_fund(disp) or load_wind_fund(disp.split("-")[0])
        lines = ["---", f"vendor: {disp}", f"code: {code}", f"market: {market}",
                 f"layer: {layer}", "depth_tier: track", f"as_of: {TODAY}",
                 "trust_note: T1审计财报/T2券商研报/T3工商榜单/T4媒体转述/T5前瞻估算",
                 "---", "", f"# {disp}（{code}）", "",
                 f"> 产业链定位：{role}", "",
                 "## 指标卡（跟踪层 · 六元组信封）", ""]
        if fund:
            lines.append(f"- {env('T3榜单', TODAY, 'TTM/最新收盘', 'Wind')} " + "；".join(fund))
            ok += 1
        else:
            lines.append("- ⚠️证据待补：Wind 财务指标拉取失败，待重试")
            fail.append(disp)
        lines += ["", f"> 深挖框架（本层专用，升级时启用）：{deep_framework}", ""]
        (out_dir / f"{key}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{layer} 指标卡完成：{ok}/{len(companies)} 家有真实数据"
          + (f"，失败：{fail}" if fail else ""))


def main():
    build_layer("L1", L1, ROOT / "rag" / "track" / "L1", "制程产能 / 客户结构 / 国产替代率 / 库存周转")
    build_layer("L3", L3, ROOT / "rag" / "track" / "L3", "AI 收入占比 / 渗透率 / ARPU / 留存")
    build_layer("L4", L4, ROOT / "rag" / "track" / "L4", "出货量 / AI 功能搭载率 / 换机周期 / 毛利率弹性")

if __name__ == "__main__":
    main()
