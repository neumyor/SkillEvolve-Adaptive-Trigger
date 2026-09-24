# Benchmark 统一配置

本目录有四个独立评测环境。其中三个旧环境曾共用一份仅供本机使用的 LLM 配置：

```text
benchmark/llm_config.json
```

对应环境：

- `benchmark/alfworld-eval`
- `benchmark/search-eval`
- `benchmark/searchqa-eval`

第四个环境为 `benchmark/terminalbench-eval`，使用自己的 `configs/*.yaml` 和环境变量。
四个环境作为独立仓库发布时，均应按各自 README 设置模型端点、模型名和密钥；
不要复制或提交本机的 `llm_config.json`。

评测时使用各环境在 `llm_config.json` 中对应的配置；如果没有环境专属配置，则使用 `default` 配置。当前配置为：

- API 基础地址：`https://llm-center.modelbest.co/v1`
- 模型：`default` 段为 `deepseek-v4.1-flash`；`alfworld-eval`、`search-eval` 和
  `searchqa-eval` 段均为 `qwen3.6-flash-distill`（2026-09-15 的 SkillOpt vs Trace2Skill
  评测所用）
- 请求路径：程序在基础地址后追加 `/chat/completions`

各段可以不一致，评测报告里必须写明当次所用的模型名。

JSON 字段说明：

```json
{
  "base_url": "OpenAI 兼容 API 的基础地址",
  "model": "模型名称",
  "api_key": "API key"
}
```

`base_url` 只填写到 `/v1`，不要把 `/chat/completions` 再写入配置。三个评测环境的其他参数仍按各自 README 和评测脚本设置，例如数据路径、评测 split、skill 文件、最大步数和输出目录。

## ALFWorld 评测入口

在 `benchmark/alfworld-eval` 上评测 SkillOpt / Trace2Skill（含生成、并发、warmup、验收）：

- 操作顺序、实测预算与踩坑清单：`alfworld-eval/README.md` 的
  [复现操作手册](../alfworld-eval/README.md#复现操作手册skillopt-与-trace2skill-端到端)；
- 主题背景与上游口径差异（各方法与论文的偏离）：同一 README 的「方法一 / 二 / 三」各节；
- 最近一次完整评测（qwen3.6-flash-distill，SkillOpt 82.09% vs Trace2Skill 66.42%，
  配对 McNemar p = 4.9e-05）与全部 caveat：
  `docs/reports/alfworld_qwen36_skillopt_vs_trace2skill.md`（工作区根目录）。

关键操作约定（详见该手册）：并发评测必须先 `warmup_endpoint.py` 再起 shard；
小规模测试用 `sample_manifest.py` 分层抽样而不是 `--limit`；Trace2Skill 必须先跑生成
阶段、评测时 `--skill-path` 指向生成的文档，并核对 `summary.json` 里的 `skill.sha256`。

## Docker

LLM 配置文件位于 `benchmark/`，而三个 Docker 镜像分别以各自评测目录为构建上下文，因此启动容器时需要将配置文件挂载到容器中，并按容器内路径使用：

```bash
-v "$PWD/../llm_config.json:/opt/benchmark/llm_config.json:ro"
```

其中宿主机路径应根据当前执行目录调整。不要将配置文件复制进镜像层，也不要在 README、日志或命令历史中再次打印 API key。

## 安全提醒

该文件包含明文 API key，仅适合当前本地评测环境使用。若文件被提交到公开仓库、上传到共享环境或泄露，应立即撤销该 key 并重新生成。
