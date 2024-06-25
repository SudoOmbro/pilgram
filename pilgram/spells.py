from typing import Dict, List

from orm.db import PilgramORMDatabase
from pilgram.classes import Spell, SpellError, Player
from pilgram.generics import PilgramDatabase
from pilgram.globals import ContentMeta

MONEY = ContentMeta.get("money.name")
SPELLS: Dict[str, Spell] = {}


def cs(cast_name: str, spell: Spell):  # stands for create spell
    SPELLS[cast_name] = spell


def db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def __midas_touch(caster: Player, args: List[str]) -> str:
    amount = caster.get_spell_charge() * 10
    caster.add_money(amount)  # we don't need to save the player data, it will be done automatically later
    return f"{amount} {MONEY} materializes in the air"


cs("mida", Spell(
    "Mida's touch",
    f"Create {MONEY} from thin air",
    10,
    0,
    __midas_touch
))
