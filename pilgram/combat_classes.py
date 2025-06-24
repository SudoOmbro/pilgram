from __future__ import annotations

import random
from abc import ABC
from copy import copy
from time import time
from typing import Any

import pilgram.classes as c
import pilgram.modifiers as m


class CombatActions:
    attack = 0
    dodge = 1
    charge_attack = 2
    use_consumable = 3
    lick_wounds = 4
    catch_breath = 5


class Damage:
    """used to express damage & resistance values"""

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
        electric: int,
    ) -> None:
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
        supplier: CombatActor,
        other: CombatActor,
        type_filter: int,
        combat_context: CombatContainer = None,
    ) -> Damage:
        result = self
        for modifier in supplier.get_modifiers(type_filter):
            new_result = modifier.apply(
                m.ModifierContext(
                    {
                        "damage": result,
                        "supplier": supplier,
                        "other": other,
                        "context": combat_context,
                    }
                )
            )
            if new_result is not None:
                result = new_result
        return result

    def get_total_damage(self) -> int:
        """return the total damage dealt by the attack. Damage can't be 0, it must be at least 1"""
        dmg = (
            self.slash
            + self.pierce
            + self.blunt
            + self.occult
            + self.fire
            + self.acid
            + self.freeze
            + self.electric
        )
        return dmg if dmg > 0 else self.MIN_DAMAGE

    def is_zero(self) -> bool:
        val = (
            self.slash
            + self.pierce
            + self.blunt
            + self.occult
            + self.fire
            + self.acid
            + self.freeze
            + self.electric
        )
        return val == 0

    def scale(self, scaling_factor: float) -> Damage:
        return Damage(
            int(self.slash * scaling_factor),
            int(self.pierce * scaling_factor),
            int(self.blunt * scaling_factor),
            int(self.occult * scaling_factor),
            int(self.fire * scaling_factor),
            int(self.acid * scaling_factor),
            int(self.freeze * scaling_factor),
            int(self.electric * scaling_factor),
        )

    def scale_with_stats(self, stats: Stats, scaling: Stats) -> Damage:
        stats_to_scale = scaling.get_all_non_zero_stats()
        result: Damage = self
        for stat in stats_to_scale:
            result = result.scale(
                1 + (stats.__dict__[stat] * (scaling.__dict__[stat] / 100))
            )
        return result

    def apply_bonus(self, bonus: int) -> Damage:
        return Damage(
            (self.slash + bonus) if self.slash else 0,
            (self.pierce + bonus) if self.pierce else 0,
            (self.blunt + bonus) if self.blunt else 0,
            (self.occult + bonus) if self.occult else 0,
            (self.fire + bonus) if self.fire else 0,
            (self.acid + bonus) if self.acid else 0,
            (self.freeze + bonus) if self.freeze else 0,
            (self.electric + bonus) if self.electric else 0,
        )

    def scale_single_value(self, key: str, scaling_factor: float) -> Damage:
        new_damage = copy(self)
        new_damage.__dict__[key] = int(new_damage.__dict__[key] * scaling_factor)
        return new_damage

    def add_single_value(self, key: str, value: int) -> Damage:
        new_damage = copy(self)
        new_damage.__dict__[key] = new_damage.__dict__[key] + value
        return new_damage

    def __add__(self, other: Any) -> Damage:
        if not isinstance(other, Damage):
            return NotImplemented
        return Damage(
            self.slash + other.slash,
            self.pierce + other.pierce,
            self.blunt + other.blunt,
            self.occult + other.occult,
            self.fire + other.fire,
            self.acid + other.acid,
            self.freeze + other.freeze,
            self.electric + other.electric,
        )

    def __mul__(self, other: Any) -> Damage:
        if not isinstance(other, Damage):
            return NotImplemented
        return Damage(
            self.slash * other.slash,
            self.pierce * other.pierce,
            self.blunt * other.blunt,
            self.occult * other.occult,
            self.fire * other.fire,
            self.acid * other.acid,
            self.freeze * other.freeze,
            self.electric * other.electric,
        )

    def __sub__(self, other: Any) -> Damage:
        """used when self attacks other"""
        if not isinstance(other, Damage):
            return NotImplemented
        slash = (self.slash - other.slash) if self.slash else 0
        pierce = (self.pierce - other.pierce) if self.pierce else 0
        blunt = (self.blunt - other.blunt) if self.blunt else 0
        occult = (self.occult - other.occult) if self.occult else 0
        fire = (self.fire - other.fire) if self.fire else 0
        acid = (self.acid - other.acid) if self.acid else 0
        freeze = (self.freeze - other.freeze) if self.freeze else 0
        electric = (self.electric - other.electric) if self.electric else 0
        return Damage(
            max(0, slash),
            max(0, pierce),
            max(0, blunt),
            max(0, occult),
            max(0, fire),
            max(0, acid),
            max(0, freeze),
            max(0, electric),
        )

    def __bool__(self) -> bool:
        dmg = (
            self.slash
            + self.pierce
            + self.blunt
            + self.occult
            + self.fire
            + self.acid
            + self.freeze
            + self.electric
        )
        return dmg != 0

    def __str__(self) -> str:
        if self.is_zero():
            return "Empty"
        return "\n".join(
            [f"{key}: {value}" for key, value in self.__dict__.items() if value != 0]
        )

    @classmethod
    def get_empty(cls) -> Damage:
        return Damage(0, 0, 0, 0, 0, 0, 0, 0)

    @classmethod
    def generate_from_seed(
        cls, seed: float, iterations: int, exclude_params: list[str] | None = None
    ) -> Damage:
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
    def load_from_json(cls, damage_json: dict[str, int]) -> Damage:
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
    def generate(
        cls, iterations: int, exclude_params: list[str] | None = None
    ) -> Damage:
        return cls.generate_from_seed(time(), iterations, exclude_params)


