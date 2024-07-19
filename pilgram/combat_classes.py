import random
from abc import ABC
from copy import copy

from time import time
from typing import Union, List, Dict

from pilgram.modifiers import ModifierType, Modifier, ModifierContext


class Damage:
    """ used to express damage & resistance values """
    MIN_DAMAGE: int = 1

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

    def modify(self, supplier: "CombatActor", other: "CombatActor", type_filter: int) -> "Damage":
        result = self
        for modifier in supplier.get_modifiers(type_filter):
            new_result = modifier.apply(ModifierContext({"damage": self, "supplier": supplier, "other": other}))
            if new_result:
                result = new_result
        return result

    def get_total_damage(self) -> int:
        """ return the total damage dealt by the attack. Damage can't be 0, it must be at least 1 """
        dmg = self.slash + self.pierce + self.blunt + self.occult + self.fire + self.acid + self.freeze + self.electric
        return dmg if dmg > 0 else self.MIN_DAMAGE

    def scale(self, scaling_factor: float) -> "Damage":
        return Damage(
            int(self.slash * scaling_factor),
            int(self.pierce * scaling_factor),
            int(self.blunt * scaling_factor),
            int(self.occult * scaling_factor),
            int(self.fire * scaling_factor),
            int(self.acid * scaling_factor),
            int(self.freeze * scaling_factor),
            int(self.electric * scaling_factor)
        )

    def apply_bonus(self, bonus: int) -> "Damage":
        return Damage(
            (self.slash + bonus) if self.slash else 0,
            (self.pierce + bonus) if self.pierce else 0,
            (self.blunt + bonus) if self.blunt else 0,
            (self.occult + bonus) if self.occult else 0,
            (self.fire + bonus) if self.fire else 0,
            (self.acid + bonus) if self.acid else 0,
            (self.freeze + bonus) if self.freeze else 0,
            (self.electric + bonus) if self.electric else 0
        )

    def scale_single_value(self, key: str, scaling_factor: float) -> "Damage":
        new_damage = copy(self)
        new_damage.__dict__[key] = int(new_damage.__dict__[key] * scaling_factor)
        return new_damage

    def add_single_value(self, key: str, value: int) -> "Damage":
        new_damage = copy(self)
        new_damage.__dict__[key] = new_damage.__dict__[key] + value
        return new_damage

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

    def __bool__(self):
        dmg = self.slash + self.pierce + self.blunt + self.occult + self.fire + self.acid + self.freeze + self.electric
        return dmg != 0

    def __str__(self):
        return "\n".join([f"{key}: {value}" for key, value in self.__dict__.items() if value > 0])

    @classmethod
    def get_empty(cls) -> "Damage":
        return Damage(0, 0, 0, 0, 0, 0, 0, 0)

    @classmethod
    def generate_from_seed(cls, seed: float, iterations: int, exclude_params: Union[List[str], None] = None) -> "Damage":
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
        return cls.generate_from_seed(time(), iterations, exclude_params)


class CombatActor(ABC):

    def __init__(self, hp_percent: float):
        self.hp_percent = hp_percent  # used out of fights
        self.hp: int = 0  # only used during fights
        self.timed_modifiers: List[Modifier] = []  # list of timed modifiers inflicted on the CombatActor

    def get_base_max_hp(self) -> int:
        """ returns the maximum hp of the combat actor (players & enemies) """
        raise NotImplementedError

    def get_base_attack_damage(self) -> Damage:
        """ generic method that should return the damage done by the entity """
        raise NotImplementedError

    def get_base_attack_resistance(self) -> Damage:
        """ generic method that should return the damage resistance of the entity """
        raise NotImplementedError

    def get_entity_modifiers(self, *type_filters: int) -> List["Modifier"]:
        """ generic method that should return an (optionally filtered) list of modifiers. (args are the filters) """
        raise NotImplementedError

    def roll(self, dice_faces: int):
        """ generic method used to roll dices for entities """
        raise NotImplementedError

    def get_modifiers(self, *type_filters: int) -> List["Modifier"]:
        """ returns the list of modifiers + timed modifiers """
        modifiers: List[Modifier] = self.get_entity_modifiers(*type_filters)
        if not type_filters:
            modifiers.extend(self.timed_modifiers)
            modifiers.sort(key=lambda x: x.OP_ORDERING)
            return modifiers
        for modifier in self.timed_modifiers:
            if modifier.TYPE in type_filters:
                modifiers.append(modifier)
        modifiers.sort(key=lambda x: x.OP_ORDERING)
        return modifiers

    def start_fight(self):
        self.hp = int(self.get_max_hp() * self.hp_percent)

    def get_max_hp(self) -> int:
        """ get max hp of the entity applying all modifiers """
        max_hp = self.get_base_max_hp()
        for modifier in self.get_entity_modifiers(ModifierType.COMBAT_START):
            val = modifier.apply(ModifierContext({"entity": self}))
            max_hp += val if val else 0
        return int(max_hp)

    def attack(self, target: "CombatActor") -> Damage:
        """ get the damage an attack would do """
        damage = self.get_base_attack_damage().modify(self, target, ModifierType.ATTACK)
        defense = target.get_base_attack_resistance().modify(target, self, ModifierType.DEFEND)
        return damage - defense

    def modify_hp(self, amount: int) -> bool:
        """ Modify actor hp. Return True if the actor was killed, otherwise return False """
        self.hp += amount
        if self.hp <= 0:
            self.hp = 0
            self.hp_percent = 0.0
            return True
        self.hp_percent = self.hp / self.get_max_hp()
        return False

    def receive_damage(self, damage: Damage) -> bool:
        """ damage the actor with damage. Return True if the actor was killed, otherwise return False """
        damage_received = -damage.get_total_damage()
        return self.modify_hp(damage_received)

    def get_delay(self) -> int:
        """ returns the delay of the actor, which is a factor that determines who goes first in the combat turn """
        raise NotImplementedError

    def get_initiative(self) -> int:
        """ returns the initiative of the actor, which determines who goes first in the combat turn """
        return self.get_delay() - self.roll(20)

    def is_dead(self) -> bool:
        return self.hp <= 0
