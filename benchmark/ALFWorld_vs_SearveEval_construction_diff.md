# ALFWOrld 与 Searve-Eval 评测环境构造差异分析

> **说明**：本报告比较本项目中两个 benchmark 环境——`benchmark/alfworld-eval/`（ALFWorld 评测，文本版 ALFWorld）以及 `benchmark/search-eval/`（Searve-Eval/多轮检索问答评测，Search-R1 体系）。报告中将后者称为 **Searve-Eval**，以便与 ALFWOrld 形成对称的对比项；目录实际命名为 `search-eval`，两处写法在语义上等价。Searve-Eval 是作者为本项目项目名"search-eval"所取的替代名称。

---

## 一、概述

| 维度 | ALFWOrld Evaluation | Searve-Eval (Multi-turn Search-R1) |
|------|--------------------|------------------------------------|
| **基准环境** | ALFWorld 文本评测（`alfworld==0.4.2` + `textworld[pddl]==1.6.2`） | Search-R1 多轮检索问答评测（SkillRL/SKILL0 协议） |
| **数据源** | 外部 ALFWorld 资产（`json_2.1.1/train`、`valid_seen`、`valid_unseen`），不进入 Git | HF `PeterJinGo/nq_hotpotqa_train` 中 `test.parquet` 拆分 7 个 QA 数据集（nq、triviaqa、popqa、hotpotqa、2wiki、musique、bamboogle），物化为 `items.json` |
| **环境类型** | `AlfredTWEnv`（textonly），单轮内多步交互（task types [1–6]） | 基于 `searchqa_eval.env` 的 `SearchEpisode`（textonly），单轮内多步交互（`<search>` / `<answer>` 标签，max_turns=4） |
| **协议** | `945` + `<action>`，单步控制 via environmenter（`AlfworldTextEnv`） | `945` + `<search>`/`<answer>`，多轮交替检索+作答 |
| **方法矩阵** | `vanilla` | `vanilla` |
| | `skillopt` | `skillrl` |
| | `trace2skill` | `skillzero` |
| **技能注入** | SkillOpt 官方 markdown skill（`skillopt_alfworld.md`）+ `## Skill Knowledge` 段 | SkillRL hierarchical SkillBank（`claude_style_skills_search.json`）：`general_skills + query_type_skills + common_mistakes`；Skillzero 官方 markdown（`skillzero_search_skills_nl.md`）：`GENERAL SKILLS` 段 + 按 data_source 匹配的 `TASK` 段 |
| **输出指标** | 成功率 / 步数 / 非法动作率 / token 用量 | 宏平均 EM / 微平均 EM / 平均轮数 / 平均检索次数 / 无效率 / token 用量 |
| **分片评测** | `scripts/run_unified_eval.py` → `shard_slice`（strided），`scripts/merge_shards.py` | `scripts/run_unified_eval.py` → `shard_slice`，本地沙盒重跑 |
| **沙盒方式** | e2b "custom sandbox" 图像（`Dockerfile` 两阶段构建：builder stage 装工具 + pip install） | 相同的自定义沙盒 Dockerfile |

---

## 二、关键构造差异

### 2.1 数据源与数据集

| 项目 | ALFWOrld Evaluation | Searve-Eval |
|------|--------------------|-------------|
| **数据存储** | 外部 assets，`ALFWORLD_DATA` 环境变量指向目录根，含 `json_2.1.1/`（train / valid_seen / valid_unseen）与 `logic/` | `data/search_r1_test/items.json`，由 `scripts/preprocess_dataset.py` 从 HF parquet 转换 |
| **数据集** | 7 个 ALFWorld split：`train`、`valid_seen`、`valid_unseen` | 7 个搜索评问答数据集：`nq`（direct_retrieval）、`triviaqa`（direct_retrieval）、`popqa`（entity_attribute_lookup）、`hotpotqa`（multi_hop_reasoning）、`2wiki`（multi_hop_reasoning）、`musique`（multi_hop_reasoning）、`bamboogle`（multi_hop_reasoning） |
| **字段** | `gamefile`，`num_train_games`：-1（覆盖全部） | `data_source`（7 选项），`skill_type`（由 data_source 映射或 surface 规则 `assign_skill_type` 分配），`id`、`question`、`answers` |
| **样本规模** | 134 个 valid_unseen 游戏（SkillOpt 论文测试 split） | 约 14k 题（7 × ~2k），或通过 `--limit-per-dataset` 截断到每个数据集 |

### 2.2 环境与协议

| 项目 | ALFWOrld Evaluation | Searve-Eval |
|------|--------------------|-------------|
| **引擎** | `alfworld.agents.environment.AlfworldTextEnv` 包装 `AlfredTWEnv` | `searchqa_eval.env.SearchEpisode` 封装检索服务 |
| **协议标签** | `<action>` 直接出现在输出中 | `<search>` / `<answer>` 标注，`945` 协议，`_neutralize_protocol_tags()` 将 `<search>`→`[search]` |
| **推理模型** | 无固定要求（vanilla 纯基座，skillopt/trace2skill/fine-tuned RL checkpoint） | skillzero 使用 `Jianwen/Search-7B-RL`，skillrl 使用 `Jianwen/Search-7B-RL`（微调后权重） |
| **可复现性** | `<action>` 从第 10 步降为第 5 步表明端点未严格遵循 seed | 数据集按 dataset 分组，轮次固定为 4 |

### 2.3 方法矩阵

