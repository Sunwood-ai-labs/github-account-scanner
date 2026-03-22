from pathlib import Path
import tempfile
import unittest

from github_scan.scheduler import (
    load_env_files,
    resolve_discord_delivery_config,
    should_notify,
    should_notify_with_filters,
)
from github_scan.task_scheduler import build_create_task_command, build_run_task_command


class SchedulerTests(unittest.TestCase):
    def test_should_notify_only_when_changed(self) -> None:
        self.assertTrue(should_notify({"changed": True, "bootstrap": False}))
        self.assertFalse(should_notify({"changed": False, "bootstrap": False}))

    def test_bootstrap_notification_is_opt_in(self) -> None:
        self.assertFalse(should_notify({"changed": False, "bootstrap": True}))
        self.assertTrue(should_notify({"changed": False, "bootstrap": True}, notify_on_bootstrap=True))

    def test_release_only_notification_skips_repository_only_changes(self) -> None:
        report = {
            "changed": True,
            "bootstrap": False,
            "statistics": {"new_release_count": 0},
            "new_releases": [],
        }
        self.assertFalse(should_notify_with_filters(report, release_only=True))

    def test_release_only_notification_allows_release_changes(self) -> None:
        report = {
            "changed": True,
            "bootstrap": False,
            "statistics": {"new_release_count": 1},
            "new_releases": [{"repository": {}, "release": {}}],
        }
        self.assertTrue(should_notify_with_filters(report, release_only=True))

    def test_test_profile_does_not_inherit_production_mention(self) -> None:
        config = resolve_discord_delivery_config(
            profile="test",
            environ={
                "DISCORD_BOT_TOKEN": "bot-token",
                "DISCORD_CHANNEL_ID": "12345",
                "DISCORD_EXPLAINER_USER_ID": "99999",
            },
        )

        self.assertEqual(config["bot_token"], "bot-token")
        self.assertEqual(config["channel_id"], "12345")
        self.assertIsNone(config["mention_user_id"])

    def test_production_profile_inherits_generic_mention(self) -> None:
        config = resolve_discord_delivery_config(
            profile="production",
            environ={
                "DISCORD_BOT_TOKEN": "bot-token",
                "DISCORD_CHANNEL_ID": "12345",
                "DISCORD_EXPLAINER_USER_ID": "99999",
            },
        )

        self.assertEqual(config["mention_user_id"], "99999")

    def test_test_profile_prefers_test_specific_channel(self) -> None:
        config = resolve_discord_delivery_config(
            profile="test",
            environ={
                "DISCORD_BOT_TOKEN": "bot-token",
                "DISCORD_CHANNEL_ID": "12345",
                "DISCORD_TEST_CHANNEL_ID": "77777",
            },
        )

        self.assertEqual(config["channel_id"], "77777")

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
        self.assertIn(r"D:\Prj\Github-scan\.venv\Scripts\python.exe D:\Prj\Github-scan\scripts\run_scheduled_monitor.py", command)

    def test_build_run_task_command(self) -> None:
        self.assertEqual(
            build_run_task_command("github-account-scanner-monitor"),
            ["schtasks", "/Run", "/TN", "github-account-scanner-monitor"],
        )


if __name__ == "__main__":
    unittest.main()
