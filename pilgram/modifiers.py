from __future__ import annotations

import random
from abc import ABC
from typing import Any

import pilgram.classes as classes
import pilgram.combat_classes as cc
import pilgram.equipment as equipment
from pilgram.strings import Strings


class ModifierType:
    COMBAT_START = 0  # applied at the start of the combat
    PRE_ATTACK = 1  # applied when the attacker starts to attack
    PRE_DEFEND = 2  # applied when the target starts to defend
    MID_ATTACK = 3  # applied just before inflicting the damage
    MID_DEFEND = 4  # applied just before the damage is inflicted
    POST_ATTACK = 5  # applied after the damage is inflicted
    POST_DEFEND = 6  # applied just after the damage was inflicted
    REWARDS = 7  # applied at combat end, during the reward phase
    MODIFY_MAX_HP = 8  # modify max hp
    TURN_START = 9  # applied at the start of the turn
    STAMINA_REGEN = 10  # applied during the stamina regen phase
    ON_DEATH = 11  # applied on death
    MODIFY_STATS = 12  # applied when getting stats


class Rarity:
    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    LEGENDARY = 3


class ModifierContext:
    def __init__(self, dictionary: dict[str, Any]) -> None:
        self.__dictionary = dictionary

    def get(self, key: str, default_value: Any = None) -> Any:
        return self.__dictionary.get(key, default_value)


_LIST: list[type[Modifier]] = []
_RARITY_INDEX: dict[int, list[type[Modifier]]] = {0: [], 1: [], 2: [], 3: []}
_NAME_LUT: dict[str, type[Modifier]] = {}


def get_modifier(modifier_id: int, strength: int) -> Modifier:
    """returns a new modifier with its strength value, given its id"""
    return _LIST[modifier_id](strength)


def get_scaled_strength_modifier(modifier_id: int, level: int) -> Modifier:
    """returns a new modifier with its strength value, given its id"""
    m: type(Modifier) = _LIST[modifier_id]
    return m.generate(level)


def get_modifier_from_name(modifier_name: str, strength: int) -> Modifier:
    """returns a new modifier with its strength value, given its name"""
    return _NAME_LUT[modifier_name](strength)


def get_modifiers_by_rarity(rarity: int) -> list[type[Modifier]]:
    return _RARITY_INDEX.get(rarity, [])


def get_all_modifiers() -> list[type[Modifier]]:
    return _LIST


def print_all_modifiers() -> None:
    for modifier in _LIST:
        print(str(modifier(modifier.MIN_STRENGTH)))
    for _, modifiers in _RARITY_INDEX.items():
        for modifier in modifiers:
            print(str(modifier(modifier.MIN_STRENGTH)))


class Modifier(ABC):
    """the basic abstract modifier class, all other modifiers should inherit from it."""

    ID: int
    RARITY: int | None = None

    TYPE: int  # This should be set manually for each defined modifier
    OP_ORDERING: int = 0  # used to order modifiers

    MAX_STRENGTH: int = (
        0  # used during generation (keep 0 if modifier should scale infinitely)
    )
    MIN_STRENGTH: int = 1  # used during generation
    SCALING: (
        int | float
    )  # determines how the modifiers scales with the level of the entity (at generation) (strength / SCALING)

    NAME: str  # The name of the modifier
    DESCRIPTION: str  # used to describe what the modifier does. {str} is the strength placeholder

    def __init__(self, strength: int, duration: int = -1) -> None:
        """
        :param strength: the strength of the modifier, used to make modifiers scale with level
        :param duration: the duration in turns of the modifier, only used for temporary modifiers during combat
        """
        self.strength = strength
        self.duration = duration

    def __init_subclass__(cls, rarity: int | None = None) -> None:
        if rarity is not None:
            modifier_id = len(_LIST)
            cls.ID = modifier_id
            cls.RARITY = rarity
            _LIST.append(cls)
            _RARITY_INDEX[rarity].append(cls)
            _NAME_LUT[cls.NAME] = cls

    def get_fstrength(self) -> float:
        """returns the strength divided by 100"""
        return self.strength / 100

    def function(self, context: ModifierContext) -> Any:
        """apply the modifier to the entities in the context, optionally return a value"""
        raise NotImplementedError

    def apply(self, context: ModifierContext) -> Any:
        """apply the modifier effect and reduce the duration if needed"""
        if self.duration > 0:
            self.duration -= 1
        elif self.duration == 0:  # if the modifier expired then do nothing
            return None
        return self.function(context)

    @staticmethod
    def write_to_log(context: ModifierContext, text: str) -> Any:
        combat_container: cc.CombatContainer | None = context.get("context", None)
        if combat_container is None:
            return
        combat_container.write_to_log(text)

    def __str__(self) -> str:
        return f"*{self.NAME}* - {Strings.rarities[self.RARITY]}\n_{self.DESCRIPTION.format(str=self.strength)}_"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Modifier):
            return (self.ID == other.ID) and (self.strength == other.strength)
        return False

    @classmethod
    def generate(cls, level: int) -> Modifier:
        strength: int = cls.MIN_STRENGTH + int(level / cls.SCALING)
        if (cls.MAX_STRENGTH != 0) and (strength > cls.MAX_STRENGTH):
            strength = cls.MAX_STRENGTH
        return cls(strength)


