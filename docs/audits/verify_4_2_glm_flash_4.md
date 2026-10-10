# 第 4.2 节表格核验：批次 4（SkillWeaver、SkillOpt、SkillGen、SkillReducer、SkVM、Who Grades the Grader?）

核验范围：仓库内对应原始 PDF 与 `skill_evolve_survey.md` 第 4.2 节当前表格。  
页码说明：以下均为 PDF 页码，不是正文节号。  
本文件只给核验结论与替换建议，不修改主综述。

## 总体判定

| 论文 | 主要问题 | 建议处理 |
|---|---|---|
| SkillWeaver | “跨网站 G3/G6”缺少实验支持；target 中的 real websites 应限定为 4 个 live websites/57 tasks | 删除跨网站迁移；保留 website-specific G1/G2-like，并新增 GPT-4o→GPT-4o-mini 的 G7-like transfer |
| SkillOpt | 方向正确，但 G6/G7 与 G3 不能合并成无条件 portability | 按 model/harness/nearby-benchmark 分列；nearby math 只支持 G3-like |
| SkillGen | 无 G6；G0 是 paired intervention/G0-like；“不伤害”不能写成保证 | 删除 G6；补充 held-out regression；IOD/OOD 与 cross-model 分开 |
| SkillReducer | 55,315 与 600 的角色被混写；cross-model/framework 证据规模有限 | 区分 corpus analysis、end-to-end evaluation、wild-scalability 与小规模 transfer |
| SkVM | G6/G7 方向正确，但不是同一 raw artifact 的直接 portability | 写成 compiler/runtime adaptation 的 target-specific portability；避免解读为语义 skill 泛化 |
| Who Grades the Grader? | “evaluator G3/G5-like”不应借用任务迁移层级 | 改为 evaluator held-out validity / anchor generalization；明确 independent judge 只审计 report task |

---

## 1. SkillWeaver

### 逐列核对

- **evolve setting：基本正确。**论文确实是 website exploration → API synthesis/practice/honing。但“website exploration”不够完整，实际包含 proposal、practice、testing 和 composition of previously generated APIs。PDF p.6。
- **source 经验范围：需要限定。**不是 pooled multi-website experience，而是每个 website 单独探索得到的 API library。每站点使用 GPT-4o 做 160 次迭代。PDF p.6。
- **target 测试范围：过宽。**不能笼统写“WebArena、Online-Mind2Web、real websites”。实际是 WebArena 5 个 sandboxed sites，以及从 Online-Mind2Web 中筛出的 4 个可访问 real websites、57 tasks；WebArena 自动评测，live websites 人工判断成功。PDF p.5。
- **G0-G8：关键错误。**当前“跨网站 G3/G6”不成立。论文的“Generalization across Website”是让 agent 在不同网站上集成各自 pre-hoc exploration 得到的 API library，而不是同一 API collection 从 source website 迁移到未探索 target website。因此不能记 G3，也不是 G6 harness/tool-schema portability。PDF p.7。
- **可支持的结论：正确方向，但“跨网站复用”过强。**可以支持 website-specific API collection 提升同一站点任务成功率；也可以支持 GPT-4o 生成 API 后在 GPT-4o-mini 上使用。但这只是 model transfer，不是跨网站 skill reuse。PDF pp.6-8。
- **evaluator 结论：应保留。**WebArena 使用自动 functional-correctness evaluation，live websites 使用人工成功判定；两类评测必须分开。PDF p.5。

### 建议替换文本

```text
SkillWeaver | website-specific API synthesis + practice/honing | per-website exploration/practice traces；每站点 160 次 GPT-4o 迭代，可组合先前 API | WebArena 5 sites；Online-Mind2Web 中筛出的 4 个 live websites/57 tasks；另测 GPT-4o→GPT-4o-mini | G1/G2-like within-site；G7-like model transfer；不支持 G3/G6 跨网站 | website-specific API collection 提高同站点成功率；自动与人工 evaluator 不能合并；不得写成跨网站 skill reuse
```

