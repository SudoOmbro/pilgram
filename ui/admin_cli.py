from typing import Dict, Union, Tuple, Callable

from orm.db import PilgramORMDatabase
from pilgram.generics import PilgramDatabase
from pilgram.globals import PLAYER_NAME_REGEX as PNR, POSITIVE_INTEGER_REGEX as PIR, ContentMeta
from ui.interpreter import CLIInterpreter
from ui.strings import Strings
from ui.utils import UserContext, InterpreterFunctionWrapper as IFW, RegexWithErrorMessage as RWE


MONEY = ContentMeta.get("money.name")


def db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def __do_action(target: object, target_attr: str, action: str, amount: int):
    if action == "add":
        target.__dict__[target_attr] += amount
    elif action == "set":
        target.__dict__[target_attr] = amount
    elif action == "sub":
        target.__dict__[target_attr] -= amount


def operate_on_player(context: UserContext, player_name: str, amount_str: str, target: str = "xp", action: str = "add") -> str:
    player = db().get_player_from_name(player_name)
    if not player:
        return f"player {player_name} does not exist"
    amount = int(amount_str)
    __do_action(player, target, action, amount)
    player.add_xp(0)  # this triggers level ups
    db().update_player_data(player)
    return f"{action} {amount_str} {target} to {player_name} - successful"


def operate_on_guild(context: UserContext, guild_name: str, amount_str: str, target: str = "prestige", action: str = "add") -> str:
    guild = db().get_guild_from_name(guild_name)
    if not guild:
        return f"guild {guild_name} does not exist"
    amount = int(amount_str)
    __do_action(guild, target, action, amount)
    db().update_guild(guild)
    return f"{action} {amount_str} {target} to {guild_name} - successful"


def __generate_int_op_command(target_attr: str, target: str, action: str) -> IFW:
    """ dynamically generate commands & functions based on the three inputs """
    func: Callable = {
        "player": operate_on_player,
        "guild": operate_on_guild
    }.get(target, None)
    assert func is not None
    return IFW([
            RWE(f"{target} name", PNR, Strings.player_name_validation_error),
            RWE("amount", PIR, Strings.invalid_money_amount)
        ],
        func,
        f"{action} {target_attr} to a {target}",
        default_args={"target": target_attr, "action": action}
    )


def add_zone(context: UserContext) -> str:
    # TODO
    pass


ADMIN_COMMANDS: Dict[str, Union[str, IFW, dict]] = {
    "add": {
        "player": {
            "money": __generate_int_op_command("money", "player", "add"),
            "xp": __generate_int_op_command("xp", "player", "add"),
            "gear": __generate_int_op_command("gear_level", "player", "add"),
            "home": __generate_int_op_command("home_level", "player", "add"),
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "add"),
            "prestige": __generate_int_op_command("home", "guild", "add"),
        }
    },
    "set": {
        "player": {
            "money": __generate_int_op_command("money", "player", "set"),
            "xp": __generate_int_op_command("xp", "player", "set"),
            "gear": __generate_int_op_command("gear_level", "player", "set"),
            "home": __generate_int_op_command("home_level", "player", "set"),
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "set"),
            "prestige": __generate_int_op_command("home", "guild", "set"),
        }
    },
    "sub": {
        "player": {
            "money": __generate_int_op_command("money", "player", "sub"),
            "xp": __generate_int_op_command("xp", "player", "sub"),
            "gear": __generate_int_op_command("gear_level", "player", "sub"),
            "home": __generate_int_op_command("home_level", "player", "sub"),
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "sub"),
            "prestige": __generate_int_op_command("home", "guild", "sub"),
        }
    }
}

ADMIN_PROCESSES: Dict[str, Tuple[Callable, ...]] = {

}

ADMIN_INTERPRETER = CLIInterpreter(ADMIN_COMMANDS, ADMIN_PROCESSES)
