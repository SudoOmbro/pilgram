import random
from abc import ABC

import pilgram.combat_classes as cc
import pilgram.classes as classes

from typing import Any, Dict, Type, List, Union

from pilgram.strings import Strings


class ModifierType:
    COMBAT_START = 0
    ATTACK = 1
    DEFEND = 2
    POST_ATTACK = 3
    POST_DEFEND = 4
    REWARDS = 5


class Rarity:
    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    LEGENDARY = 3


class ModifierContext:

    def __init__(self, dictionary: Dict[str, Any]):
        self.__dictionary = dictionary

    def get(self, key: str, default_value: Any = None) -> Any:
        return self.__dictionary.get(key, default_value)


_LIST: List[Type["Modifier"]] = []
_RARITY_INDEX: Dict[int, List[Type["Modifier"]]] = {0: [], 1: [], 2: [], 3: []}


def get_modifier(modifier_id: int, strength: int) -> "Modifier":
    """ returns a new modifier with its strength value """
    return _LIST[modifier_id](strength)


def get_modifiers_by_rarity(rarity: int) -> List[Type["Modifier"]]:
    return _RARITY_INDEX.get(rarity, [])


def print_all_modifiers():
    for modifier in _LIST:
        print(str(modifier(modifier.MIN_STRENGTH)))
    for rarity, modifiers in _RARITY_INDEX.items():
        for modifier in modifiers:
            print(str(modifier(modifier.MIN_STRENGTH)))


class Modifier(ABC):
    """ the basic abstract modifier class, all other modifiers should inherit from it. """
    ID: int
    RARITY: Union[int, None] = None

    TYPE: int  # This should be set manually for each defined modifier
    OP_ORDERING: int = 0  # used to order modifiers

    MAX_STRENGTH: int  # used during generation
    MIN_STRENGTH: int = 1  # used during generation
    SCALING: Union[int, float]  # determines how the modifiers scales with the level of the entity (at generation) (strength / SCALING)

    NAME: str  # The name of the modifier
    DESCRIPTION: str  # used to describe what the modifier does. {str} is the strength placeholder

    def __init__(self, strength: int, duration: int = -1):
        """
        :param strength: the strength of the modifier, used to make modifiers scale with level
        :param duration: the duration in turns of the modifier, only used for temporary modifiers during combat
        """
        self.strength = strength
        self.duration = duration

    def __init_subclass__(cls, rarity: Union[int, None] = None):
        if rarity is not None:
            modifier_id = len(_LIST)
            print(f"Loaded modifier '{cls.__name__}' with id {modifier_id}")
            cls.ID = modifier_id
            cls.RARITY = rarity
            _LIST.append(cls)
            _RARITY_INDEX[rarity].append(cls)

    def function(self, context: ModifierContext) -> Any:
        """ apply the modifier to the entities in the context, optionally return a value """
        raise NotImplementedError

    def apply(self, context: ModifierContext) -> Any:
        """ apply the modifier effect and reduce the duration if needed """
        if self.duration > 0:
            self.duration -= 1
        elif self.duration == 0:  # if the modifier expired then do nothing
            return None
        return self.function(context)

    def __str__(self):
        return f"*{self.NAME}* - {Strings.rarities[self.RARITY]}\n_{self.DESCRIPTION.format(str=self.strength)}_"

    @classmethod
    def generate(cls, level: int) -> "Modifier":
        return cls(cls.MIN_STRENGTH + int((level / cls.SCALING)))


class GenericDamageMult(Modifier):
    MAX_STRENGTH = 200
    MIN_STRENGTH = 100
    SCALING = 1

    DESCRIPTION = "Scales DIRECTION DAMAGE damage by {str}%"
    DAMAGE_TYPE: str

    def __init_subclass__(cls, dmg_type: str = None, mod_type: int = None, **kwargs):
        if dmg_type is None:
            raise ValueError("dmg_type cannot be None")
        super().__init_subclass__(rarity=Rarity.COMMON)
        cls.DAMAGE_TYPE = dmg_type
        cls.DESCRIPTION = cls.DESCRIPTION.replace("DAMAGE", dmg_type)
        cls.DESCRIPTION = cls.DESCRIPTION.replace("DIRECTION", "Outgoing" if mod_type == ModifierType.ATTACK else "Incoming")
        cls.NAME = f"{dmg_type.capitalize()} {'Affinity' if mod_type == ModifierType.ATTACK else 'Resistant'}"
        cls.TYPE = mod_type

    def function(self, context: ModifierContext) -> Any:
        # scales in the same way for attack & defence
        damage: cc.Damage = context.get("damage")
        return damage.scale_single_value(self.DAMAGE_TYPE, self.strength / 100)


