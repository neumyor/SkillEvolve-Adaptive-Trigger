# Terminal-Bench 上无训练的强到弱经验迁移：相关工作调研

调研日期：2026-10-08。研究目标：强模型在开发阶段产生或提炼任务经验，经验以技能、记忆、工具或执行框架保存；弱模型参数保持不变，在新任务上利用这些产物提升完成率。重点关注测试时教师退出的设置。

## 结论

**已有高度类似的工作，而且已经有 Terminal-Bench 上的直接先例。** 最应优先阅读的是 AgentBrew、SKILL-KD、Agent Memory Distillation (AMD)、SkillWeaver、AgentDistill 和 SPARK。

- AgentBrew 与“离线强教师、冻结弱学生、测试时教师退出、外部经验迁移”的目标几乎一致，且包含 Terminal-Bench 2.0 实验。
- SKILL-KD 与“教师和学生的轨迹对比，提炼学生可执行的文本技能，再验证和积累”几乎一致。
- AMD 与“强教师先跑成功经验，再将分层经验交给小模型”几乎一致，学生确实包括 4B–8B 模型。
- SkillWeaver 和 AgentDistill 表明，迁移载体可以是可执行 API / 工具模块，不局限于自然语言技能。
- SPARK 在真实 Docker / shell 交互中生成并验证技能，再交给便宜的学生；其主评测是 SkillsBench，不是 Terminal-Bench。

因此，“让强模型生成经验，弱模型通过 skill 使用，不训练参数”这一总体流程已有先例。新研究应明确超出这些先例的机制、环境难度、学生规模或评测要求。仅更换到 Terminal-Bench 也不足以建立新意。

这里的“提升能力”指冻结模型组成的 Agent 系统在外部产物辅助下提升表现，不意味着模型权重内化了该能力。

## 调研方法与证据等级

1. 使用 arXiv API 扩展检索 Terminal-Bench 与 skill / experience / memory、teacher–student、training-free distillation、procedural memory 等组合，并追踪相关论文的引用。
2. 查询页共返回 351 条去重候选，包含大量关键词误命中。这是检索池大小，不是相关论文数量；宽查询的所有返回页也并未全部获取。
3. 获取 22 份重点论文的在线原文，对其相关方法、实验设置、表格和附录进行核对；对照工作区现有 28 篇论文的提取文本。没有复现实验，也没有完成所有仓库的代码审计。
4. 证据标记：**F** 为核对过重点原文；**L** 为本地原文核对，并在线确认题名/版本/摘要；**A** 为摘要级线索，结论仅限摘要明确表述。
5. 所有数值均是论文作者报告，不是本工作区的新实验结果。不同论文的任务划分、模型、harness、反馈和预算不同，不能横向按分数排名。

在线检索记录、版本元数据及重点原文缓存保存在 `tmp/terminal_skill_literature/`。本地旧综述仅用来发现候选，不作为独立证明；SKILL-KD 使用在线 v3，而非工作区旧 v2 审计记录。

## 一、与设想高度相似的工作

### 1. AgentBrew：最直接的 Terminal-Bench 先例

