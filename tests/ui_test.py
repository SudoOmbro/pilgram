import unittest
from timeit import timeit

from pilgram.strings import Strings
from ui.functions import USER_COMMANDS, USER_PROCESSES
from ui.interpreter import CLIInterpreter
from ui.utils import UserContext, reconstruct_delimited_arguments

interpreter = CLIInterpreter(USER_COMMANDS, USER_PROCESSES, help_formatting="`{c}`{a}- _{d}_\n\n")


def create_character(character_id: int, name: str):
    context = UserContext({"id": character_id})
    interpreter.context_aware_execute(context, "create character")
    interpreter.context_aware_execute(context, name)
    interpreter.context_aware_execute(context, "Really cool guy")


class TestUi(unittest.TestCase):

    def test_reconstruct_delimited_arguments(self):
        original_string = "\"Enlist in the helldivers now!\" to \"become a legend!\" NOW!"
        result = reconstruct_delimited_arguments(original_string.split())
        self.assertEqual(result, ['Enlist in the helldivers now!', 'to', 'become a legend!', 'NOW!'])

    def test_help_function(self):
        print(interpreter.context_aware_execute(UserContext({"username": "ombro"}), "help"))

    def test_character_creation(self):
        context = UserContext({"id": 12345})
        result = interpreter.context_aware_execute(context, "create character")
        print(result)
        result = interpreter.context_aware_execute(context, "Ombro")
        print(result)
        result = interpreter.context_aware_execute(context, "0")
        print(result)
        result = interpreter.context_aware_execute(context, "Really cool guy")
        print(result)
        result = interpreter.context_aware_execute(context, "check self")
        print(result)

    def test_check_command(self):
        context = UserContext({"id": 0})
        result = interpreter.context_aware_execute(context, "check self")
        print(result)
        self.assertEqual(result, Strings.no_character_yet)
        context = UserContext({"id": 1234})
        self_result = interpreter.context_aware_execute(context, "check self")
        print(f"---------\n{self_result}\n---------")
        result = interpreter.context_aware_execute(context, "check player O")
        print(result)
        ombro_result = interpreter.context_aware_execute(context, "check player Ombro")
        self.assertEqual(self_result, ombro_result)

    def test_check_board(self):
        context = UserContext({"id": 1234})
        result = interpreter.context_aware_execute(context, "check board")
        print(result)

    def test_help_caching(self):
        user_context = UserContext({"id": 1234, "username": "Test"})
        time1 = timeit(lambda: interpreter.context_aware_execute(user_context, "help"))
        time2 = timeit(lambda: interpreter.context_aware_execute(user_context, "help"))
        self.assertTrue(time1 > time2)

    def test_duels(self):
        p1_context = UserContext({"id": 1})
        p2_context = UserContext({"id": 2})
        create_character(1, "Ombro")
        create_character(2, "Cremino")
        result = interpreter.context_aware_execute(p1_context, "duel reject cremino")
        print(result)
        result = interpreter.context_aware_execute(p1_context, "duel invite aaa")
        print(result)
        result = interpreter.context_aware_execute(p1_context, "duel invite cremino")
        print(result)
        result = interpreter.context_aware_execute(p2_context, "duel accept ombro")
        print(result)