class _GenericDamageMult(Modifier):
    MAX_STRENGTH = 100
    MIN_STRENGTH = 1
    SCALING = 2

    DESCRIPTION = "Increases DAMAGE WHAT by {str}%"
    DAMAGE_TYPE: str

    def __init_subclass__(
        cls, dmg_type: str | None = None, mod_type: int | None = None, **kwargs
    ) -> None:
        if dmg_type is None:
            raise ValueError("dmg_type cannot be None")
        cls.NAME = f"{dmg_type.capitalize()} {'Affinity' if mod_type == ModifierType.PRE_ATTACK else 'Resistant'}"
        super().__init_subclass__(rarity=Rarity.COMMON)
        cls.DAMAGE_TYPE = dmg_type
        cls.DESCRIPTION = cls.DESCRIPTION.replace("DAMAGE", dmg_type)
        cls.DESCRIPTION = cls.DESCRIPTION.replace(
            "WHAT", "damage" if mod_type == ModifierType.PRE_ATTACK else "resistance"
        )
        cls.TYPE = mod_type

    def function(self, context: ModifierContext) -> cc.Damage:
        # scales in the same way for attack & defence
        damage: cc.Damage = context.get("damage")
        return damage.scale_single_value(self.DAMAGE_TYPE, (100 + self.strength) / 100)


class _GenericDamageBonus(Modifier):
    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 0.5

    OP_ORDERING = 1

    DESCRIPTION = "DAMAGE WHAT +{str}"
    DAMAGE_TYPE: str

    def __init_subclass__(
        cls, dmg_type: str | None = None, mod_type: int | None = None, **kwargs
    ) -> None:
        if dmg_type is None:
            raise ValueError("dmg_type cannot be None")
        cls.NAME = f"{dmg_type.capitalize()} {'Optimized' if mod_type == ModifierType.PRE_ATTACK else 'shielded'}"
        super().__init_subclass__(rarity=Rarity.COMMON)
        cls.DAMAGE_TYPE = dmg_type
        cls.DESCRIPTION = cls.DESCRIPTION.replace("DAMAGE", dmg_type)
        cls.DESCRIPTION = cls.DESCRIPTION.replace(
            "WHAT", "damage" if mod_type == ModifierType.PRE_ATTACK else "resistance"
        )
        cls.TYPE = mod_type

    def function(self, context: ModifierContext) -> cc.Damage:
        # scales in the same way for attack & defence
        damage: cc.Damage = context.get("damage")
        return damage.add_single_value(self.DAMAGE_TYPE, self.strength)


