import random
from abc import ABC
from copy import copy

from time import time
from typing import Union, List, Dict, Any

import pilgram.modifiers as m
import pilgram.classes as c


class CombatActions:
    attack = 0,
    dodge = 1,
    charge_attack = 2
    use_consumable = 3
    lick_wounds = 4


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

    def modify(
            self,
            supplier: "CombatActor",
            other: "CombatActor",
            type_filter: int,
            combat_context: "CombatContainer" = None
    ) -> "Damage":
        result = self
        for modifier in supplier.get_modifiers(type_filter):
            new_result = modifier.apply(
                m.ModifierContext({"damage": self, "supplier": supplier, "other": other, "context": combat_context})
            )
            if new_result:
                result = new_result
        return result

    def get_total_damage(self) -> int:
        """ return the total damage dealt by the attack. Damage can't be 0, it must be at least 1 """
        dmg = self.slash + self.pierce + self.blunt + self.occult + self.fire + self.acid + self.freeze + self.electric
        return dmg if dmg > 0 else self.MIN_DAMAGE

    def is_zero(self):
        val = self.slash + self.pierce + self.blunt + self.occult + self.fire + self.acid + self.freeze + self.electric
        return val == 0

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
        if self.is_zero():
            return "Empty"
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
        self.hp: int = int(self.get_max_hp() * hp_percent)  # only used during fights
        self.timed_modifiers: List[m.Modifier] = []  # list of timed modifiers inflicted on the CombatActor

    def get_name(self) -> str:
        """ returns the name of the entity """
        raise NotImplementedError

    def get_level(self) -> int:
        """ returns the level of the entity """
        raise NotImplementedError

    def get_base_max_hp(self) -> int:
        """ returns the maximum hp of the combat actor (players & enemies) """
        raise NotImplementedError

    def get_base_attack_damage(self) -> Damage:
        """ generic method that should return the damage done by the entity """
        raise NotImplementedError

    def get_base_attack_resistance(self) -> Damage:
        """ generic method that should return the damage resistance of the entity """
        raise NotImplementedError

    def get_entity_modifiers(self, *type_filters: int) -> List["m.Modifier"]:
        """ generic method that should return an (optionally filtered) list of modifiers. (args are the filters) """
        raise NotImplementedError

    def roll(self, dice_faces: int):
        """ generic method used to roll dices for entities """
        raise NotImplementedError

    def get_delay(self) -> int:
        """ returns the delay of the actor, which is a factor that determines who goes first in the combat turn """
        raise NotImplementedError

    def get_stance(self):
        """ returns the stance of the actor, which determines how it behaves in combat """
        raise NotImplementedError

    def choose_action(self, opponent: "CombatActor") -> int:
        """ return what the entity wants to do (possible actions defined in CombatActions) """
        raise NotImplementedError

    def get_modifiers(self, *type_filters: int) -> List["m.Modifier"]:
        """ returns the list of modifiers + timed modifiers """
        modifiers: List[m.Modifier] = self.get_entity_modifiers(*type_filters)
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
        for modifier in self.get_entity_modifiers(m.ModifierType.MODIFY_MAX_HP):
            max_hp = modifier.apply(m.ModifierContext({"entity": self, "value": max_hp}))
        return int(max_hp)

    def get_hp_string(self) -> str:
        return f"HP: {self.hp}/{self.get_max_hp()}"

    def attack(self, target: "CombatActor", combat_context: "CombatContainer") -> Damage:
        """ get the damage an attack would do """
        damage = self.get_base_attack_damage().modify(self, target, m.ModifierType.ATTACK)
        defense = target.get_base_attack_resistance().modify(target, self, m.ModifierType.DEFEND)
        return damage - defense

    def modify_hp(self, amount: int, overheal: bool = False) -> bool:
        """ Modify actor hp. Return True if the actor was killed, otherwise return False """
        max_hp = self.get_max_hp()
        if (amount > 0) and (not overheal) and (self.hp >= max_hp):
            return False
        self.hp += amount
        if (not overheal) and (self.hp >= max_hp):
            self.hp = max_hp
            self.hp_percent = self.hp / max_hp
            return False
        if self.hp <= 0:
            self.hp = 0
            self.hp_percent = 0.0
            return True
        self.hp_percent = self.hp / max_hp
        return False

    def receive_damage(self, damage: Damage) -> bool:
        """ damage the actor with damage. Return True if the actor was killed, otherwise return False """
        damage_received = -damage.get_total_damage()
        return self.modify_hp(damage_received)

    def get_initiative(self) -> int:
        """ returns the initiative of the actor, which determines who goes first in the combat turn """
        value = self.get_delay() - self.roll(20)
        if self.get_stance() == "r":
            value -= 1
        elif self.get_stance() == "s":
            value += 1
        return value

    def is_dead(self) -> bool:
        return self.hp <= 0


