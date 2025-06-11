import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from random import randint
from typing import Any

from AI.chatgpt import ChatGPTAPI, ChatGPTGenerator
from orm.db import PilgramORMDatabase
from pilgram.classes import Artifact, EnemyMeta, Quest, Zone, ZoneEvent
from pilgram.combat_classes import Damage
from pilgram.equipment import Equipment, EquipmentType, ConsumableItem
from pilgram.generics import PilgramDatabase
from pilgram.globals import PLAYER_NAME_REGEX as PNR
from pilgram.globals import POSITIVE_INTEGER_REGEX as PIR
from pilgram.globals import YES_NO_REGEX, ContentMeta, GlobalSettings
from pilgram.strings import Strings
from ui.interpreter import CLIInterpreter
from ui.utils import InterpreterFunctionWrapper as IFW, player_arg, integer_arg
from ui.utils import RegexWithErrorMessage as RWE
from ui.utils import UserContext

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
    }.get(target)
    assert func is not None
    return IFW([
            RWE(f"{target} name", PNR, Strings.player_name_validation_error),
            RWE("amount", PIR, Strings.invalid_money_amount)
        ],
        func,
        f"{action} {target_attr} to a {target}",
        default_args={"target": target_attr, "action": action}
    )


def start_add_obj_process(context: UserContext, obj_type: str = "zone") -> str:
    try:
        target_object = {
            "zone": Zone.get_empty(),
            "quest": Quest.get_empty(),
            "event": ZoneEvent.get_empty(),
            "artifact": Artifact.get_empty(),
            "enemy": EnemyMeta.get_empty(Zone.get_empty())
        }.get(obj_type)
        context.set("type", obj_type)
        context.set("obj", target_object)
        context.start_process(f"add {obj_type}")
        context.set("Ptype", "add")
        return context.get_process_prompt(ADMIN_PROCESSES)
    except Exception as e:
        return str(e)


def start_edit_obj_process(context: UserContext, obj_id: int, obj_type: str = "zone") -> str:
    try:
        target_object = {
            "zone": lambda: db().get_zone(obj_id),
            "quest": lambda: db().get_quest(obj_id),
            "event": lambda: db().get_zone_event(obj_id),
            "artifact": lambda: db().get_artifact(obj_id),
            "enemy": lambda: db().get_enemy_meta(obj_id)
        }.get(obj_type)()
        context.set("type", obj_type)
        context.set("obj", target_object)
        context.start_process(f"edit {obj_type}")
        context.set("Ptype", "edit")
        print(target_object.__dict__)
        return context.get_process_prompt(ADMIN_PROCESSES)
    except Exception as e:
        return str(e)


def _progress(context: UserContext) -> str:
    context.progress_process()
    return context.get_process_prompt(ADMIN_PROCESSES)


class ProcessGetObjStrAttr:

    def __init__(self, target_attr: str):
        self.target_attr = target_attr

    def __call__(self, context: UserContext, user_input: str) -> str:
        if (user_input == "") and (context.get("Ptype") == "edit"):
            return f"{context.get('type')} {self.target_attr} not edited.\n" + _progress(context)
        obj = context.get("obj")
        obj.__dict__[self.target_attr] = user_input
        print(obj.__dict__)
        return _progress(context)


class ProcessGetObjIntAttr(ProcessGetObjStrAttr):

    def __call__(self, context: UserContext, user_input: str) -> str:
        if (user_input == "") and (context.get("Ptype") == "edit"):
            return f"{context.get('type')} {self.target_attr} not edited.\n" + _progress(context)
        obj = context.get("obj")
        try:
            obj.__dict__[self.target_attr] = int(user_input)
            print(obj.__dict__)
        except Exception as e:
            return str(e)
        return _progress(context)


class ProcessGetObjJsonAttr:

    def __init__(self, target_attr: str, convert_into: Any = None):
        """
        :param target_attr: the name of the object attribute to set
        :param convert_into: the class to convert the object to. Must have "load_from_json" method.
        """
        self.target_attr = target_attr
        self.convert_into = convert_into

    def __call__(self, context: UserContext, user_input: str) -> str:
        if (user_input == "") and (context.get("Ptype") == "edit"):
            return f"{context.get('type')} {self.target_attr} not edited.\n" + _progress(context)
        obj = context.get("obj")
        try:
            value = json.loads(user_input.replace("'", "\""))
            if self.convert_into:
                value = self.convert_into.load_from_json(value)
            obj.__dict__[self.target_attr] = value
        except Exception as e:
            return str(e)
        print(obj.__dict__)
        return _progress(context)


