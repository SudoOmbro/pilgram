import unittest

from pilgram.classes import Player, Notification
from pilgram.globals import GlobalSettings
from ui.telegram_bot import (
    PilgramBot,
    _delimit_markdown_entities,
)
from ui.utils import UserContext


class TestTelegram(unittest.TestCase):

    def test_delimit_markdown_entities(self):
        text = "*a_b_c_d*"
        result = _delimit_markdown_entities(text)
        self.assertEqual(result, "\\*a\\_b\\_c\\_d\\*")
        text = "aa__bb"
        result = _delimit_markdown_entities(text)
        self.assertEqual(result, "aa\\_\\_bb")

    def test_telegram_notify(self):
        bot = PilgramBot(GlobalSettings.get("Telegram bot token"))
        player = Player.create_default(633679661, "Ombro", "A really cool guy")
        bot.notify(Notification(player, "test" * 4000))

    def test_telegram_send_file(self):
        bot = PilgramBot(GlobalSettings.get("Telegram bot token"))
        player = Player.create_default(633679661, "Ombro", "A really cool guy")
        bot.send_file(player, "AAA.txt", b"AAAAA", "AAAAA")
