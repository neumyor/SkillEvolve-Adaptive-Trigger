import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))
from train_jev import file_sha256, load_encoded, reconcile_resume, training_data_gate


class FakeTorch:
    def __init__(self, states):
        self.states = states

    def load(self, path, **_kwargs):
        return self.states[str(path)]


class ResumeTests(unittest.TestCase):
    def test_training_data_gate_accepts_filtered_view_audit_schema(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "audit_independent.json").write_text(
                json.dumps({
                    "checks": {"dataset_filter_only": True, "zero_overflow": True},
                    "overflow_examples": 0,
                    "split_counts": {"train": {"examples": 7}},
                }),
                encoding="utf-8",
            )
            (data_dir / "audit.json").write_text(
                json.dumps({
                    "token_audit": {
                        "serve_max_state": 6144,
                        "serve_max_branch": 6144,
                        "serve_max_packed": 6400,
                        "serve_max_branch_semantics": "state_tokens_plus_question_branch_tokens",
                    }
                }),
                encoding="utf-8",
            )
            audit, limits, train_examples = training_data_gate(data_dir)
            self.assertEqual(audit["_normalized_overflow_inputs"], 0)
            self.assertEqual(limits["state"], 6144)
            self.assertEqual(train_examples, 7)

    def test_recovers_complete_checkpoint_written_before_latest_pointer(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "checkpoints").mkdir()
            (root / "validation").mkdir()
            states = {}
            records = []

            for epoch in (1, 2):
                checkpoint = root / "checkpoints" / f"epoch_{epoch:02d}"
                checkpoint.mkdir()
                for name in ("training_state.pt", "head.pt", "adapter_model.safetensors"):
                    (checkpoint / name).write_bytes(f"{epoch}:{name}".encode())
                prediction = root / "validation" / f"epoch_{epoch:02d}.jsonl"
                prediction.write_text(f'{{"epoch":{epoch}}}\n', encoding="utf-8")
                record = {"epoch": epoch, "selected": epoch == 2}
                records.append(record)
                state = {
                    "epoch": epoch,
                    "config_sha256": "config-hash",
                    "data_checksums": {"train": "data-hash"},
                    "validation_prediction": prediction.name,
                    "validation_prediction_sha256": file_sha256(prediction),
                    "epoch_record": record,
                    "best_epoch": epoch,
                    "best_val_nll": 0.5 / epoch,
                }
                states[str(checkpoint / "training_state.pt")] = state

            (root / "latest.json").write_text(
                json.dumps({"checkpoint": "epoch_01", "epoch": 1}), encoding="utf-8"
            )
            (root / "metrics.jsonl").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
            (root / "best.json").write_text(
                json.dumps({"checkpoint": "epoch_01", "epoch": 1}), encoding="utf-8"
            )

            checkpoint, state, events = reconcile_resume(root, FakeTorch(states))

            self.assertEqual(checkpoint.name, "epoch_02")
            self.assertEqual(state["epoch"], 2)
            self.assertEqual([event["epoch"] for event in events], [1, 2])
            self.assertEqual(json.loads((root / "latest.json").read_text())["epoch"], 2)
            self.assertEqual(json.loads((root / "best.json").read_text())["epoch"], 2)

    def test_no_checkpoint_means_resume_can_restart_first_epoch(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint, state, events = reconcile_resume(root, FakeTorch({}))
            self.assertIsNone(checkpoint)
            self.assertIsNone(state)
            self.assertEqual(events, [])

    def test_smoke_limit_only_encodes_first_requested_training_rows(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "train.jsonl"
            rows = [
                {
                    "state_hash": f"state-{index}",
                    "state": f"input-{index}",
                    "n_pass": index,
                    "n_fail": 2 - index,
                    "n_trials": 2,
                    "target_probs": [(2 - index) / 2, index / 2],
                    "dataset": "alfworld" if index < 2 else "searchqa",
                }
                for index in range(3)
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            encoded_states = []

            def encode(_tokenizer, record, **_kwargs):
                encoded_states.append(record["state"])
                return {"ids": [1], "causal_rows": [[1]], "n_opts": [2]}

            selected = load_encoded(path, None, encode, limit=2, distinct_datasets=True)

            self.assertEqual(encoded_states, ["input-0", "input-2"])
            self.assertEqual([entry["row"]["state_hash"] for entry in selected], ["state-0", "state-2"])


if __name__ == "__main__":
    unittest.main()
