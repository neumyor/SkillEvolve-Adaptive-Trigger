# MiniCPM5-2B-Jev 远程调用

2026-09-29 部署：`yyk03@11.11.18.3` 的 GPU6，远端仅监听 `127.0.0.1:8013`。本机已建立自动重连隧道，使用 `http://127.0.0.1:18013`。模型是 [ytbai/MiniCPM5-2B-Jev](https://huggingface.co/ytbai/MiniCPM5-2B-Jev)，运行其专用 `/v1/systemone` 服务。

检查服务：

```bash
curl -fsS http://127.0.0.1:18013/health
```

一次任务与 skill 的探索性查询：

```bash
curl -fsS http://127.0.0.1:18013/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{
    "state": "Task: Put a clean cup on the table. Skill: Before placing a dirty object, clean it in the sink. The agent can inspect, clean, pick up, and place objects.",
    "questions": {
      "success": {
        "type": "noul",
        "instructions": "Will the agent complete this task when using the skill?"
      }
    }
  }'
```

结果位于 `answers.success.probabilities.true`。`choice` 是最高概率的键，`confidence` 是该键的概率。`noul` 的两个键是 `false`、`true`；`choice` 问题需在 `criteria` 中列出候选项。一次请求可以放多个问题，共享同一个 `state`。

Python 调用：

```python
import json
from urllib.request import Request, urlopen

payload = {
    "state": "Task: Put a clean cup on the table. Skill: Clean dirty objects before placing them.",
    "questions": {
        "success": {
            "type": "noul",
            "instructions": "Will the agent complete this task when using the skill?",
        }
    },
}
req = Request(
    "http://127.0.0.1:18013/v1/systemone",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
)
with urlopen(req, timeout=30) as response:
    result = json.load(response)
print(result["answers"]["success"]["probabilities"]["true"])
```

本机隧道监护脚本为 [`tmp/minicpm5_2b_jev_local/tunnel.py`](../../tmp/minicpm5_2b_jev_local/tunnel.py)，监护 PID 在同目录的 `supervisor.pid`。远端部署目录为 `~/niuyiming/SkillEvolvePaperList/tmp/minicpm5_2b_jev/`，服务 PID 在 `service.pid`，日志在 `logs/service.log`。如果服务停止，确认 GPU6 空闲后，在远端运行 `python3 ~/niuyiming/SkillEvolvePaperList/tmp/minicpm5_2b_jev/start.py`。启动脚本在独立目录中加载官方文件，并将模型底座映射到已校验的本地权重；不会下载或改写模型权重。

已通过四个真实请求：支付路由、退款时限的正反例、任务与 skill 形式的探针；同一请求调换问题顺序后，各选项概率相同。服务在 GPU6 占用约 5.1 GiB，远端启动日志含 `Application startup complete`，本机经隧道的真实请求成功。这里的 `true` 概率**没有经过 Skill Evolve 数据校准**，不能解释为该 skill 的实际成功率，也不能直接替代 validation 回测。
