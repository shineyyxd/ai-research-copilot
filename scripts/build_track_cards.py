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

def main():
    ok, fail = 0, []
    for key, (disp, code, market, role) in L1.items():
        fund = load_wind_fund(disp) or load_wind_fund(disp.split("-")[0])
        lines = ["---", f"vendor: {disp}", f"code: {code}", f"market: {market}",
                 "layer: L1", "depth_tier: track", f"as_of: {TODAY}",
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
        lines += ["",
                  "> 深挖框架（本层专用，升级时启用）：制程产能 / 客户结构 / 国产替代率 / 库存周转",
                  ""]
        (OUT / f"{key}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"L1 指标卡完成：{ok}/{len(L1)} 家有真实数据" + (f"，失败：{fail}" if fail else ""))

if __name__ == "__main__":
    main()
