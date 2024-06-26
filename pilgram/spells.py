from datetime import timedelta
from typing import Dict, List, Callable

from orm.db import PilgramORMDatabase
from pilgram.classes import Spell, SpellError, Player
from pilgram.flags import HexedFlag
from pilgram.generics import PilgramDatabase
from pilgram.globals import ContentMeta

MONEY = ContentMeta.get("money.name")
SPELLS: Dict[str, Spell] = {}


def _db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def __add_to_spell_list(spell_short_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        SPELLS[spell_short_name] = Spell(
            ContentMeta.get(f"spells.{spell_short_name}.name"),
            ContentMeta.get(f"spells.{spell_short_name}.description"),
            ContentMeta.get(f"spells.{spell_short_name}.power"),
            ContentMeta.get(f"spells.{spell_short_name}.args", default=0),
            func
        )
        return func
    return decorator


@__add_to_spell_list("mida")
def __midas_touch(caster: Player, args: List[str]) -> str:
    amount = caster.get_spell_charge() * caster.get_spell_charge()
    caster.add_money(amount)  # we don't need to save the player data, it will be done automatically later
    return f"{amount} {MONEY} materialize in the air."


@__add_to_spell_list("bones")
def __bone_recall(caster: Player, args: List[str]) -> str:
    amount = caster.get_spell_charge() * caster.get_spell_charge()
    caster.add_xp(amount)  # we don't need to save the player data, it will be done automatically later
    return f"You gain {amount} xp from the wisdom of the dead."


@__add_to_spell_list("displacement")
def __eldritch_displacement(caster: Player, args: List[str]) -> str:
    ac = _db().get_player_adventure_container(caster)
    if not ac.quest:
        raise SpellError("You are not on a quest!")
    ac.finish_time -= timedelta(hours=int(caster.get_spell_charge() / 20))
    _db().update_quest_progress(ac)


@__add_to_spell_list("hex")
def __hex(caster: Player, args: List[str]) -> str:
    target = _db().get_player_from_name(args[0])
    if not target:
        raise SpellError(f"A player named {args[0]} does not exist.")
    target.flags = HexedFlag.set(target.flags)
    _db().update_player_data(target)
    return f"You hexed {target.name}."
