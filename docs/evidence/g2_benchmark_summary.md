# G2 论文数据集核验与统计分析

> 数据来源：`paper_generalization_settings.md` 中标注为 G1/G2 的 14 篇论文 PDF 逐篇核验结果。
> 可视化：`g2-benchmark-stats.html`（见附注）。

## 1. 论文清单与 A→A / A→B 分类

来源文档中严格、已支持的 G1/G2 论文级覆盖共 14 篇。下表记录每篇的 skill/prompt evolution 数据与测试数据，并区分：

- **A→A**：在 A 上 evolve，并在 A 的 held-out / test split 上测试。
- **A→B**：在 A / task A 上 evolve，在 B / task B 上测试。

| 论文 | Evolve / 训练数据 | 测试数据 | 演化→测试关系 |
|---|---|---|---|
| SkillGen | 各 benchmark 自身 construction data / base-agent 轨迹 | ALFWorld IOD/OOD；LiveCodeBench；MCPBench；Mind2Web；PubMedQA；ScienceWorld；SocialMaze；τ-Bench；ChemLLMBench | 全部 A→A |
| SkillOpt | 各 benchmark 自身 D_train rollouts + D_selection gate | 对应 benchmark held-out test | 主实验 A→A；另有 OlympiadBench→Omni-MATH A→B |
| EvoSkill | OfficeQA train split（5/10/15%）；SealQA seal-0 train split（10%） | OfficeQA held-out test；SealQA held-out test | 各自 A→A；另有 SealQA→BrowseComp A→B |
| MetaSkill-Evolve | OfficeQA、SealQA、ALFWorld 各自 train failure + validation selection | 各自 benchmark held-out test | 三个独立 A→A |
| SkillCAT | SpreadsheetBench-Verified 200 evolution samples；DocVQA validation split 前 2,700 例 | SpreadsheetBench held-out / full；WikiTQ；DocVQA 剩余 2,649 例 | Spreadsheet 和 DocVQA 分别 A→A；另有 SpreadsheetBench→WikiTQ A→B |
| Trace2Skill | SpreadsheetBench 200；DAPO 400；DocVQA 50；VRDU Registration；TSBench training decks；合成 DOCX traces | 同源 held-out 或跨任务 target | 同源 A→A；跨任务 A→B |
| SkillPyramid | ALFWorld / ScienceWorld / WebShop 各自 incoming task 流 + training split 初始库 | ALFWorld seen/unseen；ScienceWorld seen/unseen；WebShop | 三个主 benchmark 各自 A→A |
| SkillX | BFCL-v3 / AppWorld / τ²-Bench 各自 training split rollout | 对应 benchmark test split | 三个 benchmark 各自 A→A |
| WikiSkill | 5 个 benchmark 分别从空集开始，用自身 train split 演化 | 对应 benchmark test split | 5 个 cell 全部 A→A |
| SKILLRL | ALFWorld / WebShop 各自 rollout + GRPO；Search-QA 用 NQ + HotpotQA | ALFWorld；WebShop；NQ/HotpotQA；TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle | ALFWorld/WebShop A→A；NQ/HotpotQA A→A；NQ+HotpotQA→其他五个 QA A→B |
| SKILL0 | ALFWorld training split；WebShop 1000 tasks；Search-QA NQ+HotpotQA | ALFWorld；WebShop 128 fixed tasks；NQ/HotpotQA；TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle | 同 SKILLRL 结构 |
| SkillEvolver | SkillsBench 每任务自身 T_train；KernelBench 3 个任务自身 | 同任务 T_val；KernelBench 同任务 speedup | 全部 A→A |
| SkillWeaver | WebArena 5 sites 与 4 个 live websites 分别 pre-hoc exploration | 对应网站任务 | 按站点各自 A→A |
| GEPA | 六个 benchmark 各自 train split 做 prompt evolution | HotpotQA、IFBench、HoVer、PUPA、AIME-2025、LiveBench-Math 各自 test | 六个主 cell 均为 A→A |

---

## 2. A→A Benchmark 频次统计

只统计 A→A cell（同 benchmark 内 evolve → held-out test）。

