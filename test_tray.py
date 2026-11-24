# -*- coding: utf-8 -*-
"""常驻显示测试：托盘数字图标、右下角浮标、开关保存。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, QSize
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import core
from core import Reading, defaults, validate_config
from icons import level_icon, level_pixmap, readable_text, symbol
from ui import Badge, Controller, PALETTES, badge_position, covers_screen


def pixels(pixmap):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(data)


class IconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_readable_text_flips_with_background_luminance(self):
        self.assertEqual(readable_text(PALETTES["light"]["accent"]), "#ffffff")
        self.assertEqual(readable_text(PALETTES["dark"]["accent"]), "#10181a")

    def test_pixmap_is_square_and_draws_the_number(self):
        painted = level_pixmap(19, PALETTES["light"]["accent"], size=32)
        self.assertEqual((painted.width(), painted.height()), (32, 32))
        empty = level_pixmap(None, PALETTES["light"]["accent"], size=32)
        self.assertNotEqual(pixels(painted), pixels(empty))

    def test_low_battery_uses_a_different_colour(self):
        normal = level_pixmap(80, PALETTES["light"]["accent"])
        low = level_pixmap(80, PALETTES["light"]["danger"])
        self.assertNotEqual(pixels(normal), pixels(low))

    def test_three_digit_level_fits_ahead_of_100(self):
        self.assertEqual(level_pixmap(100, PALETTES["light"]["accent"]).size(),
                         level_pixmap(9, PALETTES["light"]["accent"]).size())

    def test_icon_ships_multiple_sizes_for_any_dpi(self):
        icon = level_icon(42, PALETTES["light"]["accent"])
        self.assertFalse(icon.isNull())
        self.assertFalse(icon.pixmap(16, 16).isNull())
        self.assertFalse(icon.pixmap(48, 48).isNull())


class ConfigTests(unittest.TestCase):
    def test_new_toggles_default_to_on_with_old_config(self):
        self.assertIs(defaults()["tray_percent"], True)
        self.assertIs(defaults()["badge"], True)
        migrated = validate_config({"interval": 60})
        self.assertIs(migrated["tray_percent"], True)
        self.assertIs(migrated["badge"], True)

    def test_non_boolean_values_are_rejected(self):
        value = validate_config({"tray_percent": "yes", "badge": 1})
        self.assertIs(value["tray_percent"], False)
        self.assertIs(value["badge"], False)


class BadgePositionTests(unittest.TestCase):
    """浮标必须落在任务栏条内部，而不是浮在它上方。"""

    def test_badge_sits_left_of_the_clock_inside_the_bar(self):
        taskbar = QRect(0, 1392, 2560, 48)
        point = badge_position(QSize(64, 26), taskbar, tray_left=1980)
        self.assertEqual(point.x(), 1980 - 64 - 8)
        self.assertEqual(point.y(), 1392 + (48 - 26) // 2)
        self.assertTrue(taskbar.contains(QRect(point, QSize(64, 26))))

    def test_without_tray_rect_it_stays_inside_the_taskbar(self):
        taskbar = QRect(0, 1392, 2560, 48)
        point = badge_position(QSize(64, 26), taskbar)
        self.assertTrue(taskbar.contains(QRect(point, QSize(64, 26))))

    def test_vertical_taskbar_keeps_it_inside_the_strip(self):
        taskbar = QRect(2512, 0, 48, 1440)
        point = badge_position(QSize(40, 26), taskbar)
        self.assertTrue(taskbar.contains(QRect(point, QSize(40, 26))))


class FullscreenTests(unittest.TestCase):
    def test_fullscreen_game_hides_the_badge(self):
        screen = QRect(0, 0, 2560, 1440)
        self.assertTrue(covers_screen(QRect(0, 0, 2560, 1440), screen))
        self.assertTrue(covers_screen(QRect(0, -8, 2560, 1456), screen))

    def test_windowed_app_and_desktop_do_not(self):
        screen = QRect(0, 0, 2560, 1440)
        self.assertFalse(covers_screen(QRect(100, 100, 1200, 900), screen))
        self.assertFalse(covers_screen(QRect(0, 0, 2560, 1200), screen))
        self.assertFalse(covers_screen(None, screen))


class BadgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.directory = Path(self.folder.name)
        (self.directory / "settings.json").write_text('{"language":"zh-CN"}', encoding="utf-8")
        self.server = QLocalServer()
        self.server.listen("ChargeDock-badge-" + uuid.uuid4().hex)
        args = SimpleNamespace(data_dir=self.directory, snapshot=None, snapshot_theme="light",
                               background=True, smoke_test=None)
        self.controller = Controller(self.app, args, self.server)
        self.badge = self.controller.badge

    def tearDown(self):
        self.controller.cleanup()
        self.app.processEvents()
        self.folder.cleanup()

    def feed(self, level=64, charging=False):
        self.controller.receive([Reading("mouse", "奥丁 Model O-", "", level, charging, present=True),
                                 Reading("keyboard", "夜魔", "", None),
                                 Reading("headset", "赛睿耳机", "", None)], "")
        self.app.processEvents()

    def test_badge_shows_percentage_and_follows_settings(self):
        self.feed(64)
        self.assertEqual(self.badge.text.text(), "64%")
        self.assertTrue(self.badge.allowed)

    def test_turning_badge_off_hides_it_and_saves(self):
        self.feed(64)
        self.controller.setting("badge", False)
        self.app.processEvents()
        self.assertFalse(self.badge.isVisible())
        saved = json.loads((self.directory / "settings.json").read_text(encoding="utf-8"))
        self.assertIs(saved["badge"], False)

    def test_tray_icon_carries_the_number_and_switches_back_to_logo(self):
        self.feed(64)
        numbered = pixels(self.controller.tray.icon().pixmap(32, 32))
        self.controller.setting("tray_percent", False)
        self.app.processEvents()
        logo = pixels(self.controller.tray.icon().pixmap(32, 32))
        self.assertNotEqual(numbered, logo)
        self.controller.setting("tray_percent", True)
        self.app.processEvents()
        self.assertEqual(pixels(self.controller.tray.icon().pixmap(32, 32)), numbered)

    def test_low_battery_switches_badge_to_alert_colour(self):
        self.feed(12)
        self.assertIn("12%", self.badge.text.text())
        self.assertEqual(self.badge.fill, self.controller.panel.colors["danger"])

    def test_badge_paints_a_filled_background(self):
        self.feed(64)
        image = self.badge.grab().toImage()
        self.assertGreater(image.width(), 20)
        self.assertEqual(image.pixelColor(image.width() // 2, 3).alpha(), 255)

    def test_unknown_level_is_not_shown_as_zero(self):
        self.feed(None)
        self.assertEqual(self.badge.text.text(), "—")

    def test_only_one_tray_icon_exists(self):
        self.assertEqual(len(self.controller.findChildren(QSystemTrayIcon)), 1)

    def test_nothing_connected_hides_every_card_and_the_badge(self):
        self.controller.receive([
            Reading("mouse", "奥丁 Model O-", "", error="未找到奥丁接收器或 USB 连接"),
            Reading("keyboard", "夜魔", "", error="未找到对应的接收器或 USB 连接"),
            Reading("headset", "赛睿耳机", "", error="未找到耳机基站")], "")
        self.app.processEvents()
        panel = self.controller.panel
        self.assertFalse(self.badge.isVisible())
        self.assertFalse(panel.cards["mouse"].isVisibleTo(panel))
        self.assertTrue(panel.empty_notice.isVisibleTo(panel))
        self.assertIn("未检测到设备", panel.empty_notice.text())
        # 托盘回到应用图标，不再显示一个空的电量数字。
        colors = self.controller.panel.colors
        expected = pixels(symbol("tray", colors["accent"], 32).pixmap(32, 32))
        self.assertEqual(pixels(self.controller.tray.icon().pixmap(32, 32)), expected)

    def test_plugging_the_receiver_back_shows_the_card_again(self):
        self.feed(64)
        panel = self.controller.panel
        self.assertTrue(panel.cards["mouse"].isVisibleTo(panel))
        self.assertFalse(panel.empty_notice.isVisibleTo(panel))


if __name__ == "__main__":
    unittest.main()
