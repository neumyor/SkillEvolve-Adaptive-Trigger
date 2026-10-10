# 腾讯云 E2B 沙箱使用与部署操作文档

> 基于公司内部《腾讯云e2b沙箱使用简易教程》整理，补充了使用规范和各步骤的检查清单，
> 用于指导本项目（searchqa-eval / search-eval / alfworld-eval 三个skill评测benchmark）
> 的多沙盒并行部署。

## 目录

1. [沙箱是什么、什么时候用](#1-沙箱是什么什么时候用)
2. [权限与账号申请](#2-权限与账号申请)
3. [环境安装与配置](#3-环境安装与配置)
4. [沙箱类型选择](#4-沙箱类型选择)
5. [自定义镜像制作与发布](#5-自定义镜像制作与发布)
6. [镜像预热](#6-镜像预热)
7. [沙箱生命周期使用规范](#7-沙箱生命周期使用规范)
8. [多沙盒并行评测部署（本项目专用）](#8-多沙盒并行评测部署本项目专用)
9. [并发与网络注意事项](#9-并发与网络注意事项)
10. [安全规范](#10-安全规范)
11. [故障排查清单](#11-故障排查清单)

---

## 1. 沙箱是什么、什么时候用

E2B 沙箱是按需创建的一次性隔离云端环境（可以理解为"临时小虚拟机"）。典型生命周期：

```
创建(create) → 执行命令/代码(run) → 取回结果(download/read) → 销毁(kill)
```

**适用场景**：需要环境隔离、文件隔离、大量并发的 Agent 场景，例如：
- 造数据 / 评测 / RL 训练中的沙盒执行
- 需要在隔离环境里跑不受信任或有副作用的代码
- 需要横向扩展到几十上百个并行任务（如本项目的多沙盒分片评测）

**不适用场景**：单次本地就能跑完的小任务，不需要为此起沙箱增加复杂度。

---

## 2. 权限与账号申请

| 需要的东西 | 找谁 |
|---|---|
| 腾讯云沙箱控制台权限 | @冯自成 @杨随云 |
| E2B_API_KEY / TENCENTCLOUD_SECRET_ID/KEY | 私信 @pyx 或 @ysy |
| 腾讯云agent服务对接（技术支持群） | @杨小雷（腾讯） |
| 沙箱连外网 / 自定义DNS | 联系"于是"申请可用template |

**✅ Check：开始前确认**
- [ ] 已拿到 4 个环境变量的实际值（不是占位符）
- [ ] 确认自己账号在控制台有对应命名空间的权限
- [ ] 如果需要连外网，提前跟"于是"申请好template，不要等到卡在这一步

---

## 3. 环境安装与配置

```bash
pip install e2b e2b-code-interpreter 'tencentcloud-sdk-python>=3.1.32'

export E2B_API_KEY="ark_***"
export E2B_DOMAIN="ap-beijing.internal.tencentags.com"
export TENCENTCLOUD_SECRET_ID="***"
export TENCENTCLOUD_SECRET_KEY="***"

# 并发相关，大批量使用时务必设置，否则容易卡在连接数上限
export MAX_CONCURRENT_SANDBOX_SETUP=8192
export E2B_MAX_CONNECTIONS=20000
export E2B_MAX_KEEPALIVE_CONNECTIONS=20000
export E2B_KEEPALIVE_EXPIRY=7200

# 仅在 cybertron 环境运行时需要，走专线则不需要（见第9节）
export http_proxy=http://whitelist-proxy.cybertron.svc.cluster.local:7891
```

**✅ Check：配置完成后**
- [ ] 4个凭证类环境变量已 `export`，不是写死在代码里（更不能提交进git仓库）
- [ ] 跑一遍 [Hello World 最小示例](#附录hello-world-最小验证脚本) 确认能创建/执行/销毁成功
- [ ] 明确自己是否在 cybertron 上运行，决定是否需要 `http_proxy`

---

## 4. 沙箱类型选择

| 类型 | SDK | 适合场景 | 本项目是否用 |
|---|---|---|---|
| Code Interpreter 沙箱 | `e2b_code_interpreter.Sandbox` | 只需跑一段python代码，无自定义环境（TIR类场景） | ❌ |
| 普通沙箱 + 自定义镜像 | `e2b.Sandbox` | 需要 shell 命令、装依赖、跑完整代码仓库（SWE/terminal类场景） | ✅ 本项目三个benchmark都用这个 |

原因：三个benchmark评测都是"进入项目目录 → `uv sync` 装依赖 → 跑 `scripts/run_unified_eval.py`"的完整工程流程，属于 SWE/terminal 场景，必须用带自定义镜像的普通沙箱。

**✅ Check**
- [ ] 已确认本项目场景属于"普通沙箱"而非"code interpreter沙箱"，不要选错类型多走弯路

---

## 5. 自定义镜像制作与发布

### 5.1 Dockerfile 要点

- 基础镜像自选，把项目代码 + 依赖装进去
- 如果场景是 GDPVal 类，**必须装 jupyter**，且**不能修改** `/root/.jupyter/start-up.sh` 相关内容，也**不能修改**创建 user 用户的部分（e2b 依赖这些）
- 本项目（SWE/terminal类）**没有 jupyter 的强制要求**，但仍需保留 e2b 需要的 user 创建逻辑

### 5.2 编译与推送

```bash
docker login modelbest.tencentcloudcr.com --username <你的用户名> --password <密码>
docker build . -t modelbest.tencentcloudcr.com/code-interpreter/<你的镜像名>:latest
docker push modelbest.tencentcloudcr.com/code-interpreter/<你的镜像名>:latest
```

自定义镜像的命名空间建议固定用 `code-interpreter`（教程建议不要改）。

**✅ Check：镜像发布前后**
- [ ] Dockerfile 里没有硬编码任何密钥/token（docker login 的密码单独管理，不进仓库）
- [ ] `docker build` 本地构建成功，没有报错
- [ ] `docker push` 成功后，在腾讯云镜像服务控制台能看到新镜像
- [ ] **绝对不要**把 `docker login` 的密码明文写进任何会被提交到git的文件（包括这份文档本身）

---

## 6. 镜像预热

新镜像第一次在沙箱里使用时可能会超时，必须先预热：

```bash
# 在 pingce 开发机上
cd /root/tencent_e2b/ags-cookbook/goscripts
# 修改 config.toml 里的 namespace 为你自己的
go run cmd/precache/main.go
```

**✅ Check**
- [ ] 每次推送**新版本**镜像后都重新预热一次（不是只在第一次镜像上传时做）
- [ ] `config.toml` 里的 namespace 改成了自己实际用的命名空间，而不是别人的默认值
- [ ] 预热完成后，用小规模（1~2个）沙箱先跑一次冒烟测试，确认镜像可用，再上大批量

---

## 7. 沙箱生命周期使用规范

标准模式（同步/异步 SDK 均适用）：

```python
sbx = None
try:
    sbx = Sandbox.create(..., timeout=<合理的超时时间>)
    result = sbx.commands.run("你的命令", user="root")
    # 在这里把需要的结果文件下载/读取出来
finally:
    if sbx:
        sbx.kill()
```

**核心规范**：
1. **必须用 try/finally 保证 kill**：沙箱不销毁会持续计费/占用资源配额。
2. **超时时间要设置合理**：`timeout` 太短任务跑不完会被中断；太长又浪费资源。评测类长任务建议按预估耗时的 1.5~2 倍设置。
3. **沙箱是临时的，没有持久化盘**：任何要保留的结果必须在 `kill()` 之前主动拉出来（下载/上传到对象存储），销毁后数据就没了。
4. **不要假设沙箱内网络稳定**：命令执行要考虑重试，尤其是调用外部 API（如 LLM 推理服务）时。

**✅ Check：每次跑沙箱任务前后**
- [ ] 代码里 `kill()` 在 `finally` 块里，异常路径也会执行
- [ ] 结果文件的拉取逻辑在 `kill()` **之前**执行，不是之后
- [ ] `timeout` 参数已经根据实际任务预估耗时设置，不是照抄示例的默认值
- [ ] 有基本的失败重试或告警机制（沙箱创建失败、命令执行非0退出码时不要静默吞掉）

---

## 8. 多沙盒并行评测部署（本项目专用）

本项目已经在三个benchmark（searchqa-eval / search-eval / alfworld-eval）里实现了**样本切分（sharding）+ 结果合并（merge）**能力，可以直接配合沙箱做并行评测。完整流程：

### 8.1 整体流程

```
[准备自定义镜像，含三个benchmark代码+依赖]
        ↓
[起 N 个沙箱，每个跑 --shard-index i / --num-shards N]
        ↓
[每个沙箱跑完，把 outputs/shard{i}of{N}/ 拉回本地或共享存储]
        ↓
[全部分片到齐后，本地执行 merge_shards.py 合并]
        ↓
[得到与单机串行跑一遍语料完全一致的最终 summary.json]
```

### 8.2 镜像准备

```dockerfile
FROM --platform=linux/amd64 python:3.11-slim-bookworm
RUN pip install uv
COPY searchqa-eval /opt/searchqa-eval
COPY search-eval /opt/search-eval
COPY alfworld-eval /opt/alfworld-eval
RUN cd /opt/searchqa-eval && uv sync
RUN cd /opt/search-eval  && uv sync
RUN cd /opt/alfworld-eval && uv sync
# alfworld-eval 需要 ALFWORLD_DATA 数据集，随镜像打包或启动时下载好
```

### 8.3 调度脚本示例（以 searchqa-eval 为例，另两个同理）

```python
import asyncio, os, json
from e2b import AsyncSandbox

NUM_SHARDS = 8
IMAGE = "modelbest.tencentcloudcr.com/code-interpreter/skilleval-sandbox:latest"

async def run_shard(shard_index: int):
    sbx = await AsyncSandbox.create(
        timeout=7200,
        api_key=os.getenv("E2B_API_KEY"),
        domain=os.getenv("E2B_DOMAIN"),
        template="some template",
        metadata={"x-custom-config": json.dumps({
            "image": IMAGE, "imageRegistryType": "enterprise",
            "command": ["/bin/sh", "-c"],
            "args": ["/mnt/envd -port 49983"],
            "resources": {"cpu": "2", "memory": "4Gi"},
        })},
    )
    try:
        env = {"LLM_KEY": os.environ["LLM_KEY"]}  # 只在这里注入，见第10节安全规范
        cmd = (
            f"cd /opt/searchqa-eval && uv run python scripts/run_unified_eval.py "
            f"--method skillopt --backend api "
            f"--base-url http://llm-center.modelbest.co/v1 --model MiniCPM5-2B-0822 "
            f"--num-shards {NUM_SHARDS} --shard-index {shard_index} "
            f"--out outputs/shard{shard_index}of{NUM_SHARDS}"
        )
        result = await sbx.commands.run(cmd, envs=env, timeout=6000)
        print(f"[shard {shard_index}] exit={result.exit_code}")

        local_dir = f"./collected/shard{shard_index}of{NUM_SHARDS}"
        os.makedirs(local_dir, exist_ok=True)
        for fname in ["results.jsonl", "summary.json"]:
            content = await sbx.files.read(
                f"/opt/searchqa-eval/outputs/shard{shard_index}of{NUM_SHARDS}/{fname}"
            )
            open(f"{local_dir}/{fname}", "w").write(content)
    finally:
        await sbx.kill()

async def main():
    await asyncio.gather(*[run_shard(i) for i in range(NUM_SHARDS)])

asyncio.run(main())
```

### 8.4 本地合并

```bash
cd searchqa-eval
uv run python scripts/merge_shards.py \
    ../collected/shard0of8 ... ../collected/shard7of8 \
    --out outputs/merged_final
```

`merge_shards.py` 会自动校验：
- 所有分片语料指纹（`corpus_fingerprint`）一致
- 分片编号无缺失
- 样本/episode 无跨分片重复
- 每个分片记录数达标（除非传 `--allow-incomplete`）

**✅ Check：多沙盒评测每一步**

准备阶段：
- [ ] 镜像已包含三个benchmark项目代码，且 `uv sync` 在镜像构建时验证过能成功
- [ ] alfworld-eval 所需的 `ALFWORLD_DATA` 数据在镜像里或有可靠的启动时下载方式
- [ ] 镜像已按第6节完成预热

分片启动阶段：
- [ ] `NUM_SHARDS` 在所有沙箱的调用里一致，`shard_index` 覆盖 `0..NUM_SHARDS-1` 且不重不漏
- [ ] `LLM_KEY` 通过 `envs=` 参数逐个沙箱注入，没有写进镜像或代码
- [ ] 每个沙箱的 `timeout` 覆盖了该分片的预估最大耗时（尤其 alfworld-eval 单episode可能耗时 200s~1300s+）
- [ ] 沙箱数量超过 64 时，已按第9节用 ray actor 分组，不要裸起大量沙箱直连

结果拉取阶段：
- [ ] 每个分片的 `results.jsonl` + `summary.json` 在 `kill()` 前已成功拉取到本地/共享存储
- [ ] 拉取失败或沙箱异常退出的分片，先确认 `results.jsonl` 是否可以断点续跑（本项目三个benchmark均支持resume，直接重跑同一条命令即可，不会重复计费或漏跑）

合并阶段：
- [ ] 所有 `N` 个分片目录都已收集齐全，一次性传给 `merge_shards.py`（不能传子集）
- [ ] 合并脚本正常退出且没有报"缺片/重复/指纹不一致"等错误
- [ ] 抽查合并后的 `summary.json` 关键指标是否符合预期量级（不要盲目相信脚本跑完就等于结果正确）

---

## 9. 并发与网络注意事项

| 问题 | 触发条件 | 解决办法 |
|---|---|---|
| cybertron 代理并发差，并发上千容易大量 http error | 在 cybertron 上跑 | 尽量用网络专线（见下），走专线时**不要再传 proxy 参数** |
| 沙箱数量 > 64 时，URL 解析爆掉，产生大量 http error | 单进程直连大批量沙箱 | 用 **ray actor** 隔离，每个 actor 负责一部分沙箱的访问 |
| 资源不足 | 大批量造数据+评测+RL同时进行 | 提前估算总用量，找腾讯预留资源；不够时再申请扩容 |

网络专线模式下创建沙箱的正确写法（先create再重新connect一次，且都不传 `proxy`）：

```python
sbx = await AsyncSandbox.create(**create_kwargs)  # 不传 proxy
domain = os.getenv("E2B_DOMAIN")
if domain:
    sbx = await AsyncSandbox.connect(
        sbx.sandbox_id, timeout=sandbox_timeout,
        api_key=api_key, domain=domain,
        sandbox_url=f"https://49983-{sbx.sandbox_id}.{domain}",
    )
```

**✅ Check**
- [ ] 明确当前是走 cybertron 代理还是网络专线，两种模式的 `proxy` 参数用法不同，不要混用
- [ ] 单批次沙箱数 > 64 时已经用 ray actor 分组，而不是一个循环里 `asyncio.gather` 几百个
- [ ] 大规模跑之前已经和相关同事沟通过资源预估，避免临时资源不足导致任务批量失败

---

## 10. 安全规范

1. **凭证一律走环境变量，不进代码仓库**：`E2B_API_KEY`、`TENCENTCLOUD_SECRET_ID/KEY`、`LLM_KEY` 等任何密钥，只能通过 `export`/沙箱创建时的 `envs=` 参数传递，不能出现在：
   - Dockerfile / 镜像里
   - 项目代码文件里
   - 任何会被 `git add`/`git commit` 的文件里
   - 本文档或其他会被分享的文档里
2. **docker login 密码单独保管**，不要贴在操作文档、聊天记录截图里长期留存。
3. **拉取结果前确认目标路径**：`sbx.files.read` / 下载操作要明确路径，避免误拉取到其他敏感文件。
4. 如果发现文档/聊天记录里意外泄露了明文密钥或token，**立即通知相关负责人吊销**，不要自己"顺手用一下"。

**✅ Check**
- [ ] 全流程代码 review 一遍，确认没有任何密钥硬编码
- [ ] 若发现历史遗留的明文凭证（如旧文档里的token），已上报吊销，而不是留着

---

## 11. 故障排查清单

| 现象 | 排查方向 |
|---|---|
| 沙箱创建就超时/失败 | 是否忘记预热镜像；`E2B_DOMAIN`/凭证是否正确；是否需要走代理 |
| 命令执行 exit_code 非0 | 先看 stdout/stderr；镜像里依赖是否装全；工作目录/路径是否正确 |
| 并发起沙箱时大量 http error | 沙箱数是否超过64未做ray actor隔离；是否在cybertron上走了低并发代理 |
| 分片跑到一半沙箱掉线 | 直接重跑同一条命令（本项目三个benchmark均支持resume断点续跑），无需从头开始 |
| merge_shards.py 报错缺片/重复/指纹不一致 | 检查是否传全了所有分片目录；是否混用了不同 `--limit`/`--datasets` 参数跑出来的分片 |
| 结果文件在本地找不到 | 确认拉取逻辑是在 `kill()` **之前**执行的，沙箱销毁后数据不可恢复 |

---

## 附录：Hello World 最小验证脚本

```python
#!/usr/bin/env python
import os, time, traceback
from e2b import Sandbox

def main():
    sbx = None
    try:
        sbx = Sandbox.create(
            timeout=300,
            api_key=os.getenv("E2B_API_KEY"),
            template="some template",
        )
        result = sbx.commands.run("echo hello", user="root")
        print(f"stdout={result.stdout}, exit_code={result.exit_code}")
    except Exception:
        print(traceback.format_exc())
    finally:
        if sbx:
            sbx.kill()

if __name__ == "__main__":
    main()
```

用来验证第3节的环境配置是否正确——正常应该打印 `stdout=hello`。
