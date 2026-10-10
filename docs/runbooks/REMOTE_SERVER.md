# REMOTE_SERVER.md — 远程 A800 评测服务器使用指南

本文档不入库（已加入 `.gitignore`），仅供本地开发参考。

## 硬件概览

| 项目 | 规格 |
|---|---|
| GPU | 8× NVIDIA A800-SXM4-80GB（CUDA 12.4）|
| CPU | 104 核，x86_64 |
| 内存 | 1 TB |
| 磁盘 | `/home` 挂载 Lustre（8.7 PB 可用），`/` 本地 SSD 9.7 TB 可用 |

内存和 GPU 不再是任何评测实验的硬阻塞。

## 连接

```bash
ssh yyk03@11.11.18.3
```

共享机器，**只在 `~/niuyiming/SkillEvolvePaperList/` 目录下操作**，不碰其他用户的目录。

## 网络情况与流量路由策略

服务器处于受限网络环境，直连外部服务均超时。实测结果：

| 目标 | 直连结果 | 解决方案 |
|---|---|---|
| huggingface.co | ❌ 超时 | 用 `hf-mirror.com`（✅ 已测通） |
| pypi.org | ❌ 超时 | 用清华镜像 `pypi.tuna.tsinghua.edu.cn`（可用） |
| LLM API 端点（`llm-center.modelbest.co`） | ❌ 超时 | **本地端口转发**（见下） |
| 内网 SSH | ✅ 正常 | 直连 |

### LLM 端点端口转发（两段式：本地中继 + 反向隧道）

本地机器可直连 LLM API，服务器不行。

**不能**直接用 `ssh -R 18000:llm-center.modelbest.co:443`，有两个原因：
1. 服务器上的客户端会以 `localhost` 作为 SNI/Host 发起 TLS 握手，证书校验必然失败；
2. API key 就得放到这台共享服务器上。

正确做法是本地起一个 **HTTP→HTTPS 中继**，由它在本地终结 TLS 并注入 key，
服务器侧只看到明文 HTTP：

```bash
# 1. 本地起中继（脚本见 scratchpad/llm_relay.py，不入库）
export LLM_KEY='<api key>'          # 只存在于本地环境变量
python3 llm_relay.py                 # 监听 127.0.0.1:18000

# 2. 本地起反向隧道，把本地 18000 暴露到服务器的 localhost:18000
ssh -f -N -R 18000:127.0.0.1:18000 yyk03@11.11.18.3
```

服务器上调用时 `--base-url http://localhost:18000/v1`（**http 不是 https**）。
API key 全程不落到服务器磁盘。

实测端到端延迟 ~0.54s，相对每步推理的秒级耗时可忽略。

验证链路是否通：

```bash
ssh yyk03@11.11.18.3 'curl -s -m 60 -X POST http://localhost:18000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"MiniCPM5-2B-0822\",\"messages\":[{\"role\":\"user\",\"content\":\"say OK\"}],\"max_tokens\":2048}"'
```

> 端口 18000 是约定值，避免与 vLLM 默认的 8000/8001 冲突。若占用，改为其他非特权端口。

### 推理模型（reasoning model）的两个坑

用 MiniCPM5-2B-0822 这类推理模型时踩到过，记录在此：

1. **`max_tokens` 不能给小**。CoT 走 `reasoning_content` 字段，token 预算会被它吃光，
   导致 `content` 为空。实测 `max_tokens=50` 时 `content` 恒为空；≥512 才稳定出内容。
   统一用 `--max-tokens 2048`。注意 harness 里的 `FALLBACK_RESPONSE` 会把空 `content`
   静默替换成 `look`，**不会报错**，所以这个坑只能靠看 trajectory 发现。
2. **`<think>` 块被拆到两个字段**。`content` 从思考中途开始，通常只带一个孤立的
   `</think>`。`runner.project_action` 找不到开标签就把每一步判为 invalid——哪怕
   `<action>` 解析正确且成功执行。已在三个 benchmark 的 `agent.py::_restore_think_block`
   统一修复。修复前后 invalid 从 50/50 降到 12/50，后者才是该模型真实的协议违规率。

   **把 `reasoning_content` 拼回去时有两个坑，都踩过：**

   - **不能原样拼接。** 模型思考时会复述输出格式（实测 100 步里 4 步），而
     `project_action` 取的是**第一个** `<action>`，于是解析到的是思考里的排练而非
     真正的决定——实测执行了 `look`，模型其实选的是 `inventory`。必须先把思考里的
     协议标签中性化（`<action>` → `[action]`）。search-eval 更严重：它按标签**个数**
     判有效性，原样拼接会让一次 `<answer>` 变成「同时含 search 和 answer」被判无效，
     还会去执行一次本不该有的搜索。
   - **切分要用最后一个 `</think>`，不是第一个。** 模型会在思考里引用提示词原文
     （"enclosed within `<think></think>` tags"），第一个 `</think>` 可能落在思考内部。
     按第一个切会把剩余思考留在动作侧，解析出一大段散文——实测 step 33 执行了 `look`，
     模型其实选的是 `examine desk 1`。动作部分不含该标签，所以最后一个才是真边界。

   验证方式：把已有 run 的 trajectory 拉下来，按新逻辑**回放**并对比动作差异，
   不要只跑合成用例——这两个坑都是合成用例测不出来、回放才暴露的。

