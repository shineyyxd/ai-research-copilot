# AI 投研 Copilot（ai-research-copilot）

> 把「券商实习期间手工做的投研工作」工程化为一个可复跑的 Deep Research Agent：
> **四维拆解 → 检索 → 自检 → 补检 → 汇总**，每条结论都可溯源到证据 chunk。
> 纯 Python 标准库实现，零第三方依赖、无需 API Key 即可跑通全流程；配置 `DEEPSEEK_API_KEY` 后自动升级为 LLM 汇总。

## 它解决什么问题

投研中的竞品研究有两个老大难：**大模型会幻觉**、**手工追赛道太费时**。本项目用两个机制对抗：

1. **证据链机制**：13 家国内外头部大模型厂商语料库，每条证据标注来源与五档可信度（审计财报 → 券商研报 → 工商/榜单 → 媒体转述 → 前瞻估算），矩阵每一格都可回指具体文档 chunk（来源文件 + 章节 + 相关度分数）。
2. **评测驱动迭代**：自建 20 条人工标注金标问答集，所有指标一条命令可复现（见下方评测结果）。

## 模块总览

| 模块 | 路径 | 作用 |
|---|---|---|
| 竞品研究 RAG | `rag/` | 语料入库 → 四维（技术路线/产品定位/商业化策略/生态壁垒）检索 → 生成对比矩阵 |
| Deep Research 循环 | `rag/research.py` | 移植 dzhng/deep-research 的 breadth/depth 范式：拆解 → 检索 → 自检 → 补检 → 汇总 |
| 赛道追踪器 | `tracker/` | 定时抓取 GitHub / Hacker News 双源动态，去重、聚类为 6 大主题周报 |
| 评测集 | `eval/` | 20 条金标问答驱动检索质量迭代，指标可复跑 |
| 离线 Dashboard | `dashboard/` | 零依赖单文件 HTML，矩阵/周报/梯队研判一屏总览 |
| 产出样例 | `output/` | 真实运行产物：对比矩阵、Deep Research 报告、梯队研判、周报、评测报告 |

## 快速开始

```bash
# 模块 A：竞品研究 RAG
python rag/ingest.py        # 语料入库（.md/.txt/.pdf 丢进 rag/corpus/ 即可）
python rag/query.py         # 四维检索 + 生成矩阵 → output/matrix.md

# 模块 A+：Deep Research 多轮研究循环
python rag/research.py                              # 全矩阵研究（52 子查询）
python rag/research.py "对比三家厂商的商业化策略"      # 单问题模式

# 模块 B：Agent 赛道追踪周报
env -u http_proxy -u https_proxy python tracker/run.py   # → output/digest_YYYY-MM-DD.md

# 评测：金标集复跑
python eval/eval.py         # → output/eval_report.md

# Dashboard：重新生成离线看板
python dashboard/build_dashboard.py   # → dashboard/index.html（双击即开，零依赖）
```

## 评测结果（评测驱动迭代的真实记录）

金标集 20 条人工标注问答（事实均已验证存在于语料），Top-K=3：

| 指标 | 无路由 baseline | +厂商路由器 | 维度锁定（矩阵组格） |
|---|---|---|---|
| 厂商命中 Hit@1 | 35% | **100%** | —（厂商已知） |
| 厂商命中 Hit@3 | 60% | **100%** | — |
| 维度章节命中 Hit@1 | 35% | **100%** | 100%（确定性锁） |
| 事实召回 Recall@3 | 70% | **100%** | 97% |
| 全事实命中条目 | 12/20 | **20/20** | 19/20 |

**迭代根因**：初版评测发现厂商名在跨厂商语料中交叉出现（如 minimax.md 含「增速高于智谱」），TF-IDF 把厂商名当普通词稀释，Hit@1 仅 35%。加入确定性厂商路由器（别名表 → 先路由再排序）后修复——用规则修检索，而不是靠换更大的模型。

## 技术要点

- **检索**：TF-IDF + 余弦相似度，中文字符 bigram / 英文单词混合分词（自实现，无依赖）；确定性厂商路由器 + 维度章节锁
- **Deep Research 循环**：研究问题按「四维 × 厂商」展开为 52 个子查询；每格证据做充分性检查（top-1 相关度阈值 + 证据覆盖数），不充分的格子自动生成扩展查询补检，最多加深 2 轮；输出带完整迭代日志（每格的查询演化、每轮命中与判定原因）
- **汇总**：有 `DEEPSEEK_API_KEY` → deepseek-chat 按 JSON Schema 输出（带引用约束，禁止编造证据外信息）；无 Key → 抽取式摘要兜底，报告头部诚实标注运行模式
- **赛道追踪**：GitHub Search API（近 14 天新建 agent/LLM 仓库 × star 排序）+ HN Algolia API（近 7 天 >40 分热帖），均为真实 API 无需 Key；URL 归一化去重、与上一期快照对比标记 🆕 与 star 增量、关键词规则聚类为 6 大主题；历史快照存 `tracker/history/` 支持回溯
- **产出**：单轮 80+ 条动态聚类为 6 大主题周报；52 格研判结论 100% 可溯源；零依赖离线 Dashboard 一屏总览

## 诚实标注

- 当前语料为公开信息整理的演示文档（13 家厂商），替换为真实财报/发布会实录即可用于实战
- 未配置 `DEEPSEEK_API_KEY` 时为规则驱动的确定性兜底，报告头部会注明模式
- 聚类为关键词规则分桶，非语义聚类（见下方路线图）

## 路线图

1. LLM 层：配 DeepSeek Key → 矩阵总结/周报导语质量升级
2. 检索层：TF-IDF → embedding 向量（API 或本地模型）+ 混合检索
3. 聚类层：关键词规则 → embedding 聚类（HDBSCAN/K-means）
4. 调度层：接系统级定时任务实现每日自动抓取 + 周报推送
