# Skill–Task–Result 六元组清单

六元组顺序固定为：`dataset, llm, skillevolve, skill, task, result`。`skill` 现在是 `skill_files/…md` 的相对路径，每个路径唯一对应一个复制保存的 Markdown skill 文件；完整映射和原始来源见 `skill_files/manifest.json`。

主统计是按六个字段去重后的数量；同一 task 使用不同正文 skill，或得到不同结果，分别保留。

## 按数据集统计

| 数据集 | 去重六元组 | pass | fail | 不同 skill 文件 | 覆盖 task |
|---|---:|---:|---:|---:|---:|
| alfworld | 1029 | 736 | 293 | 19 | 459 |
| searchqa | 16543 | 13063 | 3480 | 27 | 4200 |

## 按 SkillEvolve 方法和 LLM 统计

| 数据集 | LLM | 方法 | 去重六元组 | pass | fail | skill 文件数 |
|---|---|---|---:|---:|---:|---:|
| alfworld | qwen3.6-flash-distill | ExpeToSkill (expel) | 493 | 375 | 118 | 15 |
| alfworld | qwen3.6-flash-distill | RethinkSkill | 134 | 29 | 105 | 1 |
| alfworld | qwen3.7-plus | GEPA | 134 | 114 | 20 | 1 |
| alfworld | qwen3.7-plus | SkillGEN | 134 | 110 | 24 | 1 |
| alfworld | qwen3.7-plus | SkillOpt | 134 | 108 | 26 | 1 |
| searchqa | qwen3.6-flash-distill | ExpeToSkill (expel) | 10943 | 8527 | 2416 | 23 |
| searchqa | qwen3.6-flash-distill | RethinkSkill | 1400 | 1089 | 311 | 1 |
| searchqa | qwen3.7-plus | GEPA | 1400 | 1148 | 252 | 1 |
| searchqa | qwen3.7-plus | SkillGEN | 1400 | 1139 | 261 | 1 |
| searchqa | qwen3.7-plus | SkillOpt | 1400 | 1160 | 240 | 1 |

## Skill 文件整理

- 共复制整理 **46** 个 Markdown 文件到 [`skill_files/`](/Users/yimingniu/Code/SkillEvolvePaperList/skill_files)。
- ExpeToSkill 的同一短 key 在不同 run 中若正文不同，会生成不同文件；文件名包含方法、数据集、原始 key 和正文 hash。
- RethinkSkill 使用 full test round 中的实际 `SKILL.md`；GEPA 使用 `best_idx` 指向的最终 candidate；SkillGEN 使用对应 candidate JSON 的 `body`；SkillOpt 使用对应条件的 `best_skill.md`。
- `skill_files/manifest.json` 记录每个文件的正文 SHA-256、原始来源和被多少条六元组引用。

## 原始测量与审计说明

原始来源行数、纳入/排除口径保留在 [`skill_task_result_provenance.json`](/Users/yimingniu/Code/SkillEvolvePaperList/skill_task_result_provenance.json) 中。仅纳入此前确认的完整、审计通过的 ExpeToSkill、RethinkSkill、GEPA、SkillGEN 和 SkillOpt 条件。
SkillGEN SearchQA audit 记录了 2 条 HTTP 500 `data_inspection_failed` 事件，但 1400 条 test unit 完整；该警告保留在 provenance 中。GEPA 的 SearchQA 与 ALFWorld 测试 skill 均按 `result.json.result.best_idx` 绑定。
