import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import startup
from core import AlertPolicy, Reading, defaults, parse_headset, validate_config


def reading(level, key="mouse", charging=False, error=""):
    return Reading(key, key, key, level, charging, error=error)


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.policy, self.config = AlertPolicy(), defaults()

    def test_first_low_reading_and_equality(self):
        for level in (0, 10, 20):
            self.assertEqual(len(AlertPolicy().evaluate([reading(level)], self.config)), 1)
        self.assertEqual(self.policy.evaluate([reading(21)], self.config), [])

    def test_repeated_polls_do_not_repeat_alert(self):
        self.policy.evaluate([reading(20)], self.config)
        for level in (19, 18, 15, 1, 0):
            self.assertEqual(self.policy.evaluate([reading(level)], self.config), [])

    def test_both_thresholds_are_independent(self):
        self.config["alerts"]["mouse"]["threshold"] = 30
        values = self.policy.evaluate([reading(25), reading(25, "keyboard")], self.config)
        self.assertEqual([r.key for r in values], ["mouse"])

    def test_headset_never_alerts(self):
        self.assertEqual(self.policy.evaluate([reading(0, "headset")], self.config), [])

    def test_disabled_and_charging_devices_do_not_alert(self):
        self.config["alerts"]["mouse"]["enabled"] = False
        self.assertEqual(self.policy.evaluate([reading(1)], self.config), [])
        self.assertEqual(self.policy.evaluate([reading(1, "keyboard", True)], self.config), [])

    def test_offline_and_error_do_not_alert(self):
        self.assertEqual(self.policy.evaluate([reading(None), reading(1, error="offline")], self.config), [])

    def test_recovery_hysteresis(self):
        self.policy.evaluate([reading(20)], self.config)
        for level in (21, 24, 25, 20):
            self.assertEqual(self.policy.evaluate([reading(level)], self.config), [])
        self.policy.evaluate([reading(26)], self.config)
        self.assertEqual(len(self.policy.evaluate([reading(20)], self.config)), 1)

    def test_charging_rearms_after_discharge(self):
        self.policy.evaluate([reading(10)], self.config)
        self.policy.evaluate([reading(12, charging=True)], self.config)
        self.assertEqual(len(self.policy.evaluate([reading(12)], self.config)), 1)

    def test_snooze_does_not_lose_pending_alert(self):
        self.policy.snoozed_until = 1800
        self.assertEqual(self.policy.evaluate([reading(10)], self.config, now=100), [])
        self.assertEqual(len(self.policy.evaluate([reading(10)], self.config, now=1801)), 1)

    def test_invalid_settings_are_sanitized(self):
        self.assertEqual(validate_config(None), defaults())
        self.assertEqual(validate_config({"alerts": []}), defaults())
        value = validate_config({"interval": 0, "dismiss_seconds": -1, "alerts": {
            "mouse": {"threshold": 200}, "keyboard": {"threshold": -5}}})
        self.assertEqual(value["interval"], 60)
        self.assertEqual(value["dismiss_seconds"], 12)
        self.assertEqual(value["alerts"]["mouse"]["threshold"], 99)
        self.assertEqual(value["alerts"]["keyboard"]["threshold"], 1)


class HeadsetTests(unittest.TestCase):
    @staticmethod
    def packet(code, state=8):
        result = bytearray(64)
        result[:2] = b"\x06\xb0"
        result[6], result[15] = code, state
        return bytes(result)

    def test_nine_steps(self):
        for raw, percent in enumerate((0, 13, 25, 38, 50, 63, 75, 88, 100)):
            self.assertEqual(parse_headset(self.packet(raw)), (percent, False, ""))

    def test_charging(self):
        self.assertEqual(parse_headset(self.packet(7, 2)), (88, True, ""))

    def test_offline_invalid_and_unrelated(self):
        for raw in (self.packet(7, 1), self.packet(9), self.packet(7, 0), b"\0" * 64,
                    self.packet(7)[:12]):
            self.assertIsNone(parse_headset(raw)[0])
            self.assertTrue(parse_headset(raw)[2])


class StartupTests(unittest.TestCase):
    def test_startup_uses_current_user_run_key(self):
        self.assertEqual(startup.RUN_KEY, r"Software\Microsoft\Windows\CurrentVersion\Run")
        self.assertEqual(startup.VALUE_NAME, "ChargeDock")

    def test_enabling_outside_a_frozen_build_explains_why(self):
        with patch.object(startup.sys, "frozen", False, create=True):
            with self.assertRaises(RuntimeError):
                startup.set_startup(True)


if __name__ == "__main__":
    unittest.main()
