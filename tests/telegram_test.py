import unittest

from pilgram.classes import Player
from ui.telegram_bot import get_event_notification_string
from ui.utils import UserContext


class TestTelegram(unittest.TestCase):

    def test_event_handling(self):
        context = UserContext({"id": 1234, "username": "ombro"})
        self.assertIsNone(context.get_event_data())
        player = Player.create_default(1234, "ombro", "A really cool guy")
        context.set_event("donation", {"donor": player, "amount": 100, "recipient": player})
        event = context.get_event_data()
        result = get_event_notification_string(event)
        print(result)
