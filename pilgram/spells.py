from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from orm.db import PilgramORMDatabase
from pilgram.classes import Player, Spell, SpellError
from pilgram.flags import (
    AlloyGlitchFlag1,
    AlloyGlitchFlag2,
    AlloyGlitchFlag3,
    CursedFlag,
    HexedFlag,
    LuckFlag1,
    LuckFlag2,
    MightBuff1,
    MightBuff2,
    MightBuff3,
    SwiftBuff1,
    SwiftBuff2,
    SwiftBuff3, Ritual1, Ritual2,
)
from pilgram.generics import PilgramDatabase
from pilgram.globals import ContentMeta

MONEY = ContentMeta.get("money.name")
SPELLS: dict[str, Spell] = {}


def _db() -> PilgramDatabase:
    return PilgramORMDatabase.instance()


def __add_to_spell_list(spell_short_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        SPELLS[spell_short_name] = Spell(
            ContentMeta.get(f"spells.{spell_short_name}.name"),
            ContentMeta.get(f"spells.{spell_short_name}.description"),
            ContentMeta.get(f"spells.{spell_short_name}.power"),
            ContentMeta.get(f"spells.{spell_short_name}.args", default=0),
            func,
        )
        print(f"spell {spell_short_name} registered")
        return func

    return decorator


@__add_to_spell_list("mida")
def __midas_touch(caster: Player, args: list[str]) -> str:
    amount = 50 * caster.get_spell_charge()
    # we don't need to save the player data, it will be done automatically later
    caster.add_money(amount)
    return f"{amount} {MONEY} materialize in the air."


@__add_to_spell_list("bones")
def __bone_recall(caster: Player, args: list[str]) -> str:
    amount = 50 * caster.get_spell_charge()
    # we don't need to save the player data, it will be done automatically later
    caster.add_xp(amount)
    return f"You gain {amount} xp from the wisdom of the dead."


@__add_to_spell_list("displacement")
def __eldritch_displacement(caster: Player, args: list[str]) -> str:
    ac = _db().get_player_adventure_container(caster)
    if not ac.quest:
        raise SpellError("You are not on a quest!")
    displacement = int(caster.get_spell_charge() / 20)
    ac.finish_time -= timedelta(hours=displacement)
    _db().update_quest_progress(ac)
    return f"You find yourself in a different place, {displacement} hour{'s' if displacement == 1 else ''} closer to your target."


@__add_to_spell_list("glitch")
def __alloy_glitch(caster: Player, args: list[str]) -> str:
    power_used = caster.get_spell_charge()
    multiplier = 1
    for power, flag in zip(
        (30, 60, 90),
        (AlloyGlitchFlag1, AlloyGlitchFlag2, AlloyGlitchFlag3),
        strict=False,
    ):
        if power_used >= power:
            caster.flags = flag.set(caster.flags)
            multiplier *= 1.5
    return f"The next time you earn money the amount you earn will be multiplied {multiplier} times."


@__add_to_spell_list("hex")
def __hex(caster: Player, args: list[str]) -> str:
    target = _db().get_player_from_name(args[0])
    if not target:
        raise SpellError(f"A player named {args[0]} does not exist.")
    if target.cult.eldritch_resist:
        raise SpellError("The target is immune to spells.")
    power_used = caster.get_spell_charge()
    if (power_used < 100) and HexedFlag.is_set(target.flags):
        raise SpellError(f"{args[0]} is already hexed!")
    elif HexedFlag.is_set(target.flags) and CursedFlag.is_set(target.flags):
        raise SpellError(f"{args[0]} is already cursed!")
    if power_used == 100:
        target.set_flag(HexedFlag)
        target.set_flag(CursedFlag)
        _db().update_player_data(target)
        return f"You cursed {target.name}."
    target.set_flag(HexedFlag)
    _db().update_player_data(target)
    return f"You hexed {target.name}."


@__add_to_spell_list("bless")
def __bless(caster: Player, args: list[str]) -> str:
    target = _db().get_player_from_name(args[0])
    if not target:
        raise SpellError(f"A player named {args[0]} does not exist.")
    if target.cult.eldritch_resist:
        raise SpellError("The target is immune to spells.")
    power_used = caster.get_spell_charge()
    if (power_used < 100) and LuckFlag1.is_set(target.flags):
        raise SpellError(f"{args[0]} is already blessed (1)!")
    elif LuckFlag1.is_set(target.flags) and LuckFlag2.is_set(target.flags):
        raise SpellError(f"{args[0]} is already blessed (2)!")
    if power_used == 100:
        target.set_flag(LuckFlag1)
        target.set_flag(LuckFlag2)
        _db().update_player_data(target)
        return f"You blessed (2) {target.name}."
    target.set_flag(LuckFlag1)
    _db().update_player_data(target)
    return f"You blessed (1) {target.name}."


@__add_to_spell_list("heal")
def __eldritch_healing(caster: Player, args: list[str]) -> str:
    amount = int(caster.get_max_hp() * (caster.get_spell_charge() / 100))
    # we don't need to save the player data, it will be done automatically later
    caster.modify_hp(amount)
    return f"You gain {amount} HP ({caster.get_hp_string()})."


@__add_to_spell_list("might")
def __eldritch_might(caster: Player, args: list[str]) -> str:
    amount = caster.get_spell_charge()
    if amount >= 30:
        caster.set_flag(MightBuff1)
    if amount >= 60:
        caster.set_flag(MightBuff2)
    if amount >= 90:
        caster.set_flag(MightBuff3)
    # we don't need to save the player data, it will be done automatically later
    return f"You feel stronger ({int(amount / 30)}x)."


@__add_to_spell_list("swift")
def __eldritch_swiftness(caster: Player, args: list[str]) -> str:
    amount = caster.get_spell_charge()
    if amount >= 30:
        caster.set_flag(SwiftBuff1)
    if amount >= 60:
        caster.set_flag(SwiftBuff2)
    if amount >= 90:
        caster.set_flag(SwiftBuff3)
    # we don't need to save the player data, it will be done automatically later
    return f"You feel faster ({int(amount / 30)}x)."


@__add_to_spell_list("ritual")
def __summoning_ritual(caster: Player, args: list[str]) -> str:
    amount = caster.get_spell_charge()
    if amount >= 40:
        caster.set_flag(Ritual1)
    if amount >= 80:
        caster.set_flag(Ritual2)
    return f"You feel a sense of dread ({int(amount / 40)}x)"
