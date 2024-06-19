import itertools
import re
from random import randint, randrange
from typing import Union, Tuple, List

from pilgram.globals import POSITIVE_INTEGER_REGEX


WORDS_FILE_SIZE: int
with open("words.txt", "rb") as f:
    WORDS_FILE_SIZE = sum(1 for _ in f)


def roll(dice_faces: int) -> int:
    return randint(1, dice_faces)


def get_positive_integer_from_string(
        string: str,
        boundaries: Union[Tuple[int, int], None] = None,
        exclude: Union[Tuple[int, ...], None] = None
) -> Union[int, None]:
    """
    returns a positive integer from the given string if it passes all checks.
    :param string: the input string
    :param boundaries: the boundaries within which the number must be (boundaries included)
    :param exclude: values that the number must not assume.
    :return: a positive integer if all checks pass, None otherwise.
    """
    if not re.match(POSITIVE_INTEGER_REGEX, string):
        return None
    result = int(string)
    if boundaries and ((result < boundaries[0]) or (result > boundaries[1])):
        return None
    if exclude and (result in exclude):
        return None
    return result


def get_random_word() -> str:
    index: int = randrange(0, WORDS_FILE_SIZE)
    with open("words.txt", "r") as f:
        return next(itertools.islice(f, index, index + 1), None).rstrip()


def get_word_letters(word: str) -> List[str]:
    result = []
    for letter in word:
        if letter not in result:
            result.append(letter)
    return result


def replace_character_at_string_index(string: str, index: int, char: str) -> str:
    string_list = list(string)
    string_list[index] = char
    return "".join(string_list)