---

## 2. SkillOpt

### 逐列核对

- **evolve setting：基本正确。**论文是对 frozen agent 的单一外部 skill document 做 bounded rewrite，并用 validation/selection gate 决定是否接受。PDF pp.1, 6。
- **source 经验范围：应更精确。**`D_train` 产生 rollout evidence；`D_selection` 只用于 accept/reject candidate；`D_test` 只用于最终报告。主实验使用各 benchmark 的 deterministic train/selection/test split，附录说明未另行规定时默认 2:1:7。PDF pp.8, 21。
- **target 测试范围：正确但需要拆开。**主结果是 benchmark-specific held-out test；transfer 另有 separate cells。跨 harness 是 Codex↔Claude Code；跨 model 是 GPT-5.4→GPT-5.4-mini/nano；跨 benchmark 是 OlympiadBench→Omni-MATH。PDF pp.8-9, 13。
- **G0-G8：G1/G2 可保留，但不要自动升级。**“held-out test”是否达到 G2 取决于各 benchmark 的 task/template 结构；论文没有统一证明所有 benchmark 都跨 unseen template。G3 只能记 nearby math 方向，不能扩成跨功能 G4/G5。G6 与 G7 应分列。PDF pp.9, 13。
- **可支持的结论：部分正确但需要收窄。**“artifact portability”只对实验过的 model scale、两个 harness 和 nearby math 成立，不能写成一般 artifact portability。ALFWorld 也不进入 Codex/Claude Code harness rows。PDF p.8。

### 建议替换文本

```text
SkillOpt | frozen model；单一外部 skill document 的 bounded rewrite + selection gate | per-benchmark D_train rollouts；D_selection 只做 acceptance gate | benchmark-specific held-out tests；另有 Codex↔Claude Code、GPT-5.4→mini/nano、OlympiadBench→Omni-MATH | G1/G2-like；G3-like nearby math；G6 cross-harness；G7 cross-model | 支持所测 held-out gains 与有限 model/harness/nearby-benchmark transfer；不支持一般跨功能 artifact portability
```

---

## 3. SkillGen

### 逐列核对

- **evolve setting：基本正确。**论文是 single auditable skill 的 synthesis、verification-guided refinement 与 best-of-K selection，并把 skill 视为 intervention。PDF pp.1-2, 5。
- **source 经验范围：需要改得更准确。**不是泛泛的“成功/失败轨迹”。每个 benchmark/split 有 base-agent trajectories，skill-training data 分为 induction subset 与 construction-time verification subset；前者用于对比归纳，后者用于 refinement/selection。PDF pp.2, 5, 17。
- **target 测试范围：需要列清。**主实验是 paired held-out evaluation；包括 ALFWorld IOD/OOD、LiveCodeBench、MCPBench、Mind2Web、PubMedQA、ScienceWorld、SocialMaze、τ-Bench、ChemLLMBench 等 benchmark/split cells，并覆盖多个 base models。PDF pp.6-7, 17。
- **G0-G8：应删除 G6。**论文没有 cross-harness 或 environment-schema transfer。跨模型实验是把 source model 生成的 skill 交给另一个 evaluator model 执行，覆盖 ALFWorld OOD、ScienceWorld、Mind2Web、SocialMaze FTS，因此只能记 G7-like。PDF p.8。
- **ALFWorld IOD/OOD：正确，但应写明协议。**`valid_seen` 与 train task types overlap，是 IOD；`valid_unseen` 是 novel task types。它更接近同环境内的新任务类型，不是跨环境。PDF p.17。
- **可支持的结论：过强。**paired evaluation 确实记录 repair 与 regression，但 verification gate 不能保证 accepted skill 在最终 held-out 上无回归。论文自己报告 ALFWorld OOD 的 accepted skill 对 Llama-3.1-8B 造成退化，ChemLLMBench yield prediction 也有明显 regression。PDF pp.7, 19。

### 建议替换文本

