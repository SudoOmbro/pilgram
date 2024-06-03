import unittest

from ui.interpreter import context_aware_execute
from ui.utils import UserContext, reconstruct_delimited_arguments


class TestUi(unittest.TestCase):

    def test_reconstruct_delimited_arguments(self):
        original_string = "\"Enlist in the helldivers now!\" to \"become a legend!\" NOW!"
        result = reconstruct_delimited_arguments(original_string.split())
        self.assertEqual(result, ['Enlist in the helldivers now!', 'to', 'become a legend!', 'NOW!'])

    def test_echo_command(self):
        context = UserContext()
        result = context_aware_execute(context, "echo \"Hello world\"")
        self.assertEqual(result, "player says: 'Hello world'")
        result = context_aware_execute(context, "echo hello world")
        self.assertEqual(result, "player says: 'hello'")
        context = UserContext(dictionary={"username": "ombro"})
        result = context_aware_execute(context, "echo ciao")
        self.assertEqual(result, "ombro says: 'ciao'")
