from __future__ import annotations

import time
from random import Random, choice
from typing import Any

import pilgram.modifiers as m
import pilgram.classes as c
from pilgram.combat_classes import Damage, Stats
from pilgram.flags import (
    AcidBuff,
    ElectricBuff,
    FireBuff,
    Flag,
    IceBuff,
    OccultBuff,
    StrengthBuff,
)
from pilgram.globals import ContentMeta, Slots
from pilgram.listables import Listable
from pilgram.strings import Strings


MONEY = ContentMeta.get("money.name")
REROLL_MULT: int = ContentMeta.get("crafting.reroll_mult")


def _get_slot(value: str | int) -> int:
    int_value: int = Slots.get_from_string(value) if isinstance(value, str) else value
    if (int_value > Slots.NUMBER) and (int_value < 0):
        raise IndexError(f"Invalid slot '{int_value}'")
    return int_value


class EquipmentType(Listable, base_filename="items"):
    """ Defines the type of the equipment, either weapons or armor """

    def __init__(
            self,
            equipment_type_id: int,
            damage: Damage,
            resist: Damage,
            name: str,
            description: str | None,
            is_weapon: bool,
            delay: int,
            slot: int,
            value: int,
            equipment_class: str,
            scaling: Stats,
            max_perks: int
    ) -> None:
        """
        :param equipment_type_id: The id of the equipment type
        :param damage: Damage dealt
        :param resist: Damage negated
        :param name: The base name of the equipment
        :param description: The description of the equipment
        :param is_weapon: Determines whether equipment is a weapon
        :param delay: Influences how slow the player is with this equipment on
        :param slot: The slot where the equipment should go
        """
        self.equipment_type_id = equipment_type_id
        self.damage = damage
        self.resist = resist
        self.name = name
        self.description = description
        self.is_weapon = is_weapon
        self.delay = delay
        self.slot = slot
        self.value = value
        self.equipment_class = equipment_class
        self.scaling = scaling
        self.max_perks = max_perks

    def __str__(self) -> str:
        return f"Type: {self.equipment_class}\nSlot: {Strings.slots[self.slot]} {Strings.get_item_icon(self.slot)}"

    @classmethod
    def create_from_json(cls, equipment_type_json: dict[str, Any]) -> EquipmentType:
        return cls(
            equipment_type_json["id"],
            Damage.load_from_json(equipment_type_json.get("damage", {})),
            Damage.load_from_json(equipment_type_json.get("resist", {})),
            equipment_type_json["name"],
            equipment_type_json.get("description"),
            equipment_type_json.get("weapon", True),
            equipment_type_json["delay"],
            _get_slot(equipment_type_json["slot"]),
            equipment_type_json["value"],
            equipment_type_json.get("class", "weapon" if equipment_type_json["weapon"] else "armor"),
            Stats.load_from_json(equipment_type_json.get("scaling", {"strength": 1, "skill": 1})),
            equipment_type_json.get("max_perks", 2)
        )


