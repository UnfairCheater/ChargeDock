import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import hid_win
from core import Reading, MODELS
from polling import RetrySchedule
from chargedock import arguments


def good(key="mouse"):
    return Reading(key, key, key, 50, present=True)


class EnumerationTests(unittest.TestCase):
    def test_round_enumerates_only_once_and_reports_absent(self):
        with patch.object(hid_win, "enumerate_hid", return_value=[]) as enum:
            readings = core.read_all()
        enum.assert_called_once()
        self.assertEqual([r.key for r in readings], list(MODELS))
        self.assertEqual(len(readings), 1)
        self.assertIsNone(readings[0].level)
        self.assertFalse(readings[0].present)
        self.assertTrue(readings[0].error)

    def test_empty_or_invalid_request_does_not_access_devices(self):
        with patch.object(hid_win, "enumerate_hid") as enum:
            self.assertEqual(core.read_all([]), [])
            for keys in (["no-device"], ["mouse", "mouse"]):
                with self.assertRaises(ValueError):
                    core.read_all(keys)
            enum.assert_not_called()

    def test_inventory_failure_reports_error_and_keeps_the_card(self):
        with patch.object(hid_win, "enumerate_hid", side_effect=OSError("offline")) as enum:
            readings = core.read_all()
        enum.assert_called_once()
        self.assertEqual(len(readings), 1)
        self.assertIn("offline", readings[0].error)
        # 枚举失败时不知道插没插，卡片保留并显示错误。
        self.assertTrue(readings[0].present)

    def test_device_read_failure_is_reported_without_crashing(self):
        with patch.object(hid_win, "enumerate_hid", return_value=[]), \
                patch.object(core, "read_device", side_effect=OSError("boom")):
            readings = core.read_all()
        self.assertIn("boom", readings[0].error)
        self.assertTrue(readings[0].present)

    def test_present_reading_passes_through(self):
        with patch.object(hid_win, "enumerate_hid", return_value=[]), \
                patch.object(core, "read_device", return_value=good()):
            readings = core.read_all()
        self.assertEqual(readings[0].level, 50)
        self.assertTrue(readings[0].present)

    def test_cli_key_and_json_roundtrip(self):
        with patch.object(sys, "argv", ["chargedock", "--poll-key", "mouse"]):
            self.assertEqual(arguments().poll_key, ["mouse"])
        with patch.object(sys, "argv", ["chargedock", "--poll-key", "keyboard"]):
            with self.assertRaises(SystemExit):
                arguments()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "result.json"
            with patch.object(core, "read_all", return_value=[good()]) as read:
                core.poll_to_file(path, ["mouse"])
                read.assert_called_once_with(["mouse"])
            self.assertEqual(len(core.read_poll_file(path, ["mouse"])), 1)
            with self.assertRaises(ValueError):
                core.read_poll_file(path, ["keyboard"])


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.schedule = RetrySchedule(MODELS, lambda: self.now)

    def test_failed_device_exponentially_backs_off_and_caps(self):
        delays = []
        for _ in range(10):
            self.schedule.record([], ["mouse"], 60)
            delay = self.schedule.deadlines["mouse"] - self.now
            delays.append(delay)
            self.now += delay
        self.assertEqual(delays, [5, 10, 20, 40, 80, 160, 300, 300, 300, 300])

    def test_success_resets_failures_and_returns_to_normal_interval(self):
        self.schedule.record([], ["mouse"], 60)
        self.now = 5
        self.schedule.record([good()], ["mouse"], 120)
        self.assertEqual(self.schedule.failures["mouse"], 0)
        self.assertEqual(self.schedule.deadlines["mouse"], 125)

    def test_wake_resets_the_deadline(self):
        self.schedule.record([], ["mouse"], 60)
        self.assertEqual(self.schedule.failures["mouse"], 1)
        self.schedule.reset(["mouse"])
        self.assertEqual(self.schedule.failures["mouse"], 0)
        self.assertEqual(self.schedule.due(), ["mouse"])

    def test_interval_change_preserves_failed_deadline(self):
        self.schedule.record([], ["mouse"], 60)
        self.schedule.change_interval(300)
        self.assertEqual(self.schedule.deadlines["mouse"], 5)

    def test_interval_change_applies_after_success(self):
        self.schedule.record([good()], ["mouse"], 60)
        self.schedule.change_interval(300)
        self.assertEqual(self.schedule.deadlines["mouse"], 300)

    def test_due_keys_obey_deadlines_without_busy_loop(self):
        self.schedule.record([good()], list(MODELS), 60)
        self.assertEqual(self.schedule.due(), [])
        self.assertGreaterEqual(self.schedule.delay_ms(), 60000)
        self.now = 60
        self.assertEqual(self.schedule.due(), list(MODELS))

    def test_invalid_reading_counts_as_failure(self):
        reading = good()
        reading.error = "bad reply"
        self.schedule.record([reading], ["mouse"], 60)
        self.assertEqual(self.schedule.failures["mouse"], 1)


if __name__ == "__main__":
    unittest.main()
