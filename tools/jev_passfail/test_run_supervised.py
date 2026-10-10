import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).with_name("run_supervised.py")


class SupervisorTests(unittest.TestCase):
    def test_detached_child_persists_pid_status_and_log(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pid_file = root / "job.pid.json"
            status_file = root / "job.status.json"
            log_file = root / "job.log"
            started = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--pid-file", str(pid_file),
                    "--status-file", str(status_file),
                    "--log-file", str(log_file),
                    "--poll-seconds", "0.05",
                    "--",
                    sys.executable,
                    "-c",
                    "print('supervised-child-ok', flush=True)",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertIn("supervisor_pid", json.loads(started.stdout))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if status_file.exists() and json.loads(status_file.read_text())["state"] == "complete":
                    break
                time.sleep(0.05)
            pid = json.loads(pid_file.read_text())
            status = json.loads(status_file.read_text())
            self.assertGreater(pid["supervisor_pid"], 0)
            self.assertGreater(pid["child_pid"], 0)
            self.assertEqual(status["state"], "complete")
            self.assertEqual(status["exit_code"], 0)
            self.assertIn("supervised-child-ok", log_file.read_text())


if __name__ == "__main__":
    unittest.main()