def process_obj_add_confirm(context: UserContext, user_input: str) -> str:
    if not re.match(YES_NO_REGEX, user_input):
        return Strings.yes_no_error
    obj_type = context.get("type")
    obj = context.get("obj")
    if user_input == "y":
        func: Callable = {
            "zone": lambda: db().add_zone(obj),
            "quest": lambda: db().add_quest(obj),
            "event": lambda: db().add_zone_event(obj),
            "artifact": lambda: db().add_artifact(obj),
            "enemy": lambda: db().add_enemy_meta(obj)
        }.get(obj_type)
        func()
        context.end_process()
        return f"{obj_type} added successfully"
    context.end_process()
    return f"{obj_type} add process cancelled"


def process_obj_edit_confirm(context: UserContext, user_input: str) -> str:
    if not re.match(YES_NO_REGEX, user_input):
        return Strings.yes_no_error
    obj_type = context.get("type")
    obj = context.get("obj")
    if user_input == "y":
        func: Callable = {
            "zone": lambda: db().update_zone(obj),
            "quest": lambda: db().update_quest(obj),
            "event": lambda: db().update_zone_event(obj),
            "artifact": lambda: db().update_artifact(obj, None),
            "enemy": lambda: db().update_enemy_meta(obj)
        }.get(obj_type)
        func()
        context.end_process()
        return f"{obj_type} edited successfully"
    context.end_process()
    return f"{obj_type} edit process cancelled"


def process_quest_add_zone(context: UserContext, user_input: str) -> str:
    if (user_input == "") and (context.get("Ptype") == "edit"):
        return f"{context.get('type')} zone_id not edited.\n" + _progress(context)
    quest: Quest = context.get("obj")
    try:
        zone_id = int(user_input)
        zone = db().get_zone(zone_id)
        num = db().get_quests_counts()[zone.zone_id - 1]
        quest.zone = zone
        quest.num = num
        print(quest.__dict__)
        return _progress(context)
    except Exception as e:
        return str(e)


def process_event_add_zone(context: UserContext, user_input: str) -> str:
    if (user_input == "") and (context.get("Ptype") == "edit"):
        return f"{context.get('type')} zone_id not edited.\n" + _progress(context)
    event: ZoneEvent = context.get("obj")
    try:
        zone_id = int(user_input)
        zone = db().get_zone(zone_id)
        event.zone = zone
        print(event.__dict__)
        return _progress(context)
    except Exception as e:
        return str(e)


def process_enemy_add_zone(context: UserContext, user_input: str) -> str:
    if (user_input == "") and (context.get("Ptype") == "edit"):
        return f"{context.get('type')} zone_id not edited.\n" + _progress(context)
    enemy: EnemyMeta = context.get("obj")
    try:
        zone_id = int(user_input)
        zone = db().get_zone(zone_id)
        enemy.zone = zone
        print(enemy.__dict__)
        return _progress(context)
    except Exception as e:
        return str(e)


def force_generate_zone_events(context: UserContext, zone_id_str: str) -> str:
    generator = ChatGPTGenerator(ChatGPTAPI(
        GlobalSettings.get("ChatGPT token"),
        "gpt-3.5-turbo"
    ))
    try:
        zone_id = int(zone_id_str)
        zone = db().get_zone(zone_id)
        events = generator.generate_zone_events(zone)
        db().add_zone_events(events)
        return f"Zone events for zone '{zone.zone_name}' generated successfully"
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="zone")
    except Exception as e:
        return str(e)


def force_generate_enemy_metas(context: UserContext, zone_id_str: str) -> str:
    generator = ChatGPTGenerator(ChatGPTAPI(
        GlobalSettings.get("ChatGPT token"),
        "gpt-3.5-turbo"
    ))
    try:
        zone_id = int(zone_id_str)
        zone = db().get_zone(zone_id)
        enemy_metas = generator.generate_enemy_metas(zone)
        for enemy_meta in enemy_metas:
            try:
                db().add_enemy_meta(enemy_meta)
            except Exception as e:
                print(e)
        return f"Enemy metas for zone '{zone.zone_name}' generated successfully"
    except KeyError:
        return Strings.obj_does_not_exist.format(obj="zone")
    except Exception as e:
        return str(e)


