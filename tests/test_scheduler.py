from pathlib import Path
import os
import tempfile
import unittest

from github_scan.scheduler import load_env_files, should_notify
from github_scan.task_scheduler import build_create_task_command, build_run_task_command


class SchedulerTests(unittest.TestCase):
    def test_should_notify_only_when_changed(self) -> None:
        self.assertTrue(should_notify({"changed": True, "bootstrap": False}))
        self.assertFalse(should_notify({"changed": False, "bootstrap": False}))

    def test_bootstrap_notification_is_opt_in(self) -> None:
        self.assertFalse(should_notify({"changed": False, "bootstrap": True}))
        self.assertTrue(should_notify({"changed": False, "bootstrap": True}, notify_on_bootstrap=True))

    def test_load_env_files_keeps_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("DISCORD_CHANNEL_ID=12345\nGITHUB_TOKEN=from-file\n", encoding="utf-8")
            target = {"GITHUB_TOKEN": "already-set"}

            load_env_files((env_path,), environ=target)

        self.assertEqual(target["GITHUB_TOKEN"], "already-set")
        self.assertEqual(target["DISCORD_CHANNEL_ID"], "12345")

    def test_build_create_task_command_uses_python_and_runner(self) -> None:
        command = build_create_task_command(
            task_name="github-account-scanner-monitor",
            python_executable=Path(r"D:\Prj\Github-scan\.venv\Scripts\python.exe"),
            runner_script=Path(r"D:\Prj\Github-scan\scripts\run_scheduled_monitor.py"),
            interval_minutes=15,
            start_time="00:01",
        )

        self.assertIn("/Create", command)
        self.assertIn("MINUTE", command)
        self.assertIn("15", command)
        self.assertIn('"D:\\Prj\\Github-scan\\.venv\\Scripts\\python.exe" "D:\\Prj\\Github-scan\\scripts\\run_scheduled_monitor.py"', command)

    def test_build_run_task_command(self) -> None:
        self.assertEqual(
            build_run_task_command("github-account-scanner-monitor"),
            ["schtasks", "/Run", "/TN", "github-account-scanner-monitor"],
        )


if __name__ == "__main__":
    unittest.main()