3. **`extract_answer` 的回退会把思考当答案。** `searchqa-eval` 在找不到 `<answer>`
   标签时回退到「最后一个非空行」；推理模型的 content 可能整段为空，于是把 think 块
   当答案交给 token 级 F1 打分，白捡部分分。已改为回退前先剥掉 `<think>...</think>`。
   （`search-eval/scorer.py` 无此问题，它无标签时返回 `None`。）

4. **`project_action` 有 CJK 检查**：响应含中文直接判 invalid。MiniCPM 是中文模型，
   拼回 `reasoning_content` 后如果思考是中文，会整片判无效。实测这 100 步里是 0，
   但换模型/换任务需要重新确认。

### 数据集下载

小文件（config、tokenizer、manifest 等）可以用 hf CLI 走 hf-mirror：

```bash
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download <repo_id> --local-dir <path>
```

**但大权重文件必须改用 curl** —— hf CLI 在这台机器上下大 LFS 文件会
`httpx.ConnectTimeout` 且重试无效（`HF_HUB_DISABLE_XET=1` 也无效，均已实测）。
用服务器上的 `~/niuyiming/hf_pull.py`（带 sha256 校验、可续传、可自愈，
本仓库副本在 `tmp/hf_pull.py`），详见下文「大文件不要用 hf CLI」。

pip 包安装加镜像参数：

```bash
pip install <pkg> -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 代码目录与同步

- 服务器代码目录：`~/niuyiming/SkillEvolvePaperList/`
- 本地代码目录：`/Users/yimingniu/Code/SkillEvolvePaperList/`

**代码单向上行，实验产物单向下行。**

### 上行：本地 → 服务器（rsync）

本项目不是 git 仓库，直接用 rsync 推送：

```bash
rsync -avz --progress \
  --exclude='.data/' \
  --exclude='.venv/' \
  --exclude='outputs/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  /Users/yimingniu/Code/SkillEvolvePaperList/ \
  yyk03@11.11.18.3:~/niuyiming/SkillEvolvePaperList/
```

`.data/`（ALFWorld 游戏数据，2 GB）和 `.venv/`（各环境的虚拟环境）不上行——服务器上独立准备。

### 下行：服务器实验结果 → 本地（rsync）

```bash
# 拉回指定实验目录（注意源路径末尾的斜杠）
rsync -avz --progress \
  yyk03@11.11.18.3:~/niuyiming/SkillEvolvePaperList/benchmark/<env>/outputs/<run>/ \
  benchmark/<env>/outputs/<run>/

# 批量拉回所有结果，排除大体积文件
rsync -avz --progress \
  --exclude='*.ckpt' --exclude='*.pt' --exclude='*.pth' \
  --exclude='__pycache__/' --exclude='.venv/' --exclude='.data/' \
  yyk03@11.11.18.3:~/niuyiming/SkillEvolvePaperList/benchmark/ \
  benchmark/