def give_player_eldritch_power(context: UserContext, player_name: str) -> str:
    player = db().get_player_from_name(player_name)
    player.last_cast = datetime.now() - timedelta(weeks=1)
    db().update_player_data(player)
    return f"recharged eldritch power for player '{player.name}'."


def force_update(context: UserContext, player_name: str) -> str:
    player = db().get_player_from_name(player_name)
    ac = db().get_player_adventure_container(player)
    db().update_quest_progress(ac, datetime.now() - timedelta(hours=1))
    return f"Force update for player {player_name}: success"


def force_quest_complete(context: UserContext, player_name: str) -> str:
    player = db().get_player_from_name(player_name)
    ac = db().get_player_adventure_container(player)
    ac.finish_time = datetime.now() - timedelta(hours=1)
    db().update_quest_progress(ac, last_update=datetime.now() - timedelta(hours=1))
    return f"Force quest complete for player {player_name}: success"


def force_quest_end_time(context: UserContext, player_name: str, hours: str) -> str:
    player = db().get_player_from_name(player_name)
    ac = db().get_player_adventure_container(player)
    ac.finish_time = datetime.now() + timedelta(hours=int(hours))
    db().update_quest_progress(ac)
    return f"Force quest end time for player {player_name}: success ({ac.finish_time})"


def give_random_item_to_player(context: UserContext, player_name: str) -> str:
    player = db().get_player_from_name(player_name)
    items = db().get_player_items(player.player_id)
    item = Equipment.generate(player.level, EquipmentType.get_random(), randint(0, 3))
    item_id = db().add_item(item, player)
    item.equipment_id = item_id
    items.append(item)
    return f"Added '{item.name}' to player '{player_name}'."


def give_item_to_player(
        context: UserContext,
        player_name: str,
        item_type_str: str,
        item_level_str: str,
        item_rarity_str: str
) -> str:
    player = db().get_player_from_name(player_name)
    items = db().get_player_items(player.player_id)
    item_type_id = int(item_type_str)
    item_level = int(item_level_str)
    item_rarity = int(item_rarity_str)
    item = Equipment.generate(item_level, EquipmentType.get(item_type_id), item_rarity)
    item_id = db().add_item(item, player)
    item.equipment_id = item_id
    items.append(item)
    return f"Added '{item.name}' to player '{player_name}'."


def give_consumable_to_player(
        context: UserContext,
        player_name: str,
        consumable_type_str: str
) -> str:
    player = db().get_player_from_name(player_name)
    if len(player.satchel) >= player.get_max_satchel_items():
        return f"{player.name}'s Satchel is already full!"
    consumable: ConsumableItem = ConsumableItem.get(int(consumable_type_str))
    player.satchel.append(consumable)
    db().update_player_data(player)
    return f"Added '{consumable.name}' to player '{player_name}'."


def reset_guild_tourney(context: UserContext) -> str:
    """manually reset guild tourney scores"""
    db().reset_all_guild_scores()
    return "Successfully reset all guild tourney scores."


def restore_player_last_switch(context: UserContext, player_name: str) -> str:
    """ set the player's guild """
    player = db().get_player_from_name(player_name)
    if player is None:
        return Strings.obj_does_not_exist.format(obj="player")
    player.last_guild_switch = datetime.now() - timedelta(days=2)
    db().update_player_data(player)
    return f"Recharged last switch for player {player.name}"


def set_player_essences(context: UserContext, player_name: str, essences_string: str) -> str:
    player = db().get_player_from_name(player_name)
    if player is None:
        return Strings.obj_does_not_exist.format(obj="player")
    for essence_string in essences_string.split(","):
        zone_str, value_str = essence_string.split(":")
        player.essences[int(zone_str)] = int(value_str)
    db().update_player_data(player)
    return f"set player {player.name} essences to {player.essences}"


def set_player_stats(context: UserContext, player_name: str, stat_string: str) -> str:
    player = db().get_player_from_name(player_name)
    if player is None:
        return Strings.obj_does_not_exist.format(obj="player")
    for single_stat_string in stat_string.split(","):
        stat_name, value_str = single_stat_string.split(":")
        player.stats.__dict__[stat_name] = int(value_str)
    db().update_player_data(player)
    return f"set player {player.name} stats to {player.stats}"