class Stats:

    def __init__(
        self,
        vitality: int,
        strength: int,
        skill: int,
        toughness: int,
        attunement: int,
        mind: int,
        agility: int
    ):
        self.vitality = vitality
        self.strength = strength
        self.skill = skill
        self.toughness = toughness
        self.attunement = attunement
        self.mind = mind
        self.agility = agility

    def scale_single_value(self, key: str, scaling_factor: float) -> Stats:
        new_stats = copy(self)
        new_stats.__dict__[key] = int(new_stats.__dict__[key] * scaling_factor)
        return new_stats

    def add_single_value(self, key: str, value: int) -> Stats:
        new_stats = copy(self)
        new_stats.__dict__[key] += value
        return new_stats

    def scale(self, value: float):
        return Stats(
            int(self.vitality * value),
            int(self.strength * value),
            int(self.skill * value),
            int(self.toughness * value),
            int(self.attunement * value),
            int(self.mind * value),
            int(self.agility * value)
        )

    def get_all_non_zero_stats(self) -> list[str]:
        result: list[str] = []
        for stat, value in self.__dict__.items():
            if value != 0:
                result.append(stat)
        return result

    def __add__(self, other):
        if not isinstance(other, Stats):
            raise NotImplemented
        return Stats(
            self.vitality + other.vitality,
            self.strength + other.strength,
            self.skill + other.skill,
            self.toughness + other.toughness,
            self.attunement + other.attunement,
            self.mind + other.mind,
            self.agility + other.agility,
        )

    def __mul__(self, other):
        if not isinstance(other, Stats):
            raise NotImplemented
        return Stats(
            self.vitality * other.vitality,
            self.strength * other.strength,
            self.skill * other.skill,
            self.toughness * other.toughness,
            self.attunement * other.attunement,
            self.mind * other.mind,
            self.agility * other.agility,
        )

    def __str__(self) -> str:
        return "\n".join(
            [f"{key}: {value}" for key, value in self.__dict__.items() if value != 0]
        )

    def get_scaling_string(self) -> str:
        return "\n".join(
            [f"{key}: {value}%" for key, value in self.__dict__.items() if value != 0]
        )

    @classmethod
    def load_from_json(cls, stats_json: dict[str, int]) -> Stats:
        return cls(
            stats_json.get("vitality", 0),
            stats_json.get("strength", 0),
            stats_json.get("skill", 0),
            stats_json.get("toughness", 0),
            stats_json.get("attunement", 0),
            stats_json.get("mind", 0),
            stats_json.get("agility", 0)
        )

    @classmethod
    def create_default(cls, base: int = 1) -> Stats:
        return cls(base, base, base, base, base, base, base)

    @classmethod
    def generate_random(cls, base: int, iterations: int, seed: float | None = None) -> Stats:
        if seed is None:
            seed = time()
        rand = random.Random(seed)
        stats = Stats.create_default(base)
        stats_keys = list(stats.__dict__.keys())
        for _ in range(iterations):
            target = rand.choice(stats_keys)
            stats.__dict__[target] += 1
        return stats