```

**不要加 `--delete`** 做全量同步，会抹掉本地已归档的旧 run。

## Python 环境

服务器上已有 `vllm` conda 环境（Python 3.12、vLLM 0.8.5、CUDA 12.4），适合部署模型推理。评测 harness 本身用 `uv`（`~/.local/bin/uv`）管理各 benchmark 的独立 venv。

**推荐在服务器上给每个 benchmark 单独 sync 一遍 venv：**

```bash
# 以 searchqa-eval 为例
cd ~/niuyiming/SkillEvolvePaperList/benchmark/searchqa-eval
~/.local/bin/uv sync
```

`uv sync` 在服务器上会卡住——uv 要去 GitHub 下 Python 3.11，GitHub 不可达。
用已有的 conda Python，禁掉下载：

```bash
UV_PYTHON_DOWNLOADS=never ~/.local/bin/uv sync --python ~/miniconda3/envs/embed/bin/python
```

ALFWorld 数据另行下载到 `.data/alfworld/`，不随代码上行（2 GB）。默认下载源可达，
不需要 hf-mirror，但耗时较长，必须后台跑：

```bash
cd ~/niuyiming/SkillEvolvePaperList/benchmark/alfworld-eval
export ALFWORLD_DATA="$PWD/.data/alfworld"
nohup ~/.local/bin/uv run alfworld-download > ~/niuyiming/alfworld_dl.log 2>&1 &
```

只有 `json_2.1.1/`（游戏数据）是纯文本 harness 的必需项；`logic/` 和 detector 权重
即使还没下完也不影响评测启动。验证：`valid_unseen` 下应有 134 个 game。

## GPU 使用

- 跑前先用 `nvidia-smi` 确认目标卡空闲。
- 用 `CUDA_VISIBLE_DEVICES=N` 选卡。
- vLLM 服务（用于 SkillRL checkpoint 推理）起在一张卡上，评测 harness 通过 `--backend api` 调用。
  7B 单卡（`--gpu-memory-utilization 0.50`，占 41339 MiB）足够，**不需要 tensor parallel**；
  两个 checkpoint 可分别占卡 6/卡 7 同时在线（实测）。

环境实测（2026-09-15）：`~/miniconda3/envs/vllm` 为 Python 3.12.11 / **vLLM 0.8.5** /
torch 2.6.0+cu124 / CUDA 12.4；**8× A800-80GB 当时全部空闲**（旧文档"卡 7 最少"已过时，
每次现场查）。vLLM 原生支持 Qwen2 系列，两个 checkpoint 都是 `Qwen2ForCausalLM`
（Qwen2.5-7B-Instruct 底座），**不需要 `--trust-remote-code`**。

### 结论：服务器能满足 SkillRL ckpt 推理需求（2026-09-15 验证）

已在服务器上真机跑通并留下产物，**不是纸面推断**：

| 环节 | 状态 |
|---|---|
| 0.5B 模型 下载 → sha256 校验 → vLLM 起服务 → OpenAI 端点调用 | ✅ 全部通过 |
| `Alfworld-7B-SFT` 下载（19/19 文件 sha256 OK）→ vLLM 起服务 → harness 跑通 | ✅ |
| `Alfworld-7B-RL` FSDP ckpt 下载（13/13 sha256 OK）→ merger 合并成 HF → vLLM 起服务 → harness 跑通 | ✅ 单集 success=True |
| 显存/磁盘/算力 | ✅ 单卡 7B 仅 14.25 GiB 权重；`/home` 8.7 PB 可用 |
| 外部网络 | ⚠️ 仍需 hf-mirror + 清华 pypi；下载大文件必须走 `hf_pull.py` |

**唯一真正的阻塞点已解除**：之前卡住的两件事（hf CLI 下不动大 LFS、`dl.sh` 续传
产出损坏分片）都已用 `hf_pull.py` 解决，两个 ckpt 现已落地并校验完毕，无需再下载。

### 大文件不要用 hf CLI，用 `hf_pull.py`（手写 HTTP + sha256 校验）

**实测结论：`hf download` / `huggingface-cli download` 在这台机器上无法下载大 LFS 文件。**
小文件（config/tokenizer）正常，一到权重就 `httpx.ConnectTimeout: timed out`，
重试无效；加 `HF_HUB_DISABLE_XET=1` 也**同样失败**（已验证两种情况）。
而同一 URL 用 `curl` 直接下**稳定且更快**（实测 0.5B 模型 988 MB / 33 s ≈ 30 MB/s，
早先另一次实测 6.6 MB/s）。`curl -C -` 还能断点续传，断线只损失在途字节。

**但裸 `curl -C -` 也不够。** 2026-09-15 下 7B checkpoint 时，旧的 `~/niuyiming/dl.sh`
（curl + `-C -` 续传）暴露两个静默损坏模式：

1. **孤儿进程并发写**。脚本经 `ssh '... &'` 启动、ssh 会话中断被杀后，`xargs -P` 派生的
   子 shell 和 curl **不随父进程退出**（PPID 变 1），继续往目标文件写；再重启一个新
   下载进程时，新旧两个进程同时写同一路径。
2. **续传把整包追加到已有文件尾**。某些响应下服务端忽略 `Range` 而回 200，`curl -C -`
   于是把完整内容追加到部分文件后面，产出**比原始文件更大**的分片
   （实测 `model-00003` 得 1891453616 B，正确值 1864467800 B）。

两者都不报错，只会留下"尺寸看起来还行、实际损坏"的权重。

**统一改用 `~/niuyiming/hf_pull.py`**（本仓库 `tmp/hf_pull.py`，用 scp 同步上去）。
它从仓库 tree API 一次取回每个文件的**期望大小 + LFS sha256**，下完逐个校验；
尺寸不符或 sha256 不符都会丢弃重下；已有文件也先验 sha256 才跳过，因此**可重复执行、
自愈**，被中断后重跑即可。

```bash
cd ~/niuyiming
# 下载（--parallel 控制并发连接）
python3 -u hf_pull.py <repo_id> <dest_dir> <file_list> --parallel 3
# 只校验不下载：对已下好的目录做全量 sha256 体检，exit code 非 0 表示有坏文件
python3 -u hf_pull.py <repo_id> <dest_dir> <file_list> --check
```

小文件清单直接列即可，例如 0.5B 模型：

```bash
cd ~/niuyiming
printf "%s\n" config.json generation_config.json merges.txt tokenizer.json \
  tokenizer_config.json vocab.json model.safetensors > qwen_files.txt