class _GenericDamageAbsorb(Modifier):
    TYPE = ModifierType.MID_DEFEND

    MAX_STRENGTH = 100
    MIN_STRENGTH = 1
    SCALING = 0.5

    DESCRIPTION = "absorb {str}% of incoming DAMAGE damage as HP"
    DAMAGE_TYPE: str

    def __init_subclass__(cls, dmg_type: str = None, **kwargs) -> None:
        if dmg_type is None:
            raise ValueError("dmg_type cannot be None")
        cls.NAME = f"{dmg_type.capitalize()} Absorption"
        super().__init_subclass__(rarity=Rarity.UNCOMMON)
        cls.DAMAGE_TYPE = dmg_type
        cls.DESCRIPTION = cls.DESCRIPTION.replace("DAMAGE", dmg_type)

    def function(self, context: ModifierContext) -> None:
        # scales in the same way for attack & defence
        damage: cc.Damage = context.get("damage")
        defender: cc.CombatActor = context.get("target")
        element_damage: int = damage.__dict__[self.DAMAGE_TYPE]
        if element_damage > 0:
            hp = int(element_damage * self.get_fstrength())
            if hp == 0:
                hp = 1
            defender.modify_hp(hp, overheal=True)
            self.write_to_log(
                context,
                f"{defender.get_name()} heals {hp} HP from {self.DAMAGE_TYPE} damage. ({defender.get_hp_string()})",
            )


class SlashAttackMult(
    _GenericDamageMult, dmg_type="slash", mod_type=ModifierType.PRE_ATTACK
):
    pass


class PierceAttackMult(
    _GenericDamageMult, dmg_type="pierce", mod_type=ModifierType.PRE_ATTACK
):
    pass


class BluntAttackAttackMult(
    _GenericDamageMult, dmg_type="blunt", mod_type=ModifierType.PRE_ATTACK
):
    pass


class OccultAttackMult(
    _GenericDamageMult, dmg_type="occult", mod_type=ModifierType.PRE_ATTACK
):
    pass


class FireAttackMult(
    _GenericDamageMult, dmg_type="fire", mod_type=ModifierType.PRE_ATTACK
):
    pass


class AcidAttackMult(
    _GenericDamageMult, dmg_type="acid", mod_type=ModifierType.PRE_ATTACK
):
    pass


class FreezeAttackMult(
    _GenericDamageMult, dmg_type="freeze", mod_type=ModifierType.PRE_ATTACK
):
    pass


class ElectricAttackMult(
    _GenericDamageMult, dmg_type="electric", mod_type=ModifierType.PRE_ATTACK
):
    pass


class SlashDefendMult(
    _GenericDamageMult, dmg_type="slash", mod_type=ModifierType.PRE_DEFEND
):
    pass


class PierceDefendMult(
    _GenericDamageMult, dmg_type="pierce", mod_type=ModifierType.PRE_DEFEND
):
    pass


class BluntDefendAttackMult(
    _GenericDamageMult, dmg_type="blunt", mod_type=ModifierType.PRE_DEFEND
):
    pass


class OccultDefendMult(
    _GenericDamageMult, dmg_type="occult", mod_type=ModifierType.PRE_DEFEND
):
    pass


class FireDefendMult(
    _GenericDamageMult, dmg_type="fire", mod_type=ModifierType.PRE_DEFEND
):
    pass


class AcidDefendMult(
    _GenericDamageMult, dmg_type="acid", mod_type=ModifierType.PRE_DEFEND
):
    pass


class FreezeDefendMult(
    _GenericDamageMult, dmg_type="freeze", mod_type=ModifierType.PRE_DEFEND
):
    pass


class ElectricDefendMult(
    _GenericDamageMult, dmg_type="electric", mod_type=ModifierType.PRE_DEFEND
):
    pass


class SlashAttackBonus(
    _GenericDamageBonus, dmg_type="slash", mod_type=ModifierType.PRE_ATTACK
):
    pass


class PierceAttackBonus(
    _GenericDamageBonus, dmg_type="pierce", mod_type=ModifierType.PRE_ATTACK
):
    pass


class BluntAttackAttackBonus(
    _GenericDamageBonus, dmg_type="blunt", mod_type=ModifierType.PRE_ATTACK
):
    pass


class OccultAttackBonus(
    _GenericDamageBonus, dmg_type="occult", mod_type=ModifierType.PRE_ATTACK
):
    pass


class FireAttackBonus(
    _GenericDamageBonus, dmg_type="fire", mod_type=ModifierType.PRE_ATTACK
):
    pass


class AcidAttackBonus(
    _GenericDamageBonus, dmg_type="acid", mod_type=ModifierType.PRE_ATTACK
):
    pass


class FreezeAttackBonus(
    _GenericDamageBonus, dmg_type="freeze", mod_type=ModifierType.PRE_ATTACK
):
    pass