class CombatActor(ABC):

    def __init__(self, hp_percent: float, team: int, stats: Stats) -> None:
        self.hp_percent = hp_percent  # used out of fights
        self.stats = stats
        self.hp: int = int(self.get_max_hp() * hp_percent)  # only used during fights
        # list of timed modifiers inflicted on the CombatActor
        self.timed_modifiers: list[m.Modifier] = []
        self.team = team

    def get_name(self) -> str:
        """returns the name of the entity"""
        raise NotImplementedError

    def get_level(self) -> int:
        """returns the level of the entity"""
        raise NotImplementedError

    def get_base_max_hp(self) -> int:
        """returns the maximum hp of the combat actor (players & enemies)"""
        raise NotImplementedError

    def get_base_attack_damage(self) -> Damage:
        """generic method that should return the damage done by the entity"""
        raise NotImplementedError

    def get_base_attack_resistance(self) -> Damage:
        """generic method that should return the damage resistance of the entity"""
        raise NotImplementedError

    def get_entity_modifiers(self, *type_filters: int) -> list[m.Modifier]:
        """generic method that should return an (optionally filtered) list of modifiers. (args are the filters)"""
        raise NotImplementedError

    def roll(self, dice_faces: int):
        """generic method used to roll dices for entities, default implementation provided."""
        return random.randint(1, dice_faces)

    def get_delay(self) -> int:
        """returns the delay of the actor, which is a factor that determines who goes first in the combat turn"""
        raise NotImplementedError

    def get_stance(self):
        """
        returns the stance of the actor, which determines how it behaves in combat, default implementation provided.
        """
        return "b"

    def choose_action(self, opponent: CombatActor) -> int:
        """
        return what the entity wants to do (possible actions defined in CombatActions), default implementation provided.
        """
        if self.hp_percent > 0.5:
            return random.choice(
                (
                    CombatActions.attack,
                    CombatActions.attack,
                    CombatActions.attack,
                    CombatActions.charge_attack,
                    CombatActions.dodge,
                )
            )
        return random.choice(
            (
                CombatActions.attack,
                CombatActions.attack,
                CombatActions.attack,
                CombatActions.charge_attack,
                CombatActions.dodge,
                CombatActions.dodge,
                CombatActions.lick_wounds,
            )
        )

    def get_modifiers(self, *type_filters: int) -> list[m.Modifier]:
        """returns the list of modifiers + timed modifiers"""
        modifiers: list[m.Modifier] = self.get_entity_modifiers(*type_filters)
        if not type_filters:
            modifiers.extend(self.timed_modifiers)
            modifiers.sort(key=lambda x: x.OP_ORDERING)
            return modifiers
        for modifier in self.timed_modifiers:
            if modifier.TYPE in type_filters:
                modifiers.append(modifier)
        modifiers.sort(key=lambda x: x.OP_ORDERING)
        return modifiers

    def start_fight(self) -> None:
        self.hp = int(self.get_max_hp() * self.hp_percent)

    def get_max_hp(self) -> int:
        """get max hp of the entity applying all modifiers"""
        max_hp = self.get_base_max_hp()
        for modifier in self.get_entity_modifiers(m.ModifierType.MODIFY_MAX_HP):
            max_hp = modifier.apply(
                m.ModifierContext({"entity": self, "value": max_hp})
            )
        return int(max_hp)

    def get_stats(self) -> Stats:
        stats = self.stats
        for modifier in self.get_entity_modifiers(m.ModifierType.MODIFY_STATS):
            stats = modifier.apply(
                m.ModifierContext({"entity": self, "stats": stats})
            )
        return stats

    def get_hp_string(self) -> str:
        """returns: 'HP: hp/max hp'"""
        return f"HP: {self.hp}/{self.get_max_hp()}"

    def attack(self, target: CombatActor, combat_context: CombatContainer) -> Damage:
        """get the damage an attack would do"""
        damage = self.get_base_attack_damage().modify(
            self, target, m.ModifierType.PRE_ATTACK, combat_context=combat_context
        )
        defense = target.get_base_attack_resistance().modify(
            target, self, m.ModifierType.PRE_DEFEND, combat_context=combat_context
        )
        return damage - defense

    def modify_hp(self, amount: int, overheal: bool = False) -> bool:
        """Modify actor hp. Return True if the actor was killed, otherwise return False"""
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
        """damage the actor with damage. Return True if the actor was killed, otherwise return False"""
        damage_received = -damage.get_total_damage()
        return self.modify_hp(damage_received)

    def get_initiative(self) -> int:
        """returns the initiative of the actor, which determines who goes first in the combat turn"""
        value = self.get_delay() - random.randint(1, 20)
        if self.get_stance() == "r":
            value -= 1
        elif self.get_stance() == "s":
            value += 1
        return value

    def is_dead(self) -> bool:
        return self.hp <= 0

    def get_rewards(self, player: c.Player) -> tuple[int, int]:
        level = self.get_level()
        multiplier = int(40 * player.vocation.combat_rewards_multiplier)
        if level > player.level:
            multiplier += 5 * (level - player.level)
        return multiplier * level, multiplier * level

    @staticmethod
    def get_stamina_regeneration() -> float:
        return 0.2 + random.choice((-0.02, -0.01, 0.0, 0.01, 0.02))

    def get_prestige(self, zone_level: int) -> int:
        """Returns the prestige given by killing this actor"""
        return max(1, int((self.get_level() - zone_level) / 2))

    def has_pet(self) -> bool:
        return False


