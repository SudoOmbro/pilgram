import random

from time import time
from copy import copy
from typing import Union, List


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
    def generate(cls, iterations: int, exclude_params: Union[List[str], None] = None) -> "Damage":
        return cls.generate_from_seed(int(time()), iterations, exclude_params)


class Equipment:

    def __init__(self):
        pass


class Weapon(Equipment):

    def __init__(self, damage: Damage):
        super().__init__()
        self.damage = damage


class Armor(Equipment):

    def __init__(self, resistance: Damage):
        super().__init__()
        self.resistance = resistance