python3 -u hf_pull.py Qwen/Qwen2.5-0.5B-Instruct ~/niuyiming/checkpoints/qwen05b \
  qwen_files.txt --parallel 3
```

> **必须用 `setsid nohup python3 -u ... > log 2>&1 < /dev/null &` 起**，否则 ssh 一断
> 进程就被杀（见「长任务运行」）。另外**别用 `kill $(pgrep -f 脚本名)` 收工**：派生出的
> `bash -c`/`curl` 子进程 cmdline 不含脚本名，杀不掉，会变成孤儿继续写文件。
> 干净收工要按 PID 连子进程一起杀（见下文「收工」小节）。

> `hf download` 的 `--include` 与位置参数同时给会报
> `Ignoring --include since filenames have being explicitly set`，此时位置参数被当作
> 文件名——语义相同，但别混用以免误判。

### 部署 SkillRL checkpoint（vLLM）

**关键：两个 checkpoint 的格式不同，不能照抄同一条命令。**

| checkpoint | 大小 | 格式 | vLLM 能否直接加载 |
|---|---|---|---|
| `Jianwen/Alfworld-7B-SFT` | 15.2 GB | 标准 HF（`checkpoint-140/` 子目录下） | ✅ 可以，但路径要指到子目录 |
| `Jianwen/Alfworld-7B-RL` | 91.4 GB | **verl FSDP 训练 ckpt** | ❌ **不能**，须先合并 |

**RL 不是 HF 模型**：它只有 `actor/model_world_size_4_rank_{0..3}.pt`（4×7.6 GB）
加 61 GB 的 `optim_world_size_*` 优化器状态，`model.safetensors` 返回 404，
根目录也没有 `config.json`。直接 `--model .../Alfworld-7B-RL` 必然失败。

> **两个 checkpoint 已于 2026-09-15 全部下到服务器并逐个 sha256 校验通过**，
> 无需重复下载：`~/niuyiming/checkpoints/Alfworld-7B-SFT`（19/19 文件，15.25 GB，
> 实占 16.8 GB）、`~/niuyiming/checkpoints/Alfworld-7B-RL`（13/13 文件，28.4 GB）、
> `~/niuyiming/checkpoints/Alfworld-7B-RL-hf`（合并产物）。下面的下载命令仅在需要
> 重下或换机器时使用。

#### A. 直接可用：SFT checkpoint

```bash
cd ~/niuyiming
printf "%s\n" checkpoint-140/config.json checkpoint-140/generation_config.json \
  checkpoint-140/model.safetensors.index.json checkpoint-140/tokenizer.json \
  checkpoint-140/tokenizer_config.json checkpoint-140/vocab.json checkpoint-140/merges.txt \
  checkpoint-140/added_tokens.json checkpoint-140/special_tokens_map.json \
  checkpoint-140/chat_template.jinja \
  checkpoint-140/model-00001-of-00009.safetensors checkpoint-140/model-00002-of-00009.safetensors \
  checkpoint-140/model-00003-of-00009.safetensors checkpoint-140/model-00004-of-00009.safetensors \
  checkpoint-140/model-00005-of-00009.safetensors checkpoint-140/model-00006-of-00009.safetensors \
  checkpoint-140/model-00007-of-00009.safetensors checkpoint-140/model-00008-of-00009.safetensors \
  checkpoint-140/model-00009-of-00009.safetensors > sft_files.txt
setsid nohup python3 -u hf_pull.py Jianwen/Alfworld-7B-SFT \
  ~/niuyiming/checkpoints/Alfworld-7B-SFT sft_files.txt --parallel 3 \
  > ~/niuyiming/pull_sft.out 2>&1 < /dev/null &

# 校验（19/19 全 SHA-OK 才算好）
python3 -u hf_pull.py Jianwen/Alfworld-7B-SFT \
  ~/niuyiming/checkpoints/Alfworld-7B-SFT sft_files.txt --check

# 起服务（注意 --model 指到 checkpoint-140 子目录）
CUDA_VISIBLE_DEVICES=7 ~/miniconda3/envs/vllm/bin/python -m vllm.entrypoints.openai.api_server \
  --model ~/niuyiming/checkpoints/Alfworld-7B-SFT/checkpoint-140 \
  --served-model-name alfworld-sft --port 8001 --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.50
