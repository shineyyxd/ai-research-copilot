# AI 投研 Copilot（ai-research-copilot）

> 把「券商实习期间手工做的投研工作」工程化为一个**接真实数据源、可复跑、可审计**的
> Deep Research Agent：**四维拆解 → 检索 → 自检 → 补检 → 汇总**，每条结论携带
> `[trust_tier|as_of|caliber|src]` 证据信封，可溯源到证据 chunk。
> 纯 Python 标准库实现，零第三方依赖、无需 API Key 即可跑通全流程；配置 `DEEPSEEK_API_KEY` 后自动升级为 LLM 汇总。

## v2（2026-10）升级了什么

| 维度 | v1（2026-07） | v2（2026-10） |
|---|---|---|
| 数据源 | 手工整理静态语料（13 家） | **真实接口接入**：天眼查（工商/融资）+ Wind（财务/公告），17 家 L2 厂商 + 70 家产业链厂商池 |
| 证据模型 | source/section/score | **六元组信封**：trust_tier/as_of/caliber/src，每条事实机器可验证 |
| Agent 架构 | 单脚本 for 循环 | **节点式 Harness**（`rag/harness.py`）：supervisor→planner→[interrupt 审批]→researcher→critic→reporter，SQLite 断点恢复 + JSONL 审计日志 |
| 评测 | 20 条金标检索评测 | + **金标防腐化**（stable/time-sensitive + as_of）+ **端到端 faithfulness 评测**（数字回指率/信封完整率） |
| 自动化 | 无 | **GitHub Actions**：每日追踪器 cron 自动 commit 周报（带质量门禁）+ 每次 push 评测回归 |
| 厂商池 | 13 家模型厂商 | 三维分类（市场×产业链层×研究深度）：L2 模型层 17 家深挖 + L1/L3/L4 跟踪层，见 [厂商池](docs/vendor-pool-v2.md) |

## 快速开始

```bash
# 入库（v2 语料）→ 矩阵 → 节点式 Deep Research → 双层评测
export CORPUS_DIR=rag/corpus_v2 INDEX_PATH=rag/index_v2.json OUT_DIR=output_v2
python rag/ingest.py            # 18 文档 → chunk 索引
python rag/query.py             # 四维对比矩阵 → output_v2/matrix.md
python rag/research_graph.py    # 节点式研究循环（断点恢复+审计）→ research_report.md
python eval/eval.py             # 金标回归：Hit@1 35%→100%
python eval/faithfulness.py     # 忠实性：数字回指率/信封完整率

# 带人工审批点的运行（计划生成后暂停，编辑计划后放行）
REQUIRE_APPROVAL=1 python rag/research_graph.py
APPROVED=1 python rag/research_graph.py    # 审批放行，从断点续跑

# 赛道追踪周报（GitHub/HN 双源，Actions 每日自动运行）
python tracker/run.py && python scripts/quality_gate.py
```

## 评测结果（一条命令可复现）

**检索层**（20 条金标问答，v2 语料 68 chunk / 16 厂商回归通过）：

| 指标 | 无路由 baseline | +厂商路由器 | 维度锁定 |
|---|---|---|---|
| 厂商命中 Hit@1 | 35% | **100%** | — |
| 事实召回 Recall@3 | 70% | **100%** | 96.7% |
| 金标防腐化 | — | stable 7/7 · time-sensitive 13/13 | — |

**生成层**（v2 新增，端到端忠实性）：

| 检查项 | 结果 |
|---|---|
| 数字回指率（汇总数字 ↔ 证据原文） | **190/190 = 100%** |
| 信封完整率（事实携带四要素） | **80/80 = 100%** |

## 数据源与合规边界

- **真实数据接口**：天眼查（工商登记/融资历史）、Wind（市值估值/公司公告），
  快照日期 2026-10-23；GitHub Search / HN Algolia（赛道动态，无需 Key）
- **合规边界**：原始数据快照（`data/`）仅本地留存、不入公开仓库；
  仓库内只放研判结论 + 证据指针（来源/时点/口径），引用而非搬运
- **诚实标注**：未上市厂商（DeepSeek/月之暗面/阶跃/零一/Mistral）无审计财报，
  证据弱于上市厂商，矩阵中显式标注 ⚠️证据待补；未配 LLM Key 时为确定性规则兜底，
  报告头部注明运行模式

## 目录

```
rag/            检索与研究循环（ingest/query/research + harness/research_graph）
rag/corpus_v2/  L2 模型层 17 家语料（实时数据层 + v1 叙事层，六元组信封）
tracker/        赛道追踪器（GitHub/HN 双源，快照回溯）
eval/           金标评测 + 端到端忠实性评测
dashboard/      零依赖离线 Dashboard（build_dashboard.py 重新生成）
docs/           厂商池 v2（三维分类 70 家）
scripts/        build_corpus_v2.py（语料组装器）+ quality_gate.py（质量门禁）
.github/        Actions：daily-tracker（每日周报）+ eval-regression（push 回归）
output/         v1 产物归档 ｜ output_v2/  v2 产物（矩阵/报告/审计/断点）
```

## 路线图

- P1 检索层：TF-IDF → 混合检索（BM25+向量+rerank），厂商路由器保留为 metadata filter
- P1 数据层：跟踪层 L1/L3/L4 批量接入；scholar 论文源补技术维度
- P2 聚类层：关键词规则 → embedding 聚类；Harness 迁移至官方 LangGraph（节点函数原样保留）
- P2 调度层：公告/财报日历驱动的增量语料更新
