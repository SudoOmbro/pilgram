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


def get_spell_target(caster, args: list[str], target_pos: int = 0) -> tuple[Player, bool]:  # target, self cast
    if len(args) == 0:
        return caster, True
    target = _db().get_player_from_name(args[target_pos])
    if not target:
        raise SpellError(f"A player named {args[0]} does not exist.")
    return target, False


def get_cast_string(target: Player, self_cast: bool) -> str:
    return f" target: {"yourself" if self_cast else target.name}."


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
    target, self_cast = get_spell_target(caster, args)
    amount = 50 * caster.get_spell_charge()
    # we don't need to save the player data, it will be done automatically later
    money_am = target.add_money(amount)
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(target, f"{money_am} {MONEY} materialize in front of you.")
    return get_cast_string(target, self_cast)


@__add_to_spell_list("bones")
def __bone_recall(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    amount = 50 * caster.get_spell_charge()
    # we don't need to save the player data, it will be done automatically later
    xp_am = target.add_xp(amount)
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(target, f"You gain {xp_am} xp from the wisdom of the dead.")
    return get_cast_string(target, self_cast)


@__add_to_spell_list("displacement")
def __eldritch_displacement(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    ac = _db().get_player_adventure_container(target)
    if not ac.quest:
        raise SpellError("You are not on a quest!")
    displacement = int(caster.get_spell_charge() / 20)
    ac.finish_time -= timedelta(hours=displacement)
    _db().update_quest_progress(ac)
    _db().create_and_add_notification(
        target,
        f"You find yourself in a different place, {displacement} hour{'s' if displacement == 1 else ''} closer to your target."
    )
    return get_cast_string(target, self_cast)


@__add_to_spell_list("glitch")
def __alloy_glitch(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    power_used = caster.get_spell_charge()
    multiplier = 1
    for power, flag in zip(
        (30, 60, 90),
        (AlloyGlitchFlag1, AlloyGlitchFlag2, AlloyGlitchFlag3),
        strict=False,
    ):
        if power_used >= power:
            target.flags = flag.set(target.flags)
            multiplier *= 1.5
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(
        target,
        f"The next time you earn money the amount you earn will be multiplied {multiplier} times."
    )
    return get_cast_string(target, self_cast)


@__add_to_spell_list("hex")
def __hex(caster: Player, args: list[str]) -> str:
    target = _db().get_player_from_name(args[0])
    if not target:
        raise SpellError(f"A player named {args[0]} does not exist.")
    if target.vocation.eldritch_resist:
        raise SpellError("The target is immune to spells.")
    power_used = caster.get_spell_charge()
    if (power_used < 100) and HexedFlag.is_set(target.flags):
        raise SpellError(f"{args[0]} is already hexed!")
    elif HexedFlag.is_set(target.flags) and CursedFlag.is_set(target.flags):
        raise SpellError(f"{args[0]} is already cursed!")
    if power_used >= 100:
        target.set_flag(HexedFlag)
        target.set_flag(CursedFlag)
        _db().update_player_data(target)
        _db().create_and_add_notification(target, "You feel cursed...")
        return f"You cursed {target.name}."
    target.set_flag(HexedFlag)
    _db().create_and_add_notification(target, "You feel hexed...")
    _db().update_player_data(target)
    return f"You hexed {target.name}."


@__add_to_spell_list("bless")
def __bless(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    if target.vocation.eldritch_resist:
        raise SpellError("The target is immune to spells.")
    power_used = caster.get_spell_charge()
    if (power_used < 100) and LuckFlag1.is_set(target.flags):
        raise SpellError(f"{args[0]} is already blessed (1)!")
    elif LuckFlag1.is_set(target.flags) and LuckFlag2.is_set(target.flags):
        raise SpellError(f"{args[0]} is already blessed (2)!")
    if power_used >= 100:
        target.set_flag(LuckFlag1)
        target.set_flag(LuckFlag2)
        if not self_cast:
            _db().update_player_data(target)
        _db().create_and_add_notification(target, "You feel very blessed")
        return f"You blessed (2) {"yourself" if self_cast else target.name}."
    target.set_flag(LuckFlag1)
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(target, "You feel blessed")
    return f"You blessed (1) {"yourself" if self_cast else target.name}."


@__add_to_spell_list("heal")
def __eldritch_healing(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    amount = int(target.get_max_hp() * (caster.get_spell_charge() / 100))
    # we don't need to save the player data, it will be done automatically later
    target.modify_hp(amount)
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(target, f"You gain {amount} HP ({target.get_hp_string()}).")
    return get_cast_string(target, self_cast)


@__add_to_spell_list("might")
def __eldritch_might(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    amount = caster.get_spell_charge()
    if amount >= 40:
        target.set_flag(MightBuff1)
    if amount >= 80:
        target.set_flag(MightBuff2)
    if amount >= 120:
        target.set_flag(MightBuff3)
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(target, f"You feel stronger ({int(amount / 30)}x)")
    return get_cast_string(target, self_cast)


@__add_to_spell_list("swift")
def __eldritch_swiftness(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    amount = caster.get_spell_charge()
    if amount >= 40:
        target.set_flag(SwiftBuff1)
    if amount >= 80:
        target.set_flag(SwiftBuff2)
    if amount >= 120:
        target.set_flag(SwiftBuff3)
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(target, f"You faster stronger ({int(amount / 30)}x)")
    return get_cast_string(target, self_cast)


@__add_to_spell_list("ritual")
def __summoning_ritual(caster: Player, args: list[str]) -> str:
    target, self_cast = get_spell_target(caster, args)
    amount = caster.get_spell_charge()
    if amount >= 50:
        target.set_flag(Ritual1)
    if amount >= 100:
        target.set_flag(Ritual2)
    if not self_cast:
        _db().update_player_data(target)
    _db().create_and_add_notification(target, f"You feel a sense of dread ({int(amount / 40)}x)")
    return get_cast_string(target, self_cast)