```

#### B. RL checkpoint：先合并 FSDP 再服务

`repos/pulled/SkillRL/scripts/model_merger.py` 正是干这个的，它匹配的文件名
`model_world_size_(\d+)_rank_0.pt` 与该 ckpt 完全一致。**只需 4 个模型分片**
（约 30.5 GB）——`optim` 在 merger 里零引用，61 GB 优化器状态可以完全跳过；
它用 `local_dir` 同时作为 config/tokenizer 来源，而 `actor/` 里这些文件齐全。

```bash
cd ~/niuyiming
printf "%s\n" actor/config.json actor/generation_config.json \
  actor/tokenizer.json actor/tokenizer_config.json actor/vocab.json actor/merges.txt \
  actor/added_tokens.json actor/special_tokens_map.json actor/chat_template.jinja \
  actor/model_world_size_4_rank_0.pt actor/model_world_size_4_rank_1.pt \
  actor/model_world_size_4_rank_2.pt actor/model_world_size_4_rank_3.pt > rl_files.txt
setsid nohup python3 -u hf_pull.py Jianwen/Alfworld-7B-RL \
  ~/niuyiming/checkpoints/Alfworld-7B-RL rl_files.txt --parallel 2 \
  > ~/niuyiming/pull_rl.out 2>&1 < /dev/null &
```

合并时**有两个文档没写的坑，照抄旧命令必定失败**：

```bash
cd ~/niuyiming/SkillEvolvePaperList/repos/pulled/SkillRL
PYTHONPATH=/home/yyk/yyk03/niuyiming/shim \
  ~/miniconda3/envs/vllm/bin/python -u scripts/model_merger.py merge --backend fsdp \
  --local_dir ~/niuyiming/checkpoints/Alfworld-7B-RL/actor \
  --target_dir ~/niuyiming/checkpoints/Alfworld-7B-RL-hf
```

1. **必须有 `merge` 子命令。** 脚本用的是 `add_subparsers(dest="operation", required=True)`，
   旧文档里 `model_merger.py --backend fsdp ...` 会直接死在
   `error: the following arguments are required: operation`。
2. **必须给 `verl` 打 shim。** 脚本第 70 行 `from verl.utils import hf_processor, hf_tokenizer`
   是模块级 import；但用 `python scripts/xxx.py` 起时 `sys.path[0]` 是 `scripts/` 而不是
   仓库根，**仓库里那份 `verl/` 根本不会被 import 到**，报
   `ModuleNotFoundError: No module named 'verl'`。装真 verl 又会拖进 tensordict 等一串依赖，
   而 merger 只用那两个函数，所以用 `~/niuyiming/shim/verl/utils/__init__.py`
   这个最小替身，`PYTHONPATH` 指过去即可（已验证）。

实测合并总耗时约 1 分钟（4 分片并行加载只要 5 s，其余是往 Lustre 写 15.2 GB），
产出 4 分片共 15.2 GB：

```bash
# 起服务（RL 与 SFT 可同时驻留，换卡换端口即可）
CUDA_VISIBLE_DEVICES=6 ~/miniconda3/envs/vllm/bin/python -m vllm.entrypoints.openai.api_server \
  --model ~/niuyiming/checkpoints/Alfworld-7B-RL-hf \
  --served-model-name alfworld-rl --port 8002 --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.50
```

> **`--dtype` 不用加。** 旧文档说"合并出的 config 继承 `actor/config.json` 的
> `dtype: float32`，显存吃紧时加 `--dtype bfloat16`"——实测**不成立**：
> `actor/config.json` 确实是 `float32`，但 merger 落盘时会写成 `bfloat16`
> （实测合并产物 config.json 为 `"dtype": "bfloat16"`），vLLM 按它加载，
> 7B 权重只占 14.25 GiB。**两个 checkpoint 的 config 都是 bfloat16，
> SFT 的 `checkpoint-140/config.json` 也是 bfloat16。**

评测时 `--base-url http://localhost:8001/v1 --model <--served-model-name 的值>`。
**注意 `--base-url` 要带 `/v1`**（harness 会自己补 `/chat/completions`）。

### 起服务的实测要点

- **日志是块缓冲的**：进程起来后日志可能长时间为空，别据此判断失败。
  用 `netstat -tlnp | grep 8001` 看端口是否 LISTEN，或直接打 `/v1/models`。
- **启动耗时（2026-09-15 实测，Lustre 冷读）**：

  | 模型 | 权重加载 | 引擎初始化（KV cache + warmup） | 进程起到就绪 |
  |---|---|---|---|
  | Qwen2.5-0.5B | 0.93 s（0.93 GiB）| 23.4 s | 约 45 s |
  | Alfworld-7B-SFT | 8.5 s（14.25 GiB）| 66.4 s | 约 1.5 min |
  | Alfworld-7B-RL（合并版）| 7.5 s（14.25 GiB）| 62.2 s | 约 2 min（首次含 torch.compile 落盘，第二次会快）|

  即"0.5B 要 2 分钟"的说法偏悲观；真正的瓶颈是引擎初始化而不是读权重。