```text
SkillGen | single SU synthesis→verification-guided refinement→best-of-K selection；paired with/without-skill intervention | per-benchmark base-agent success/failure trajectories；induction subset + construction-time verification subset | paired held-out tests across ALFWorld IOD/OOD、LiveCodeBench、MCPBench、Mind2Web、PubMedQA、ScienceWorld、SocialMaze、τ-Bench、ChemLLMBench；另设 6-model transfer matrix | G0-like paired intervention；ALFWorld IOD/OOD；G7-like cross-model；无 G6 | 平均 held-out 增益可复现，但 accepted skill 仍可能造成 held-out regression；valid_unseen 是同环境 novel task types，不是跨环境
```

---

## 4. SkillReducer

### 逐列核对

- **evolve setting：基本正确，但建议改写。**它不是 discovery/creation，而是 post-authoring skill compression/debloating；Stage 1 处理 routing description，Stage 2 处理 body 与 progressive disclosure。PDF pp.1, 4, 8。
- **source 经验范围：当前混用了两个不同规模。**55,315 skills 用于 empirical study；600 skills 才进入完整 compression 与 task evaluation；另有 198 wild skills 只做 compression/faithfulness scalability，不做完整 task evaluation。PDF pp.1, 8。
- **target 测试范围：需要拆开。**不能笼统写“functional retention、SkillsBench、cross-model/framework”。实际包含：600 skills 的 generated-task paired evaluation；SkillsBench 87 tasks；198 wild skills 的 compression-only check；30 skills×5 tasks×5 models/4 families 的 cross-model set；30 skills×3 tasks 的 OpenCode framework set。PDF pp.8, 10。
- **G0-G8：G6/G7 可保留，但必须限定规模。**跨 5 个 model、4 个 families 支持 G7-like retention；OpenCode 支持 G6-like framework retention。但这些都是小规模 transfer cells，且所有 600 skills 使用 Anthropic skill protocol；Cursor/Windsurf 未测试。PDF pp.10-11。
- **可支持的结论：方向正确。**它支持压缩后的 token saving 与 tested functional retention，不证明 skill discovery 或 task-level generalization。“不是 discovery 泛化”应保留，并进一步限定为“compression retention”。

### 建议替换文本

```text
SkillReducer | post-authoring skill compression/debloating | 55,315-skill corpus only for empirical analysis；600 skills for end-to-end compression/evaluation；198 wild skills for compression-only scalability | 600-skill generated-task retention；SkillsBench 87 tasks；30-skill cross-model set；OpenCode 30-skill set | G6-like framework retention；G7-like cross-model retention；compression retention，不是 discovery generalization | 压缩降低 token cost 且在所测任务上保持或改善功能；不能外推为 broad platform portability 或 skill acquisition
```

---

## 5. SkVM

### 逐列核对

- **evolve setting：方向正确，但应强调不是 trajectory-driven skill evolution。**SkVM 把 skill 当 code，用 capability profiling、AOT/JIT compilation、environment binding、concurrency extraction 和 recompilation 适配执行载体。PDF pp.1-2。
- **source 经验范围：基本正确。**输入是 existing skill code、model/harness capability profile 与 environment/runtime information；不是从 rollout experience 中归纳新语义 skill。PDF pp.1-2, 9。
- **target 测试范围：正确。**评估覆盖 SkillsBench 与 PinchBench 的 118 tasks、8 个 models、3 个 harnesses；每任务生成 5 个 diverse input instances。PDF p.9。
- **G0-G8：G6/G7 方向正确，但不应读成 raw artifact portability。**SkVM 会针对 target model/harness 生成 optimized variants；所以它支持 compiler/runtime 层的跨 model/harness 可执行性，不是“同一 raw skill 不做任何适配直接可移植”。PDF pp.1-2, 9-10。
- **可支持的结论：基本正确，但建议补充 mismatch 事实。**论文报告原始 skill 在约 15% tasks 上造成退化，另有约 17% 不变；SkVM 的贡献正是在异质 model/harness 上降低 mismatch，并改善 completion、tokens 和 latency。PDF pp.1, 10。
- **边界判断：应保留。**这是 execution portability/efficiency，不是语义 skill 泛化，也不是 task-function transfer。

