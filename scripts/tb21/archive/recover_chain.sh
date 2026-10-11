#!/usr/bin/env bash
# Recovery chain: rerun only the trials lost to infrastructure exceptions.
# Each run is a fresh RUN_ID so recovered arms are separately identifiable.
cd ~/niuyiming/SkillExpand-tbeval || exit 1
. ./env.sh
RUNNER=/data2/niuyiming/scripts/run_tencent_tb21_smoke_niuyiming.sh
LOGS=$HOME/niuyiming/SkillExpand-tbeval/logs
export TBENCH_RUN_MODE=selected TBENCH_EVAL_MODE=bare
export TBENCH_N_CONCURRENT=6 TBENCH_MAX_TRIAL_RETRIES=1
export TBENCH_VERIFIER_OVERRIDE=7200.0
export JOBS_DIR=/data2/niuyiming/e1_recover/jobs
mkdir -p "$JOBS_DIR"

run() {
  local model=$1 effort=$2 runid=$3 nattempts=$4
  shift 4
  echo "[$(date +%F\ %T)] START $runid: $nattempts attempts x $# tasks (model=$model, effort=${effort:-default})"
  MODEL_NAME="$model" TBENCH_N_ATTEMPTS="$nattempts" RUN_ID="$runid" \
    TBENCH_REASONING_EFFORT="$effort" TBENCH_TASK_NAMES="$*" \
    bash "$RUNNER" > "$LOGS/$runid.log" 2>&1
  echo "[$(date +%F\ %T)] END $runid rc=$?"
}

# qwen (target: 2 valid arms per task)
run qwen3.6-flash-distill "" e1_q36flash_rec1 1 \
  build-pov-ray circuit-fibsqrt code-from-image configure-git-webserver \
  extract-moves-from-video feal-linear-cryptanalysis gpt2-codegolf \
  largest-eigenval make-doom-for-mips mteb-retrieve path-tracing \
  qemu-alpine-ssh raman-fitting sanitize-git-repo train-fasttext
run qwen3.6-flash-distill "" e1_q36flash_rec2 2 \
  adaptive-rejection-sampler pytorch-model-recovery \
  torch-pipeline-parallelism torch-tensor-parallelism

# dpsk (target: 5 valid arms per task)
run DEEPSEEK_up5zdj max e1_dsv4max_rec1 1 \
  code-from-image filter-js-from-html fix-git headless-terminal \
  largest-eigenval llm-inference-batching-scheduler pytorch-model-cli regex-log
run DEEPSEEK_up5zdj max e1_dsv4max_rec2 2 \
  configure-git-webserver model-extraction-relu-logits
run DEEPSEEK_up5zdj max e1_dsv4max_rec3 3 \
  mteb-retrieve
run DEEPSEEK_up5zdj max e1_dsv4max_rec4 4 \
  pytorch-model-recovery torch-pipeline-parallelism torch-tensor-parallelism

echo "[$(date +%F\ %T)] CHAIN COMPLETE"