ADMIN_COMMANDS: dict[str, str | IFW | dict] = {
    "add": {
        "player": {
            "money": __generate_int_op_command("money", "player", "add"),
            "xp": __generate_int_op_command("xp", "player", "add"),
            "gear": __generate_int_op_command("gear_level", "player", "add"),
            "home": __generate_int_op_command("home_level", "player", "add"),
            "pieces": __generate_int_op_command("artifact_pieces", "player", "add"),
            "randitem": IFW([player_arg("player name")], give_random_item_to_player, "Add a random item to the player's inventory"),
            "item": IFW([player_arg("player name"), integer_arg("item type"), integer_arg("item level"), integer_arg("item rarity")], give_item_to_player, "Add an item to the player's inventory"),
            "consumable": IFW([player_arg("player name"), integer_arg("consumable type")], give_consumable_to_player, "Add a Consumable to the player's satchel"),
            "sanity": __generate_int_op_command("sanity", "player", "add"),
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "add"),
            "prestige": __generate_int_op_command("prestige", "guild", "add"),
        },
        "zone": IFW(None, start_add_obj_process, "Create a new zone", {"obj_type": "zone"}),
        "quest": IFW(None, start_add_obj_process, "Create a new quest", {"obj_type": "quest"}),
        "event": IFW(None, start_add_obj_process, "Create a new event", {"obj_type": "event"}),
        "artifact": IFW(None, start_add_obj_process, "Create a new artifact", {"obj_type": "artifact"}),
        "enemy": IFW(None, start_add_obj_process, "Create a new enemy", {"obj_type": "enemy"}),
    },
    "set": {
        "player": {
            "money": __generate_int_op_command("money", "player", "set"),
            "xp": __generate_int_op_command("xp", "player", "set"),
            "gear": __generate_int_op_command("gear_level", "player", "set"),
            "home": __generate_int_op_command("home_level", "player", "set"),
            "pieces": __generate_int_op_command("artifact_pieces", "player", "set"),
            "level": __generate_int_op_command("level", "player", "set"),
            "sanity": __generate_int_op_command("sanity", "player", "set"),
            "essences": IFW([player_arg("player name"), RWE("essences", None, None)], set_player_essences, "Set player essences"),
            "stats": IFW([player_arg("player name"), RWE("stats", None, None)], set_player_stats, "Set player stats"),
            "flags": __generate_int_op_command("flags", "player", "set"),
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "set"),
            "prestige": __generate_int_op_command("prestige", "guild", "set"),
        }
    },
    "sub": {
        "player": {
            "money": __generate_int_op_command("money", "player", "sub"),
            "xp": __generate_int_op_command("xp", "player", "sub"),
            "gear": __generate_int_op_command("gear_level", "player", "sub"),
            "home": __generate_int_op_command("home_level", "player", "sub"),
            "pieces": __generate_int_op_command("artifact_pieces", "player", "sub"),
            "sanity": __generate_int_op_command("sanity", "player", "sub"),
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "sub"),
            "prestige": __generate_int_op_command("prestige", "guild", "sub"),
        }
    },
    "edit": {
        "zone": IFW([RWE("Zone id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit a zone", {"obj_type": "zone"}),
        "quest": IFW([RWE("Quest id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit a quest", {"obj_type": "quest"}),
        "event": IFW([RWE("Event id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit an event", {"obj_type": "event"}),
        "artifact": IFW([RWE("Artifact id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit an artifact", {"obj_type": "artifact"}),
    },
    "generate": {
        "events": IFW([RWE("Zone id", PIR, "Invalid integer id")], force_generate_zone_events, "Generate new zone events"),
        "enemies": IFW([RWE("Zone id", PIR, "Invalid integer id")], force_generate_enemy_metas, "Generate new enemies")
    },
    "recharge": {
        "power": IFW([player_arg("player name")], give_player_eldritch_power, "recharge player eldritch power"),
        "switch": IFW([player_arg("player name")], restore_player_last_switch, "recharge player last switch"),
    },
    "force": {
        "update": IFW([player_arg("player name")], force_update, "Force update for the given player"),
        "quest": {
            "complete": IFW([player_arg("player name")], force_quest_complete, "Force quest complete for the given player"),
            "time": IFW([player_arg("player name"), RWE("hours", PIR, "Invalid integer id")], force_quest_end_time, "Force quest finish time in [hours] for the given player")
        }
    },
    "tourney": {
        "reset": IFW(None, reset_guild_tourney, "Reset all guild scores")
    }
}

ADMIN_PROCESSES: dict[str, tuple[tuple[str, Callable], ...]] = {
    "add zone": (
        ("Write Zone name", ProcessGetObjStrAttr("zone_name")),
        ("Write Zone level", ProcessGetObjIntAttr("level")),
        ("Write Zone description", ProcessGetObjStrAttr("zone_description")),
        ("Write zone damage modifiers", ProcessGetObjJsonAttr("damage_modifiers", convert_into=Damage)),
        ("Write zone resist modifiers", ProcessGetObjJsonAttr("resist_modifiers", convert_into=Damage)),
        ("Write zone extra data", ProcessGetObjJsonAttr("extra_data")),
        ("Confirm?", process_obj_add_confirm)
    ),
    "add quest": (
        ("Write Quest name", ProcessGetObjStrAttr("name")),
        ("Write Quest zone id", process_quest_add_zone),
        ("Write Quest description", ProcessGetObjStrAttr("description")),
        ("Write Quest success text", ProcessGetObjStrAttr("success_text")),
        ("Write Quest failure text", ProcessGetObjStrAttr("failure_text")),
        ("Confirm?", process_obj_add_confirm)
    ),
    "add event": (
        ("Write event description", ProcessGetObjStrAttr("event_text")),
        ("Write Quest zone id", process_event_add_zone),
        ("Confirm?", process_obj_add_confirm)
    ),
    "add artifact": (
        ("Write artifact name", ProcessGetObjStrAttr("name")),
        ("Write artifact description", ProcessGetObjStrAttr("description")),
        ("Confirm?", process_obj_add_confirm)
    ),
    "add enemy": (
        ("Write enemy name", ProcessGetObjStrAttr("name")),
        ("Write enemy zone", process_enemy_add_zone),
        ("Write enemy description", ProcessGetObjStrAttr("description")),
        ("Write enemy win text", ProcessGetObjStrAttr("win_text")),
        ("Write enemy loss text", ProcessGetObjStrAttr("lose_text")),
        ("Confirm?", process_obj_add_confirm)
    ),
    "edit zone": (
        ("Write Zone name", ProcessGetObjStrAttr("zone_name")),
        ("Write Zone level", ProcessGetObjIntAttr("level")),
        ("Write Zone description", ProcessGetObjStrAttr("zone_description")),
        ("Write zone damage modifiers", ProcessGetObjJsonAttr("damage_modifiers", convert_into=Damage)),
        ("Write zone resist modifiers", ProcessGetObjJsonAttr("resist_modifiers", convert_into=Damage)),
        ("Write zone extra data", ProcessGetObjJsonAttr("extra_data")),
        ("Confirm?", process_obj_edit_confirm)
    ),
    "edit quest": (
        ("Write Quest name", ProcessGetObjStrAttr("name")),
        ("Write Quest zone id", process_quest_add_zone),
        ("Write Quest number", ProcessGetObjIntAttr("number")),
        ("Write Quest description", ProcessGetObjStrAttr("description")),
        ("Write Quest success text", ProcessGetObjStrAttr("success_text")),
        ("Write Quest failure text", ProcessGetObjStrAttr("failure_text")),
        ("Confirm?", process_obj_edit_confirm)
    ),
    "edit event": (
        ("Write event description", ProcessGetObjStrAttr("event_text")),
        ("Write Quest zone id", process_event_add_zone),
        ("Confirm?", process_obj_edit_confirm)
    ),
    "edit artifact": (
        ("Write artifact name", ProcessGetObjStrAttr("name")),
        ("Write artifact description", ProcessGetObjStrAttr("description")),
        ("Confirm?", process_obj_edit_confirm)
    ),
    "edit enemy": (
        ("Write enemy name", ProcessGetObjStrAttr("name")),
        ("Write enemy zone", process_enemy_add_zone),
        ("Write enemy description", ProcessGetObjStrAttr("description")),
        ("Write enemy win text", ProcessGetObjStrAttr("win_text")),
        ("Write enemy loss text", ProcessGetObjStrAttr("lose_text")),
        ("Confirm?", process_obj_edit_confirm)
    ),
}

ADMIN_INTERPRETER = CLIInterpreter(ADMIN_COMMANDS, ADMIN_PROCESSES)
