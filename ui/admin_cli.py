import re
from typing import Dict, Union, Tuple, Callable

from AI.chatgpt import ChatGPTGenerator, ChatGPTAPI
from orm.db import PilgramORMDatabase
from pilgram.classes import Zone, Quest, ZoneEvent, Artifact
from pilgram.generics import PilgramDatabase
from pilgram.globals import PLAYER_NAME_REGEX as PNR, POSITIVE_INTEGER_REGEX as PIR, ContentMeta, YES_NO_REGEX, \
    GlobalSettings
from ui.interpreter import CLIInterpreter
from pilgram.strings import Strings
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


def start_add_obj_process(context: UserContext, obj_type: str = "zone") -> str:
    try:
        target_object = {
            "zone": Zone.get_empty(),
            "quest": Quest.get_empty(),
            "event": ZoneEvent.get_empty(),
            "artifact": Artifact.get_empty()
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
            "artifact": lambda: db().get_artifact(obj_id)
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
            "artifact": lambda: db().add_artifact(obj)
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
            "artifact": lambda: db().update_artifact(obj, None)
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
        return Strings.zone_does_not_exist
    except Exception as e:
        return str(e)


ADMIN_COMMANDS: Dict[str, Union[str, IFW, dict]] = {
    "add": {
        "player": {
            "money": __generate_int_op_command("money", "player", "add"),
            "xp": __generate_int_op_command("xp", "player", "add"),
            "gear": __generate_int_op_command("gear_level", "player", "add"),
            "home": __generate_int_op_command("home_level", "player", "add"),
            "pieces": __generate_int_op_command("artifact_pieces", "player", "add"),
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "add"),
            "prestige": __generate_int_op_command("home", "guild", "add"),
        },
        "zone": IFW(None, start_add_obj_process, "Create a new zone", {"obj_type": "zone"}),
        "quest": IFW(None, start_add_obj_process, "Create a new quest", {"obj_type": "quest"}),
        "event": IFW(None, start_add_obj_process, "Create a new event", {"obj_type": "event"}),
        "artifact": IFW(None, start_add_obj_process, "Create a new artifact", {"obj_type": "artifact"})
    },
    "set": {
        "player": {
            "money": __generate_int_op_command("money", "player", "set"),
            "xp": __generate_int_op_command("xp", "player", "set"),
            "gear": __generate_int_op_command("gear_level", "player", "set"),
            "home": __generate_int_op_command("home_level", "player", "set"),
            "pieces": __generate_int_op_command("artifact_pieces", "player", "set")
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
            "pieces": __generate_int_op_command("artifact_pieces", "player", "sub")
        },
        "guild": {
            "level": __generate_int_op_command("level", "guild", "sub"),
            "prestige": __generate_int_op_command("home", "guild", "sub"),
        }
    },
    "edit": {
        "zone": IFW([RWE("Zone id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit a zone", {"obj_type": "zone"}),
        "quest": IFW([RWE("Quest id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit a quest", {"obj_type": "quest"}),
        "event": IFW([RWE("Event id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit an event", {"obj_type": "event"}),
        "artifact": IFW([RWE("Artifact id", PIR, "Invalid integer id")], start_edit_obj_process, "Edit an artifact", {"obj_type": "artifact"}),
    },
    "generate": {
        "events": IFW([RWE("Zone id", PIR, "Invalid integer id")], force_generate_zone_events, "Generate new zone events")
    }
}

ADMIN_PROCESSES: Dict[str, Tuple[Tuple[str, Callable], ...]] = {
    "add zone": (
        ("Write Zone name", ProcessGetObjStrAttr("zone_name")),
        ("Write Zone level", ProcessGetObjIntAttr("level")),
        ("Write Zone description", ProcessGetObjStrAttr("zone_description")),
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
        ("Write Quest zone id", process_quest_add_zone),
        ("Confirm?", process_obj_add_confirm)
    ),
    "add artifact": (
        ("Write artifact name", ProcessGetObjStrAttr("name")),
        ("Write artifact description", ProcessGetObjStrAttr("description")),
        ("Confirm?", process_obj_add_confirm)
    ),
    "edit zone": (
        ("Write Zone name", ProcessGetObjStrAttr("zone_name")),
        ("Write Zone level", ProcessGetObjIntAttr("level")),
        ("Write Zone description", ProcessGetObjStrAttr("zone_description")),
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
        ("Write Quest zone id", process_quest_add_zone),
        ("Confirm?", process_obj_edit_confirm)
    ),
    "edit artifact": (
        ("Write artifact name", ProcessGetObjStrAttr("name")),
        ("Write artifact description", ProcessGetObjStrAttr("description")),
        ("Confirm?", process_obj_add_confirm)
    )
}

ADMIN_INTERPRETER = CLIInterpreter(ADMIN_COMMANDS, ADMIN_PROCESSES)
