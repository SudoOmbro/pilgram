import random
from abc import ABC

import pilgram.combat_classes as cc
import pilgram.classes as classes
import pilgram.equipment as equipment

from typing import Any, Dict, Type, List, Union

from pilgram.strings import Strings


class ModifierType:
    COMBAT_START = 0
    ATTACK = 1
    DEFEND = 2
    POST_ATTACK = 3
    POST_DEFEND = 4
    REWARDS = 5
    MODIFY_MAX_HP = 6


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


def get_all_modifiers() -> List[Type["Modifier"]]:
    return _LIST


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
            cls.ID = modifier_id
            cls.RARITY = rarity
            _LIST.append(cls)
            _RARITY_INDEX[rarity].append(cls)

    def get_fstrength(self) -> float:
        """ returns the strength divided by 100 """
        return self.strength / 100

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

    @staticmethod
    def write_to_log(context: ModifierContext, text: str) -> Any:
        combat_container: Union[cc.CombatContainer, None] = context.get("context", None)
        if combat_container is None:
            return
        combat_container.write_to_log(text)

    def __str__(self):
        return f"*{self.NAME}* - {Strings.rarities[self.RARITY]}\n_{self.DESCRIPTION.format(str=self.strength)}_"

    def __eq__(self, other):
        if isinstance(other, Modifier):
            return (self.ID == other.ID) and (self.strength == other.strength)
        return False

    @classmethod
    def generate(cls, level: int) -> "Modifier":
        strength: int = cls.MIN_STRENGTH + int(level / cls.SCALING)
        if (cls.MAX_STRENGTH != 0) and (strength > cls.MAX_STRENGTH):
            strength = cls.MAX_STRENGTH
        return cls(strength)


class GenericDamageMult(Modifier):
    MAX_STRENGTH = 100
    MIN_STRENGTH = 1
    SCALING = 2

    DESCRIPTION = "Increases DAMAGE WHAT by {str}%"
    DAMAGE_TYPE: str

    def __init_subclass__(cls, dmg_type: str = None, mod_type: int = None, **kwargs):
        if dmg_type is None:
            raise ValueError("dmg_type cannot be None")
        super().__init_subclass__(rarity=Rarity.COMMON)
        cls.DAMAGE_TYPE = dmg_type
        cls.DESCRIPTION = cls.DESCRIPTION.replace("DAMAGE", dmg_type)
        cls.DESCRIPTION = cls.DESCRIPTION.replace("WHAT", "damage" if mod_type == ModifierType.ATTACK else "resistance")
        cls.NAME = f"{dmg_type.capitalize()} {'Affinity' if mod_type == ModifierType.ATTACK else 'Resistant'}"
        cls.TYPE = mod_type

    def function(self, context: ModifierContext) -> Any:
        # scales in the same way for attack & defence
        damage: cc.Damage = context.get("damage")
        return damage.scale_single_value(self.DAMAGE_TYPE, (100 + self.strength) / 100)


class GenericDamageBonus(Modifier):
    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 2

    DESCRIPTION = "DAMAGE WHAT +{str}"
    DAMAGE_TYPE: str

    def __init_subclass__(cls, dmg_type: str = None, mod_type: int = None, **kwargs):
        if dmg_type is None:
            raise ValueError("dmg_type cannot be None")
        super().__init_subclass__(rarity=Rarity.COMMON)
        cls.DAMAGE_TYPE = dmg_type
        cls.DESCRIPTION = cls.DESCRIPTION.replace("DAMAGE", dmg_type)
        cls.DESCRIPTION = cls.DESCRIPTION.replace("WHAT", "damage" if mod_type == ModifierType.ATTACK else "resistance")
        cls.NAME = f"{dmg_type.capitalize()} {'Optimized' if mod_type == ModifierType.ATTACK else 'shielded'}"
        cls.TYPE = mod_type

    def function(self, context: ModifierContext) -> Any:
        # scales in the same way for attack & defence
        damage: cc.Damage = context.get("damage")
        return damage.add_single_value(self.DAMAGE_TYPE, self.strength)


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

class SlashAttackBonus(GenericDamageBonus, dmg_type="slash", mod_type=ModifierType.ATTACK): pass
class PierceAttackBonus(GenericDamageBonus, dmg_type="pierce", mod_type=ModifierType.ATTACK): pass
class BluntAttackAttackBonus(GenericDamageBonus, dmg_type="blunt", mod_type=ModifierType.ATTACK): pass
class OccultAttackBonus(GenericDamageBonus, dmg_type="occult", mod_type=ModifierType.ATTACK): pass
class FireAttackBonus(GenericDamageBonus, dmg_type="fire", mod_type=ModifierType.ATTACK): pass
class AcidAttackBonus(GenericDamageBonus, dmg_type="acid", mod_type=ModifierType.ATTACK): pass
class FreezeAttackBonus(GenericDamageBonus, dmg_type="freeze", mod_type=ModifierType.ATTACK): pass
class ElectricAttackBonus(GenericDamageBonus, dmg_type="electric", mod_type=ModifierType.ATTACK): pass
class SlashDefendBonus(GenericDamageBonus, dmg_type="slash", mod_type=ModifierType.DEFEND): pass
class PierceDefendBonus(GenericDamageBonus, dmg_type="pierce", mod_type=ModifierType.DEFEND): pass
class BluntDefendAttackBonus(GenericDamageBonus, dmg_type="blunt", mod_type=ModifierType.DEFEND): pass
class OccultDefendBonus(GenericDamageBonus, dmg_type="occult", mod_type=ModifierType.DEFEND): pass
class FireDefendBonus(GenericDamageBonus, dmg_type="fire", mod_type=ModifierType.DEFEND): pass
class AcidDefendBonus(GenericDamageBonus, dmg_type="acid", mod_type=ModifierType.DEFEND): pass
class FreezeDefendBonus(GenericDamageBonus, dmg_type="freeze", mod_type=ModifierType.DEFEND): pass
class ElectricDefendBonus(GenericDamageBonus, dmg_type="electric", mod_type=ModifierType.DEFEND): pass