class ElectricAttackBonus(
    _GenericDamageBonus, dmg_type="electric", mod_type=ModifierType.PRE_ATTACK
):
    pass


class SlashDefendBonus(
    _GenericDamageBonus, dmg_type="slash", mod_type=ModifierType.PRE_DEFEND
):
    pass


class PierceDefendBonus(
    _GenericDamageBonus, dmg_type="pierce", mod_type=ModifierType.PRE_DEFEND
):
    pass


class BluntDefendAttackBonus(
    _GenericDamageBonus, dmg_type="blunt", mod_type=ModifierType.PRE_DEFEND
):
    pass


class OccultDefendBonus(
    _GenericDamageBonus, dmg_type="occult", mod_type=ModifierType.PRE_DEFEND
):
    pass


class FireDefendBonus(
    _GenericDamageBonus, dmg_type="fire", mod_type=ModifierType.PRE_DEFEND
):
    pass


class AcidDefendBonus(
    _GenericDamageBonus, dmg_type="acid", mod_type=ModifierType.PRE_DEFEND
):
    pass


class FreezeDefendBonus(
    _GenericDamageBonus, dmg_type="freeze", mod_type=ModifierType.PRE_DEFEND
):
    pass


class ElectricDefendBonus(
    _GenericDamageBonus, dmg_type="electric", mod_type=ModifierType.PRE_DEFEND
):
    pass


