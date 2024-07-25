import time
from random import Random, choice
from typing import Union, List, Dict, Any, Type, Tuple

import pilgram.modifiers as m

from pilgram.flags import StrengthBuff, OccultBuff, Flag, FireBuff, IceBuff, AcidBuff, ElectricBuff
from pilgram.globals import ContentMeta
from pilgram.listables import Listable
from pilgram.combat_classes import Damage
from pilgram.strings import Strings


MONEY = ContentMeta.get("money.name")


class Slots:
    HEAD = 0
    CHEST = 1
    LEGS = 2
    ARMS = 3
    PRIMARY = 4
    SECONDARY = 5

    NUMBER = 6

    ARMOR = (HEAD, CHEST, LEGS, ARMS)
    WEAPONS = (PRIMARY, SECONDARY)

    @classmethod
    def get_from_string(cls, string: str) -> int:
        class_vars = {key: value for key, value in vars(cls).items() if not key.startswith('_')}
        return class_vars[string.upper()]


def _get_slot(value: Union[str, int]) -> int:
    if type(value) is str:
        value = Slots.get_from_string(value)
    if (value > Slots.NUMBER) and (value < 0):
        raise IndexError(f"Invalid slot '{value}'")
    return value


class EquipmentType(Listable, meta_name="equipment types"):
    """ Defines the type of the equipment, either weapons or armor """

    def __init__(
            self,
            equipment_type_id: int,
            damage: Damage,
            resist: Damage,
            name: str,
            description: Union[str, None],
            is_weapon: bool,
            delay: int,
            slot: int,
            value: int,
            equipment_class: str,
    ):
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

    @classmethod
    def create_from_json(cls, equipment_type_json: Dict[str, Any]) -> "EquipmentType":
        return cls(
            equipment_type_json["id"],
            Damage.load_from_json(equipment_type_json.get("damage", {})),
            Damage.load_from_json(equipment_type_json.get("resist", {})),
            equipment_type_json["name"],
            equipment_type_json.get("description", None),
            equipment_type_json["weapon"],
            equipment_type_json["delay"],
            _get_slot(equipment_type_json["slot"]),
            equipment_type_json["value"],
            equipment_type_json.get("equipment_class", "weapon" if equipment_type_json["weapon"] else "armor"),
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
            modifiers: List["m.Modifier"]
    ):
        self.equipment_id = equipment_id
        self.level = level
        self.name = name
        self.seed = seed
        self.equipment_type = equipment_type
        self.damage = damage + self.equipment_type.damage.scale(level)
        self.resist = resist + self.equipment_type.resist.scale(level)
        self.modifiers = modifiers

    def get_modifiers(self, type_filters: Union[Tuple[int, ...], None]) -> List["m.Modifier"]:
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

    def reroll(self):
        seed = time.time()
        rarity = len(self.modifiers)
        dmg_type_string, damage, resist = self.get_dmg_and_resist_values(self.level, seed, self.equipment_type.is_weapon)
        self.name = self.generate_name(self.equipment_type, dmg_type_string, rarity)
        self.modifiers = self.generate_modifiers(rarity, rarity)
        self.damage = self.equipment_type.damage.scale(self.level) + damage
        self.resist = self.equipment_type.resist.scale(self.level) + resist

    def enchant(self):
        self.name += Strings.enchant_symbol
        self.modifiers.append(self._get_random_modifier(self.level))

    def __str__(self):
        string = f"*{self.name}* | lv. {self.level}\n- {Strings.slots[self.equipment_type.slot]} -\nWeight: {self.equipment_type.delay}\nValue: {self.get_value()} {MONEY}"
        if self.equipment_type.description:
            string += f"\n_{self.equipment_type.description}_"
        if self.damage:
            string += f"\n\n*Damage*:\n{str(self.damage)}"
        if self.resist:
            string += f"\n\n*Resist*:\n{str(self.resist)}"
        if not self.modifiers:
            return string
        return string + f"\n\n*Perks*:\n\n{'\n\n'.join(str(x) for x in self.modifiers)}"

    def __eq__(self, other):
        if isinstance(other, Equipment):
            return self.equipment_id == other.equipment_id
        return False

    @staticmethod
    def generate_name(
            equipment_type: EquipmentType,
            damage_types: List[str],
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
    def get_dmg_and_resist_values(level: int, seed: float, is_weapon: bool) -> Tuple[List[str], Damage, Damage]:
        rng = Random(seed)
        number_of_modifiers: int = rng.randint(1, 3)
        modifiers_to_exclude = ["slash", "pierce", "blunt", "occult", "fire", "acid", "freeze", "electric"]
        chosen_modifiers: List[str] = []
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
    def _get_random_modifier(cls, level: int) -> "m.Modifier":
        category = choice((
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.COMMON,
            m.Rarity.UNCOMMON,
            m.Rarity.UNCOMMON,
            m.Rarity.UNCOMMON,
            m.Rarity.RARE,
            m.Rarity.RARE,
            m.Rarity.LEGENDARY
        ))
        modifier_type = choice(m.get_modifiers_by_rarity(category))
        return modifier_type.generate(level)

    @classmethod
    def generate_modifiers(cls, amount: int, item_level: int) -> List["m.Modifier"]:
        modifiers: List[m.Modifier] = []
        if amount > 0:
            for i in range(amount):
                modifiers.append(cls._get_random_modifier(item_level))
        return modifiers

    @classmethod
    def generate(cls, level: int, equipment_type: EquipmentType, rarity: int) -> "Equipment":
        seed = time.time()
        dmg_type_string, damage, resist = cls.get_dmg_and_resist_values(level, seed, equipment_type.is_weapon)
        modifiers: List[m.Modifier] = cls.generate_modifiers(rarity, level)
        return cls(
            0,
            level,
            equipment_type,
            cls.generate_name(equipment_type, dmg_type_string, rarity),
            seed,
            damage,
            resist,
            modifiers
        )


class ConsumableItem(Listable, meta_name="consumables"):
    """ consumables that can be used by the player or are used automatically in combat. """

    def __init__(
            self,
            consumable_id: int,
            name: str,
            description: str,
            verb: str,
            value: int,  # buy price, sell price is halved
            effects: Dict[str, Any]
    ):
        buffs: List[str] = effects.get("buffs", [])
        self.consumable_id = consumable_id
        self.name = name
        self.description = description
        self.verb = verb
        self.value = value
        self.hp_restored = effects.get("hp_restored", 0)
        self.hp_percent_restored = effects.get("hp_percent_restored", 0.0)
        self.revive = effects.get("revive", False)
        self.buff_flag: Flag = self.get_buff_flag(buffs)
        # internal vars used to build the description
        self.buffs = buffs
        self.effects = list(effects.keys())

    def is_healing_item(self) -> bool:
        """ return whether a consumable is just a healing item """
        return (not self.revive) and (self.buff_flag == 0)

    def __str__(self):
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
    def get_buff_flag(cls, buff_strings: List[str]) -> Flag:
        result = Flag.get_empty()
        buff_map: Dict[str, Type[Flag]] = {
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
    def create_from_json(cls, consumables_json: Dict[str, Any]) -> "ConsumableItem":
        return cls(
            consumables_json["id"],
            consumables_json["name"],
            consumables_json["description"],
            consumables_json["verb"],
            consumables_json["value"],
            consumables_json.get("effects", {})
        )