class FirstHitBonus(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 0
    SCALING = 0.5

    NAME = "Sneak attack"
    DESCRIPTION = "Deal {str} bonus damage of each type if the target is at full health"

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("target")
        damage = context.get("damage")
        if target.hp_percent >= 1.0:
            self.write_to_log(context, f"Sneak attack! +{self.strength} damage")
            return damage.apply_bonus(self.strength)
        return damage


class KillAtPercentHealth(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 50
    SCALING = 5

    NAME = "Lethality"
    DESCRIPTION = "Instantly kill the target if its health is below {str}%"

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("other")
        if target.hp_percent <= self.get_fstrength():
            # doing this will instantly kill the entity since the minimum damage an attack can do is 1
            target.hp = 0
            target.hp_percent = 0.0
            self.write_to_log(context, f"{target.get_name()} is executed!")
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
        if attacker.hp_percent <= self.get_fstrength():
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
        scaling_factor = 0.8 + (random.random() * self.get_fstrength())
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
            scale = self.get_fstrength()
            self.write_to_log(context, f"Lucky Hit!")
            return damage.scale(scale)
        return damage


class PoisonTipped(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 10
    SCALING = 10

    NAME = "Poison Tipped"
    DESCRIPTION = "Inflicts the target with poison for {str} turns (2 x {str} damage per turn)"

    class PoisonProc(Modifier):
        TYPE = ModifierType.POST_DEFEND

        def function(self, context: ModifierContext) -> Any:
            target: cc.CombatActor = context.get("supplier")
            target.modify_hp(-self.strength)

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("other")
        target.timed_modifiers.append(self.PoisonProc(self.strength, self.strength * 2))
        return context.get("damage")


class EldritchShield(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.COMBAT_START

    MAX_STRENGTH = 3
    SCALING = 30

    NAME = "Eldritch Shield"
    DESCRIPTION = "Any hits will only do 1 damage for the first {str} attacks received."

    class TankHits(Modifier):
        TYPE = ModifierType.DEFEND

        def function(self, context: ModifierContext) -> Any:
            damage = context.get("damage")
            entity = context.get("supplier")
            if damage.get_total_damage() > 1:
                self.write_to_log(context, f"{entity.get_name()}'s shield nullifies the hit.")
                if self.duration == 0:
                    self.write_to_log(context, f"{entity.get_name()}'s shield breaks!")
                return cc.Damage.get_empty()
            else:
                self.duration += 1

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.timed_modifiers.append(self.TankHits(0, duration=self.strength))
        self.write_to_log(context, f"An Eldritch Shield forms around {entity.get_name()}")
        return 0


class Vampiric(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.POST_ATTACK

    MAX_STRENGTH = 5
    SCALING = 20

    NAME = "Vampiric"
    DESCRIPTION = "Gains {str}% of the damage dealt as hp"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        healing = int(damage.get_total_damage() * self.get_fstrength())
        attacker.modify_hp(healing)
        self.write_to_log(context, f"{attacker.get_name()} leeches {healing} HP.")
        return damage


class UnyieldingWill(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.COMBAT_START

    MAX_STRENGTH = 2
    SCALING = 80

    NAME = "Unyielding Will"
    DESCRIPTION = "Gives {str} free revives per combat"

    class FreeRevive(Modifier):
        TYPE = ModifierType.POST_DEFEND

        def function(self, context: ModifierContext) -> Any:
            me: cc.CombatActor = context.get("supplier")
            if me.hp == 0:
                self.write_to_log(context, f"Thanks to their Unyielding Will {me.get_name()} still stands.")
                me.modify_hp(int(me.get_max_hp() / 50))
            else:
                self.duration += 1  # if the bonus was not used then restore duration

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.timed_modifiers.append(self.FreeRevive(1, duration=self.strength))


class BloodThirst(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.COMBAT_START

    MAX_STRENGTH = 20
    SCALING = 5

    NAME = "Blood Thirst"
    DESCRIPTION = "Gain {str} HP at the start of combat."

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.modify_hp(self.strength)
        self.write_to_log(context, f"{entity.get_name()}'s blood thirst heals them for {entity.hp} HP.")


class Blessed(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.MODIFY_MAX_HP

    MAX_STRENGTH = 50
    SCALING = 2

    NAME = "Blessed"
    DESCRIPTION = "Increases max HP by {str}%."

    def function(self, context: ModifierContext) -> Any:
        value = context.get("value")
        return int(value * (1 + self.get_fstrength()))


class Bashing(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.ATTACK

    MAX_STRENGTH = 50
    SCALING = 2

    NAME = "Bashing"
    DESCRIPTION = "Deal {str}% more damage if you are using a shield"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        if isinstance(attacker, classes.Player):
            secondary = attacker.equipped_items.get(equipment.Slots.SECONDARY)
            if not secondary.equipment_type.is_weapon:
                return damage.scale(1 + (self.get_fstrength()))
        return damage


print(f"Loaded {len(_LIST)} modifiers")  # Always keep at the end