- 就绪判据（日志里出现即 OK）：
  `INFO ... [launcher.py:36] Route: /v1/chat/completions` 与
  `INFO: Application startup complete.`
- 不设 `--gpu-memory-utilization` 时 vLLM 默认按 0.9 预留；实测 `--gpu-memory-utilization 0.50`
  在 80 GB 卡上占 41339 MiB，7B 足够且给同卡其他人留余量，**共享机器建议用 0.5**；
  冒烟测试可再降到 0.30。
- 停止服务别用宽 pattern 的 `pkill`（会连自己的 ssh 父 shell 一起杀，返回 255）：
  ```bash
  PID=$(pgrep -f "vllm.entrypoints.openai.api_server" | head -1); kill $PID
  ```
  但这行本身也会**匹配到你自己那条 ssh 命令行**（cmdline 里含同样的字符串），
  `pgrep -f` 把 shell 也列进去——多服务并存时按端口挑就很危险。
  用 `^` 锚定到 python 可执行文件路径，shell 的 cmdline 以 `bash -c` 开头，天然不会命中
  （已实测，只列出真正的服务进程）：
  ```bash
  VLLM_PY='^/home/yyk/yyk03/miniconda3/envs/vllm/bin/python -m vllm\.entrypoints'
  pgrep -af "$VLLM_PY"                      # 先看有哪些、各占哪个端口
  for p in $(pgrep -f "$VLLM_PY"); do
    tr '\0' ' ' < /proc/$p/cmdline | grep -q -- "--port 8002" && kill "$p"
  done
  ```
  （这台机器没有 `lsof`，用 `/proc/$p/cmdline` 认端口最可靠。）

### vLLM 链路已端到端验证（2026-09-15）

三个模型都跑通了 **harness → vLLM OpenAI 兼容端点 → GPU** 全链路，
且**两个 SkillRL 7B checkpoint 都已真实下到本地、校验、起服务并跑过 harness**：

| 模型 | GPU/端口 | 下载校验 | harness 结果 |
|---|---|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct` | 7 / 8001 | 7/7 SHA-OK | `api_calls: 50`, `api_errors: 0`, `invalid_action_rate: 0.0`（只验链路）|
| `Alfworld-7B-SFT` | 7 / 8001 | 19/19 SHA-OK | `invalid_action_rate: 0.0`, 50 步 29.9 s |
| `Alfworld-7B-RL`（合并版）| 6 / 8002 | 13/13 SHA-OK | **success=True**, 9 步 7.3 s, `invalid=0` |

复现命令（改 `--base-url` / `--model` 即可切换模型）：

```bash
cd ~/niuyiming/SkillEvolvePaperList/benchmark/alfworld-eval
export ALFWORLD_DATA="$PWD/.data/alfworld"
~/.local/bin/uv run python scripts/run_unified_eval.py \
  --method vanilla --backend api \
  --base-url http://localhost:8001/v1 --model alfworld-sft \
  --split valid_unseen --limit 1
```

说明：

- 0.5B 那行成功率 0.0 是预期的（0.5B 做不了 ALFWorld），它只验证链路；
  `api_errors: 0` + `invalid_action_rate: 0.0` 才是要看的东西。
- RL 合并版**一局就 success=True**，比 SFT 版（50 步未完成）明显更好，
  这是权重确实被正确合并、而不是加载了一堆垃圾的旁证——值得作为合并后的冒烟判据。
- 7B 单集 7–30 s，相对之前走本地中继的 MiniCPM5-2B（单集 204–870 s）快一到两个数量级，
  本机 vLLM 是**优选项**，中继只在需要外部 API 时才用。

补充实测（Server 侧，用于容量规划）：

- **并发**：单卡 7B、16 路并发、每路 256 token，共 4096 completion token / 4.97 s
  ≈ **825 tok/s**；8 路并发 0.36 s 全返回（0.5B）。
- **两模型可并存**：SFT 在卡 7/8001、RL 在卡 6/8002 同时在线互不影响
  （共占 2/8 卡）。这正是「多沙盒并行前先解决中继单点」的替代方案：
  候选模型都常驻本地，评测直接打 `localhost`。

### 部署 search-eval 检索服务（FAISS）

```bash
# 下载 wiki-18 + e5 索引（~60 GB，写入 ~/niuyiming/data/searchR1）
export HF_ENDPOINT=https://hf-mirror.com
SAVE_PATH=~/niuyiming/data/searchR1 \
  ~/.local/bin/uv run python benchmark/search-eval/scripts/download_retriever_assets.sh