class Equipment:

    def __init__(
            self,
            equipment_id: int,
            level: int,
            equipment_type: EquipmentType,
            name: str,
            seed: float,
            damage: Damage,
            resist: Damage,
            modifiers: list[m.Modifier],
            rerolls: int
    ) -> None:
        self.equipment_id = equipment_id
        self.level = level
        self.name = name
        self.seed = seed
        self.equipment_type = equipment_type
        self.damage = damage + self.equipment_type.damage.scale(level)
        self.resist = resist + self.equipment_type.resist.scale(level)
        self.modifiers = modifiers
        self.rerolls = rerolls

    def get_modifiers(self, type_filters: tuple[int, ...] | None) -> list[m.Modifier]:
        if not type_filters:
            return self.modifiers
        result = []
        for modifier in self.modifiers:
            if modifier.TYPE in type_filters:
                result.append(modifier)
        return result

    def get_rarity(self) -> int:
        return len(self.modifiers)

    def get_value(self) -> int:
        return (self.equipment_type.value + self.level) * (self.get_rarity() + 1)

    def get_reroll_price(self, player: c.Player) -> int:
        return int(self.get_value() * REROLL_MULT * player.vocation.reroll_cost_multiplier + (self.rerolls * self.get_value()))

    def reroll(self, stats_bonus: int, modifier_bias: int) -> None:
        self.seed = time.time()
        rarity = len(self.modifiers)
        dmg_type_string, damage, resist = self.generate_dmg_and_resist_values(
            self.level + stats_bonus, self.seed, self.equipment_type.is_weapon
        )
        self.name = self.generate_name(self.equipment_type, dmg_type_string, rarity)
        self.modifiers = self.generate_modifiers(rarity, self.level, bias=modifier_bias)
        self.damage = self.equipment_type.damage.scale(self.level) + damage
        self.resist = self.equipment_type.resist.scale(self.level) + resist
        self.rerolls += 1

    def enchant(self) -> bool:
        if len(self.modifiers) >= self.equipment_type.max_perks:
            return False
        self.name += Strings.enchant_symbol
        self.modifiers.append(self._get_random_modifier(self.level))
        return True

    def temper(self):
        self.level += 1
        _, damage, resist = self.generate_dmg_and_resist_values(
            self.level, self.seed, self.equipment_type.is_weapon
        )
        self.damage = self.equipment_type.damage.scale(self.level) + damage
        self.resist = self.equipment_type.resist.scale(self.level) + resist
        self.rerolls += 1


    def __str__(self) -> str:
        string = f"*{self.name}* | lv. {self.level}\n_{self.equipment_type}\nWeight: {self.equipment_type.delay} Kg\nValue: {self.get_value()} {MONEY}_"
        if self.equipment_type.description:
            string += f"\n\n_{self.equipment_type.description}_"
        if self.damage:
            string += f"\n\n*Damage ({self.damage.get_total_damage()})*:\n{str(self.damage)}"
        if self.resist:
            string += f"\n\n*Resist ({self.resist.get_total_damage()})*:\n{str(self.resist)}"
        string += f"\n\n*Scaling*:\n{str(self.equipment_type.scaling.get_scaling_string())}"
        if not self.modifiers:
            return string
        return string + f"\n\n*Perks ({len(self.modifiers)}/{self.equipment_type.max_perks})*:\n\n{'\n\n'.join(str(x) for x in self.modifiers)}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Equipment):
            return self.equipment_id == other.equipment_id
        return False

    def __hash__(self) -> int:
        return hash(self.equipment_id)

    @staticmethod
    def generate_name(
            equipment_type: EquipmentType,
            damage_types: list[str],
            rarity: int
    ) -> str:
        pool = Strings.weapon_modifiers if equipment_type.is_weapon else Strings.armor_modifiers
        name = equipment_type.name
        added_of = False
        for modifier in damage_types:
            adjective = choice(pool[modifier])
            if adjective.startswith("-"):
                if added_of:
                    name += f" & {adjective[1:]}"
                else:
                    name += " of " + adjective[1:]
                    added_of = True
            else:
                name = adjective + " " + name
        return name + (" " + (Strings.enchant_symbol * rarity) if rarity > 0 else "")

    @staticmethod
    def generate_dmg_and_resist_values(level: int, seed: float, is_weapon: bool) -> tuple[list[str], Damage, Damage]:
        rng = Random(seed)
        number_of_modifiers: int = rng.randint(1, 3)
        modifiers_to_exclude = ["slash", "pierce", "blunt", "occult", "fire", "acid", "freeze", "electric"]
        chosen_modifiers: list[str] = []
        for _ in range(number_of_modifiers):
            modifier_string = modifiers_to_exclude.pop(rng.randint(0, len(modifiers_to_exclude) - 1))
            chosen_modifiers.append(modifier_string)
        if is_weapon:
            damage = Damage.generate_from_seed(seed, level, modifiers_to_exclude)
            return chosen_modifiers, damage, Damage.get_empty()
        else:
            resist = Damage.generate_from_seed(seed, level, modifiers_to_exclude)
            return chosen_modifiers, Damage.get_empty(), resist

    @classmethod
    def _get_random_modifier(cls, level: int, bias: int = 0) -> m.Modifier:
        category = choice((
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.UNCOMMON,
            m.Rarity.UNCOMMON,
            m.Rarity.UNCOMMON,
            m.Rarity.UNCOMMON,
            m.Rarity.RARE,
            m.Rarity.RARE,
            m.Rarity.LEGENDARY
        )[bias:])
        modifier_type = choice(m.get_modifiers_by_rarity(category))
        return modifier_type.generate(level)

    @classmethod
    def generate_modifiers(cls, amount: int, item_level: int, bias: int = 0) -> list[m.Modifier]:
        modifiers: list[m.Modifier] = []
        if amount > 0:
            for i in range(amount):
                modifiers.append(cls._get_random_modifier(item_level, bias=bias))
        return modifiers

    @classmethod
    def generate(cls, level: int, equipment_type: EquipmentType, rarity: int) -> Equipment:
        seed = time.time()
        dmg_type_string, damage, resist = cls.generate_dmg_and_resist_values(level, seed, equipment_type.is_weapon)
        if rarity > equipment_type.max_perks:
            rarity = equipment_type.max_perks
        modifiers: list[m.Modifier] = cls.generate_modifiers(rarity, level)
        return cls(
            0,
            level,
            equipment_type,
            cls.generate_name(equipment_type, dmg_type_string, rarity),
            seed,
            damage,
            resist,
            modifiers,
            0
        )


