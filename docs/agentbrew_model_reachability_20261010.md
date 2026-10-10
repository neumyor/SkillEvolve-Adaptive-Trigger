# AgentBrew 新模型 ID 可达性

2026-10-10。用户指定教师provider ID `DEEPSEEK_up5zdj`、学生
`qwen3.6-flash-distill`。教师底层身份`deepseek-v4-flash-0731`来自用户说明；
服务response仅报告`deepseek-v4-flash`，不能单凭此证明具体revision。

## 实际请求

服务器node29经腾讯E2B访问`https://llm-center.modelbest.co/v1/chat/completions`，
使用远程已有忽略.env凭据。独立健康目录，无benchmark指令、测试答案或经验池写入。
两个独立sandbox并行进行，每模型一次请求，无重试，原始SSE和response/usage留存。

| 角色 | 请求model ID | response model | 请求输出上限 | 结果 | 总耗时含sandbox |
| --- | --- | --- | --- | --- | --- |
| 教师 | DEEPSEEK_up5zdj | deepseek-v4-flash | 64000 | JSON `{"ok":true}`、stop、完整DONE | 19.431秒 |
| 学生 | qwen3.6-flash-distill | qwen3.6-flash | 65536 | JSON `{"ok":true}`、stop、完整DONE | 6.020秒 |

请求保留学生top_p0.95/top_k20/enable_thinking=true/preserve_thinking=true；
教师temperature0，不额外覆盖reasoning。两个sandbox均完成清理。
接口接受该输出预算参数，但短响应不证明满64000/65536长度生成可完成或完整任务成功。
教师usage原样为prompt35/completion31/total125，三个字段不自洽；不改写raw，不据此推断真实总用量。
学生usage为prompt31/completion201/total232，reasoning188。供应商usage保留原值。

## 产物与配置

远程：`/home/xinhaidong/agentbrew-tb21-formal-batch-20261009/outputs/model_health_20261010_new_ids`。
本地：`benchmark/terminalbench-eval/tmp/agentbrew_model_health_20261010/remote_artifacts`。
包含protocol、每角色request/response/result、原始SSE、sandbox ID和report。
本地后续TB2.1配置及继承的batch/smoke已更新两个model ID；旧远程release、实验合同、
轨迹和费用不变。未开始新的正式实验。
