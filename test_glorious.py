# -*- coding: utf-8 -*-
"""Glorious（奥丁）电量协议测试：只验证解析与调度，不需要真实设备。"""
import unittest
from unittest.mock import patch

import core
import glorious_proto as gp
import hid_win as hw
import rog_proto


def reply(status=0xA1, level=57, charging=0, command=0x83):
    packet = bytearray(65)
    packet[1] = status
    packet[3] = 0x02
    packet[4] = 0x02
    packet[6] = command
    packet[7] = charging
    packet[8] = level
    return bytes(packet)


def interface(pid=0x2024, feature_len=65):
    return hw.HidInterface(
        path=f"\\\\?\\hid#vid_258a&pid_{pid:04x}&mi_02&col01#test#{{guid}}",
        vid=0x258A, pid=pid, version=0, usage_page=0xFFFF, usage=0,
        input_len=0, output_len=0, feature_len=feature_len,
        product="Model O- Wireless", manufacturer="Glorious", serial="",
    )


class MatchTests(unittest.TestCase):
    def test_receiver_pid_matches_and_is_not_wired(self):
        spec = gp.match_device(interface())
        self.assertEqual(spec.title, "奥丁 Model O-")
        self.assertFalse(spec.wired)

    def test_cable_pid_matches_and_is_marked_wired(self):
        spec = gp.match_device(interface(0x2013))
        self.assertEqual(spec.title, "奥丁 Model O-")
        self.assertTrue(spec.wired)

    def test_other_report_length_or_vendor_is_ignored(self):
        self.assertIsNone(gp.match_device(interface(feature_len=520)))
        other = interface()
        other.vid = 0x0B05
        self.assertIsNone(gp.match_device(other))

    def test_unknown_sinowealth_pid_is_not_probed(self):
        self.assertIsNone(gp.match_device(interface(0x0112)))


class RequestTests(unittest.TestCase):
    def test_request_is_65_bytes_and_matches_reference_layout(self):
        packet = gp.request_packet(65)
        self.assertEqual(len(packet), 65)
        self.assertEqual(packet[0], 0x00)
        self.assertEqual((packet[3], packet[4], packet[6]), (0x02, 0x02, 0x83))
        self.assertEqual(sum(packet), 0x02 + 0x02 + 0x83)


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.spec = gp.match_device(interface())

    def test_awake_reply_yields_level(self):
        reading = gp.parse_reply(self.spec, reply(level=57))
        self.assertEqual((reading.level, reading.charging, reading.error), (57, False, ""))

    def test_charging_flag_is_read_from_byte_seven(self):
        self.assertTrue(gp.parse_reply(self.spec, reply(level=88, charging=1)).charging)

    def test_cable_connection_counts_as_charging(self):
        spec = gp.match_device(interface(0x2013))
        self.assertTrue(gp.parse_reply(spec, reply(level=99)).charging)

    def test_zero_level_is_not_reported_as_empty_battery(self):
        self.assertEqual(gp.parse_reply(self.spec, reply(level=0)).level, 1)

    def test_out_of_range_level_is_rejected(self):
        self.assertIn("无效电量", gp.parse_reply(self.spec, reply(level=150)).error)

    def test_asleep_and_waking_states_are_distinguished(self):
        self.assertIn("休眠", gp.parse_reply(self.spec, reply(status=0xA4)).error)
        self.assertIn("唤醒", gp.parse_reply(self.spec, reply(status=0xA0)).error)
        self.assertIn("无法识别", gp.parse_reply(self.spec, reply(status=0xB7)).error)

    def test_reply_for_another_command_is_not_treated_as_battery(self):
        self.assertIsNone(gp.parse_reply(self.spec, reply(command=0x82)))
        self.assertIsNone(gp.parse_reply(self.spec, b"\x00\xa1"))


class FakeDevice:
    instances = []

    def __init__(self, replies, write=True):
        self.path = "fake"
        self.write_access = write
        self.replies = list(replies)
        self.written = []
        FakeDevice.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def set_feature_report(self, data):
        self.written.append(bytes(data))

    def get_feature_report(self, report_id, length=None):
        return self.replies.pop(0) if self.replies else bytes(length or 65)


class ReadTests(unittest.TestCase):
    def setUp(self):
        FakeDevice.instances = []

    def test_waking_reply_is_asked_again(self):
        with patch.object(hw, "HidDevice", lambda path, write=False: FakeDevice(
                [reply(status=0xA0), reply(level=42)])), \
                patch("glorious_proto.time.sleep"):
            reading = gp.read_device([interface()])
        self.assertEqual(reading.level, 42)
        self.assertEqual(len(FakeDevice.instances[0].written), 2)

    def test_no_matching_interface_returns_none(self):
        self.assertIsNone(gp.read_device([]))
        self.assertIsNone(gp.read_device([interface(feature_len=520)]))

    def test_read_only_handle_reports_clear_error(self):
        with patch.object(hw, "HidDevice", lambda path, write=False: FakeDevice([reply()], write=False)):
            reading = gp.read_device([interface()])
        self.assertIsNone(reading.level)
        self.assertIn("无法写入查询命令", reading.error)

    def test_unanswered_query_reports_error(self):
        with patch.object(hw, "HidDevice", lambda path, write=False: FakeDevice([b"\x00" * 65, b"\x00" * 65])), \
                patch("glorious_proto.time.sleep"):
            reading = gp.read_device([interface()])
        self.assertIsNone(reading.level)
        self.assertIn("未回复", reading.error)


class CoreDispatchTests(unittest.TestCase):
    def test_mouse_slot_uses_glorious_protocol_first(self):
        with patch("glorious_proto.read_device",
                   return_value=gp.GloriousReading("奥丁 Model O-", 63, False)):
            reading = core.read_mouse([])
        self.assertEqual((reading.key, reading.level, reading.title), ("mouse", 63, "奥丁 Model O-"))

    def test_mouse_slot_falls_back_to_rog_protocol(self):
        with patch("glorious_proto.read_device", return_value=None), \
                patch.object(rog_proto, "read_device",
                             return_value=rog_proto.RogReading("ROG 魔刃 X", 71, False)):
            reading = core.read_mouse([])
        self.assertEqual((reading.level, reading.title), (71, "ROG 魔刃 X"))

    def test_glorious_error_is_kept_without_falling_back(self):
        with patch("glorious_proto.read_device",
                   return_value=gp.GloriousReading("奥丁 Model O-", error="鼠标休眠或未连接")), \
                patch.object(rog_proto, "read_device") as legacy:
            reading = core.read_mouse([])
        legacy.assert_not_called()
        self.assertIsNone(reading.level)
        self.assertIn("休眠", reading.error)

    def test_missing_receiver_reports_absent_without_borrowing_rog_name(self):
        with patch("glorious_proto.read_device", return_value=None), \
                patch.object(rog_proto, "read_device", return_value=None):
            reading = core.read_mouse([])
        self.assertFalse(reading.present)
        self.assertEqual(reading.title, "奥丁 Model O-")
        self.assertNotIn("ROG", reading.title)
        self.assertIn("未找到", reading.error)

    def test_rog_fallback_is_marked_present(self):
        with patch("glorious_proto.read_device", return_value=None), \
                patch.object(rog_proto, "read_device",
                             return_value=rog_proto.RogReading("ROG 魔刃 X", 71, False)):
            reading = core.read_mouse([])
        self.assertTrue(reading.present)
        self.assertEqual(reading.title, "ROG 魔刃 X")


if __name__ == "__main__":
    unittest.main()