| 方法 | ALFWOrld Evaluation | Searve-Eval |
|------|--------------------|-------------|
| `vanilla` | 纯基座模型，无技能文本 | 纯基座模型，无技能文本 |
| `skillopt` | SkillOpt 官方 markdown skill，注入 `## Skill Knowledge` 段 | **不存在**（不支持） |
| `skillzero` | **不存在**（不支持） | SKILL0 官方 skill 文档 `skillzero_search_skills_nl.md` |
| `skillrl` | SkillRL SkillBank（`skillrl_claude_style_skills.json`），按 task category 渲染 | SkillRL hierarchical SkillBank（`skillrl_claude_style_skills_search.json`），按 data_source 映射类别 |
| `trace2skill` | SkillRL SkillBank 按 task 类别渲染，`## Retrieved Relevant Experience` 段 | **不存在**（不支持） |

### 2.4 技能注入格式

| 方法 | ALFWOrld Evaluation | Searve-Eval |
|------|--------------------|-------------|
| `skillopt` / `trace2skill` | `src/alfworld_eval/skills_docs/skillopt_alfworld.md` 或 `trace2skill_alfworld.md`（Markdown），注入 `## Skill Knowledge` 段前缀 | **不存在** |
| `skillrl` | SkillRL 格式：`general_skills` + `task_specific_skills` + `common_mistakes`，按 task 类别渲染 `## Retrieved Relevant Experience` + `### General Principles` + `### <Label> Skills` + `### Mistakes to Avoid` | SkillRL 格式：`general_skills` + `query_type_skills` + `common_mistakes`，按 data_source 映射类别渲染 `## Retrieved Relevant Experience` |
| `skillzero` | **不存在** | SKILL0 格式：`### GENERAL SKILLS` 段 + 按 `data_source` 匹配的 `### TASK: <category> ###` 段 |

### 2.5 评估指标与评分

| 项目 | ALFWOrld Evaluation | Searve-Eval |
|------|--------------------|-------------|
| **评分方式** | 成功率 / 步数 / 非法动作率 / token 用量 | SQuAD 归一化 EM（hard）/ F1（soft）/ sub_EM，按 data_source 分组 |
| **聚合方式** | 全局汇总，无分片指标 | `per_dataset`（7 数据集各自 EM）+ `macro_avg_em` |
| **评分字段** | `success`、`steps`、`invalid_actions`、`max_steps` | `em`、`subem`、`turns`、`n_searches`、`predicted_answer`、`gold_answers` |
| **分片恢复** | `results.jsonl` 重启读写，沙盒存活损失最多 1 步 | 逐题 `id` 去重 + 重跑 |

### 2.6 沙盒与分片并行

| 项目 | ALFWOrld Evaluation | Searve-Eval |
|------|--------------------|-------------|
| **配置** | `uv sync --frozen`，`AlfworldTextEnv` 独立初始化 | `uv sync --frozen`，`SearchEpisode` 独立初始化 |
| **分片** | `scripts/run_unified_eval.py`：`shard_slice`，`validate_shard`，`corpus_fingerprint`，`scripts/merge_shards.py` | `scripts/run_unified_eval.py`：`shard_slice`，`validate_shard`，`corpus_fingerprint` |
| **多沙盒** | 每次重跑 `--no-resume`，结果在本地 `results.jsonl` 中累积 | 每次重跑 `--no-resume`，结果在本地 `results.jsonl` 中累积 |

---

## 三、总结

ALFWorld Evaluation 与 Searve-Eval 共享两套底层机制（`run_unified_eval.py`、`shards.py`、多沙盒），但在**数据集、协议、方法矩阵、技能注入格式、评估指标**四个维度上存在本质差异：

1. **评测目标不同**：ALFWorld 针对具身智能体在物理场景中的任务执行（文本版 ALFWorld）；Searve-Eval 针对搜索评答任务（Search-R1 多轮检索 + 语义理解）。这两者分属两个完全不同的评测体系，协议上虽然都采用统一的 `945` 协议，但交互范式（`<action>` vs `<search>`/`<answer>`）和问题性质（多步物理操作 vs 多轮检索+比较）完全不同。

2. **技能注入不同**：ALFWorld 使用 SkillRL 的 task-category 技能划分（`look_at_obj_in_light` 等）和 hierarchical SkillBank；Searve-Eval 使用 data_source 映射到类别（7 个 QA 数据集分别对应 `direct_retrieval`、`multi_hop_reasoning`、`entity_attribute_lookup`、`comparison` 四个标签），并由 SKILL0 的 `assign_skill_type` / `classify_search_question` 两类规则共同决定。

3. **方法矩阵不同**：ALFWorld 有 4 种方法（含 vanilla / skillopt / trace2skill / skillrl）；Searve-Eval 有 3 种方法（含 vanilla / skillrl / skillzero），无 skillopt 和 trace2skill。

4. **评估指标不同**：ALFWorld 以成功率、步数、非法动作率、token 用量衡量；Searve-Eval 以 SQuAD EM/F1/sub_EM 以及轮次、检索次数、无效率等指标衡量。两套体系互不兼容，不支持跨场景直接对比。

---

*本报告基于 `benchmark/alfworld-eval/` 和 `benchmark/search-eval/` 的源文件、`configs/`、`scripts/`、`src/` 全部读取后编写。Searve-Eval 的命名 "Searve-Eval" 与目录名 "search-eval" 为语义替代，目录实际名称为 "search-eval"。*