| 频次 | Benchmark | 出现论文 |
|---:|---|---|
| **7** | ALFWorld | SkillGen · SkillOpt · MetaSkill-Evolve · SkillPyramid · WikiSkill · SKILLRL · SKILL0 |
| **4** | OfficeQA | SkillOpt · EvoSkill · MetaSkill-Evolve · WikiSkill |
| **4** | SpreadsheetBench | SkillOpt · SkillCAT · Trace2Skill · WikiSkill |
| **3** | SealQA | EvoSkill · MetaSkill-Evolve · WikiSkill |
| **3** | DocVQA | SkillOpt · SkillCAT · Trace2Skill |
| **3** | WebShop | SkillPyramid · SKILLRL · SKILL0 |
| **3** | HotpotQA | SKILLRL · SKILL0 · GEPA |
| **2** | LiveMath / LiveMathematicianBench | SkillOpt · WikiSkill |
| **2** | ScienceWorld | SkillGen · SkillPyramid |
| **2** | NQ | SKILLRL · SKILL0 |
| **1** | SearchQA | SkillOpt |
| **1** | LiveCodeBench | SkillGen |
| **1** | MCPBench | SkillGen |
| **1** | Mind2Web | SkillGen |
| **1** | PubMedQA | SkillGen |
| **1** | SocialMaze | SkillGen |
| **1** | τ-Bench (Retail) | SkillGen |
| **1** | ChemLLMBench | SkillGen |
| **1** | DAPO | Trace2Skill |
| **1** | TSBench | Trace2Skill |
| **1** | BFCL-v3 | SkillX |
| **1** | AppWorld | SkillX |
| **1** | τ²-Bench | SkillX |
| **1** | SkillsBench | SkillEvolver |
| **1** | KernelBench | SkillEvolver |
| **1** | WebArena | SkillWeaver |
| **1** | Online-Mind2Web | SkillWeaver |
| **1** | IFBench | GEPA |
| **1** | HoVer | GEPA |
| **1** | PUPA | GEPA |
| **1** | AIME-2025 | GEPA |
| **1** | LiveBench-Math | GEPA |

**合计：38 个 A→A 数据集–论文组合，覆盖 32 个不同 benchmark。**

### 关键观察

1. **ALFWorld 是绝对主力**：7/14 篇（50%）在 A→A 主实验中使用它。
2. **OfficeQA、SpreadsheetBench 各 4 篇**，构成第二梯队。
3. **SealQA、DocVQA、WebShop、HotpotQA 各 3 篇**，构成第三梯队。
4. **长尾极重**：32 个 benchmark 中有 22 个只被 1 篇论文使用，说明 A→A 评测面高度分散。

---

## 3. A→B 迁移组合统计

以下是 14 篇论文中所有明确报告的 A→B 任务迁移 cell（共 11 个独立迁移方向）：

| # | 源 (evolve) | 目标 (test) | 论文 |
|---:|---|---|---|
| 1 | SealQA | BrowseComp | EvoSkill |
| 2 | OlympiadBench | Omni-MATH | SkillOpt |
| 3 | SpreadsheetBench | WikiTableQuestions | SkillCAT · Trace2Skill |
| 4 | SpreadsheetBench | HiTab | Trace2Skill |
| 5 | DAPO | AIME 2026 | Trace2Skill |
| 6 | VRDU Registration | VAREX Flat | Trace2Skill |
| 7 | Synthetic DOCX | OfficeBench DOCX | Trace2Skill |
| 8 | NQ + HotpotQA | TriviaQA | SKILLRL · SKILL0 |
| 9 | NQ + HotpotQA | PopQA | SKILLRL · SKILL0 |
| 10 | NQ + HotpotQA | 2Wiki | SKILLRL · SKILL0 |
| 11 | NQ + HotpotQA | MuSiQue | SKILLRL · SKILL0 |
| 12 | NQ + HotpotQA | Bamboogle | SKILLRL · SKILL0 |

> 注：#3 的 SpreadsheetBench→WikiTableQuestions 由 SkillCAT 和 Trace2Skill 两篇独立报告，是唯一被多篇论文重复验证的 A→B cell。#8–#12 由 SKILLRL 和 SKILL0 共用同一组 source 数据但目标方法不同。

### 按功能簇分类 A→B cell

