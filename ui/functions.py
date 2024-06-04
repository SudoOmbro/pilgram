from typing import Tuple, Type

from orm.db import PilgramORMDatabase
from pilgram.classes import Player
from pilgram.generics import PilgramDatabase
from pilgram.globals import ContentMeta
from ui.utils import UserContext


DB: PilgramDatabase = PilgramORMDatabase.instance()


def placeholder(context: UserContext) -> str:
    """ temporary placeholder function """
    return "hello world"


def echo(context: UserContext, text) -> str:
    try:
        username = context.get("username")
    except KeyError:
        username = "player"
    return f"{username} says: '{text}'"


def check_self(context: UserContext) -> str:
    try:
        ch = DB.get_player_data(context.get("id"))
        return str(ch)
    except KeyError:
        return "You haven't made a character yet!"


def check_player(context: UserContext, player_name: str) -> str:
    try:
        player = DB.get_player_data(DB.get_player_id_from_name(player_name))
        return str(player)
    except KeyError:
        return f"A player with name {player_name} does not exist"


def start_character_creation(context: UserContext) -> str:
    try:
        player = DB.get_player_data(context.get("id"))
        return f"You already have a character! Their name is {player.name} and they are very sad now :("
    except KeyError:
        context.start_process("character creation")
        return "Ok, let's start by naming your character. Send me a name"


CC_STEPS: Tuple[str, ...] = (
    "name",
    "description"
)


def character_creation_process(context: UserContext, user_input: str) -> str:
    context.set(CC_STEPS[context.get_process_step()], user_input)
    if context.get_process_step() == len(CC_STEPS):
        # finish character creation
        context.end_process()
        player = Player.create_default(
            context.get("id"), context.get("name"), context.get("description")
        )
        world_name = ContentMeta.get("world.name")
        DB.add_player(player)
        return f"Your character has been created! Welcome to the world of {world_name}!"
    context.progress_process()
    return f"Ok now send me you character's {CC_STEPS[context.get_process_step()]}"
