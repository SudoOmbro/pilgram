import random
from abc import ABC
from copy import copy

from time import time
from typing import Union, List, Dict, Type, Any


class ModifierType:
    PRE_ATTACK = 0
    PRE_DEFEND = 1
    POST_ATTACK = 2
    POST_DEFEND = 3
    HP_MODIFIER = 4


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

    def modify(self, supplier: "CombatActor", type_filter: int) -> "Damage":
        result = self
        for modifier in supplier.get_modifiers(type_filter):
            result = modifier.apply(result, supplier)
        return result

    def get_total_damage(self) -> int:
        """ return the total damage dealt by the attack. Damage can't be 0, it must be at least 1 """
        dmg = self.slash + self.pierce + self.blunt + self.occult + self.fire + self.acid + self.freeze + self.electric
        return dmg if dmg > 0 else 1

    def scale(self, scaling_factor: int) -> "Damage":
        return Damage(
            self.slash * scaling_factor,
            self.pierce * scaling_factor,
            self.blunt * scaling_factor,
            self.occult * scaling_factor,
            self.fire * scaling_factor,
            self.acid * scaling_factor,
            self.freeze * scaling_factor,
            self.electric * scaling_factor
        )

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

    def __sub__(self, other):
        """ used when self attacks other """
        slash = (self.slash - other.slash) if self.slash else 0
        pierce = (self.pierce - other.pierce) if self.pierce else 0
        blunt = (self.blunt - other.blunt) if self.blunt else 0
        occult = (self.occult - other.occult) if self.occult else 0
        fire = (self.fire - other.fire) if self.fire else 0
        acid = (self.acid - other.acid) if self.acid else 0
        freeze = (self.freeze - other.freeze) if self.freeze else 0
        electric = (self.electric - other.electric) if self.electric else 0
        return Damage(
            slash if slash > 0 else 0,
            pierce if pierce > 0 else 0,
            blunt if blunt > 0 else 0,
            occult if occult > 0 else 0,
            fire if fire > 0 else 0,
            acid if acid > 0 else 0,
            freeze if freeze > 0 else 0,
            electric if electric > 0 else 0
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
        return cls(
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


class CombatActor(ABC):

    def __init__(self, hp_percent: float):
        self.hp_percent = hp_percent  # used out of fights
        self.hp: int = 0  # only used during fights

    def get_base_max_hp(self) -> int:
        """ returns the maximum hp of the combat actor (players & enemies) """
        raise NotImplementedError

    def get_base_attack_damage(self) -> Damage:
        """ generic method that should return the damage done by the entity """
        raise NotImplementedError

    def get_base_attack_resistance(self) -> Damage:
        """ generic method that should return the damage resistance of the entity """
        raise NotImplementedError

    def get_modifiers(self, *args: int) -> List["Modifier"]:
        """ generic method that should return an (optionally filtered) list of modifiers. (args are the filters) """
        raise NotImplementedError

    def start_fight(self):
        self.hp = int(self.get_max_hp() * self.hp_percent)

    def get_max_hp(self) -> int:
        max_hp = self.get_base_max_hp()
        for modifier in self.get_modifiers(ModifierType.HP_MODIFIER):
            max_hp = modifier.apply(max_hp, self)
        return int(max_hp)

    def attack(self, target: "CombatActor") -> Damage:
        damage = self.get_base_attack_damage().modify(self, ModifierType.PRE_ATTACK)
        defence = target.get_base_attack_resistance().modify(self, ModifierType.PRE_DEFEND)
        damage_done = damage - defence
        damage_done = damage_done.modify(target, ModifierType.POST_DEFEND)
        return damage_done.modify(self, ModifierType.POST_ATTACK)


class Modifier(ABC):
    DATABASE: Dict[int, Type["Modifier"]] = {}
    ID: int

    TYPE: int  # This should be set manually for each defined modifier

    def __init__(self, strength: int):
        self.strength = strength

    def __init_subclass__(cls, **kwargs):
        modifier_id = len(list(Modifier.DATABASE.keys()))
        cls.ID = modifier_id
        Modifier.DATABASE[modifier_id] = cls

    def apply(self, value: Any, actor: CombatActor) -> Any:
        """ apply the modifier to the value & actor, optionally return a value """
        raise NotImplementedError

    @staticmethod
    def get(modifier_id: int, strength: int) -> "Modifier":
        return Modifier.DATABASE[modifier_id](strength)