# 起检索服务（占用 8000 端口）
cd ~/niuyiming/SkillEvolvePaperList/repos/pulled/SkillRL
bash examples/search/retriever/retrieval_launch.sh
```

vLLM 推理服务用 8001，检索服务用 8000，两者不冲突。

## 长任务运行

通过 `ssh host '...'` 一次性启动时，光用 `nohup ... &` 不够——ssh 会继续等着
继承的 stdout，命令看起来「卡住」。加 `setsid` 并重定向 stdin：

```bash
ssh yyk03@11.11.18.3 'cd <dir> && setsid nohup <cmd> > ~/niuyiming/eval.log 2>&1 < /dev/null & sleep 3; echo launched'
```

**必须加 `-u`（或 `PYTHONUNBUFFERED=1`）**，否则日志中途一直是空的：
Python 往文件写 stdout 默认是块缓冲（8KB）不是行缓冲，8 小时的任务要等进程退出
才 flush，看起来完全像卡死。踩过一次，白等了 10 分钟才反应过来。

```bash
export PYTHONUNBUFFERED=1
setsid nohup ~/.local/bin/uv run python -u scripts/run_unified_eval.py ... \
  > ~/niuyiming/eval.log 2>&1 < /dev/null &
```

**进度只能看日志**：`outputs/<run>/` 要等整个 run 结束才写盘（`save_results` 在最后
才调用），中途目录不存在是正常的，不能拿它判断进度。每条 episode 结束会打印一行
`[i/N] ... success=... invalid=...`。

**全量跑之前先 `--limit 2` 冒烟。** 这次正是靠冒烟跑发现了 split 文件缺失和推理模型
的 `<think>` 拆分问题；否则 134 局跑 8 小时，拿到的是一份 invalid_rate=0.99 的
废数据，还很难判断是 harness bug 还是模型不行。

查看进度：

```bash
ssh yyk03@11.11.18.3 'tail -f ~/niuyiming/eval.log'
```

检查是否在跑：

```bash
ssh yyk03@11.11.18.3 'pgrep -af "run_unified_eval" | grep -v pgrep'
```

> 这台机器**没有 `ss` 和 `lsof`**，只有 `netstat`。用 `ss` 查连接会静默返回空，
> 容易误判成「没有网络请求、进程卡死」。查隧道是否在传数据用：
> `netstat -tnp | grep 18000`（大量 TIME_WAIT = 请求正常完成）。
> 另一个可靠信号是 `/proc/<pid>/stat` 第 14/15 列的 CPU 时间在涨。

### 收工：杀子进程别再留孤儿（2026-09-15 踩过）

**`kill $(pgrep -f 脚本名)` 杀不干净。** `xargs -P` / `bash -c` 派生出的子进程
cmdline 里没有脚本名，父进程死后它们被 init 收养（PPID=1）继续干活——下载脚本会继续
往目标文件写、随时污染重启后的新下载（实测见「大文件必须用 curl 下载」）。

先看清整棵树再动手，注意 `pgrep -f` 会匹配到**你自己这条 ssh 命令行**（命令里出现
目标字符串就自杀，ssh 返回 255）：

```bash
# 用 [ ] 打断字面量，避免匹配到当前命令行自己
ps -u yyk03 -o pid,ppid,etime,cmd | grep -E "hf_[p]ull|cur[l]|one \"\\\$@\""
```

确认后按 PID 连子进程一起收：

```bash
for p in <父PID1> <父PID2>; do
  for c in $(pgrep -P "$p"); do
    pkill -P "$c"; kill "$c"
  done
  kill "$p"