class CombatContainer:

    def __init__(self, participants: List[CombatActor], helpers: Dict[CombatActor, Union[CombatActor, None]]):
        self.participants = participants
        self.helpers = helpers
        self.combat_log: str = ""
        self.damage_scale: Dict[CombatActor, float] = {}
        self.resist_scale: Dict[CombatActor, float] = {}
        self._reset_damage_and_resist_scales()

    def _reset_damage_and_resist_scales(self):
        for actor in self.participants:
            self.damage_scale[actor] = 1.0
            self.resist_scale[actor] = 1.0

    def write_to_log(self, text: str):
        self.combat_log += f"\n> {text}"

    def _cleanup_after_combat(self):
        """ remove all timed modifiers from combat participants """
        for participant in self.participants:
            participant.timed_modifiers.clear()

    def get_mod_context(self, context: Dict[str, Any]) -> "m.ModifierContext":
        context["context"] = self
        return m.ModifierContext(context)

    def _start_combat(self):
        self.combat_log = "*" + " vs ".join(f"{x.get_name()} (lv. {x.get_level()})" for x in self.participants) + "*\n"
        for participant in self.participants:
            participant.hp = int(participant.get_max_hp() * participant.hp_percent)
            for modifier in participant.get_entity_modifiers(m.ModifierType.COMBAT_START):
                modifier.apply(self.get_mod_context({"entity": participant}))

    def _attack(self, attacker: CombatActor, target: CombatActor):
        self.write_to_log(f"{attacker.get_name()} attacks {target.get_name()}")
        damage = attacker.attack(target, self).scale(self.resist_scale[target]).scale(self.damage_scale[attacker])
        self.damage_scale[attacker] = 1.0
        self.resist_scale[target] = 1.0
        total_damage = damage.get_total_damage()
        target.modify_hp(-total_damage)
        self.write_to_log(f"{target.get_name()} takes {total_damage} damage ({target.get_hp_string()}).")
        for modifier in attacker.get_modifiers(m.ModifierType.POST_ATTACK):
            modifier.apply(self.get_mod_context({"damage": damage, "supplier": attacker, "other": target}))
        for modifier in target.get_modifiers(m.ModifierType.POST_DEFEND):
            modifier.apply(self.get_mod_context({"damage": damage, "supplier": attacker, "other": target}))

    def fight(self) -> str:
        """ simulate combat between players and enemies. Return battle report in a string. """
        is_fight_over: bool = False
        self._start_combat()
        while not is_fight_over:
            # sort participants based on what they rolled on initiative
            self.participants.sort(key=lambda a: a.get_initiative())
            # get opponents by copying & reversing the participant list
            opponents = copy(self.participants)
            opponents.reverse()
            # choose & perform actions
            for i, actor in enumerate(self.participants):
                if actor.is_dead():
                    continue
                action_id = actor.choose_action(opponents[i])
                if action_id == CombatActions.attack:
                    self._attack(actor, opponents[i])
                elif action_id == CombatActions.dodge:
                    factor = actor.get_delay() / 100
                    if factor > 0.9:
                        factor = 0.9
                    self.resist_scale[actor] = factor
                    self.write_to_log(f"{actor.get_name()} prepares to dodge. (next dmg received: {int(factor * 100)}%)")
                elif action_id == CombatActions.charge_attack:
                    self.damage_scale[actor] += 0.5
                    self.write_to_log(f"{actor.get_name()} charges an heavy attack (next attack {int(self.damage_scale[actor] * 100)}% dmg).")
                elif action_id == CombatActions.use_consumable:
                    if isinstance(actor, c.Player):
                        text = actor.use_random_consumable(add_you=False)
                        self.write_to_log(f"{actor.get_name()} {text}")
                elif action_id == CombatActions.lick_wounds:
                    hp_restored = 1 + actor.get_level()
                    actor.modify_hp(hp_restored if hp_restored > 0 else 1)
                    self.write_to_log(f"{actor.get_name()} licks their wounds, restoring {hp_restored} HP ({actor.get_hp_string()}).")
                if actor.is_dead():
                    if isinstance(actor, c.Player):
                        # if player died but has a revive in his inventory then use it
                        pos: int = -1
                        for j, consumable in enumerate(actor.satchel):
                            if consumable.revive:
                                pos = j
                                break
                        if pos != -1:
                            actor.use_consumable(pos)
                # use helpers
                if self.helpers[actor] and (random.randint(1, 5) == 1):  # 20% chance of helper intervention
                    helper = self.helpers[actor]
                    damage = int(helper.get_level() * (1 + random.random()))
                    opponents[i].modify_hp(-damage)
                    self.write_to_log(f"{helper.get_name()} helps {actor.get_name()} by dealing {damage} damage to {opponents[i].get_name()}.")
            for i, actor in enumerate(self.participants):
                if actor.is_dead():
                    is_fight_over = True
                    self.write_to_log(f"The combat is over, {opponents[i].get_name()} has won.")
        self._cleanup_after_combat()
        return self.combat_log
