from typing import Union, List, Dict, Any

from pilgram.listables import Listable
from pilgram.combat import Modifier, Damage


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
        :param is_weapon: Defines whether the equipment is weapons or armor
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

    def __init__(self):
        pass  # TODO

    @classmethod
    def create_from_json(cls, consumables_json: Dict[str, Any]) -> "ConsumableItem":
        return ConsumableItem()