class ConsumableItem(Listable, base_filename="consumables"):
    """ consumables that can be used by the player or are used automatically in combat. """

    def __init__(
            self,
            consumable_id: int,
            name: str,
            description: str,
            verb: str,
            value: int,  # buy price, sell price is halved
            effects: dict[str, Any]
    ) -> None:
        buffs: list[str] = effects.get("buffs", [])
        self.consumable_id = consumable_id
        self.name = name
        self.description = description
        self.verb = verb
        self.value = value
        self.hp_restored: int = effects.get("hp_restored", 0)
        self.hp_percent_restored: float = effects.get("hp_percent_restored", 0.0)
        self.revive: bool = effects.get("revive", False)
        self.buff_flag: Flag = self.get_buff_flag(buffs)
        self.sanity_restored: int = effects.get("sanity_restored", 0)
        self.bait_power: float = effects.get("bait_power", 0.0)
        # internal vars used to build the description
        self.buffs = buffs
        self.effects = list(effects.keys())

    def is_healing_item(self) -> bool:
        """ return whether a consumable is just a healing item """
        return (not self.revive) and (self.buff_flag == 0)

    def __str__(self) -> str:
        string = f"*{self.name}*\n_{self.description}_\nPrice: {self.value} {MONEY}\nEffects:\n"
        for effect in self.effects:
            value = self.__dict__[effect]
            if type(value) is float:
                string += f"- {Strings.effect_names.get(effect, effect)}: {int(value * 100)}%\n"
            elif type(value) is list:
                string += f"- {Strings.effect_names.get(effect, effect)}: {', '.join(value)}\n"
            elif type(value) is bool:
                if value:
                    string += f"- {Strings.effect_names.get(effect, effect)}\n"
            else:
                string += f"- {Strings.effect_names.get(effect, effect)}: {value}\n"
        return string

    @classmethod
    def get_buff_flag(cls, buff_strings: list[str]) -> Flag:
        result = Flag.get_empty()
        buff_map: dict[str, type[Flag]] = {
            "strength": StrengthBuff,
            "occult": OccultBuff,
            "fire": FireBuff,
            "ice": IceBuff,
            "acid": AcidBuff,
            "electric": ElectricBuff
        }
        for string in buff_strings:
            if string in buff_map:
                result = buff_map[string].set(result)
        return result

    @classmethod
    def create_from_json(cls, consumables_json: dict[str, Any]) -> ConsumableItem:
        return cls(
            consumables_json["id"],
            consumables_json["name"],
            consumables_json["description"],
            consumables_json["verb"],
            consumables_json["value"],
            consumables_json.get("effects", {})
        )