class SlashAttackMult(GenericDamageMult, dmg_type="slash", mod_type=ModifierType.ATTACK): pass
class PierceAttackMult(GenericDamageMult, dmg_type="pierce", mod_type=ModifierType.ATTACK): pass
class BluntAttackAttackMult(GenericDamageMult, dmg_type="blunt", mod_type=ModifierType.ATTACK): pass
class OccultAttackMult(GenericDamageMult, dmg_type="occult", mod_type=ModifierType.ATTACK): pass
class FireAttackMult(GenericDamageMult, dmg_type="fire", mod_type=ModifierType.ATTACK): pass
class AcidAttackMult(GenericDamageMult, dmg_type="acid", mod_type=ModifierType.ATTACK): pass
class FreezeAttackMult(GenericDamageMult, dmg_type="freeze", mod_type=ModifierType.ATTACK): pass
class ElectricAttackMult(GenericDamageMult, dmg_type="electric", mod_type=ModifierType.ATTACK): pass
class SlashDefendMult(GenericDamageMult, dmg_type="slash", mod_type=ModifierType.DEFEND): pass
class PierceDefendMult(GenericDamageMult, dmg_type="pierce", mod_type=ModifierType.DEFEND): pass
class BluntDefendAttackMult(GenericDamageMult, dmg_type="blunt", mod_type=ModifierType.DEFEND): pass
class OccultDefendMult(GenericDamageMult, dmg_type="occult", mod_type=ModifierType.DEFEND): pass
class FireDefendMult(GenericDamageMult, dmg_type="fire", mod_type=ModifierType.DEFEND): pass
class AcidDefendMult(GenericDamageMult, dmg_type="acid", mod_type=ModifierType.DEFEND): pass
class FreezeDefendMult(GenericDamageMult, dmg_type="freeze", mod_type=ModifierType.DEFEND): pass
class ElectricDefendMult(GenericDamageMult, dmg_type="electric", mod_type=ModifierType.DEFEND): pass


class KillAtPercentHealth(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 50
    SCALING = 5

    NAME = "Lethality"
    DESCRIPTION = "Instantly kill the target if its health is below {str}%"

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("other")
        if target.hp_percent <= (self.strength / 100):
            # doing this will instantly kill the entity since the minimum damage an attack can do is 1
            target.hp = 0
            target.hp_percent = 0.0
        return context.get("damage")


class Berserk(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 60
    SCALING = 2

    NAME = "Berserk"
    DESCRIPTION = "Doubles damage if HP goes under {str}%."

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        if attacker.hp_percent <= (self.strength / 100):
            return damage.scale(2.0)
        return damage


class ChaosBrand(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 200
    MIN_STRENGTH = 100
    SCALING = 0.5

    NAME = "Chaos Brand"
    DESCRIPTION = "Randomly scales the attack damage by a number in a range from 80% to {str}%"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        scaling_factor = 0.8 + (random.random() * (self.strength / 100))
        return damage.scale(scaling_factor)


class LuckyHit(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 500
    MIN_STRENGTH = 100
    SCALING = 0.6

    NAME = "Lucky Hit"
    DESCRIPTION = "Gives 20% chance of dealing {str}% damage"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        if attacker.roll(10) > 8:
            return damage.scale(self.strength / 100)


class PoisonTipped(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 10
    SCALING = 10

    NAME = "Poison Tipped"
    DESCRIPTION = "Inflicts the target with poison for {str} turns ({str} damage per turn)"

    class PoisonProc(Modifier):
        TYPE = ModifierType.POST_DEFEND

        def function(self, context: ModifierContext) -> Any:
            target: cc.CombatActor = context.get("target")
            target.modify_hp(-self.strength)

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("target")
        target.timed_modifiers.append(self.PoisonProc(self.strength, self.strength))



class EldritchShield(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.COMBAT_START

    MAX_STRENGTH = 5
    SCALING = 20

    NAME = "Eldritch Shield"
    DESCRIPTION = "Any hits will only do 1 damage for the first {str} attacks received."

    class TankHits(Modifier):
        TYPE = ModifierType.DEFEND

        def function(self, context: ModifierContext) -> Any:
            return cc.Damage.get_empty()

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.timed_modifiers.append(self.TankHits(0, duration=self.strength))


class Vampiric(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.POST_ATTACK

    MAX_STRENGTH = 5
    SCALING = 20

    NAME = "Vampiric"
    DESCRIPTION = "Gains {str}% of the damage dealt as hp"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("attacker")
        attacker.modify_hp(int(damage.get_total_damage() * (self.strength / 100)))


class UnyieldingWill(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.COMBAT_START

    MAX_STRENGTH = 2
    SCALING = 80

    NAME = "Unyielding Will"
    DESCRIPTION = "Gives {str} free revives per combat"

    class FreeRevive(Modifier):
        TYPE = ModifierType.POST_DEFEND

        def function(self, context: ModifierContext) -> Any:
            target: cc.CombatActor = context.get("target")
            if target.hp == 0:
                target.modify_hp(int(target.get_max_hp() / 50))
            else:
                self.duration += 1  # if the bonus was not used then restore duration

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.timed_modifiers.append(self.FreeRevive(1, duration=self.strength))