class CombatContainer:
    MAX_TURNS: int = 1000

    def __init__(
        self,
        participants: list[CombatActor],
        helpers: dict[CombatActor, CombatActor | None],
    ) -> None:
        self.participants = participants
        self.helpers = helpers
        self.combat_log: str = ""
        self.damage_scale: dict[CombatActor, float] = {}
        self.resist_scale: dict[CombatActor, float] = {}
        self.stamina: dict[CombatActor, float] = {}
        self.turn = 0
        self.death_was_notified: list[CombatActor] = []

    def _reset_damage_and_resist_scales(self) -> None:
        for actor in self.participants:
            self.damage_scale[actor] = 1.0
            self.resist_scale[actor] = 1.0
            self.stamina[actor] = 1.0

    def write_to_log(self, text: str) -> None:
        self.combat_log += f"\n{text}"

    def _cleanup_after_combat(self) -> None:
        """remove all timed modifiers from combat participants"""
        for participant in self.participants:
            participant.timed_modifiers.clear()

    def get_mod_context(self, context: dict[str, Any]) -> m.ModifierContext:
        context["context"] = self
        return m.ModifierContext(context)

    def _start_combat(self) -> None:
        teams: dict[int, list[CombatActor]] = {}
        for actor in self.participants:
            if actor.team not in teams:
                teams[actor.team] = []
            teams[actor.team].append(actor)
            if actor.has_pet():
                # teams[actor.team].append(actor.pet)
                self.participants.append(actor.pet)
        self._reset_damage_and_resist_scales()
        self.combat_log = (
            "*"
            + " vs ".join(
                " & ".join(f"{x.get_name()} (lv. {x.get_level()})" for x in team) for team in teams.values()
            )
            + "*"
        )
        for participant in self.participants:
            participant.hp = int(participant.get_max_hp() * participant.hp_percent)
            for modifier in participant.get_entity_modifiers(
                m.ModifierType.COMBAT_START
            ):
                modifier.apply(self.get_mod_context({"entity": participant}))

    def regenerate_stamina(self, actor: CombatActor, opponent: CombatActor) -> None:
        amount = actor.get_stamina_regeneration()
        for modifier in actor.get_modifiers(m.ModifierType.STAMINA_REGEN):
            amount *= modifier.apply(self.get_mod_context({"entity": actor, "opponent": opponent, "turn": self.turn}))
        self.stamina[actor] += amount
        if self.stamina[actor] > 1.0:
            self.stamina[actor] = 1.0

    def _attack(self, attacker: CombatActor, target: CombatActor) -> None:
        self.write_to_log(f"{attacker.get_name()} attacks.")
        # deplete stamina
        self.stamina[attacker] -= (attacker.get_delay() / 100)
        if self.stamina[attacker] < 0.0:
            self.stamina[attacker] = 0.0
        # get total damage inflicted
        damage = (
            attacker.attack(target, self)
            .scale(self.resist_scale[target])
            .scale(self.damage_scale[attacker])
        )
        # reset damage & resist scales
        self.damage_scale[attacker] = 1.0
        self.resist_scale[target] = 1.0
        # apply mid attack & defend modifiers (before inflicting the damage)
        for modifier in attacker.get_modifiers(m.ModifierType.MID_ATTACK):
            new_damage = modifier.apply(
                self.get_mod_context(
                    {"damage": damage, "attacker": attacker, "target": target, "turn": self.turn}
                )
            )
            if new_damage is not None:
                damage = new_damage
        for modifier in target.get_modifiers(m.ModifierType.MID_DEFEND):
            new_damage = modifier.apply(
                self.get_mod_context(
                    {"damage": damage, "attacker": attacker, "target": target, "turn": self.turn}
                )
            )
            if new_damage is not None:
                damage = new_damage
        # actually inflict the damage
        total_damage = damage.get_total_damage()
        target.modify_hp(-total_damage)
        self.write_to_log(
            f"{target.get_name()} takes {total_damage} dmg ({target.get_hp_string()})."
        )
        # apply post attack & defend modifiers (after the damage was inflicted)
        for modifier in attacker.get_modifiers(m.ModifierType.POST_ATTACK):
            modifier.apply(
                self.get_mod_context(
                    {"damage": damage, "supplier": attacker, "other": target}
                )
            )
        for modifier in target.get_modifiers(m.ModifierType.POST_DEFEND):
            modifier.apply(
                self.get_mod_context(
                    {"damage": damage, "supplier": attacker, "other": target}
                )
            )

    def _try_revive(self, actor: CombatActor, opponent: CombatActor) -> bool:
        """ return true if the actor manages to revive, otherwise false """
        # first try to see the actor has any modifiers that revive him
        for modifier in actor.get_modifiers(m.ModifierType.ON_DEATH):
            modifier.apply(self.get_mod_context({"entity": actor, "opponent": opponent, "turn": self.turn}))
        if not actor.is_dead():
            return True
        # then if the actor is still dead and it's a player try to use consumables
        if isinstance(actor, c.Player):
            # if player died but has a revive in his inventory then use it
            pos: int = -1
            for j, consumable in enumerate(actor.satchel):
                if consumable.revive:
                    pos = j
                    break
            if pos != -1:
                text, _ = actor.use_consumable(pos + 1, add_you=False)
                self.write_to_log(
                    f"{actor.get_name()} {text}, they are revived! ({actor.get_hp_string()})"
                )
                return True
        return False

    def get_alive_actors(self) -> list[CombatActor]:
        result: list[CombatActor] = []
        for participant in self.participants:
            if not participant.is_dead():
                result.append(participant)
        # self.write_to_log("alive actors: " + ", ".join(x.get_name() for x in result))
        return result

    def choose_attack_target(self, attacker: CombatActor) -> CombatActor | None:
        temp_participants = self.get_alive_actors()
        random.shuffle(temp_participants)
        for participant in temp_participants:
            if participant.team != attacker.team:
                return participant
        return None

    def is_fight_over(self) -> bool:
        teams: list[int] = []
        for participant in self.get_alive_actors():
            if participant.team not in teams:
                teams.append(participant.team)
        return len(teams) == 1

    def fight(self) -> str:
        """simulate combat between players and enemies. Return battle report in a string."""
        is_fight_over: bool = False
        self._start_combat()
        while not is_fight_over:
            self.turn += 1
            if self.turn > self.MAX_TURNS:
                amount: int = 100 * (self.turn - self.MAX_TURNS)
                for participant in self.get_alive_actors():
                    participant.modify_hp(-amount)
                    self.write_to_log(f"SUDDEN DEATH! {participant.get_name()} loses {amount} HP ({participant.get_hp_string()})")
            self.write_to_log("")
            # sort participants based on what they rolled on initiative
            self.participants.sort(key=lambda a: a.get_initiative())
            # choose & perform actions
            for actor in self.participants:
                # lose dodge over time
                if self.resist_scale[actor] < 1.0:
                    self.resist_scale[actor] += 0.1
                else:
                    self.resist_scale[actor] = 1.0
                # choose opponent and try to revive if dead
                opponent = self.choose_attack_target(actor)
                if actor.is_dead():
                    if not self._try_revive(actor, opponent):
                        continue
                if not opponent:
                    continue
                # actually start turn
                for modifier in actor.get_modifiers(m.ModifierType.TURN_START):
                    modifier.apply(self.get_mod_context({"entity": actor, "opponent": opponent, "turn": self.turn}))
                if actor.is_dead():
                    # the actor may also die here since poison or other effects might be applied
                    if not self._try_revive(actor, opponent):
                        continue
                # only do something if the actor has full stamina
                self.regenerate_stamina(actor, opponent)
                if not self.stamina[actor] >= 1.0:
                    action_id = CombatActions.catch_breath
                else:
                    action_id = actor.choose_action(opponent)
                # actually do stuff
                if action_id == CombatActions.attack:
                    self._attack(actor, opponent)
                elif action_id == CombatActions.dodge:
                    if self.resist_scale[actor] < 1.0:
                        # if actor is already dodging then attack
                        self._attack(actor, opponent)
                    else:
                        # if actor isn't already dodging then dodge
                        factor = actor.get_delay() / 100
                        if factor > 0.9:
                            factor = 0.9
                        self.resist_scale[actor] = factor
                        self.write_to_log(
                            f"{actor.get_name()} dodges (next dmg taken -{100 - int(factor * 100)}%)."
                        )
                elif action_id == CombatActions.charge_attack:
                    self.damage_scale[actor] *= 1.5
                    self.write_to_log(
                        f"{actor.get_name()} takes aim (next dmg dealt +{int(self.damage_scale[actor] * 100) - 100}%)."
                    )
                elif action_id == CombatActions.use_consumable:
                    if isinstance(actor, c.Player):
                        text, used_item = actor.use_healing_consumable(add_you=False)
                        if used_item:
                            self.write_to_log(
                                f"{actor.get_name()} {text}. ({actor.get_hp_string()})"
                            )
                        else:
                            self._attack(actor, opponent)
                elif action_id == CombatActions.lick_wounds:
                    hp_restored = (1 + actor.get_level()) * 10
                    actor.modify_hp(hp_restored if hp_restored > 0 else 1)
                    self.write_to_log(
                        f"{actor.get_name()} licks their wounds (+{hp_restored} HP) ({actor.get_hp_string()})."
                    )
                elif action_id == CombatActions.catch_breath:
                    self.write_to_log(f"{actor.get_name()} is recovering ({int(self.stamina[actor] * 100)}%)")
                # use helpers
                if (actor in self.helpers) and self.helpers[actor] and (random.randint(1, 5) == 1):  # 20% chance of helper intervention
                    helper = self.helpers[actor]
                    damage = int(helper.get_level() * (1 + random.random()))
                    opponent.modify_hp(-damage)
                    self.write_to_log(
                        f"{helper.get_name()} helps {actor.get_name()} by dealing {damage} dmg to {opponent.get_name()}."
                    )
            for actor in self.participants:
                if actor.is_dead():
                    opponent = self.choose_attack_target(actor)
                    if not self._try_revive(actor, opponent):
                        if actor not in self.death_was_notified:
                            self.write_to_log(f"\n{actor.get_name()} died.")
                            self.death_was_notified.append(actor)
                    is_fight_over = self.is_fight_over()
        self.write_to_log(f"\n{" & ".join(x.get_name() for x in self.get_alive_actors())} won.")
        self._cleanup_after_combat()
        return self.combat_log
