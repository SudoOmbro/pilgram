import random

from time import time
from copy import copy
from typing import Union, List, Dict, Any

from pilgram.listables import Listable


class Damage:
    """ used to express damage & resistance values """

    def __init__(
        self,
        slash: int,
        pierce: int,
        blunt: int,
        occult: int,
        fire: int,
        acid: int,
        freeze: int,
        electric: int
    ):
        self.slash = slash
        self.pierce = pierce
        self.blunt = blunt
        self.occult = occult
        self.fire = fire
        self.acid = acid
        self.freeze = freeze
        self.electric = electric

    def __add__(self, other):
        return Damage(
            self.slash + other.slash,
            self.pierce + other.pierce,
            self.blunt + other.blunt,
            self.occult + other.occult,
            self.fire + other.fire,
            self.acid + other.acid,
            self.freeze + other.freeze,
            self.electric + other.electric
        )

    def __mul__(self, other):
        return Damage(
            self.slash * other.slash,
            self.pierce * other.pierce,
            self.blunt * other.blunt,
            self.occult * other.occult,
            self.fire * other.fire,
            self.acid * other.acid,
            self.freeze * other.freeze,
            self.electric * other.electric
        )

    @classmethod
    def get_empty(cls) -> "Damage":
        return Damage(0, 0, 0, 0, 0, 0, 0, 0)

    @classmethod
    def generate_from_seed(cls, seed: int, iterations: int, exclude_params: Union[List[str], None] = None) -> "Damage":
        damage = cls.get_empty()
        rng = random.Random(seed)
        params = copy(damage.__dict__)
        if exclude_params:
            for param in exclude_params:
                if param in params:
                    params.pop(param)
        for _ in range(iterations):
            param = rng.choice(list(params.keys()))
            damage.__dict__[param] += 1
        return damage

    @classmethod
    def load_from_json(cls, damage_json: Dict[str, int]) -> "Damage":
        return Damage(
            damage_json.get("slash", 0),
            damage_json.get("pierce", 0),
            damage_json.get("blunt", 0),
            damage_json.get("occult", 0),
            damage_json.get("fire", 0),
            damage_json.get("acid", 0),
            damage_json.get("freeze", 0),
            damage_json.get("electric", 0),
        )

    @classmethod
    def generate(cls, iterations: int, exclude_params: Union[List[str], None] = None) -> "Damage":
        return cls.generate_from_seed(int(time()), iterations, exclude_params)


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

    def __init__(self, is_weapon: bool, equipment_type_id: int, damage: Damage, name: str, slot: int):
        """
        :param is_weapon: Defines whether the equipment is weapons or armor
        :param equipment_type_id: The id of the equipment type
        :param damage: Could be either damage dealt (for weapons) or damage resistance (for armors)
        :param name: The base name of the equipment
        :param slot: The slot where the equipment should go
        """
        self.is_weapon = is_weapon
        self.equipment_type_id = equipment_type_id
        self.damage = damage
        self.name = name
        self.slot = slot

    @classmethod
    def create_from_json(cls, equipment_type_json: Dict[str, Any]) -> "EquipmentType":
        return cls(
            equipment_type_json.get("weapon", False),
            equipment_type_json["id"],
            Damage.load_from_json(equipment_type_json["damage"]),
            equipment_type_json["name"],
            _get_slot(equipment_type_json["slot"])
        )


class Modifier:
    pass


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