class FirstHitBonus(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.PRE_ATTACK
    OP_ORDERING = 1

    MAX_STRENGTH = 0
    SCALING = 0.5

    NAME = "Sneak attack"
    DESCRIPTION = "Deal {str} bonus damage of each type if the target is at full health"

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("other")
        damage = context.get("damage")
        if target.hp_percent >= 1.0:
            self.write_to_log(context, f"Sneak attack! +{self.strength} damage")
            return damage.apply_bonus(self.strength)
        return damage


class KillAtPercentHealth(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 50
    SCALING = 5

    NAME = "Obliteration"
    DESCRIPTION = "Instantly kill the target if its health is below {str}%"

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("other")
        if target.hp_percent <= self.get_fstrength():
            # doing this will instantly kill the entity since the minimum damage an attack can do is 1
            target.hp = 0
            target.hp_percent = 0.0
            self.write_to_log(context, "Obliteration.")
        return context.get("damage")


class Berserk(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.PRE_ATTACK

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
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 200
    MIN_STRENGTH = 100
    SCALING = 0.5

    NAME = "Chaos Brand"
    DESCRIPTION = (
        "Randomly scales the attack damage by a number in a range from 80% to {str}%"
    )

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        scaling_factor = 0.8 + (random.random() * self.get_fstrength())
        self.write_to_log(context, f"Chaos: {int(scaling_factor * 100)}%")
        return damage.scale(scaling_factor)


class LuckyHit(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 500
    MIN_STRENGTH = 100
    SCALING = 0.6

    NAME = "Lucky Hit"
    DESCRIPTION = "Gives 20% chance of dealing {str}% damage"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        if random.randint(1, 10) > 8:
            scale = self.get_fstrength()
            self.write_to_log(context, "Lucky Hit!")
            return damage.scale(scale)
        return damage


class PoisonTipped(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 10
    SCALING = 10

    NAME = "Poison Tipped"
    DESCRIPTION = (
        "Inflicts the target with poison for {str} turns (2 x {str} damage per turn)"
    )

    class PoisonProc(Modifier):
        TYPE = ModifierType.TURN_START

        def function(self, context: ModifierContext) -> Any:
            target: cc.CombatActor = context.get("entity")
            target.modify_hp(-self.strength)
            self.write_to_log(
                context,
                f"{target.get_name()} takes {self.strength} poison dmg. ({target.get_hp_string()})",
            )

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
        TYPE = ModifierType.MID_DEFEND

        def function(self, context: ModifierContext) -> Any:
            damage = context.get("damage")
            target = context.get("target")
            if damage.get_total_damage() > 1:
                if self.duration == 0:
                    self.write_to_log(
                        context,
                        f"{target.get_name()}'s shield nullifies the hit and it breaks!",
                    )
                else:
                    self.write_to_log(
                        context, f"{target.get_name()}'s shield nullifies the hit."
                    )
                return cc.Damage.get_empty()
            else:
                self.duration += 1
                return damage

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.timed_modifiers.append(self.TankHits(0, duration=self.strength))
        self.write_to_log(
            context, f"An Eldritch Shield forms around {entity.get_name()}"
        )
        return 0


class Vampiric(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.POST_ATTACK

    MAX_STRENGTH = 10
    MIN_STRENGTH = 1
    SCALING = 20

    NAME = "Vampiric"
    DESCRIPTION = "Gains {str}% of the damage dealt as hp"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        healing = int(damage.get_total_damage() * self.get_fstrength())
        if healing == 0:
            healing = 1
        attacker.modify_hp(healing)
        self.write_to_log(
            context,
            f"{attacker.get_name()} leeches {healing} HP. ({attacker.get_hp_string()})",
        )


class UnyieldingWill(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.COMBAT_START

    MAX_STRENGTH = 2
    MIN_STRENGTH = 1
    SCALING = 80

    NAME = "Unyielding Will"
    DESCRIPTION = "Gives {str} free revives per combat"

    class FreeRevive(Modifier):
        TYPE = ModifierType.ON_DEATH

        def function(self, context: ModifierContext) -> Any:
            entity: cc.CombatActor = context.get("entity")
            if entity.hp == 0:
                self.write_to_log(context, f"{entity.get_name()} still stands.")
                entity.modify_hp(int(entity.get_max_hp() / 2))
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
        entity.modify_hp(self.strength, overheal=True)
        self.write_to_log(
            context,
            f"{entity.get_name()}'s blood thirst heals them for {self.strength} HP ({entity.get_hp_string()}).",
        )


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
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 50
    SCALING = 2

    NAME = "Bashing"
    DESCRIPTION = "Deal {str}% more damage if a shield is equipped in the secondary slot"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        if isinstance(attacker, classes.Player):
            secondary = attacker.equipped_items.get(equipment.Slots.SECONDARY, None)
            if (
                (secondary is not None)
                and (not secondary.equipment_type.is_weapon)
                and (secondary.equipment_type.equipment_class == "shield")
            ):
                return damage.scale(1 + (self.get_fstrength()))
        else:
            return damage.scale(1.2)
        return damage


class Thorns(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.PRE_DEFEND

    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 5

    NAME = "Thorns"
    DESCRIPTION = "Any attacker will receive {str} damage."

    def function(self, context: ModifierContext) -> Any:
        attacker: cc.CombatActor = context.get("other")
        attacker.modify_hp(-self.strength)
        self.write_to_log(
            context,
            f"{attacker.get_name()} loses {self.strength} HP from thorns. ({attacker.get_hp_string()})",
        )
        return context.get("damage")


class FireAbsorb(_GenericDamageAbsorb, dmg_type="fire"):
    pass


class AcidAbsorb(_GenericDamageAbsorb, dmg_type="acid"):
    pass


class FreezeAbsorb(_GenericDamageAbsorb, dmg_type="freeze"):
    pass


class ElectricAbsorb(_GenericDamageAbsorb, dmg_type="electric"):
    pass


class RouletteAttack(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 3.5

    NAME = "Roulette Attack"
    DESCRIPTION = "Deal +{str} damage of a random type"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        key = random.choice(list(damage.__dict__.keys()))
        damage_modifier = damage.get_empty()
        damage.__dict__[key] = self.strength
        return damage + damage_modifier


class IdiotGodBlessing(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.COMBAT_START

    MAX_STRENGTH = 100
    MIN_STRENGTH = 10
    SCALING = 5

    NAME = "Idiot God Blessing"
    DESCRIPTION = "Gives you 1 free revive per combat (restores {str}% hp)."

    class FreeRevive(Modifier):
        TYPE = ModifierType.ON_DEATH

        def function(self, context: ModifierContext) -> Any:
            entity: cc.CombatActor = context.get("entity")
            if entity.is_dead():
                entity.modify_hp(int(entity.get_max_hp() * self.get_fstrength()))
                self.write_to_log(
                    context,
                    f"The Idiot God blessing revives {entity.get_name()}! ({entity.get_hp_string()})",
                )
            else:
                self.duration += 1

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.timed_modifiers.append(self.FreeRevive(self.strength, duration=1))
        return 0


class Brutal(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.POST_ATTACK

    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 3

    NAME = "Brutality"
    DESCRIPTION = "Deal +{str} unblockable damage"

    def function(self, context: ModifierContext) -> Any:
        target: cc.CombatActor = context.get("other")
        target.modify_hp(-self.strength)
        self.write_to_log(
            context,
            f"{target.get_name()} is brutalized for {self.strength} dmg. ({target.get_hp_string()})",
        )


class Ferocity(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 10
    MIN_STRENGTH = 1
    SCALING = 10

    NAME = "Ferocity"
    DESCRIPTION = "Deal {str}0% more damage but also take {str} damage when attacking"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        attacker.modify_hp(-self.strength)
        self.write_to_log(context, f"{attacker.get_name()} loses {self.strength} HP from the ferocity of the attack. ({attacker.get_hp_string()})")
        return damage.scale(1 + (self.strength / 10))


class LambEmbrace(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.TURN_START

    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 3

    NAME = "Lamb's Embrace"
    DESCRIPTION = "Regenerate {str} HP at the start of the turn"

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.modify_hp(self.strength)
        self.write_to_log(context, f"{entity.get_name()} regenerates {self.strength} HP. ({entity.get_hp_string()})")


class EldritchSynergy(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 4

    NAME = "Eldritch Synergy"
    DESCRIPTION = "Deal {str}% more damage for each owned artifact"

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("supplier")
        damage: cc.Damage = context.get("damage")
        if isinstance(entity, classes.Player):
            if entity.artifacts:
                return damage.scale(1 + (self.get_fstrength() * len(entity.artifacts)))
        else:
            return damage.scale(1.5)
        return damage


class Dread(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.TURN_START

    MAX_STRENGTH = 0
    MIN_STRENGTH = 1
    SCALING = 1.5

    NAME = "Dread Aura"
    DESCRIPTION = "Deal {str} damage at the start of your turn"

    def function(self, context: ModifierContext) -> Any:
        opponent: cc.CombatActor = context.get("opponent")
        opponent.modify_hp(-self.strength)
        self.write_to_log(context, f"{opponent.get_name()} takes {self.strength} Dread damage. ({opponent.get_hp_string()})")


class Akimbo(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 50
    SCALING = 2

    NAME = "Akimbo"
    DESCRIPTION = "Deal {str}% more damage if you have weapons in both primary & secondary slots"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        attacker: cc.CombatActor = context.get("supplier")
        if isinstance(attacker, classes.Player):
            secondary = attacker.equipped_items.get(equipment.Slots.SECONDARY, None)
            if (
                (secondary is not None)
                and secondary.equipment_type.is_weapon
            ):
                return damage.scale(1 + (self.get_fstrength()))
        else:
            return damage.scale(1.2)
        return damage


class OccultAbsorb(_GenericDamageAbsorb, dmg_type="occult"):
    pass


class PlayerDamageMult(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 100
    MIN_STRENGTH = 1
    SCALING = 2

    NAME = "Hearth-breaker"
    DESCRIPTION = "Deal {str}% more damage if the target of the attack is a Player/Shade"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        target: cc.CombatActor = context.get("other")
        if isinstance(target, classes.Player):
            return damage.scale(1 + (self.get_fstrength()))
        return damage


class AdditionalHelper(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.COMBAT_START

    SCALING = 0.3

    NAME = "Shade Helper"
    DESCRIPTION = "Grants a Shade helper that has a 40% chance of dealing {str} unblockable damage."

    class Helper(Modifier):
        TYPE = ModifierType.TURN_START

        def function(self, context: ModifierContext) -> Any:
            if random.randint(1, 100) < 40:
                entity: cc.CombatActor = context.get("entity")
                target: cc.CombatActor = context.get("opponent")
                target.modify_hp(-self.strength)
                self.write_to_log(context, f"{entity.get_name()}'s Shade Helper attacks {target.get_name()} for {self.strength} damage ({target.get_hp_string()}).")

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        entity.timed_modifiers.append(self.Helper(self.strength))
        self.write_to_log(
            context, f"A Shade Helper spawns for {entity.get_name()}"
        )
        return 0


class StaminaRegenLowHP(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.STAMINA_REGEN

    MAX_STRENGTH = 200
    MIN_STRENGTH = 110
    SCALING = 2

    NAME = "Adrenaline"
    DESCRIPTION = "Regenerate {str}% stamina if you have less than 25% HP."

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        if entity.hp_percent <= 0.25:
            return 1 + (self.strength / 100)
        return 1.0


class StaminaRegenHighHP(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.STAMINA_REGEN

    MAX_STRENGTH = 150
    MIN_STRENGTH = 110
    SCALING = 1

    NAME = "Momentum"
    DESCRIPTION = "Regenerate {str}% stamina if you have more than 75% HP."

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        if entity.hp_percent >= 0.75:
            return 1 + (self.strength / 100)
        return 1.0


class Flinching(Modifier, rarity=Rarity.UNCOMMON):
    TYPE = ModifierType.PRE_ATTACK

    MAX_STRENGTH = 50
    MIN_STRENGTH = 10
    SCALING = 2

    NAME = "Flinching"
    DESCRIPTION = "{str}% chance of flinching the target on attack (next attack 50% damage)."

    class FlinchedEffect(Modifier):
        TYPE = ModifierType.PRE_ATTACK

        def function(self, context: ModifierContext) -> Any:
            damage: cc.Damage = context.get("damage")
            return damage.scale(0.5)

    def function(self, context: ModifierContext) -> cc.Damage:
        target: cc.CombatActor = context.get("other")
        if random.random() < (self.strength / 100):
            target.timed_modifiers.append(self.FlinchedEffect(0, duration=1))
            self.write_to_log(context, f"{target.get_name()} flinches!")
        return context.get("damage")


class CommandingPresence(Modifier, rarity=Rarity.RARE):
    TYPE = ModifierType.MID_ATTACK

    MAX_STRENGTH = 5
    MIN_STRENGTH = 1
    SCALING = 20

    NAME = "Commanding Presence"
    DESCRIPTION = "Increase attack by {str}% every turn"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        turn: int = context.get("turn")
        return damage.scale(1 + ((self.strength / 100) * turn))


class _GenericStatIncrease(Modifier):
    TYPE = ModifierType.MODIFY_STATS

    MIN_STRENGTH = 1
    SCALING = 8

    DESCRIPTION = "increase STAT by {str}"
    STAT: str

    def __init_subclass__(cls, stat: str = None, **kwargs) -> None:
        if stat is None:
            raise ValueError("stat cannot be None")
        cls.NAME = f"{stat.capitalize()} imbued"
        super().__init_subclass__(rarity=Rarity.COMMON)
        cls.STAT = stat
        cls.DESCRIPTION = cls.DESCRIPTION.replace("STAT", stat)

    def function(self, context: ModifierContext) -> cc.Stats:
        entity: cc.CombatActor = context.get("entity")
        stats: cc.Stats = context.get("stats")
        return stats.add_single_value(self.STAT, self.strength)


class IncreaseVitality(_GenericStatIncrease, stat="vitality"):
    pass


class IncreaseStrength(_GenericStatIncrease, stat="strength"):
    pass


class IncreaseSkill(_GenericStatIncrease, stat="skill"):
    pass


class IncreaseToughness(_GenericStatIncrease, stat="toughness"):
    pass


class IncreaseAttunement(_GenericStatIncrease, stat="attunement"):
    pass


class IncreaseMind(_GenericStatIncrease, stat="mind"):
    pass


class IncreaseAgility(_GenericStatIncrease, stat="agility"):
    pass


class ScaleAllStats(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.MODIFY_STATS

    MAX_STRENGTH = 200
    MIN_STRENGTH = 100
    SCALING = 1

    NAME = "Intensive Training"
    DESCRIPTION = "Scale all stats by {str}%"

    def function(self, context: ModifierContext) -> Any:
        entity: cc.CombatActor = context.get("entity")
        stats: cc.Stats = context.get("stats")
        return stats.scale(self.strength / 100)


class _GenericWeaponProficiency(Modifier):
    TYPE = ModifierType.PRE_ATTACK

    MIN_STRENGTH = 10
    SCALING = 1.2

    DESCRIPTION = "increases your damage with WPN type weapons by {str}%"
    WPN: str

    def __init_subclass__(cls, weapon_type: str = None, **kwargs) -> None:
        if weapon_type is None:
            raise ValueError("weapon_type cannot be None")
        cls.NAME = f"{weapon_type.capitalize()} Proficiency"
        super().__init_subclass__(rarity=Rarity.UNCOMMON)
        cls.WPN = weapon_type
        cls.DESCRIPTION = cls.DESCRIPTION.replace("WPN", weapon_type)

    def function(self, context: ModifierContext) -> cc.Damage:
        attacker: cc.CombatActor = context.get("supplier")
        damage: cc.Damage = context.get("damage")
        if isinstance(attacker, classes.Player):
            primary = attacker.equipped_items.get(equipment.Slots.PRIMARY, None)
            secondary = attacker.equipped_items.get(equipment.Slots.SECONDARY, None)
            if (
                    (primary is not None)
                    and (primary.equipment_type.equipment_class == self.WPN)
            ):
                damage = damage.scale(1 + (self.get_fstrength()))
            if (
                    (secondary is not None)
                    and secondary.equipment_type.is_weapon
                    and (secondary.equipment_type.equipment_class == self.WPN)
            ):
                damage = damage.scale(1 + (self.get_fstrength()))
            return damage
        return damage.scale(1 + (2 * self.get_fstrength()))


class SwordProficiency(_GenericWeaponProficiency, weapon_type="sword"):
    pass


class PolearmProficiency(_GenericWeaponProficiency, weapon_type="polearm"):
    pass


class DaggerProficiency(_GenericWeaponProficiency, weapon_type="dagger"):
    pass


class FirearmProficiency(_GenericWeaponProficiency, weapon_type="firearm"):
    pass


class ThrownProficiency(_GenericWeaponProficiency, weapon_type="thrown"):
    pass


class FistProficiency(_GenericWeaponProficiency, weapon_type="fist"):
    pass


class MagicProficiency(_GenericWeaponProficiency, weapon_type="magic"):
    pass


class CrossbowProficiency(_GenericWeaponProficiency, weapon_type="crossbow"):
    pass


class MaceProficiency(_GenericWeaponProficiency, weapon_type="mace"):
    pass


class HammerProficiency(_GenericWeaponProficiency, weapon_type="hammer"):
    pass


class GreatswordProficiency(_GenericWeaponProficiency, weapon_type="greatsword"):
    pass


class TrueStrike(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.PRE_ATTACK

    MIN_STRENGTH = 2
    MAX_STRENGTH = 25
    SCALING = 8

    NAME = "True Strike"
    DESCRIPTION = "Remove {str}% of enemy health per hit (unblockable)"

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        target: cc.CombatActor = context.get("other")
        amount: int = int((target.get_max_hp() / 100) * self.strength)
        target.modify_hp(-amount)
        self.write_to_log(context, f"True Strike for {self.strength}% HP ({target.get_hp_string()})")
        return damage


class StickProficiency(_GenericWeaponProficiency, weapon_type="stick"):
    pass


class Immolation(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.ON_DEATH

    MIN_STRENGTH = 25
    MAX_STRENGTH = 100
    SCALING = 2

    NAME = "Immolation"
    DESCRIPTION = "On death deal {str}% of enemy health in damage to an enemy (unblockable)"

    def function(self, context: ModifierContext) -> Any:
        caster: cc.CombatActor = context.get("entity")
        opponent: cc.CombatActor = context.get("opponent")
        damage = int(opponent.get_max_hp() * self.get_fstrength())
        opponent.modify_hp(-damage)
        self.write_to_log(context, f"{caster.get_name()} dies and Immolates, dealing {damage} to {opponent.get_name()}")


class AcceleratingDefence(Modifier, rarity=Rarity.LEGENDARY):
    TYPE = ModifierType.MID_DEFEND

    MAX_STRENGTH = 5
    MIN_STRENGTH = 1
    SCALING = 20

    NAME = "Entropic Recursion"
    DESCRIPTION = "Decrease damage taken by {str}% each turn (up to 95%)."

    def function(self, context: ModifierContext) -> Any:
        damage: cc.Damage = context.get("damage")
        percent_decrease: int = self.strength if self.strength < 95 else 95
        return damage.scale((100 - percent_decrease) / 100)


print(f"Loaded {len(_LIST)} perks")  # Always keep at the end
