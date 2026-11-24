import ctypes
import unittest
from ctypes import wintypes
from unittest.mock import MagicMock, patch

from core import Reading
from wake_monitor import RawInputHeader, WakeGate, WakeMonitor, device_kind


class WakeTests(unittest.TestCase):
    def test_idle_then_activity_queries_once(self):
        gate = WakeGate()
        self.assertTrue(gate.observe("mouse", now=0))
        for instant in (0.1, 0.2, 2, 10):
            self.assertFalse(gate.observe("mouse", now=instant))
        self.assertTrue(gate.observe("mouse", now=31))
        self.assertFalse(gate.observe("mouse", now=31.1))

    def test_offline_device_input_bypasses_idle_requirement(self):
        gate = WakeGate()
        gate.observe("mouse", now=0)
        self.assertTrue(gate.observe("mouse", missing=True, now=6))
        self.assertFalse(gate.observe("mouse", missing=True, now=6.1))

    def test_only_glorious_mice_match(self):
        self.assertEqual(device_kind(r"\\?\hid#VID_258A&PID_2024&MI_00", 0), "mouse")
        self.assertEqual(device_kind(r"\\?\hid#VID_258A&PID_2013", 0), "mouse")
        self.assertIsNone(device_kind(r"\\?\hid#VID_258A&PID_2024&MI_01", 1))
        self.assertIsNone(device_kind(r"\\?\hid#VID_258A&PID_0112", 1))
        # 已移除的 ROG / 赛睿设备不再被识别。
        self.assertIsNone(device_kind(r"\\?\hid#VID_0B05&PID_1A1A", 0))
        self.assertIsNone(device_kind(r"\\?\hid#VID_1038&PID_12E0", 2))

    def test_native_header_event_and_resume_reach_callback(self):
        api, app, callback = MagicMock(), MagicMock(), MagicMock()
        api.RegisterRawInputDevices.return_value = True
        with patch("wake_monitor.ctypes.WinDLL", return_value=api):
            monitor = WakeMonitor(app, 123, callback, lambda: {"mouse": Reading("mouse", "", "", None)})
        def header_only(handle, command, output, size, header_size):
            self.assertEqual(command, 0x10000005)  # RID_HEADER, never RID_INPUT.
            header = ctypes.cast(output, ctypes.POINTER(RawInputHeader)).contents
            header.kind, header.device = 1, 456
            return ctypes.sizeof(RawInputHeader)
        api.GetRawInputData.side_effect = header_only
        monitor.lookup = lambda handle, raw_type=None: "mouse"
        message = wintypes.MSG()
        message.message, message.lParam = 0xFF, 789
        self.assertEqual(monitor.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message)), (False, 0))
        callback.assert_called_once()
        callback.reset_mock()
        message.message, message.wParam = 0x218, 18
        monitor.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message))
        callback.assert_called_once()
        monitor.close()
        app.removeNativeEventFilter.assert_called_once_with(monitor)


if __name__ == "__main__":
    unittest.main()