| 功能簇 | 迁移方向 | 数量 |
|---|---|---:|
| 搜索/事实性 QA | NQ+HotpotQA → TriviaQA/PopQA/2Wiki/MuSiQue/Bamboogle；SealQA → BrowseComp | 6 |
| 表格操作→表格 QA | SpreadsheetBench → WikiTQ / HiTab | 2 |
| 数学 | OlympiadBench → Omni-MATH；DAPO → AIME 2026 | 2 |
| 文档/信息抽取 | VRDU → VAREX Flat | 1 |
| 办公文档 | Synthetic DOCX → OfficeBench DOCX | 1 |

---

## 4. Benchmark 共现组合

多 benchmark 论文中经常同时出现在同一篇的 benchmark 组合（co-occurrence），按覆盖论文数排序：

| 共现组合 | 论文数 | 论文 |
|---|---:|---|
| OfficeQA + SealQA | 4 | SkillOpt · EvoSkill · MetaSkill-Evolve · WikiSkill |
| SpreadsheetBench + OfficeQA | 4 | SkillOpt · SkillCAT · Trace2Skill · WikiSkill |
| ALFWorld + WebShop | 3 | SkillPyramid · SKILLRL · SKILL0 |
| ALFWorld + OfficeQA + SealQA | 3 | SkillOpt · MetaSkill-Evolve · WikiSkill |
| SpreadsheetBench + DocVQA | 3 | SkillOpt · SkillCAT · Trace2Skill |
| NQ + HotpotQA | 2 | SKILLRL · SKILL0 |

**OfficeQA + SealQA** 是最高频共现对，4 篇论文同时使用；其次为 **SpreadsheetBench + OfficeQA**（4 篇）和 **ALFWorld + WebShop**（3 篇）。

---

## 5. 可视化

配套交互式统计图（含三个 tab 切换视图：A→A 频次条形图、A→B 迁移组合、benchmark 共现）：

- 本地路径：`/Users/yimingniu/.codex/visualizations/2026/09/08/01a0803f-a9d0-7063-810f-f4f01b0954b3/g2-benchmark-stats.html`

---

## 6. 关键注意事项与证据

### 注意事项

- 多 benchmark 并列 ≠ 同一 skill/artifact 的 A→B transfer。
- SkillGen、MetaSkill-Evolve、WikiSkill、SkillX、SkillEvolver 均未报告真正的 A→B 任务迁移实验。
- Trace2Skill 和 SkillCAT 的 OOD cell 是把 target 数据转换为 compatible task format 后再测试。
- SkillWeaver 的 "Generalization across Website" 不是 website A→website B 的 skill transfer。
- GEPA 的 IFBench 设置使用 IF-RLVR train 源，但仍是同一 instruction-following 体系内的设计性 OOD split。

### 统计口径

- 只统计 A→A 主实验 cell；A→B target 数据集不计入 A→A 频次。
- SkillPyramid 的 GAIA-Lite 是 web-mined skills 独立分析 cell，未计入。
- τ-Bench（SkillGen）与 τ²-Bench（SkillX）是不同 benchmark，分开计。
- 跨模型、跨 harness 均不计为任务泛化。

### 证据定位（节选）

| 论文 | 定位 |
|---|---|
| SkillGen | Table 1 p.7；Table 3 / Appendix C.2–C.4 pp.16–17；Figure 4 p.8 |
| SkillOpt | Table 1 pp.7–8；Table 4 p.9；Appendix C p.20 |
| EvoSkill | §3.1–3.3 pp.5–7；Table 1 p.6 |
| MetaSkill-Evolve | §4.1 pp.6–7；Table 1 p.8；Appendix F p.13 |
| SkillCAT | Experimental Setup pp.4–5；Table 1 p.5；Figure 3 p.6 |
| Trace2Skill | Table 1 p.4；Table 2 p.6；Table 3 p.6；Table 13 p.19；Appendix A pp.13–14 |
| SkillPyramid | §3.1 p.5；Table 1 p.6；Appendix A.1 pp.10–11；GAIA-Lite Table 4 p.8 |
| SkillX | §5.1 p.5；Table 1 p.6；Table 2 p.9；Appendix A.1 p.15 |
| WikiSkill | Problem Setup p.3；Table 1 p.8；Table 2 p.10；Table 6 pp.19–20 |
| SKILLRL | Table 1 p.6；Table 2 p.7；Algorithm 1 p.4；Figure 3 p.7；Appendix B.1 Table 4 p.14 |
| SKILL0 | Sec. 4.1 pp.5–6；Table 1 p.6；Table 2 p.6；Table 7 p.19 |
| SkillEvolver | §4.1 p.6；p.7；Table 1 p.8；Appendix A.3/A.6/A.8 pp.13–18 |
| SkillWeaver | §3.1–3.2 p.5；§3.4 p.6；Table 1/Table 2 p.7；Appendix B/C pp.26–29 |
| GEPA | Section 4 p.8；Table 1/Table 2 p.8；Appendix E.1 pp.23–25；Appendix E.4 p.27 |