- 论文：[AgentBrew: Lifelong Knowledge Brewing from Strong Teachers to Weak LLM Agents](https://arxiv.org/abs/2607.16851v1)，2026-07-18，**F**。
- 核心流程：冻结学生尝试开发任务；失败后强教师读取任务和失败轨迹，生成适配学生能力的结构化笔记；Ralph Loop 重跑学生，只有环境验证成功的笔记才进入持久记忆；最终冻结记忆，测试时教师退出。
- 笔记明确要求具体触发条件、操作顺序、能力缺口与检查项，避免教师省略学生无法补全的推理步骤。经验不是单纯的成功轨迹摘要。
- 与用户设想的差别：教师主要分析学生失败并生成纠正指导，独立教师成功 rollout 不是所有开发任务的必需环节。
- 主实验：DeepSeek-Chat-v3.1 教师、Qwen3-14B 学生，覆盖 MATH/GSM8K、MBPP/MBPP+、AppWorld。
- **Terminal-Bench 2.0，§3.8 / Figure 5**：89 题，分层 25/64 开发/测试划分；Claude Code harness；DeepSeek-v4-pro 教师、DeepSeek-v4-flash 学生；测试时学生独立运行。
- 报告结果：裸学生 45.3%，教师 50.0%，学生+AgentBrew 51.6%。按 64 题还原，分别约为 29、32、33 题通过：相对裸学生净增约 4 题，相对教师点估计仅多约 1 题。
- 成本：作者报告服务成本 $0.04/题，教师 $0.06/题，另有约 $116 的一次性经验构建成本。按固定每题节省 $0.02 粗算，约 5,800 次部署任务才覆盖该构建成本；这是基于报告价格的条件计算，不含价格变化与其他成本。
- **边界**：不能据这组小规模点估计确认稳定超过教师；Terminal-Bench 案例的学生是较弱 API 模型，不等于已证明 4B/7B 本地模型在同环境有效。需要原始逐题配对证据与重复运行才能审计恢复/回归数量。

### 2. SKILL-KD：轨迹对比与学生验证，几乎对应方法核心

- 论文：[SKILL-KD: Contrastive Skill Distillation for LLM Agents](https://arxiv.org/abs/2607.28048v3)，首次 2026-07-30，核对版本更新于 2026-10-05，**F**。
- 流程：学生失败轨迹 + 同任务教师轨迹 → 可行动的文本技能补丁 → 学生重跑 → 失败时继续修改 → 接受有效补丁。
- 维护 trace-linked 编辑历史，通过 Drift-Aware Skill Consolidation 控制重复、局部过拟合及技能漂移。教师失败轨迹也可以包含有效的局部经验，教师不被当作 oracle。
- 学生参数冻结；测试时读取最终技能文件。每个 benchmark 单独构建技能库，不能解释成一个统一库跨所有任务域泛化。
- 教师/学生：Qwen3.7-plus → Qwen3.5-4B；ChatGPT-5.5 → Qwen3.6-35B-A3B。
- 评测：SearchQA、SpreadsheetBench、DocVQA、LiveMath、ALFWorld；原文没有 Terminal-Bench 主实验。
- **Table 1**：4B 学生五域宏平均 43.5% → 66.8%；其中 ALFWorld 30.6% → 86.6%。宏平均混合异质任务，只用于论文内对应设置。
- 数据隔离：有官方划分时保留；其他数据固定 seed 划成 2:1:7；技能仅使用开发训练部分构建，最终测试独立。术语“training partition”不表示梯度训练。
- **边界**：已经研究教师–学生差异、学生侧验证与漂移控制；再提出“对比教师成功和学生失败”本身不足以成为新机制。其固定整体技能文件设置，也未解决 Terminal-Bench 大规模技能检索与组合执行问题。

### 3. AMD：教师经验帮助真实的小模型

- 论文：[Agent Memory Distillation: Empowering Small LLM Agents with Hierarchical Teacher Memory](https://arxiv.org/abs/2608.07169v1)，2026-08-07，**F**。
- GPT-5-mini 教师先生成成功轨迹，将经验构成 Workflow、Subtask、Function 三类记忆。
- Workflow 与 Subtask 记忆在任务开始时注入；Function 记忆在工具错误出现时检索。学生不做参数更新。
- 学生包括 Qwen3-4B、Qwen3-8B、Gemma4-E4B、Llama3.1-8B；评测 AppWorld、BFCL V3、ToolSandbox。
- 作者指出，直接传递平面教师记忆收益不稳定；中间粒度的 Subtask 示例贡献最大，教师能力与学生兼容性都影响效果。
- **重要评测区分**：主表是在同 benchmark 构建并使用记忆；严格的任务隔离证据在附录 B.3，且只针对 Qwen3-4B。包括 7:3 memory-build/test split 和检索时排除本题来源记忆两种协议。
- **Table 6，严格 cross-split**：AppWorld 16.07% → 41.07%；BFCL V3 16.13% → 30.65%；ToolSandbox 16.67% → 22.92%。不把主表的较大增益自动当作全模型留出结果。
- **边界**：无 Terminal-Bench 实验；结构化工具 schema 中有效，不自动保证能迁移到开放 shell、环境修复与复杂安装任务。

### 4. SkillWeaver：把强模型经验转成可执行 API

- 论文：[SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills](https://arxiv.org/abs/2504.07079v1)，2025-04-09，**F**。
- GPT-4o 在每个网站主动探索、练习、合成与调试 Python/Playwright API；积累带前提条件、说明和使用历史的技能库。
- 同一批 API 可以给 GPT-4o-mini 使用，弱模型不训练参数。
- 主环境为 WebArena 与四个真实网站的 Online-Mind2Web 子集。
- **Table 1**：GPT-4o-mini 的网站域宏平均成功率 9.2% → 14.1%。摘要/正文还有其他相对增幅表述，因此这里只使用可直接定位的表格绝对值。
- **边界**：每个网站分别探索构建 API；不是一个网站的 API 自动迁移到未知网站。提升可能来自把长操作序列封装为确定性程序，这也是合法且值得研究的迁移机制。

### 5. AgentDistill：无需训练的教师工具模块复用

- 论文：[AgentDistill: Training-Free Agent Distillation with Generalizable MCP Boxes](https://arxiv.org/abs/2506.14728v1)，2025-06-17，**F**。
- 教师自主生成可复用任务求解模块，组织成 MCP-Box；小模型学生直接复用模块进行任务解决。
- 评测主要是生物医学和数学任务，不是 Terminal-Bench。
- **边界**：迁移对象以工具/程序模块为主；“教师生成工具”与“弱模型吸收自然语言推理策略”应分别测量。

### 6. SPARK：真实终端探索后生成学生技能

- 论文：[Evidence Over Plans: Online Trajectory Verification for Skill Distillation](https://arxiv.org/abs/2605.09192v2)，首次 2026-05-09，**F**。
- 教师在 Docker 中实际运行 shell、读取失败反馈、更新探索备忘录；成功轨迹蒸馏成 `SKILL.md`，交给便宜的学生。
- 提出 Posterior Distillation Index，区分技能内容是环境证据还是未验证的计划；强调技能应在交互后形成。
- 主任务来自 SkillsBench 86 题，另合成任务变体检查跨实例复用。教师示例包括 Claude Opus 4.6，学生示例包括 GPT-5.4 mini。
- **边界**：主任务技能生成和使用与同任务密切相关；需把同题辅助与新构造变体迁移分开理解。论文没有 Terminal-Bench 主结果，不宜凭“使用 shell”改写成该 benchmark 证据。

### 7. AI4AI at Test-Time：强模型构建弱模型执行框架

- 论文：[AI4AI at Test-Time: Strong-to-Weak Capability Transfer via Harnesses](https://arxiv.org/abs/2608.12307v1)，2026-08-12，**F**。
- 强 builder 在小开发集上构建并修订 routing、prompt、确定性求解程序与输出检查，增强冻结弱 target。
- 四个 Theory-of-Mind benchmark；主要效果来自结构外化、确定性代码及格式控制。
- **边界**：更接近自动系统设计，而不是必须先跑教师经验再提炼；任务结构相对规整，无 Terminal-Bench 实验。文中 5% validation 与 full test 的措辞需在复现时进一步明确隔离口径。

### 8. 更早与相邻的直接先例

| 工作 | 迁移方式 | 环境与边界 | 证据 |
|---|---|---|---|
| [Concept Distillation](https://arxiv.org/abs/2408.09365v2)，2024 | 收集弱模型错误，强模型归纳规则，用验证集筛选后加入提示 | NL2Code / 数学；早期 strong-to-weak 文本规则先例，非长程交互 Agent | F |
| [SkillX](https://arxiv.org/abs/2604.04804v2)，2026 | GLM-4.6 轨迹 → planning / functional / atomic 分层技能 → 弱 Agent | AppWorld / BFCL-v3 / τ²-Bench；与先跑教师经验的设想非常接近 | L |
| [TED](https://arxiv.org/abs/2603.26778v1)，2026 | 教师对比学生推理、自己的解法及正确答案，生成并压缩上下文经验 | MathVision / VisualPuzzles；冻结学生，但使用正确答案，非开放 shell | F |
| [ASDA](https://arxiv.org/abs/2603.16112v2)，2026 | 教师诊断学生错误，生成流程、代码模板和例题技能 | FAMMA 金融推理；冻结模型、领域任务 | F |
| [Reason Wide, Not Deep](https://arxiv.org/abs/2608.07885v1)，2026 | 分析既有轨迹库，编译技能给非推理模式使用 | ALFWorld / τ² / 表格；不要求教师成功轨迹，不能等同于不同尺寸模型迁移 | F |
| [P2Skill](https://arxiv.org/abs/2608.14094v1)，2026 | 云端大模型迭代修订本地 SLM 的隐私路由技能 | 仍包含云端协作；不等于测试阶段强模型完全退出 | F |

## 二、Terminal-Bench 上应对照的工作

| 工作 | 与我们的关系 | 原文支持与边界 | 证据 |
|---|---|---|---|
| [AgentBrew](https://arxiv.org/abs/2607.16851v1) | 最接近的直接基线 | 25 题开发、64 题测试；弱学生+冻结经验，教师退出；较弱 API 模型而非 4B 学生案例 | F |
| [SkillsVote](https://arxiv.org/abs/2605.18401v2) | 历史终端轨迹生成库，在新终端任务上离线复用 | TB-Pro 历史库 → TB2；GPT-5.4 mini +5.8 pp，指标为 avg@5 Accuracy，不能当作 best-of-5 pass@5；推荐阶段的模型配置须单独核查 | F |
| [When Self-Evolution Backfires / VaG](https://arxiv.org/abs/2608.05810v2) | 技能安全准入、积累与冻结库跨模型迁移 | TB2 50/14/25 distill/gate/test；Hy3 构建技能，跨四模型无重演化；研究不是专门的 student-gap 蒸馏 | F |
| [Agentic Harness Engineering / AHE](https://arxiv.org/abs/2604.25850v4) | GPT-5.4 演化框架，再换其他模型使用 | 同时改工具、中间层、记忆；原文明确在全 89 题上演化，TB2 结果不构成独立任务留出；SWE-bench 转移另算 | F |
| [RSI-Router](https://arxiv.org/abs/2609.34712v1) | 大小模型轨迹对比，生成模型特定技能 | DeepSeek-V4.1-Flash 与 Qwen3.5-9B 路由；测试时大模型继续承担部分步骤，属于协作系统 | F |
| [DENSE](https://arxiv.org/abs/2609.21423v4) | 将轨迹变成结构化子任务反馈 | TB2.1 REFIT 检查同一任务的反馈辅助重试；不是持久技能的未见任务迁移 | F |
| [Scaling Test-Time Compute for Agentic Coding](https://arxiv.org/abs/2604.16529v1) | 轨迹摘要、并行选择与后续重试 | TB2 / SWE-bench；可作为额外推理预算对照，不是离线强到弱迁移 | A |
| [AutoSaddler](https://arxiv.org/abs/2608.23041v1) | 失败轨迹驱动离线框架修改与验证 | TB2、GAIA2、SWE-bench Pro；具体教师/学生及划分仍需原文复核 | A |
| [DarwinX](https://arxiv.org/abs/2608.07545v1) | 冻结模型下搜索和选择执行框架，含教师证据 | TB2.1 / TerminalWorld / WebArena；摘要的跨模型与跨 benchmark 主张还需逐实验核验 | A |
| [FreeEvolve](https://arxiv.org/abs/2610.09197v1) | 演化优化过程本身，生成可迁移的 meta-skill | 2026-10-06 新论文，含 TB2.1；目标偏如何优化 Agent，不能自动当作教师独立探索后教小模型 | F |
| [SkillFlow](https://arxiv.org/abs/2504.06188v3) | 技能检索基线及负面证据 | v3 摘要报告 TB 上检索使用率高但没有性能提升，提示语料覆盖和可执行资源质量的重要性 | A |
| [How Well Do Agentic Skills Work in the Wild](https://arxiv.org/abs/2604.04323v1) | 大库检索、查询特定技能修订 | TB2 补充实验；不是教师经验采集→学生迁移的完整链条 | A |

### 三条重要的证据限制

**AHE 的模型迁移与任务迁移要分开。** 原文 §4.1 明确在完整 89 道 TB2 题上驱动演化，并在该题集上换模型评测。可以支持框架跨模型复用，不能直接支持对从未用于优化的新 TB2 任务泛化。其 SWE-bench 结果属于另一迁移方向。

**SkillsVote 的离线终端迁移值得对照。** §4.2 / Table 1 报告历史 TB-Pro 库帮助 GPT-5.4 mini 约 +5.8 pp。但它不以强教师到极小学生的能力缺口为中心，而且推荐器成本、模型，以及历史/目标任务近重复仍需代码与数据审计。

**VaG 的数据隔离比“全题集上反复优化”更贴近我们的需求。** §Experiments 区分 Event=50、Holdout=14、Test=25，最终 Test 不参与蒸馏与准入筛选。摘要的 72% 和不同表格中 Event/Test 数字应逐项区分，本报告不将这些数字合并排名。

## 三、相邻路线与需要排除的工作

### 可借鉴的经验学习基础

| 工作 | 能借鉴什么 | 与当前目标的区别 | 证据 |
|---|---|---|---|
| [ExpeL](https://arxiv.org/abs/2308.10144v3) | 从任务经验中提炼自然语言 insight，再召回 | 重点是经验学习，不是专门为强教师到弱学生设计 | A |
| [Agent Workflow Memory](https://arxiv.org/abs/2409.07429v1) | 将轨迹抽象为可复用 workflow | 重点是网页工作流与记忆复用 | A |
| [ReasoningBank](https://arxiv.org/abs/2509.25140v2) | 成功/失败经验、检索、记忆与 test-time scaling | 原方法重点是 Agent 自我演化；可改为教师经验源基线 | A |
| [ACE](https://arxiv.org/abs/2510.04618v3) | 将上下文作为外部状态，持续增量维护 playbook | 重点是上下文工程，不要求强弱模型能力不对称 | A |
| [Trace2Skill](https://arxiv.org/abs/2603.25158v5) | 批量轨迹归纳成技能目录与 SOP，跨模型/任务测试 | 并非专门针对学生失败的缺口；跨模型包含弱到强方向，不能统称 strong-to-weak | L |
| [SkillOpt](https://arxiv.org/abs/2605.23904v2) | 文本技能的有界编辑与验证选择，冻结模型 | 是外部技能优化器；强优化器存在不代表源经验全来自强教师 | L |
| [CoEvoSkills](https://arxiv.org/abs/2604.01687v3) | 多文件技能包 + 验证器共同改进，跨模型复用 | 主环境 SkillsBench；需要区分同任务包制作与新任务技能迁移 | L |
| [WikiSkill](https://arxiv.org/abs/2608.27454v1) | 原始轨迹→持久 wiki→技能，跨模型部署 | 经验基础设施与技能合成共同起作用；无 TB 主结果 | L |
| [AdaSkill](https://arxiv.org/abs/2604.01608v5) | 多 Agent 工作流压成单 Agent 技能；区分代码资源与流程指导 | 结构化数据科学，来源是复合系统，不专门是更大模型 | F |

### 名称相似但不满足“不训练”要求

- [CODESKILL](https://arxiv.org/abs/2605.25430v2)，**F**：下游 coding agent 冻结，但技能管理器经过 SFT 和 GRPO/RL。符合“不训练学生”，不符合“整个方法都不做训练”。其 prompt-based 管理器变体仍可作为对照。
- [SKILLRL](https://arxiv.org/abs/2602.08234v1)、[SKILL0](https://arxiv.org/abs/2604.02268v2)，本地原文：包含 policy/参数更新或技能内化。
- [Terminal-World](https://arxiv.org/abs/2605.20876v1)、[SkillSynth](https://arxiv.org/abs/2604.25727v1)、[Meta-Task](https://arxiv.org/abs/2607.27929v1)，**A**：技能用于构建环境与教师轨迹，最终训练 terminal 模型。可借鉴开发任务生成，不是完整的无训练迁移方法。
- [Socratic-SWE](https://arxiv.org/abs/2606.07412v1)，**A**：轨迹→技能→生成训练任务→更新 solver。
- [Sample-Efficient Learning from Agent Experience](https://arxiv.org/abs/2607.21051v1)，**A**：Experience Distillation 把上下文收益内化到权重，名字相似但更新载体不同。
- [APEx](https://arxiv.org/abs/2609.02253v1)，**A**：采用交替 GRPO 与测试时 RL，不能当作无参数更新方案。

### 评测反证必须纳入

[Rethinking the Evaluation of Harness Evolution for Agents](https://arxiv.org/abs/2607.12227v4)，2026-10-05 更新，**F**：作者在 TB2.1 比较匹配反馈/预算的搜索、重试与框架演化，并检查任务留出；报告框架演化未优于简单 test-time scaling、泛化有限。这是该研究方向的反证，不能只引用提出方法时的增益数字。它不证明所有无训练技能迁移无效，说明提升归因需要受控实验。

## 四、对我们选题的影响

### 已被明确覆盖的想法

- 强模型生成规则，弱模型通过提示使用：Concept Distillation / TED / ASDA。
- 强教师经验→冻结小学生的分层记忆：AMD。
- 面向弱学生的指导生成，并重跑学生验证：AgentBrew / SKILL-KD。
- 强模型探索→可执行技能 API→弱模型：SkillWeaver / AgentDistill / SPARK。
- 在 Terminal-Bench 上冻结外部记忆帮助较弱模型：AgentBrew；历史终端技能迁移：SkillsVote。
- 强模型构建框架，部署给弱模型：AI4AI / AHE 跨模型设置。

这些部分可以作为方法组件或基线。它们各自已存在，不宜单独作为“首次”的主张。

### 值得收窄和验证的研究问题

1. **非常小的模型在复杂终端任务上的可教性。** AgentBrew 的 TB 案例不是 4B/7B 本地学生，AMD 的小模型结果不是开放 shell。可以测 4B–14B 冻结模型在严格留出终端任务上的教师经验收益，但这是待验证的切入点，不是已经证明为空白。
2. **经验载体与能力缺口的匹配。** 同一批教师轨迹分别变成文本规则、子任务示例、执行脚本、诊断决策树；比较弱学生在哪些失败类别需要哪种支持。已有文献分别覆盖这些载体，贡献应落在统一受控比较或新的选择机制。
3. **源任务族到未见终端任务族的迁移。** 不只换路径和数字，还隔离模板、仓库、依赖模式、任务族；考察环境修复、构建与调试策略能否跨任务复用。现有跨数据集和跨模型结果不足以自动证明该级别泛化。
4. **有限教师探索预算下的经验选择。** 教师应该优先解决学生最缺的哪类问题？是成功轨迹、失败轨迹，还是教师–学生对比最有价值？已有自适应采样/演化论文需继续对照，不能把主动选择本身视为全新想法。
5. **可教范围与失败边界。** 区分知识缺失、程序性操作缺失、长程状态维护、实例特定推理不足、环境故障。技能可能帮助前几类，却不能替代每次任务所需的深推理；如实报告不能救回的任务。

### 推荐定位

**面向冻结小型 Terminal Agent 的、经学生执行验证的教师经验编译：研究经验载体如何匹配能力缺口，并在任务族留出与总成本约束下验证迁移。**

这个定位更容易与 AgentBrew、SKILL-KD、AMD、SkillWeaver 建立清楚的比较。重点不是换一个 skill 文件格式，而是证明何种经验在何种学生和任务条件下可执行、可泛化、值得成本。

## 五、后续实验应固定的口径

- 开发任务、技能选择任务、最终测试任务分离；进一步检查任务模板与近重复。
- 测试时教师退出，技能库冻结；检索器/路由器若另调强模型，需明示，不能默认为“只有小模型”。
- 逐题配对报告完成率提升、救回率与回归率；裸模型单次失败不能被定义为绝对“不具备能力”。
- 同时比较裸学生、学生自己的经验、教师原始轨迹、教师直接写的通用规则、教师–学生对比技能、教师生成脚本，以及匹配预算的学生多次尝试。
- 经验来源、技能长度、上下文预算、任务步数、工具集与反馈权限尽可能受控；若脚本扩大工具能力，应另外归因。
- 单列教师探索、学生验证、技能修改、检索器与部署成本；跨进程累积原始 token/成本记录。
- 先注册主指标和选择规则，再看最终测试；保留完整逐任务证据，按工作区 AGENTS.md 做干跑、不变量、等条件、统计与完整性审计。

## 推荐阅读顺序

1. **AgentBrew §2、§3.8**：完整设置和最直接的 Terminal-Bench 先例。
2. **SKILL-KD 方法、Table 1、附录 A**：轨迹对比、学生执行验证、技能漂移。
3. **AMD 方法、附录 B.3 / Table 6**：小模型、经验粒度和任务隔离。
4. **SkillWeaver §2–§4 / AgentDistill §3**：可执行技能与工具转移。
5. **SPARK §3–§4**：真实终端证据与跨实例技能质量。
6. **SkillsVote §4 / VaG 实验设置**：终端技能库迁移、检索和安全准入。
7. **Rethinking the Evaluation of Harness Evolution §3–§4**：匹配预算、任务留出及负面证据。

本调研支持“已有高度类似先例”这一判断，不支持任何新方法必定有效、某论文结果已独立复现，或上述切入点必然具备发表新颖性的判断。
