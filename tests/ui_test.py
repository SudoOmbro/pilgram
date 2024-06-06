import unittest

from ui.interpreter import context_aware_execute
from ui.strings import Strings
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
        context = UserContext({"username": "ombro"})
        result = context_aware_execute(context, "echo ciao")
        self.assertEqual(result, "ombro says: 'ciao'")

    def test_help_function(self):
        print(context_aware_execute(UserContext({"username": "ombro"}), "help"))

    def test_character_creation(self):
        context = UserContext({"id": 1234})
        result = context_aware_execute(context, "create character")
        print(result)
        result = context_aware_execute(context, "Ombro")
        print(result)
        result = context_aware_execute(context, "Really cool guy")
        print(result)

    def test_check_command(self):
        context = UserContext({"id": 0})
        result = context_aware_execute(context, "check self")
        print(result)
        self.assertEqual(result, Strings.no_character_yet)
        context = UserContext({"id": 1234})
        self_result = context_aware_execute(context, "check self")
        print(f"---------\n{self_result}\n---------")
        result = context_aware_execute(context, "check player O")
        print(result)
        ombro_result = context_aware_execute(context, "check player Ombro")
        self.assertEqual(self_result, ombro_result)

    def test_check_board(self):
        context = UserContext({"id": 1234})
        result = context_aware_execute(context, "check board")
        print(result)
