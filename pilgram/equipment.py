from typing import Union, List, Dict, Any, Type

from pilgram.flags import StrengthBuff, OccultBuff, Flag, FireBuff, IceBuff, AcidBuff, ElectricBuff
from pilgram.listables import Listable
from pilgram.combat import Modifier, Damage
from pilgram.strings import Strings


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

    def __init__(self, equipment_type_id: int, damage: Damage, resist: Damage, name: str, slot: int):
        """
        :param equipment_type_id: The id of the equipment type
        :param damage: Damage dealt
        :param resist: Damage negated
        :param name: The base name of the equipment
        :param slot: The slot where the equipment should go
        """
        self.equipment_type_id = equipment_type_id
        self.damage = damage
        self.resist = resist
        self.name = name
        self.slot = slot

    @classmethod
    def create_from_json(cls, equipment_type_json: Dict[str, Any]) -> "EquipmentType":
        return cls(
            equipment_type_json["id"],
            Damage.load_from_json(equipment_type_json.get("damage", {})),
            Damage.load_from_json(equipment_type_json.get("resist", {})),
            equipment_type_json["name"],
            _get_slot(equipment_type_json["slot"])
        )


class Equipment:

    def __init__(self, equipment_type_id: int, damage: Damage, modifiers: List[Modifier]):
        self.weapon_type: EquipmentType = EquipmentType.LIST[equipment_type_id]
        self.damage = damage + self.weapon_type.damage
        self.modifiers = modifiers


class ConsumableItem(Listable, meta_name="consumables"):

    def __init__(
            self,
            consumable_id: int,
            name: str,
            description: str,
            value: int,  # buy price, sell price is halved
            effects: Dict[str, Any]
    ):
        buffs: List[str] = effects.get("buffs", [])
        self.consumable_id = consumable_id
        self.name = name
        self.description = description
        self.value = value
        self.hp_restored = effects.get("hp_restored", 0)
        self.hp_percent_restored = effects.get("hp_percent_restored", 0.0)
        self.revive = effects.get("revive", False)
        self.buff_flag = self.get_buff_flag(buffs)
        # internal vars used to build the description
        self.buffs = buffs
        self.effects = list(effects.keys())

    def __str__(self):
        string = f"*{self.name}*\n_{self.description}_\nValue: {self.value}\nEffects:\n"
        for effect in self.effects:
            value = self.__dict__[effect]
            if type(value) is float:
                string += f"{Strings.effect_names.get(effect, effect)}: {int(value * 100)}%\n"
            elif type(value) is list:
                string += f"{Strings.effect_names.get(effect, effect)}: {', '.join(value)}\n"
            elif type(value) is bool:
                if value:
                    string += f"{Strings.effect_names.get(effect, effect)}\n"
            else:
                string += f"{Strings.effect_names.get(effect, effect)}: {value}\n"
        return string

    @classmethod
    def get_buff_flag(cls, buff_strings: List[str]) -> int:
        result = 0
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
                result |= buff_map[string]
        return result

    @classmethod
    def create_from_json(cls, consumables_json: Dict[str, Any]) -> "ConsumableItem":
        return ConsumableItem(
            consumables_json["id"],
            consumables_json["name"],
            consumables_json["description"],
            consumables_json["value"],
            consumables_json.get("effects", {})
        )