## 7. 可复现性核验

### 7.1 核验口径

本节针对上面的 14 篇 G2 论文，核验日期为 **2026-09-09**。核验分为两层：

1. **论文声明层**：检查 PDF 首页、脚注、代码可用性声明和项目页，判断论文是否给出作者仓库。
2. **仓库现实层**：访问仓库页面/API 和 README，检查仓库是否仍公开、是否被归档/禁用，以及是否有安装依赖、运行入口、benchmark 适配、数据/skill artifact、checkpoint 或 API 配置。

“有官方仓库”只表示代码入口可被找到并访问，不表示可以无缺口地重现论文主表。难度评估针对**论文级结果复现**，而不是只运行一个 demo：

- **中等偏高**：官方仓库、安装说明和基本入口较清楚，但精确结果仍依赖外部 benchmark、LLM API 或额外环境。
- **高**：官方仓库存在，但训练/评测需要重型 GPU、复杂 agent harness、多个外部服务，或缺少论文级配置/模型产物。
- **很高**：没有可确认的作者仓库，或仓库缺少方法核心、依赖和端到端评测材料，基本需要手工重建。

### 7.2 逐篇核验结果

| 论文 | 论文/项目页是否给作者 repo | 当前仓库状态 | 可复现入口与材料 | 主要缺口 | 论文级复现难度 |
|---|---|---|---|---|---|
| **SkillGen** | 是：[yccm/SkillGen](https://github.com/yccm/SkillGen) | 公开、未归档、未禁用；Apache-2.0；主分支可访问 | `requirements.txt`；`main.py` 训练入口；`eval_skill.py` held-out 评测入口；包含若干 benchmark 数据/适配器和数据准备脚本 | 依赖 OpenRouter/OpenAI 等 hosted API；部分 benchmark 仍需外部准备；未提供论文结果对应的已生成 skill checkpoint | **中等偏高** |
| **SkillOpt** | 是：PDF 的 `aka.ms/SkillOpt` 项目页可导向 [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) | 公开、未归档；MIT；仓库活跃 | README、文档和复现指南；`skillopt-train`、`skillopt-eval`、`skillopt-sleep`；benchmark split manifest；提供部分参考 skill artifact | 多数 benchmark 需先物化 upstream 数据；OfficeQA 需要 gated access；论文级组合涉及多模型、多 benchmark 和较高 API 成本 | **中等偏高** |
| **EvoSkill** | 是：[sentient-agi/EvoSkill](https://github.com/sentient-agi/EvoSkill) | 公开、未归档；Apache-2.0；有 release，当前仍活跃 | `uv sync`/安装脚本；`evoskill init/run/eval`；支持 Claude Code、Codex、OpenCode、OpenHands、Goose、Harbor、Docker/Daytona | 论文实验依赖 Claude Code + Opus 级模型，运行可能持续数小时；论文 exact split 未完全内置；OfficeQA 等数据需额外获取 | **高** |
| **MetaSkill-Evolve** | 否；PDF 未发现作者代码声明或作者 repo | 未找到可确认的作者官方仓库；`loversky02/metaskill-evolve` 为第三方实现，不计入 | 无作者 README、依赖、训练/评测入口或官方 artifact | 两时间尺度 meta-skill、anti-cheating hook、变体生成 pipeline 和 checkpoint 均未发布；需自行搭建 Harbor/Claude Code 等环境 | **很高** |
| **SkillCAT** | 否；PDF 未发现作者 repo 或代码可用性声明 | 未找到可确认的作者官方仓库 | 只能依据论文中的 ReAct、SpreadsheetBench、WikiTableQuestions、DocVQA 等实验描述重建 | 无官方代码、依赖、入口、数据处理脚本和论文级 skill artifact；需自行重建 A→A/A→B 评测管线 | **很高** |
| **Trace2Skill** | 是：[Qwen-Applications/Trace2Skill](https://github.com/Qwen-Applications/Trace2Skill) | 公开、未归档；主分支可访问；仓库存在性已确认。一次 Git tree/API 探针返回异常，故不把它视为完全稳定的代码交付 | README 提供安装、OpenAI-compatible API 配置、SpreadsheetBench/兼容评测/轨迹分析/技能演化入口；含部分数据目录和 `released_skills/` | 未见标准 `requirements.txt`/环境文件；无模型 checkpoint；README 也明确长 ReAct 管线难以 exact 复现；材料明显偏向 Spreadsheet setting | **高** |
| **SkillPyramid** | 否；PDF 未发现作者 repo 或代码声明 | 未找到可确认的作者官方仓库 | 论文附录提供 ALFWorld、ScienceWorld、WebShop 的 prompt 和实现细节；实验依赖 API calls | 层级技能巩固/演化核心需自行实现；多个交互式环境和大量 API 调用均需重新配置 | **很高** |
| **SkillX** | 是：[zjunlp/SkillX](https://github.com/zjunlp/SkillX) | 公开、未归档；MIT；主分支可访问 | README 说明 AppWorld、BFCL-v3、τ²-Bench；`pipeline.py` 提供技能抽取 CLI；有轨迹 JSONL 格式和部分 AppWorld skill DB | README 没有可用的安装/Quick Start；无依赖文件；未完整覆盖论文三个 benchmark；端到端评测、模型和 API 配置需自行补齐 | **很高** |
| **WikiSkill** | 否；PDF 全文未发现作者 GitHub/repo 链接 | 未找到可确认的作者官方仓库 | 无作者代码入口；只能按论文及附录重建 | 无 README、依赖、入口、数据脚本、skill artifact 或 checkpoint；环境与评测实现均需自行恢复 | **很高** |
| **SKILLRL** | 是：[aiming-lab/SkillRL](https://github.com/aiming-lab/SkillRL) | 公开、未归档、未禁用；MIT；主分支可访问 | 安装说明；ALFWorld/WebShop/Search 环境配置；SFT/RL 脚本；SkillBank 格式；HF checkpoint 和 SFT 数据链接 | vLLM/flash-attn 与 verl 依赖较重；README 记载训练需要多 GPU；Search 依赖额外检索环境，WebShop 环境仍需单独准备 | **高** |
| **SKILL0** | 是：[ZJU-REAL/SkillZero](https://github.com/ZJU-REAL/SkillZero) | 公开、未归档；Apache-2.0；主分支可访问 | conda 环境和依赖；ALFWorld/Search 数据与预处理；retriever 服务；3B/7B 训练脚本；`skills/` 中有技能文件和 mapping | 未提供官方 checkpoint；训练需多 GPU；Search 需要额外 retriever/索引；WebShop 的完整复现入口不清楚 | **高** |
| **SkillEvolver** | 否；PDF 未发现作者 SkillEvolver repo | 未找到可确认的作者官方仓库；论文引用的 Claude Code、Harbor、SkillsBench、KernelBench 是外部依赖 | 论文附录有 meta-skill 形式、伪代码和实验配置，但没有作者实现 | meta-skill 文件、训练变体生成、anti-cheating hook、实验脚本和结果数据库均未作为完整复现包发布 | **很高** |
| **SkillWeaver** | 是：[OSU-NLP-Group/SkillWeaver](https://github.com/OSU-NLP-Group/SkillWeaver) | 公开、未归档；主分支可访问；Python 3.10/Playwright 说明完整 | `requirements.txt`；`attempt_task`、`explore`、`evaluate_benchmark` 入口；prompt 模板；部分 skill library；WebArena Docker 编排说明 | 无预训练 checkpoint；需自行启动 shopping、shopping_admin、reddit、gitlab、map 等 WebArena 容器；探索过程依赖 LLM，结果不完全确定 | **中等偏高** |
| **GEPA** | 是：[gepa-ai/gepa](https://github.com/gepa-ai/gepa) | 公开、未归档；MIT；主分支可访问，仓库活跃 | `pip install gepa`；AIME Quick Start；`optimize`/`optimize_anything`；DSPy 与多个 adapter；`pyproject.toml` 依赖清楚 | 当前仓库重点是通用框架和 AIME 示例，不是论文六 benchmark 的一键复现包；HotpotQA、IFBench、HoVer、PUPA、LiveBench-Math 和 GRPO 对比需自行接入 | **中等偏高** |

### 7.3 汇总统计

#### 官方代码可得性

| 类别 | 篇数 | 占 14 篇 |
|---|---:|---:|
| 有可确认的作者官方公开仓库 | **9** | **64.3%** |
| 未找到可确认的作者官方仓库 | **5** | **35.7%** |

有官方仓库的 9 篇为：SkillGen、SkillOpt、EvoSkill、Trace2Skill、SkillX、SKILLRL、SKILL0、SkillWeaver、GEPA。未找到作者官方仓库的 5 篇为：MetaSkill-Evolve、SkillCAT、SkillPyramid、WikiSkill、SkillEvolver。

仓库存在性检查结果为：上述 9 个仓库均可访问，且本次核验中未发现已归档或被禁用的官方仓库。需要特别注意 Trace2Skill：仓库本身存在，但在一次 GitHub tree/API 探针中出现空树/异常响应，因此其“存在”与“代码交付稳定性”分开记录。

#### 按复现难度

| 论文级复现难度 | 篇数 | 论文 |
|---|---:|---|
| 中等偏高 | **4** | SkillGen、SkillOpt、SkillWeaver、GEPA |
| 高 | **4** | EvoSkill、Trace2Skill、SKILLRL、SKILL0 |
| 很高 | **6** | MetaSkill-Evolve、SkillCAT、SkillPyramid、SkillX、WikiSkill、SkillEvolver |

本次没有将任何论文评为“低难度”。即使代码入口完整，多数论文仍依赖商业/托管 LLM API、交互式 benchmark、外部检索服务、容器化网站环境或较高 GPU/rollout 成本。

#### 主要复现阻塞点

| 阻塞点 | 影响 |
|---|---|
| 作者仓库缺失 | 5 篇论文需要手工重建方法和评测管线，无法直接核对实现细节 |
| 论文级数据/划分不完整 | 多篇论文需要单独申请或下载 gated benchmark，或自行物化 upstream 数据 |
| 模型/API 成本 | SkillGen、EvoSkill、SkillOpt、SkillWeaver、GEPA 等仍需外部 LLM/API；EvoSkill 的论文配置尤其昂贵 |
| 交互式环境 | WebArena、ALFWorld、WebShop、Search 等环境需要额外安装、容器或检索服务 |
| 训练资源 | SKILLRL、SKILL0 等 RL/SFT 路径涉及 vLLM、flash-attn、verl 和多 GPU |
| 结果非确定性 | skill discovery/evolution 依赖 rollout 和 LLM 反馈，即便代码相同也可能出现结果波动 |
| checkpoint/artifact 不完整 | 有些仓库提供示例 skill 或部分 artifact，但不提供论文主表对应的完整 checkpoint、轨迹和中间产物 |

### 7.4 总体结论

这 14 篇 G2 论文的**代码可得性尚可，但论文级可复现性整体偏弱**：

1. 约三分之二论文有公开作者仓库，但其中只有部分仓库同时提供了清晰的安装、数据、训练和评测闭环。
2. 公开仓库中，SkillOpt、SkillRL、SkillWeaver、SkillGen、GEPA 的“框架或 demo 级复现”相对最容易启动；这不等价于能重现论文主表数值。
3. EvoSkill、Trace2Skill、SKILL0 需要较重的模型、环境或训练配置；SkillX 虽有仓库，但当前公开材料不足以支撑端到端论文结果复现。
4. MetaSkill-Evolve、SkillCAT、SkillPyramid、WikiSkill、SkillEvolver 没有可确认的作者实现，复现工作基本属于从论文描述重新工程化。
5. 因此，建议将“是否有 repo”和“是否能复现论文结果”作为两个独立指标：前者为 **9/14**，后者不应按 9/14 直接估计，实际需要逐篇补齐数据、模型、环境和运行预算。
