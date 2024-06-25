from typing import Dict, List, Callable

from orm.db import PilgramORMDatabase
from pilgram.classes import Spell, SpellError, Player
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
    amount = caster.get_spell_charge() * 10
    caster.add_money(amount)  # we don't need to save the player data, it will be done automatically later
    return f"{amount} {MONEY} materialize in the air"
