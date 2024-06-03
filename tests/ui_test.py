import unittest

from ui.interpreter import context_aware_execute
from ui.utils import UserContext


class TestUi(unittest.TestCase):

    def test_echo_command(self):
        context = UserContext()
        result = context_aware_execute(context, "echo \"hello world\"")
        self.assertEqual(result, "player says: 'hello world'")
        result = context_aware_execute(context, "echo hello world")
        self.assertEqual(result, "player says: 'hello'")
        context = UserContext(dictionary={"username": "ombro"})
        result = context_aware_execute(context, "echo ciao")
        self.assertEqual(result, "ombro says: 'ciao'")