done
# 复查必须为空
ps -u yyk03 -o pid,cmd | awk '/cur[l]/ && /hf-mirror/'
```

## 实测吞吐与并行化决策

MiniCPM5-2B-0822 单机串行跑 alfworld-eval（每集上限 50 步）：

| 方法 | 单集耗时 | 说明 |
|---|---|---|
| vanilla | 204.5s – 870.7s（实测均值 ~540s） | 波动来自推理长度 |
| skillopt | 1341.1s（1 集） | 技能文档给每条 prompt 加 ~1500 token，每步都变慢 |

反直觉的一点：**协议遵守得越好反而越慢**——invalid 低意味着模型真的在长篇推理。
skillopt 单集 1341s × 134 集 ≈ **50 小时**，单机串行不可接受。已决定改为
多沙盒并行，每个沙盒跑一个 shard，本文档的单机串行方案仅作为 fallback 保留。

并行化时注意：per-episode 之间无状态依赖，按 `--items` 切片即可水平扩展；
真正的共享瓶颈是 LLM 端点的并发配额，不是 CPU/内存。

**改用本机 vLLM 跑 SkillRL ckpt 后，上面这张表的结论要重算。**
同一套 alfworld-eval、同样单卡单实例（2026-09-15 实测）：

| 被测模型 | 部署位置 | 单集耗时 | 相对 MiniCPM 中继 |
|---|---|---|---|
| MiniCPM5-2B-0822（外部 API + 本地中继）| 本地→服务器隧道 | 204.5 – 870.7 s | 基准 |
| Alfworld-7B-SFT | 服务器卡 7 / vLLM | 29.9 s（50 步）| 约 7–29× 更快 |
| Alfworld-7B-RL（合并版）| 服务器卡 6 / vLLM | 7.3 s（9 步，成功）| 约 28–119× 更快 |

原因是每一步的往返都从「公网 API + 中继」变成了机内 HTTP。单卡 7B 还能跑出
**825 tok/s**（16 路并发 × 256 token 实测），所以 **134 局不再需要多沙盒**：
粗算 134 × 30 s ≈ 70 min 量级即可跑完，并行化从「必须」降级为「可选优化」。

### 中继是无监督的单点故障

`llm_relay.py` 是个前台单进程，没有 supervisor。这次 skillopt 冒烟跑到第 2 集时
中继自己死了，harness 侧表现为 `RuntimeError: API agent failed after 3 retries:
Remote end closed connection without response`——**日志里看不出是中继挂了还是
端点拒绝**，得回本地 `ps aux | grep llm_relay` 才能区分。

多沙盒并行前必须先解决：中继要么进 supervisor/tmux 自动重启，要么每个沙盒
自带出口。另外 `pkill -f "<pattern>"` 时，如果 pattern 出现在 ssh 远程命令行里，
pkill 会连自己的父 shell 一起杀掉，ssh 返回 255 —— 这不代表 kill 失败，
用短模式（如 `pgrep -af run_unified`）另外确认。

**最彻底的解法是不用中继**：SkillRL 的两个 ckpt 已于 2026-09-15 校验并成功起服务，
只要评测用的是本地 checkpoint，直接 `--base-url http://localhost:8001/v1`（或 8002），
不依赖本地隧道，也就不存在这个单点。中继只在需要调 `llm-center` 那几个外部模型时保留。



以下命令在服务器上执行，`$EP`=端点 URL，`$M`=模型名：

```bash
# searchqa-eval（~10 分钟，1400 条）
cd ~/niuyiming/SkillEvolvePaperList/benchmark/searchqa-eval
~/.local/bin/uv run python scripts/run_unified_eval.py \
  --method skillopt --backend api --base-url $EP --model $M --seed 42

# alfworld-eval（134 条；单机串行实测见下表，已判定太慢，改走多沙盒并行）
# 必须带 --items 指到 SkillOpt 的 134 条 test split，否则报 FileNotFoundError；
# 该文件在 repos/pulled/ 下，记得一并 rsync 上去（只同步 benchmark/ 会漏掉）。
# 非 vanilla 方法还需确认 src/alfworld_eval/skills_docs/ 存在，否则
# load_skill_provider 直接 FileNotFoundError（该目录一开始根本没建）。
cd ~/niuyiming/SkillEvolvePaperList/benchmark/alfworld-eval
export ALFWORLD_DATA="$PWD/.data/alfworld"
~/.local/bin/uv run python scripts/run_unified_eval.py \
  --method skillopt --backend api --base-url $EP --model $M \
  --max-tokens 2048 --temperature 0 --seed 42 \
  --split valid_unseen --record-trajectory

# search-eval（建议先采样，全量 51713 条过大）
cd ~/niuyiming/SkillEvolvePaperList/benchmark/search-eval
~/.local/bin/uv run python scripts/run_unified_eval.py \
  --backend api --base-url $EP --model $M \
  --backend-retriever http --limit-per-dataset 200 --seed 42
```

## 注意事项

1. **LLM 端口转发必须在本地保持连接**：隧道断开后服务器上的 API 调用立刻失败。长任务跑前先确认隧道活着，建议在 tmux 里开隧道。
   **本地 checkpoint 走 vLLM 时不需要隧道**（`localhost:8001`/`8002`），优先用这种方式。
2. **uv 路径**：服务器上 `uv` 在 `~/.local/bin/uv`，不在 PATH 默认位置，调用时写全路径。
3. **pytest 使用 `uv run python -m pytest`**，不要用 `uv run pytest`（会解析到 conda 全局 pytest）。
4. **ALFWorld 必须设环境变量**：`export ALFWORLD_DATA="$PWD/.data/alfworld"` 必须在每次运行前设好。
5. **结果可追溯**：长任务启动前记录一行标记：
   ```bash
   echo "$(date) method=skillopt env=searchqa-eval" >> ~/niuyiming/eval.log
   ```
6. **动 SkillRL 的 ckpt / merger 前先看「部署 SkillRL checkpoint（vLLM）」**：
   merger 需要 `merge` 子命令 + `PYTHONPATH=~/niuyiming/shim`，两个都不是可选参数。
7. **别在没校验的情况下相信已下好的权重**：任何中断过的下载都可能留下"尺寸对、内容错"
   的分片，跑之前用 `hf_pull.py ... --check` 过一遍（几秒钟级别，省掉一次白跑的评测）。