### 建议替换文本

```text
SkVM | skill-as-code compiler/runtime adaptation；capability profiling + AOT/JIT + environment binding | existing skill code、target model/harness capability profiles；无 rollout-based skill acquisition | 118 tasks across SkillsBench/PinchBench；8 models、3 harnesses、5 instances/task | G6/G7-like compiler/runtime portability；不是 raw-artifact portability，也不是语义 skill 泛化 | 在所测异质 model/harness 上改善 execution compatibility、completion、tokens 和 latency；原始 skill 存在明显 mismatch
```

---

## 6. Who Grades the Grader?

### 逐列核对

- **evolve setting：基本正确。**论文同时演化 evaluator/metric 与 skill loop；metric 是 drawback detector 的 composition，并受 lifecycle 管理。但应强调 evaluator evolution 是主要对象，skill loop 是 co-evolution 的下游使用方。PDF pp.1-3。
- **source 经验范围：需要补全。** metric 使用 large unlabeled train outputs、10 个 anchored dev/reference items，以及 detector consensus regularization。locked held-out anchor never read；在 co-evolution 中，evolved metric 只 grades skill-loop training tasks，held-out measurement 不经过该 metric。PDF pp.1-3。
- **target 测试范围：需要拆开。**locked test 覆盖 MBPP+、Spider 2.0-Snow、report generation。MBPP+ 和 Spider 有较强 ground truth；report generation 没有准确 metric，使用 imperfect RAQS reference，并由 independent judge 做外部 audit。independent judge 主要用于 report task，不是所有 locked-test 的统一 evaluator。PDF pp.1-2, 6。
- **G0-G8：当前“evaluator G3/G5-like reliability”应删除。**G3/G5 描述的是任务/功能 source→target transfer，而该文是在同一 task family 内检验 evaluator 从 anchored dev/unlabeled train 到 locked held-out 的 validity；它没有跨任务族 metric transfer，也没有 G5。PDF pp.1-3。
- **可支持的结论：需要限定。**论文支持在三个 tested task families 上，Double Ratchet 能恢复 88–110% 的 reference-loop held-out lift，并展示 anchor guards 能抵抗 Goodhart collapse；report task 另有 independent judge 捕获 gaming。但这不是普通 task-transfer generalization，也不是 universal evaluator。PDF pp.1, 5-7。

### 建议替换文本

```text
Who Grades the Grader? | evaluator/metric evolution + skill-loop co-evolution | large unlabeled train outputs + 10 anchored dev items + detector consensus；locked anchor never read | MBPP+、Spider 2.0-Snow、report generation locked held-out tests；report additionally audited by independent judge | evaluator held-out validity / anchor generalization；不属于 G3/G5 task transfer | 在三个 tested task families 中恢复 reference-loop lift 并抵抗 Goodhart；不能写成跨任务 evaluator generalization 或普通 skill score
```

---

## 对主表的最小修改清单

1. **SkillWeaver**：删除“跨网站 G3/G6”；改为 website-specific G1/G2-like，并补 GPT-4o→GPT-4o-mini 的 G7-like transfer。  
2. **SkillOpt**：保留 G1/G2、G3、G6、G7，但把 nearby math、cross-harness、cross-model 写成分离证据。  
3. **SkillGen**：删除 G6；把 G0 改为 paired intervention/G0-like；补充 accepted-skill held-out regression。  
4. **SkillReducer**：区分 55,315 corpus analysis、600 end-to-end evaluation、198 wild compression-only check 与小规模 G6/G7 retention cells。  
5. **SkVM**：保留 G6/G7，但写成 compiler/runtime target-specific portability；不要当作 raw artifact 直接跨目标移植。  
6. **Who Grades the Grader?**：删除“G3/G5-like”，改为 evaluator held-out validity / anchor generalization；说明 independent judge 主要针对 report task。
