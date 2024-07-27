import itertools
import re
from collections.abc import Callable
from random import choice, randint, randrange, shuffle

from pilgram.globals import POSITIVE_INTEGER_REGEX

DIRECTIONS = [(1, 0), (0, 1), (-1, 0), (0, -1)]


class MAZE:
    VISITED = -1
    EMPTY = 0
    WALL = 1
    PLAYER = 2
    TRAP_ON = 3
    TRAP_OFF = 4
    END = 5


TILE_REPRESENTATIONS: dict[int, str] = {
    MAZE.EMPTY: "⬜",
    MAZE.WALL: "⬛",
    MAZE.PLAYER: "🧑",
    MAZE.TRAP_ON: "⭕",
    MAZE.TRAP_OFF: "❌",
    MAZE.END: "🏆",
    MAZE.VISITED: "👣"
}


WORDS_FILE_SIZE: int
with open("words.txt", "rb") as f:
    WORDS_FILE_SIZE = sum(1 for _ in f)


def roll(dice_faces: int) -> int:
    return randint(1, dice_faces)


def get_positive_integer_from_string(
        string: str,
        boundaries: tuple[int, int] | None = None,
        exclude: tuple[int, ...] | None = None
) -> int | None:
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
    with open("words.txt") as f:
        return next(itertools.islice(f, index, index + 1), None).rstrip()


def get_word_letters(word: str) -> list[str]:
    result = []
    for letter in word:
        if letter not in result:
            result.append(letter)
    return result


def replace_character_at_string_index(string: str, index: int, char: str) -> str:
    string_list = list(string)
    string_list[index] = char
    return "".join(string_list)


def print_maze(maze) -> str:
    result = ""
    for row in maze:
        result += "".join(TILE_REPRESENTATIONS[tile] for tile in row) + "\n"
    return result


def get_direction_plus_90_degrees(direction_index: int) -> tuple[int, int]:
    return DIRECTIONS[(direction_index + 1) % 4]


def generate_maze(width: int, height: int, trap_probability: int):
    # Initialize the maze grid
    maze = [[MAZE.WALL for _ in range(width)] for _ in range(height)]
    # Start at a random position
    start_x, start_y = choice(((1, 1), (width - 2, 1), (width - 2, height - 2), (1, height - 2)))
    maze[start_y][start_x] = MAZE.PLAYER
    max_depth_reached = 0, (start_x, start_y)
    trap_placing_func: Callable = choice((
        lambda dx, dy: MAZE.TRAP_ON + int((dx + dy) > 0),
        lambda dx, dy: MAZE.TRAP_OFF - int((dx + dy) > 0),
    ))

    def try_placing_trap(x, y, dx, dy):
        if (randint(0, 10) < trap_probability) and (maze[y][x] != MAZE.PLAYER):
            # try to place a trap
            can_place_trap: bool = True
            for index, (dir_y, dir_x) in enumerate(DIRECTIONS):
                if maze[y + dir_y][x + dir_x] == (MAZE.TRAP_ON or MAZE.TRAP_OFF):
                    # don't place traps besides other trap
                    can_place_trap = False
                    break
                p_dir_y, p_dir_x = get_direction_plus_90_degrees(index)
                # print(print_maze(maze))
                if (maze[y + p_dir_y][x + p_dir_x] == MAZE.EMPTY) and (maze[y + dir_y][x + dir_x] == MAZE.EMPTY):
                    # don't place traps on corners
                    can_place_trap = False
                    break
            if can_place_trap:
                # by doing this we are 95% sure the maze will be solvable without taking damage
                maze[y][x] = trap_placing_func(dx, dy)

    def dfs(x, y, depth):
        nonlocal max_depth_reached
        directions = DIRECTIONS[:]
        shuffle(directions)
        for dx, dy in directions:
            new_x, new_y = x + (2 * dx), y + (2 * dy)
            if (0 <= new_x < width) and (0 <= new_y < height) and (maze[new_y][new_x] == MAZE.WALL):
                maze[new_y - dy][new_x - dx] = MAZE.EMPTY
                maze[new_y][new_x] = MAZE.EMPTY
                try_placing_trap(x, y, dx, dy)
                dfs(new_x, new_y, depth + 1)
        if depth > max_depth_reached[0]:
            max_depth_reached = (depth, (x, y))

    # generate maze
    dfs(start_x, start_y, 0)
    # add end goal
    end_x, end_y = max_depth_reached[1]
    maze[end_y][end_x] = MAZE.END
    return maze
