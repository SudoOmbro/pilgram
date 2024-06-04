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


def start_character_creation(context: UserContext) -> str:
    player = DB.get_player_data(context.get("id"))
    if player:
        return f"You already have a character! Their name is {player.name} and they are very sad now :("
    context.start_process("character creation")
    return "Ok, let's start by naming your character. Send me a name"


CC_STEPS: Tuple[str, ...] = (
    "name",
    "description"
)


def character_creation_process(context: UserContext, user_input: str) -> str:
    context.set(CC_STEPS[context.get_process_step()], user_input)
    if context.get_process_step() == len(CC_STEPS):
        context.end_process()
        context.set("player", Player.create_default(
            context.get("id"), context.get("name"), context.get("description")
        ))
        world_name = ContentMeta.get("world.name")
        return f"Your character has been created! Welcome to the world of {world_name}!"
    context.progress_process()
    return f"Ok now send me you character's {CC_STEPS[context.get_process_step()]}"
