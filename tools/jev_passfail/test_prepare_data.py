import sys
import unittest
from pathlib import Path

from prepare_data import assign_splits, get_unit_task, row_task_text


class PrepareDataTests(unittest.TestCase):
    def test_expe_route_is_dataset_scoped(self):
        root = Path("/source")
        search_route = root / "repos/pulled/ExpeToSkill/runs/run-a/searchqa/run/routes/final/manifest.json"
        alf_route = root / "repos/pulled/ExpeToSkill/runs/run-a/alfworld/run/routes/final/manifest.json"
        source_index = {
            "routes": [
                {
                    "path": search_route,
                    "dataset": "searchqa",
                    "split": "final",
                    "route_root": tuple(search_route.relative_to(root).parts[:6]),
                    "tasks": {"7": "Search question"},
                },
                {
                    "path": alf_route,
                    "dataset": "alfworld",
                    "split": "final",
                    "route_root": tuple(alf_route.relative_to(root).parts[:6]),
                    "tasks": {"7": "ALFWorld goal"},
                },
            ]
        }
        text, resolver, files = row_task_text(
            "searchqa",
            "ExpeToSkill (expel)",
            "7",
            {"sources": ["repos/pulled/ExpeToSkill/runs/run-a/searchqa/final/scores.jsonl"]},
            root,
            source_index,
        )
        self.assertEqual(text, "Search question")
        self.assertEqual(resolver, "expe_route_dataset_run")
        self.assertEqual(files, [search_route.relative_to(root).as_posix()])

    def test_expe_route_uses_exact_task_id_and_source_split(self):
        root = Path("/source")
        final_route = root / "repos/pulled/ExpeToSkill/runs/run-a/searchqa/run/routes/final/manifest.json"
        admission_route = root / "repos/pulled/ExpeToSkill/runs/run-a/searchqa/run/routes/admission/manifest.json"
        source_index = {
            "routes": [
                {
                    "path": final_route,
                    "dataset": "searchqa",
                    "split": "final",
                    "route_root": tuple(final_route.relative_to(root).parts[:6]),
                    "tasks": {"734": "The exact-id final question", "1734": "A different question"},
                },
                {
                    "path": admission_route,
                    "dataset": "searchqa",
                    "split": "admission",
                    "route_root": tuple(admission_route.relative_to(root).parts[:6]),
                    "tasks": {"734": "The admission-set question"},
                },
            ]
        }
        text, _, files = row_task_text(
            "searchqa",
            "ExpeToSkill (expel)",
            "734",
            {"sources": ["repos/pulled/ExpeToSkill/runs/run-a/searchqa/final-evolve1/scores.jsonl"]},
            root,
            source_index,
        )
        self.assertEqual(text, "The exact-id final question")
        self.assertEqual(files, [final_route.relative_to(root).as_posix()])

    def test_expe_route_does_not_guess_offset_when_exact_id_is_missing(self):
        root = Path("/source")
        route = root / "repos/pulled/ExpeToSkill/runs/run-a/searchqa/run/routes/final/manifest.json"
        source_index = {
            "routes": [{
                "path": route,
                "dataset": "searchqa",
                "split": "final",
                "route_root": tuple(route.relative_to(root).parts[:6]),
                "tasks": {"1734": "A different question"},
            }]
        }
        with self.assertRaisesRegex(ValueError, "exact route lookup yielded 0 values"):
            row_task_text(
                "searchqa",
                "ExpeToSkill (expel)",
                "734",
                {"sources": ["repos/pulled/ExpeToSkill/runs/run-a/searchqa/final-evolve1/scores.jsonl"]},
                root,
                source_index,
            )

    def test_alfworld_skillopt_test_index_maps_to_unit(self):
        root = Path("/source")
        unit_path = root / "units/000000_case.json"
        entry = {
            "path": unit_path,
            "unit": {
                "metadata": {"initial_observation": "Your task is to: put the cup away."},
                "messages": [],
            },
        }
        source_index = {
            "skillgen": {"alfworld": {}, "searchqa": {}},
            "skillgen_by_index": {"alfworld": {0: entry}, "searchqa": {}},
        }
        text, resolver, files = row_task_text(
            "alfworld", "SkillOpt", "test:0000", {}, root, source_index
        )
        self.assertEqual(text, "Your task is to: put the cup away.")
        self.assertEqual(resolver, "skillopt_instance_id_paired_skillgen_unit")
        self.assertEqual(files, ["units/000000_case.json"])
        rethink_text, rethink_resolver, rethink_files = row_task_text(
            "alfworld", "RethinkSkill", "test:0000", {}, root, source_index
        )
        self.assertEqual(rethink_text, text)
        self.assertEqual(rethink_resolver, "rethink_case_id_paired_skillgen_unit")
        self.assertEqual(rethink_files, files)

    def test_unit_task_uses_user_message_only(self):
        task = "## Task\n## Context\nEvidence text\n\n## Question\nWhat is the answer?"
        unit = {
            "messages": [
                {"role": "user", "content": "Skill instructions\n\n" + task},
                {"role": "assistant", "content": "Secret gold answer"},
            ],
            "metadata": {"gold_answers": ["Secret gold answer"]},
        }
        resolved = get_unit_task("searchqa", unit)
        self.assertEqual(resolved, "## Context\nEvidence text\n\n## Question\nWhat is the answer?")
        self.assertNotIn("Secret gold answer", resolved)

    def test_task_group_splits_are_deterministic_and_exclusive(self):
        rows = [
            {"dataset": "searchqa", "task_group": f"searchqa:{i}"}
            for i in range(30)
        ] + [
            {"dataset": "alfworld", "task_group": f"alfworld:{i}"}
            for i in range(20)
        ]
        first = assign_splits(rows, 20260929)
        second = assign_splits(rows, 20260929)
        self.assertEqual(first, second)
        memberships = {
            split: {(row["dataset"], row["task_group"]) for row in values}
            for split, values in first.items()
        }
        self.assertFalse(memberships["train"] & memberships["validation"])
        self.assertFalse(memberships["train"] & memberships["test"])
        self.assertFalse(memberships["validation"] & memberships["test"])


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    unittest.main()
