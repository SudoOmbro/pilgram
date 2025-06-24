from __future__ import annotations

import json
import logging
import math
import os
import random
import threading
from time import time
from collections.abc import Callable
from copy import copy
from datetime import datetime, timedelta
from typing import Any

import numpy as np

import pilgram.modifiers as m
from pilgram.combat_classes import CombatActions, CombatActor, Damage, Stats
from pilgram.equipment import ConsumableItem, Equipment, EquipmentType, Slots
from pilgram.flags import (
    AcidBuff,
    AlloyGlitchFlag1,
    AlloyGlitchFlag2,
    AlloyGlitchFlag3,
    CursedFlag,
    ElectricBuff,
    FireBuff,
    Flag,
    HexedFlag,
    IceBuff,
    LuckFlag1,
    LuckFlag2,
    OccultBuff,
    StrengthBuff,
    MightBuff1,
    MightBuff2,
    MightBuff3,
    SwiftBuff1,
    SwiftBuff2,
    SwiftBuff3, DeathwishMode,
)
from pilgram.globals import ContentMeta, GlobalSettings
from pilgram.listables import Listable
from pilgram.strings import MONEY, Strings
from pilgram.utils import (
    FuncWithParam,
    print_bonus,
    read_text_file,
    read_json_file,
    read_update_interval,
    save_text_to_file,
    save_json_to_file,
)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


BASE_QUEST_DURATION: timedelta = read_update_interval(GlobalSettings.get("quest.base duration"))
DURATION_PER_ZONE_LEVEL: timedelta = read_update_interval(GlobalSettings.get("quest.duration per level"))
DURATION_PER_QUEST_NUMBER: timedelta = read_update_interval(GlobalSettings.get("quest.duration per number"))
RANDOM_DURATION: timedelta = read_update_interval(GlobalSettings.get("quest.random duration"))
POWER_PER_ARTIFACT: int = ContentMeta.get("artifacts.power_per_artifact")
MINIMUM_ASCENSION_LEVEL: int = ContentMeta.get("ascension.minimum_level")
LEVEL_INCREASE_PER_ASCENSION: int = ContentMeta.get("ascension.level_increase_per_ascension")
POWER_PER_DAY: int = ContentMeta.get("artifacts.power_per_day")
RAID_DELAY: timedelta = read_update_interval(ContentMeta.get("guilds.raid_delay"))

QTE_CACHE: dict[
    int, QuickTimeEvent
] = {}  # runtime cache that contains all users + quick time events pairs


class Event:

    def __init__(self, even_type: str, recipient: Player, data: dict) -> None:
        self.type = even_type
        self.recipient = recipient
        self.data = data


class InternalEventBus:
    _instance = None
    _LOCK = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not isinstance(cls._instance, cls):
            cls._instance = object.__new__(cls)
            cls._instance.events = []
        return cls._instance

    def notify(self, event: Event) -> None:
        with self._LOCK:
            self.events.append(event)

    def consume(self) -> Event | None:
        with self._LOCK:
            if len(self.events) == 0:
                return None
            return self.events.pop(0)

    def consume_all(self) -> list[Event]:
        with self._LOCK:
            events = copy(self.events)
            self.events.clear()
            return events


class Zone:
    """contains info about a zone. Zone 0 should be the town to reuse the zone event system"""

    def __init__(
        self,
        zone_id: int,
        zone_name: str,
        level: int,
        zone_description: str,
        damage_modifiers: Damage,
        resist_modifiers: Damage,
        extra_data: dict,
    ):
        """
        :param zone_id: zone id
        :param zone_name: zone name
        :param level: zone level, control the minimum level a player is required to be to accept quests in the zone
        :param zone_description: zone description
        :param damage_modifiers: damage modifiers for enemies in the zone
        :param resist_modifiers: resist modifiers for enemies in the zone
        :param extra_data: extra data for the zone, can contain perks & quirks
        """
        assert level > 0
        self.zone_id = zone_id
        self.zone_name = zone_name
        self.level = level
        self.zone_description = zone_description
        self.damage_modifiers: Damage = damage_modifiers
        self.resist_modifiers: Damage = resist_modifiers
        self.extra_data = extra_data

    def __eq__(self, other):
        if isinstance(other, Zone):
            return self.zone_id == other.zone_id
        return False

    def __str__(self):
        result = f"*{self.zone_name}* | lv. {self.level}\n\n{self.zone_description}\n\n*Damage modifiers*:\n{self.damage_modifiers}\n\n*Resist modifiers*:\n{self.resist_modifiers}"
        result += f"\n\n*Essence effects*:\n{"Increase one random stat" if self.extra_data.get("essence", None) is None else "\n".join([f"Increase {stat} by {value}" for stat, value in self.extra_data["essence"].items()])}"
        return result

    def __hash__(self):
        return hash(self.zone_id)

    @classmethod
    def get_empty(cls) -> Zone:
        return Zone(0, "", 1, "", Damage.get_empty(), Damage.get_empty(), {})


TOWN_ZONE: Zone = Zone(
    0,
    ContentMeta.get("world.city.name"),
    1,
    ContentMeta.get("world.city.description"),
    Damage.get_empty(),
    Damage.get_empty(),
    {},
)


class Anomaly:
    """ AI generated anomaly that modifies a specific zone's parameters """

    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, name: str, description: str, zone: Zone, effects: dict, expire_date: datetime) -> None:
        self.name = name
        self.description = description
        self.zone = zone
        self.expire_date = expire_date
        # effects
        self.xp_mult: float = effects.get("xp mult", 1.0)
        self.money_mult: float = effects.get("money mult", 1.0)
        self.level_bonus: int = effects.get("level bonus", 0)
        self.item_drop_bonus: int = effects.get("item drop bonus", 0)
        self.artifact_drop_bonus: int = effects.get("artifact drop bonus", 0)

    def get_json(self):
        return {
            "name": self.name,
            "description": self.description,
            "zone_id": self.zone.zone_id,
            "expire_date": self.expire_date.strftime(self.DATE_FORMAT),
            "effects": {
                "xp mult": self.xp_mult,
                "money mult": self.money_mult,
                "level bonus": self.level_bonus,
                "item drop bonus": self.item_drop_bonus,
                "artifact drop bonus": self.artifact_drop_bonus
            }
        }

    def get_effects_string(self) -> str:
        result = ""
        if self.xp_mult != 1.0:
            result += f"XP mult: {int(100 * self.xp_mult)}%\n"
        if self.money_mult != 1.0:
            result += f"BA mult: {int(100 * self.money_mult)}%\n"
        if self.level_bonus != 0:
            result += f"Enemy level bonus: {self.level_bonus}\n"
        if self.item_drop_bonus != 0:
            result += f"Item drop bonus: {self.item_drop_bonus}\n"
        if self.artifact_drop_bonus != 0:
            result += f"Artifact drop bonus: {self.artifact_drop_bonus}"
        return result

    def is_expired(self) -> bool:
        return datetime.now() > self.expire_date

    @classmethod
    def get_empty(cls):
        return Anomaly("No Anomaly", "No current anomaly observed", TOWN_ZONE, {}, datetime.now())

    def __str__(self):
        return f"Anomaly in {self.zone.zone_name} ({self.zone.zone_id}):\n\n*{self.name}*\n\n_{self.description}_\n\n{self.get_effects_string()}"


class Quest:
    """contains info about a human written or AI generated quest"""

    BASE_XP_REWARD = ContentMeta.get("quests.base_xp_reward")
    BASE_MONEY_REWARD = ContentMeta.get("quests.base_money_reward")

    def __init__(
        self,
        quest_id: int,
        zone: Zone,
        number: int,
        name: str,
        description: str,
        success_text: str,
        failure_text: str,
        is_raid: bool = False
    ) -> None:
        """
        :param quest_id (int): unique id of the quest
        :param zone (Zone): zone of the quest
        :param number (int): ordered number of the quest, players do quests incrementally in the same order in each zone
        :param description (str): description of the quest
        :param success_text (str): text to send player when the quest is successful
        :param failure_text (str): text to send player when the quest is not successful
        """
        self.quest_id = quest_id
        self.zone = zone
        self.number = number
        self.name = name
        self.description = description
        self.success_text = success_text
        self.failure_text = failure_text
        self.is_raid = is_raid

    def get_value_to_beat(self, player: Player) -> int:
        sqrt_multiplier = (1.2 * self.zone.level) - (
            (player.level + player.gear_level) / 2
        )
        if sqrt_multiplier < 1:
            sqrt_multiplier = 1
        num_multiplier = 4 / self.zone.level
        offset = 6 + self.zone.level - player.level
        if offset < 0:
            offset = 0
        value_to_beat = int(
            (sqrt_multiplier * math.sqrt(num_multiplier * self.number)) + offset
        )
        if value_to_beat > 19:
            value_to_beat = 19
        return value_to_beat

    def finish_quest(
        self, player: Player
    ) -> tuple[bool, int, int]:  # win/lose, roll, roll to beat
        """return true if the player has successfully finished the quest"""
        value_to_beat = self.get_value_to_beat(player)
        roll = player.roll(20)
        if roll == 1:
            log.info(f"{player.name} rolled a critical failure on quest {self.name}")
            return False, 1, value_to_beat  # you can still get a critical failure
        if roll == 20:
            log.info(f"{player.name} rolled a critical success on quest {self.name}")
            return True, 20, value_to_beat  # you can also get a critical success
        if (roll - value_to_beat) == -1:
            # if the player missed the roll by 1 have an 80% chance of gracing them
            if random.randint(1, 10) > 2:
                roll += 1
        log.info(f"{self.name}: to beat: {value_to_beat}, {player.name} rolled: {roll}")
        return roll >= value_to_beat, roll, value_to_beat

    def get_rewards(self, player: Player) -> tuple[int, int]:
        """return the amount of xp & money the completion of the quest rewards"""
        guild_level = player.guild_level()
        multiplier = self.zone.level + self.number
        guild_level_bonus = guild_level * (5000 if guild_level < 10 else 10000)
        bonus = random.randint(0, 50) + guild_level_bonus
        return (
            int(
                ((self.BASE_XP_REWARD * multiplier) + bonus) * player.vocation.quest_xp_mult
            ),
            int(
                ((self.BASE_MONEY_REWARD * multiplier) + bonus) * player.vocation.quest_money_mult
            ),
        )  # XP, Money

    def get_duration(self, player: Player) -> timedelta:
        duration: timedelta = (
            BASE_QUEST_DURATION
            + (
                (DURATION_PER_ZONE_LEVEL * self.zone.level)
                + (DURATION_PER_QUEST_NUMBER * self.number)
                + (random.randint(0, self.zone.level) * RANDOM_DURATION)
            )
            * player.vocation.quest_time_multiplier
        ) - timedelta(minutes=30 * player.get_stats().agility)
        if duration < BASE_QUEST_DURATION:
            return BASE_QUEST_DURATION
        return duration

    def get_prestige(self) -> int:
        return self.zone.level + self.number

    def __str__(self) -> str:
        return f"*{self.number + 1} - {self.name}*\n\n{self.description}"

    def __hash__(self) -> int:
        return hash(self.quest_id)

    @classmethod
    def get_empty(cls) -> Quest:
        return Quest(0, Zone.get_empty(), 0, "", "", "", "")

    @classmethod
    def create_default(
        cls,
        zone: Zone,
        num: int,
        name: str,
        description: str,
        success: str,
        failure: str,
    ) -> Quest:
        return Quest(0, zone, num, name, description, success, failure)


class Progress:
    """stores the player quest progress for each zone"""

    def __init__(self, zone_progress: dict[int, int]) -> None:
        """
        :param zone_progress:
            dictionary that contains the player quest progress in the zone, stored like this: {zone: progress, ...}
        """
        self.zone_progress = zone_progress

    def get_zone_progress(self, zone: Zone) -> int:
        return self.zone_progress.get(zone.zone_id - 1, 0)

    def set_zone_progress(self, zone: Zone, progress: int) -> None:
        self.zone_progress[zone.zone_id - 1] = progress

    def __str__(self) -> str:
        return "\n".join(
            f"zone {zone}: progress {progress}" for zone, progress in self.zone_progress
        )

    def __repr__(self) -> str:
        return str(self.zone_progress)

    @classmethod
    def get_from_encoded_data(
        cls, progress_data: Any, parsing_function: Callable[[Any], dict[int, int]]
    ) -> Progress:
        """
        :param progress_data:
            The data that contains the player quest progress.
            How it is stored on the database is independent of the implementation here.
        :param parsing_function:
            The function used to parse progress_data, must return the correct data format
        """
        zone_progress: dict[int, int] = parsing_function(progress_data)
        return cls(zone_progress)


class SpellError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Spell:
    def __init__(
        self,
        name: str,
        description: str,
        required_power: int,
        required_artifacts: int,
        level: int,
        required_args: int,
        function: Callable[[Player, list[str] | tuple[str, ...]], str],
    ) -> None:
        self.name = name
        self.description = description
        self.required_power = required_power
        self.required_artifacts = required_artifacts
        self.level = level
        self.required_args = required_args
        self.function = function

    def can_cast(self, caster: Player) -> bool:
        return (caster.ascension >= self.level) and (caster.get_spell_charge() >= self.required_power ) and (caster.artifact_pieces >= self.required_artifacts)

    def check_args(self, args: tuple[str, ...]) -> bool:
        if self.required_args == 0:
            return True
        return len(args) == self.required_args

    def cast(self, caster: Player, args: tuple[str, ...]) -> str:
        try:
            result = self.function(caster, args)
            caster.last_cast = datetime.now()
            caster.artifact_pieces -= self.required_artifacts
            return f"You cast {self.name}, " + result
        except SpellError as e:
            return e.message


class Player(CombatActor):
    """contains all information about a player"""

    MAXIMUM_POWER: int = 100
    MAX_HOME_LEVEL = 10

    FIST_DAMAGE = Damage(0, 0, 1, 0, 0, 0, 0, 0)

    def __init__(
        self,
        player_id: int,
        name: str,
        description: str,
        guild: Guild | None,
        level: int,
        xp: int,
        money: int,
        progress: Progress,
        gear_level: int,
        home_level: int,
        artifact_pieces: int,
        last_cast: datetime,
        artifacts: list[Artifact],
        flags: np.uint32,
        renown: int,
        vocations: list[Vocation],
        satchel: list[ConsumableItem],
        equipped_items: dict[int, Equipment],
        hp_percent: float,
        stance: str,
        completed_quests: int,
        last_guild_switch: datetime,
        vocations_progress: dict[int, int],
        sanity: int,
        ascension: int,
        stats: Stats,
        essences: dict[int, int],
        max_level_reached: int,
        max_money_reached: int,
        max_renown_reached: int,
        pet: Pet | None
    ) -> None:
        """
        :param player_id (int): unique id of the player
        :param name (str): name of the player
        :param description (str): user written description of the player
        :param guild: the guild this player belongs to
        :param level (int): current player level, potentially unlimited
        :param xp (int): current xp of the player
        :param money (int): current money of the player
        :param progress (Progress): contains progress object, which tracks the player progress in each zone,
        :param gear_level (int): current gear level of the player, potentially unlimited
        :param home_level(int): current level of the home owned by the player, potentially unlimited
        :param artifact_pieces (int): number of artifact pieces of the player. Use 10 to build a new artifact.
        :param last_cast (datetime): last spell cast datetime.
        :param flags (np.uint32): flags of the player, can be used for anything
        :param renown (int): renown of the player, used for ranking
        :param vocations: the player's vocations
        :param satchel: the player's satchel which holds consumable items
        :param equipped_items: the player's equipped items
        :param hp_percent: the player's hp percentage
        :param stance: the player's stance
        :param completed_quests: the player's completed quests
        :param last_guild_switch: The time in which the player last changed guild
        :param vocations_progress: the player's vocations progress
        :param sanity: the player's sanity, used to hunt/explore
        :param ascension: the player's ascension level
        :param stats: the player's stats
        :param essences: the player's essences
        :param max_level_reached: the maximum level the player has ever reached
        :param max_money_reached: the maximum money the player has ever reached
        :param max_renown_reached: the maximum renown the player has ever reached
        :param pet: the currently equipped pet
        """
        self.player_id = player_id
        self.name = name
        self.description = description
        self.guild = guild
        self.progress = progress
        self.money = money
        self.level = level
        self.xp = xp
        self.gear_level = gear_level
        self.home_level = home_level
        self.artifact_pieces = artifact_pieces
        self.last_cast = last_cast
        self.artifacts = artifacts
        self.flags = flags
        self.renown = renown
        self.vocation = Vocation.empty()
        self.equip_vocations(vocations)
        self.satchel = satchel
        self.equipped_items = equipped_items
        super().__init__(hp_percent, 0, stats)
        self.stance = stance
        self.completed_quests = completed_quests
        self.last_guild_switch = last_guild_switch
        self.vocations_progress = vocations_progress
        self.sanity = sanity
        self.ascension = ascension
        self.essences = essences
        self.max_level_reached = max_level_reached
        self.max_money_reached = max_money_reached
        self.max_renown_reached = max_renown_reached
        self.pet = pet

    def equip_vocations(self, vocations: list[Vocation]) -> None:
        self.vocation: Vocation = Vocation.empty()
        for v in vocations:
            self.vocation += v

    def get_name(self) -> str:
        return self.name

    def get_level(self) -> int:
        return self.level

    def guild_level(self) -> int:
        if self.guild:
            return self.guild.level
        return 0

    def get_required_xp(self) -> int:
        lv = self.level
        value = (100 * (lv * lv)) + (1000 * lv)
        return int(value * self.vocation.upgrade_cost_multiplier)

    def get_level_progress(self) -> float:
        return (self.xp / self.get_required_xp()) * 100

    def get_gear_upgrade_required_money(self) -> int:
        lv = self.gear_level
        value = (50 * (lv * lv)) + (1000 * lv)
        return int(value * self.vocation.upgrade_cost_multiplier)

    def get_home_upgrade_required_money(self) -> int:
        lv = self.home_level + 1
        value = (200 * (lv * lv)) + (600 * lv)
        return int(value * self.vocation.upgrade_cost_multiplier)

    def can_upgrade_gear(self) -> bool:
        return True

    def can_upgrade_home(self) -> bool:
        return self.home_level < self.MAX_HOME_LEVEL

    def upgrade_gear(self) -> None:
        self.gear_level += 1

    def upgrade_home(self) -> None:
        self.home_level += 1

    def upgrade_vocation(self, vocation_id: int) -> None:
        if vocation_id not in self.vocations_progress:
            self.vocations_progress[vocation_id] = 2
        else:
            self.vocations_progress[vocation_id] += 1

    def level_up(self) -> None:
        req_xp = self.get_required_xp()
        while self.xp >= req_xp:
            self.level += 1
            self.xp -= req_xp
            req_xp = self.get_required_xp()
            InternalEventBus().notify(Event("level up", self, {"level": self.level}))
        if self.level > self.max_level_reached:
            self.max_level_reached = self.level

    def add_xp(self, amount: float) -> int:
        """adds xp to the player & returns how much was actually added to the player"""
        amount *= self.vocation.general_xp_mult + (self.ascension / 4)
        if DeathwishMode.is_set(self.flags):
            amount *= 2
        self.xp += int(amount)
        if self.xp >= self.get_required_xp():
            self.level_up()
        return int(amount)

    def add_money(self, amount: float) -> int:
        """adds money to the player & returns how much was actually added to the player"""
        amount *= self.vocation.general_money_mult
        for flag in (AlloyGlitchFlag1, AlloyGlitchFlag2, AlloyGlitchFlag3):
            if flag.is_set(self.flags):
                amount = int(amount * 1.5)
                self.unset_flag(flag)
        amount = int(amount)
        if DeathwishMode.is_set(self.flags):
            amount *= 2
        self.money += amount
        if self.money >= self.max_money_reached:
            self.max_money_reached = self.money
        return amount

    def add_artifact_pieces(self, amount: int) -> None:
        self.artifact_pieces += amount

    def roll(self, dice_faces: int) -> int:
        """roll a dice and apply all advantages / disadvantages"""
        roll = random.randint(1, dice_faces) + self.vocation.roll_bonus
        for modifier, flag in zip(
            (-1, -1, 1, 2), (HexedFlag, CursedFlag, LuckFlag1, LuckFlag2), strict=False
        ):
            if flag.is_set(self.flags):
                roll += modifier
                self.unset_flag(flag)
        if random.randint(1, 10) > 5:
            # skew the roll to avoid players failing too much
            roll += random.randint(1, 5)
        if roll < 1:
            return 1
        if roll > dice_faces:
            return dice_faces
        return roll

    def get_number_of_tried_quests(self) -> int:
        result: int = 0
        for _, progress in self.progress.zone_progress.items():
            result += progress
        return result

    def print_username(self, mode: str = "telegram") -> str:
        if mode == "telegram":
            return f"[{self.name}](tg://user?id={self.player_id})"
        return self.name

    def get_max_charge(self) -> int:
        """ return eldritch power charge """
        if not self.artifacts:
            return 0
        max_charge = (len(self.artifacts) * POWER_PER_ARTIFACT) + self.vocation.power_bonus + (self.ascension * 5)
        if self.vocation.power_bonus_per_zone_visited:
            max_charge += (
                len(self.progress.zone_progress)
                * self.vocation.power_bonus_per_zone_visited
            )
        return max_charge + self.get_stats().attunement

    def get_spell_charge(self) -> int:
        """returns spell charge of the player"""
        max_charge = self.get_max_charge()
        charge = int(
            ((datetime.now() - self.last_cast).total_seconds() / 86400) * POWER_PER_DAY
        )
        if charge > max_charge:
            return max_charge
        return charge

    def set_flag(self, flag: type[Flag]) -> None:
        """

        :rtype: object
        """
        self.flags = flag.set(self.flags)

    def unset_flag(self, flag: type[Flag]) -> None:
        self.flags = flag.unset(self.flags)

    def get_inventory_size(self) -> int:
        return 10 + self.home_level * 4

    def get_pet_inventory_size(self) -> int:
        return self.home_level

    def get_max_number_of_artifacts(self) -> int:
        return self.home_level * 2

    def get_max_satchel_items(self) -> int:
        return 10

    # combat stats

    def get_base_max_hp(self) -> int:
        return int(
            (
                (self.level * 10) + (self.gear_level * 5) + (self.get_stats().vitality * 5)
            ) * self.vocation.hp_mult
        ) + self.vocation.hp_bonus

    def get_insanity_scaling(self) -> float:
        if self.sanity > 25:
            return 1.0
        elif self.sanity > 0:
            return 1.15
        return 1.15 - (self.sanity / 100)

    def get_base_attack_damage(self) -> Damage:
        base_damage = self.vocation.damage.scale(self.level)
        slots = []
        stats = self.get_stats()
        for slot, item in self.equipped_items.items():
            base_damage += item.damage.scale_with_stats(stats, item.equipment_type.scaling)
            slots.append(slot)
        if Slots.PRIMARY not in slots:
            base_damage += self.FIST_DAMAGE.scale(self.level)
        if Slots.SECONDARY not in slots:
            base_damage += self.FIST_DAMAGE.apply_bonus(self.gear_level)
        # apply buffs
        if StrengthBuff.is_set(self.flags):
            base_damage = base_damage.scale_single_value("slash", 1.5)
            base_damage = base_damage.scale_single_value("pierce", 1.5)
            base_damage = base_damage.scale_single_value("blunt", 1.5)
        if OccultBuff.is_set(self.flags):
            base_damage = base_damage.scale_single_value("occult", 2)
        if FireBuff.is_set(self.flags):
            base_damage = base_damage.scale_single_value("fire", 2)
        if AcidBuff.is_set(self.flags):
            base_damage = base_damage.scale_single_value("acid", 2)
        if IceBuff.is_set(self.flags):
            base_damage = base_damage.scale_single_value("freeze", 2)
        if ElectricBuff.is_set(self.flags):
            base_damage = base_damage.scale_single_value("electric", 2)
        spell_buff = (
            int(MightBuff1.is_set(self.flags)) +
            int(MightBuff2.is_set(self.flags)) +
            int(MightBuff3.is_set(self.flags))
        )
        base_damage = base_damage.scale(1 + (0.5 * spell_buff))
        insanity_scaling = self.get_insanity_scaling()
        if insanity_scaling > 2:
            insanity_scaling = 2
        return base_damage.scale(insanity_scaling)

    def get_base_attack_resistance(self) -> Damage:
        base_resistance = self.vocation.resist.scale(self.level)
        stats = self.get_stats()
        for _, item in self.equipped_items.items():
            base_resistance += item.resist.scale_with_stats(stats, item.equipment_type.scaling)
        insanity_scaling = 1 / self.get_insanity_scaling()
        return base_resistance.scale(insanity_scaling)

    def get_entity_modifiers(self, *type_filters: int) -> list[m.Modifier]:
        result: list[m.Modifier] = []
        for _, item in self.equipped_items.items():
            result.extend(item.get_modifiers(type_filters))
        return result

    def __clamp_hp(self, max_hp: int) -> None:
        if self.hp > max_hp:
            self.hp = max_hp

    def use_consumable(
        self, position_in_satchel: int, add_you: bool = True
    ) -> tuple[str, bool]:
        """return the use text & if you actually used a consumable"""
        if not self.satchel:
            return "No items in satchel!", False
        if position_in_satchel > len(self.satchel):
            return Strings.satchel_position_out_of_range.format(num=len(self.satchel)), False
        if position_in_satchel > 0:
            position_in_satchel -= 1
        item = self.satchel.pop(position_in_satchel)
        max_hp = self.get_max_hp()
        self.hp = int(self.hp_percent * max_hp)
        self.hp += item.hp_restored
        self.__clamp_hp(max_hp)
        self.hp += int(max_hp * item.hp_percent_restored)
        self.__clamp_hp(max_hp)
        if self.hp != max_hp:
            self.hp_percent = self.hp / max_hp
        else:
            self.hp_percent = 1.0
        self.flags = self.flags | item.buff_flag
        self.add_sanity(item.sanity_restored)
        text = Strings.used_item.format(verb=item.verb, item=item.name)
        if add_you:
            return "You " + text, True
        return text, True

    def use_healing_consumable(self, add_you: bool = True) -> tuple[str, bool]:
        if not self.satchel:
            return "No items in satchel!", False
        max_hp: int = self.get_max_hp()
        pos: int = -1
        best_healing: int = 0
        for i, item in enumerate(self.satchel):
            if item.is_healing_item():
                item_healing = int(item.hp_restored + (item.hp_percent_restored * max_hp))
                if item_healing > best_healing:
                    best_healing = item_healing
                    pos = i
        if pos == -1:
            return "No healing items in satchel!", False
        text, _ = self.use_consumable(pos + 1, add_you=add_you)
        return text, True

    def equip_item(self, item: Equipment) -> None:
        self.equipped_items[item.equipment_type.slot] = item

    def equip_pet(self, pet: Pet) -> None:
        self.pet = pet

    def is_item_equipped(self, item: Equipment) -> bool:
        for equipped_item in self.equipped_items.values():
            if equipped_item == item:
                return True
        return False

    def is_pet_equipped(self, pet: Pet) -> bool:
        if self.pet is None:
            return False
        return pet.id == self.pet.id

    def has_pet(self) -> bool:
        return self.pet is not None

    def get_stance(self) -> str:
        return self.stance

    def get_delay(self) -> int:
        value = 0
        for item in self.equipped_items.values():
            value += item.equipment_type.delay
        spell_buff = (
            int(SwiftBuff1.is_set(self.flags)) +
            int(SwiftBuff2.is_set(self.flags)) +
            int(SwiftBuff3.is_set(self.flags))
        )
        value -= (spell_buff * 15)
        return value if value > 0 else 0

    STANCE_POOL = {
        "b": (
            CombatActions.attack,
            CombatActions.attack,
            CombatActions.dodge,
            CombatActions.charge_attack,
            CombatActions.dodge,
            CombatActions.use_consumable,
        ),
        "s": (
            CombatActions.attack,
            CombatActions.dodge,
            CombatActions.dodge,
            CombatActions.use_consumable,
        ),
        "r": (
            CombatActions.attack,
            CombatActions.attack,
            CombatActions.attack,
            CombatActions.charge_attack,
            CombatActions.dodge,
        ),
        "a": (CombatActions.attack, CombatActions.attack),
    }
    STANCE_POOL_NC = {  # No Consumables
        "b": (
            CombatActions.attack,
            CombatActions.attack,
            CombatActions.dodge,
            CombatActions.charge_attack,
            CombatActions.dodge,
        ),
        "s": (CombatActions.attack, CombatActions.attack, CombatActions.dodge),
        "r": (
            CombatActions.attack,
            CombatActions.attack,
            CombatActions.attack,
            CombatActions.charge_attack,
            CombatActions.charge_attack,
            CombatActions.dodge,
        ),
        "a": (CombatActions.attack, CombatActions.attack),
    }

    def choose_action(self, opponent: CombatActor) -> int:
        main_pool = (
            self.STANCE_POOL
            if (self.satchel and (self.hp_percent < 0.55))
            else self.STANCE_POOL_NC
        )
        selected_pool = main_pool.get(
            self.get_stance(), (CombatActions.attack, CombatActions.dodge)
        )
        if self.vocation.lick_wounds:
            selected_pool += (CombatActions.lick_wounds,)
        selection = random.choice(selected_pool)
        return selection

    def get_vocation_limit(self) -> int:
        if self.level < 5:
            return 0
        if self.level < 20:
            return 1
        return 2

    def get_vocation_level(self, vocation_id: int) -> int:
        return self.vocations_progress.get(vocation_id, 1)

    def get_max_sanity(self):
        return 99 + self.get_stats().mind

    def add_sanity(self, amount: int):
        self.sanity += amount
        max_sanity = self.get_max_sanity()
        if self.sanity > max_sanity:
            self.sanity = max_sanity
        if (amount < 0) and (self.sanity <= 25):
            InternalEventBus().notify(Event("sanity low", self, {"sanity": self.sanity}))

    def add_essence(self, zone_id: int, amount: int):
        if self.essences.get(zone_id, None) is None:
            self.essences[zone_id] = 0
        if DeathwishMode.is_set(self.flags):
            amount *= 2
        self.essences[zone_id] += amount

    def get_ascension_level(self) -> int:
        return MINIMUM_ASCENSION_LEVEL + (self.ascension * LEVEL_INCREASE_PER_ASCENSION)

    def can_ascend(self) -> bool:
        return self.level >= self.get_ascension_level()

    def add_renown(self, amount: int) -> None:
        self.renown += amount
        if self.renown >= self.max_renown_reached:
            self.max_renown_reached = self.renown

    def use_best_bait_item(self) -> ConsumableItem or None:
        best_item: ConsumableItem or None = None
        pos: int = 0
        for i, consumable in enumerate(self.satchel):
            if best_item is None:
                best_item = consumable
                pos = i
            elif consumable.bait_power > best_item.bait_power:
                best_item = consumable
                pos = i
        if best_item is not None:
            self.satchel.pop(pos)
        return best_item

    # utility

    def __str__(self) -> str:
        max_hp = self.get_max_hp()
        guild = f" | {self.guild.name} (lv. {self.guild.level})" if self.guild else ""
        string = f"{self.print_username()} | lv. {self.level}{guild}\n`{self.xp}/{self.get_required_xp()} xp ({self.get_level_progress():.2f}%)`\n"
        if self.ascension != 0:
            string += f"Ascension level: {self.ascension}\n"
        if self.vocation.name:
            string += f"{self.vocation.name}\n"
        string += f"HP:  `{int(max_hp * self.hp_percent)}/{max_hp}`\n"
        string += f"Sanity: `{self.sanity}/{self.get_max_sanity()}`\n"
        string += f"{self.money} *{MONEY}*\n*Home* lv. {self.home_level}, *Gear* lv. {self.gear_level}\n"
        string += f"Stance: {Strings.stances[self.stance][0]}\nRenown: {self.renown}"
        if (self.get_max_charge() > 0) or (len(self.artifacts) > 0):
            string += f"\nEldritch power: `{self.get_spell_charge()}/{self.get_max_charge()}`"
            string += f"\n\n_{self.description}\n\nQuests: {self.get_number_of_tried_quests()}\nArtifact pieces: {self.artifact_pieces}_"
            string += (
                f"\n\nArtifacts ({len(self.artifacts)}/{self.get_max_number_of_artifacts()}):\n"
                + ("\n".join(f"{a.artifact_id}. *{a.name}*" for a in self.artifacts))
                if len(self.artifacts) > 0
                else "\n\nNo artifacts yet."
            )
        else:
            string += f"\n\n_{self.description}\n\nQuests: {self.get_number_of_tried_quests()} tried, {self.completed_quests} completed.\nArtifact pieces: {self.artifact_pieces}_"
        if self.equipped_items:
            string += f"\n\nEquipped items:\n*{'\n'.join(f"{Strings.get_item_icon(slot)} - {item.name}" for slot, item in sorted(self.equipped_items.items()))}*"
        if self.pet:
            string += f"\n\nPet: *{self.pet.get_name()}*"
        if self.satchel:
            string += f"\n\nSatchel:\n{'\n'.join(f"{i + 1}. {x.name}" for i, x in enumerate(self.satchel))}"
        return string

    def __repr__(self) -> str:
        return str(self.__dict__)

    def __hash__(self) -> int:
        return hash(self.player_id)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Player):
            return self.player_id == other.player_id
        return False

    @classmethod
    def create_default(cls, player_id: int, name: str, description: str) -> Player:
        player_defaults = ContentMeta.get("defaults.player")
        return Player(
            player_id,
            name,
            description,
            None,
            1,
            0,
            player_defaults["money"],
            Progress({}),
            player_defaults["gear"],
            player_defaults["home"],
            0,
            datetime.now(),
            [],
            np.uint32(0),
            0,
            [],
            [],
            {},
            1.0,
            "b",
            0,
            datetime.now() - timedelta(days=1),
            {},
            100,
            0,
            Stats.create_default(),
            {},
            0,
            0,
            0,
            None
        )


class Guild:
    """Player created guilds that other players can join. Players get bonus xp & money from quests when in guilds"""

    MAX_LEVEL: int = ContentMeta.get("guilds.max_level")
    PLAYERS_PER_LEVEL: int = ContentMeta.get("guilds.players_per_level")
    MAX_PLAYERS: int = ContentMeta.get("guilds.max_players")

    def __init__(
        self,
        guild_id: int,
        name: str,
        level: int,
        description: str,
        founder: Player,
        creation_date: datetime,
        prestige: int,
        tourney_score: int,
        tax: int,
        bank: int,
        last_raid: datetime
    ) -> None:
        """
        :param guild_id: unique id of the guild
        :param name: player given name of the guild
        :param level: the current level of the guild, controls how many players can be in a guild (4 * level). Max is 10
        :param description: player given description of the guild
        :param founder: the player who found the guild,
        :param creation_date: the date the guild was created
        :param prestige: the amount of prestige the guild has
        :param tourney_score: the score of the bi-weekly tournament the guild has
        :param tax: how much the quest rewards are taxed by the guild
        :param bank: the guild's bank
        """
        self.guild_id = guild_id
        self.name = name
        self.level = level
        self.description = description
        self.founder = founder
        self.creation_date = creation_date
        self.prestige = prestige
        self.tourney_score = tourney_score
        self.tax = tax
        self.bank = bank
        self.deleted: bool = False
        self.last_raid = last_raid

    def get_max_members(self) -> int:
        value = self.level * self.PLAYERS_PER_LEVEL
        if value > self.MAX_PLAYERS:
            return self.MAX_PLAYERS
        return value

    def get_bank_logs_file_path(self):
        # we should separate data layer & control layer but eh, it's fine for this for now.
        return f"bank_logs/{self.guild_id}.txt"

    def get_bank_logs_data(self) -> str:
        file_path = self.get_bank_logs_file_path()
        try:
            data = read_text_file(file_path)
            if data:
                return data
            else:
                return Strings.no_logs
        except FileNotFoundError:
            save_text_to_file(file_path, '')  # create the file
            return Strings.no_logs

    def create_bank_log(self, log_type: str, player_id: int, amount: int):
        file_path = self.get_bank_logs_file_path()
        data = self.get_bank_logs_data()
        if data == Strings.no_logs:
            data = ''
        new_data = data + json.dumps({"transaction": log_type, "by": player_id, "amount": amount}) + "\n"
        save_text_to_file(file_path, new_data)
        return new_data

    def can_add_member(self, current_members: int) -> bool:
        return current_members < self.get_max_members()

    def can_upgrade(self) -> bool:
        return self.level >= self.MAX_LEVEL

    def get_upgrade_required_money(self) -> int:
        lv = self.level
        return (10000 * (lv * lv)) + (1000 * lv)

    def upgrade(self) -> None:
        self.level += 1

    def can_raid(self) -> bool:
        return (datetime.now() - self.last_raid) >= RAID_DELAY

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Guild):
            return self.guild_id == other.guild_id
        return False

    def __str__(self) -> str:
        return f"*{self.name}* | lv. {self.level}\nPrestige: {self.prestige}\nFounder: {self.founder.print_username() if self.founder else '???'}\n_Since {self.creation_date.strftime("%d %b %Y")}_\n\n{self.description}\n\n_Tax: {self.tax}%\nTourney score: {self.tourney_score}_"
    
    def __hash__(self) -> int:
        return hash(self.guild_id)

    @classmethod
    def create_default(cls, founder: Player, name: str, description: str) -> Guild:
        return Guild(0, name, 1, description, founder, datetime.now(), 0, 0, 5, 0, datetime.now())

    @classmethod
    def print_members(cls, members: list[tuple[int, str, int]]) -> str:
        return "\n".join(f"{name} | lv. {level}" for _, name, level in members)


class ZoneEvent:
    """
    Events that happen during the day every X hours of which the player is notified.
    Players get bonus xp & money from events depending on their home level.
    """

    def __init__(self, event_id: int, zone: Zone | None, event_text: str) -> None:
        """
        :param event_id: unique id of the event
        :param zone: the zone that this event happens in. If none then it's the town
        :param event_text: a short text describing the event
        """
        self.event_id = event_id
        self.zone = zone
        self.event_text = event_text
        self.zone_level = zone.level if zone else 0
        self.base_value = 2
        self.bonus = zone.zone_id if zone else 0

    def __val(self, player: Player) -> int:
        """get base event reward value"""
        if player.level >= (self.zone_level - 3):
            return (
                (self.base_value + self.zone_level + player.home_level)
                * random.randint(1, 10)
            ) + self.bonus
        return (
            (self.base_value + player.home_level) * random.randint(1, 10)
        ) + self.bonus

    def get_rewards(self, player: Player) -> tuple[int, int]:
        """returns xp & money rewards for the event. Influenced by player home level"""
        return int(self.__val(player) * player.vocation.event_xp_mult), int(
            self.__val(player) * player.vocation.event_money_mult
        )

    def __str__(self) -> str:
        return self.event_text

    def __hash__(self) -> int:
        return hash(self.event_id)

    @classmethod
    def get_empty(cls) -> ZoneEvent:
        return ZoneEvent(0, Zone.get_empty(), "")

    @classmethod
    def create_default(cls, zone: Zone, event_text: str) -> ZoneEvent:
        return ZoneEvent(0, zone, event_text)


class AdventureContainer:
    """Utility class to help manage player updates"""

    def __init__(
        self,
        player: Player,
        quest: Quest | None,
        finish_time: datetime | None,
        last_update: datetime,
    ):
        """
        :param player:
            the player questing
        :param quest:
            if not None then it's the quest the player is currently doing, otherwise it means the player is in town
        :param finish_time:
            the time the quest finishes. If None the player is in town
        """
        self.player = player
        self.quest = quest
        self.finish_time = finish_time
        self.last_update = last_update

    def is_quest_finished(self) -> bool:
        """returns whether the current quest is finished by checking the finish time"""
        return datetime.now() > self.finish_time

    def is_on_a_quest(self) -> bool:
        """returns whether the player is on a quest"""
        return self.quest is not None

    def player_id(self) -> int:
        """non-verbose way to get player id"""
        return self.player.player_id

    def quest_id(self) -> int | None:
        """non-verbose way to get quest id"""
        return self.quest.quest_id if self.quest else None

    def zone(self) -> Zone | None:
        """returns Zone if player is on a quest, None if player is in town"""
        return self.quest.zone if self.quest else None

    def __str__(self) -> str:
        if self.quest:
            if datetime.now() >= self.finish_time:
                return f"{self.quest}\n\n_Time left: Should be done very soon..._"
            tl: timedelta = self.finish_time - datetime.now()
            days_str = f"{tl.days} day{'' if tl.days == 1 else 's'}"
            hours = tl.seconds // 3600
            hours_str = f"{hours} hour{'' if hours == 1 else 's'}"
            return f"{self.quest}\n\n_Time left: about {days_str} & {hours_str}_"
        else:
            return "Not on a quest"

    def __hash__(self) -> int:
        return hash(self.player_id())


class Artifact:
    """
    rare & unique items player can acquire by combining fragments they find while questing.
    Each artifact should be unique, owned by a single player.
    """

    def __init__(
        self,
        artifact_id: int,
        name: str,
        description: str,
        owner: Player | None,
        owned_by_you: bool = False,
    ) -> None:
        self.artifact_id = artifact_id
        self.name = name
        self.description = description
        if owned_by_you:
            self.owner = "you"
        elif owner:
            self.owner = owner.name
        else:
            self.owner = None

    def __str__(self) -> str:
        if self.owner:
            return f"n. {self.artifact_id} - *{self.name}*\nOwned by {self.owner}\n\n_{self.description}_\n\n"
        return f"n. {self.artifact_id} - *{self.name}*\n\n_{self.description}_"

    @classmethod
    def get_empty(cls) -> Artifact:
        return Artifact(0, "", "", None)


class QuickTimeEvent(Listable["QuickTimeEvent"], base_filename="qtes"):
    def __init__(
        self,
        description: str,
        successes: list[str],
        failures: list[str],
        options: list[tuple[str, int]],
        rewards: list[list[Callable[[Player], None]]],
        maluses: list[list[Callable[[Player], None]]]
    ) -> None:
        """
        :param description: description of the quick time event
        :param successes: descriptions of the quick time event successful completions
        :param failures: descriptions of the quick time event failures
        :param options: the options to give the player
        :param rewards: the functions used to give rewards to the players on QTE success
        :param maluses: the functions used to give maluses to the player on QTE failure
        """
        assert len(options) == len(rewards) == len(successes) == len(failures)
        self.description = description
        self.successes = successes
        self.failures = failures
        self.options = options
        self.rewards = rewards
        self.maluses = maluses

    def __get_reward(self, index: int) -> Callable[[Player], list[Any]]:
        reward_functions = self.rewards[index]

        def execute_funcs(player: Player):
            result = []
            for func in reward_functions:
                result.append(func(player))
            return result

        return execute_funcs

    def __get_malus(self, index: int) -> Callable[[Player], list[Any]]:
        malus_functions = self.maluses[index]

        def execute_funcs(player: Player):
            result = []
            for func in malus_functions:
                result.append(func(player))
            return result

        return execute_funcs

    def resolve(
        self, chosen_option: int
    ) -> tuple[Callable[[Player], list] | None, str, bool]:
        """return if the qte succeeded and the string associated"""
        option = self.options[chosen_option]
        roll = random.randint(1, 100)
        if roll <= option[1]:
            return self.__get_reward(chosen_option), self.successes[chosen_option], True
        return self.__get_malus(chosen_option), self.failures[chosen_option], False

    # rewards ----

    @staticmethod
    def _add_money(player: Player, amount: int) -> None:
        player.add_money(amount)
        return None

    @staticmethod
    def _add_xp(player: Player, amount: int) -> None:
        player.add_xp(amount)
        return None

    @staticmethod
    def _add_artifact_pieces(player: Player, amount: int) -> None:
        player.add_artifact_pieces(amount)
        return None

    @staticmethod
    def _add_item(player: Player, rarity_str: str) -> Equipment:
        if not rarity_str:
            rarity = random.randint(0, 3)
        else:
            rarity = {
                f"({Strings.rarities[0]})": 0,
                f"({Strings.rarities[1]})": 1,
                f"({Strings.rarities[2]})": 2,
                f"({Strings.rarities[3]})": 3,
            }.get(rarity_str, 0)
        return Equipment.generate(player.level, EquipmentType.get_random(), rarity)

    @staticmethod
    def _add_renown(player: Player, amount: int) -> None:
        player.add_renown(amount)
        return None

    @staticmethod
    def _add_sanity(player: Player, amount: int) -> None:
        player.add_sanity(amount)
        return None

    # maluses ----

    @staticmethod
    def _lose_hp(player: Player, amount: int) -> None:
        player.modify_hp(-amount)
        if player.is_dead():
            player.modify_hp(1)  # this cannot kill
        return None

    @staticmethod
    def _lose_money(player: Player, amount: int) -> None:
        player.money -= amount
        if player.money < 0:
            player.money = 0
        return None

    @staticmethod
    def _lose_xp(player: Player, amount: int) -> None:
        player.xp -= amount
        if player.xp < 0:
            player.xp = 0
        return None

    @staticmethod
    def _lose_renown(player: Player, amount: int) -> None:
        player.add_renown(-amount)
        return None

    @staticmethod
    def _lose_sanity(player: Player, amount: int) -> None:
        player.add_sanity(-amount)
        return None

    @classmethod
    def __get_rewards_from_string(cls, reward_string: str) -> list[FuncWithParam]:
        split_reward_str = reward_string.split(", ")
        funcs_list: list[FuncWithParam] = []
        for reward_func_components in split_reward_str:
            components = reward_func_components.split(" ")
            if components[0] == "xp":
                funcs_list.append(FuncWithParam(cls._add_xp, int(components[1])))
            elif components[0] == "mn":
                funcs_list.append(FuncWithParam(cls._add_money, int(components[1])))
            elif components[0] == "ap":
                funcs_list.append(
                    FuncWithParam(cls._add_artifact_pieces, int(components[1]))
                )
            elif components[0] == "item":
                funcs_list.append(FuncWithParam(cls._add_item, components[1]))
            elif components[0] == "rn":
                funcs_list.append(FuncWithParam(cls._add_renown, int(components[1])))
            elif components[0] == "sa":
                funcs_list.append(FuncWithParam(cls._add_sanity, int(components[1])))
        return funcs_list

    @classmethod
    def __get_maluses_from_string(cls, reward_string: str) -> list[FuncWithParam]:
        split_reward_str = reward_string.split(", ")
        funcs_list: list[FuncWithParam] = []
        for reward_func_components in split_reward_str:
            components = reward_func_components.split(" ")
            if components[0] == "xp":
                funcs_list.append(FuncWithParam(cls._lose_xp, int(components[1])))
            elif components[0] == "mn":
                funcs_list.append(FuncWithParam(cls._lose_money, int(components[1])))
            elif components[0] == "hp":
                funcs_list.append(
                    FuncWithParam(cls._lose_hp, int(components[1]))
                )
            elif components[0] == "rn":
                funcs_list.append(FuncWithParam(cls._lose_renown, int(components[1])))
            elif components[0] == "sa":
                funcs_list.append(FuncWithParam(cls._lose_sanity, int(components[1])))
        return funcs_list

    @classmethod
    def create_from_json(cls, qte_json: dict[str, str]) -> QuickTimeEvent:
        # get object
        choices = qte_json.get("choices")
        # init empty lists
        options: list[tuple[str, int]] = []
        successes: list[str] = []
        failures: list[str] = []
        rewards: list[list[Callable[[Player], None]]] = []
        maluses: list[list[Callable[[Player], None]]] = []
        for choice in choices:
            # get params
            option = choice.get("option")
            chance = choice.get("chance")
            rewards_str = choice.get("rewards")
            maluses_str = choice.get("maluses", "hp 1")
            success = (
                choice.get("success")
                + "\n\nYou gain "
                + rewards_str.replace("xp", "XP:")
                .replace("mn", f"{MONEY}:")
                .replace("ap", "Artifact pieces:")
                .replace("item", "an item")
                .replace("rn", "Renown")
                .replace("sa", "Sanity")
            )
            failure = (
                choice.get("failure")
                + "\n\nYou lose "
                + maluses_str.replace("xp", "XP:")
                .replace("mn", f"{MONEY}:")
                .replace("hp", "HP:")
                .replace("rn", "Renown")
                .replace("sa", "Sanity")
            )
            # add params to struct
            options.append((option, chance))
            successes.append(success)
            failures.append(failure)
            rewards.append(cls.__get_rewards_from_string(rewards_str))
            maluses.append(cls.__get_maluses_from_string(maluses_str))
        return cls(qte_json.get("description"), successes, failures, options, rewards, maluses)

    def __str__(self):
        return f"{self.description}\n{'\n'.join(f'{i + 1}. {s}' for i, (s, p) in enumerate(self.options))}"


class Vocation(Listable["Vocation"], base_filename="vocations"):
    """a horrible way to implement modifiers but it works"""

    MAX_LEVEL = 5

    def __init__(
        self,
        vocation_id: int,
        unique_id: int,
        name: str,
        description: str,
        modifiers: dict,
        level: int
    ) -> None:
        """
        :param vocation_id: the general vocation id, it stays the same for every level of the vocation
        :param unique_id: the actual unique id of the vocation object.
        :param name: the name of the vocation
        :param description: description of the vocation
        :param modifiers: modifiers given by the vocation, determines bonuses given
        :param level: level of the vocation, determines upgrade cost
        """
        # generic vars
        self.vocation_id = vocation_id
        self.unique_id = unique_id
        self.original_vocations: list[Vocation] = []  # contains the original vocation objects that created the current one.
        self.level = level
        self.name = name
        self.description = description
        # stats modifiers
        self.general_xp_mult: float = modifiers.get("general_xp_mult", 1.0)
        self.general_money_mult: float = modifiers.get("general_money_mult", 1.0)
        self.quest_xp_mult: float = modifiers.get("quest_xp_mult", 1.0)
        self.quest_money_mult: float = modifiers.get("quest_money_mult", 1.0)
        self.event_xp_mult: float = modifiers.get("event_xp_mult", 1.0)
        self.event_money_mult: float = modifiers.get("event_money_mult", 1.0)
        self.can_meet_players: bool = modifiers.get("can_meet_players", True)
        self.power_bonus: int = modifiers.get("power_bonus", 0)
        self.roll_bonus: int = modifiers.get("roll_bonus", 0)
        self.quest_time_multiplier: float = modifiers.get("quest_time_multiplier", 1.0)
        self.eldritch_resist: bool = modifiers.get("eldritch_resist", False)
        self.artifact_drop_bonus: int = modifiers.get("artifact_drop_bonus", 0)
        self.upgrade_cost_multiplier: float = modifiers.get("upgrade_cost_multiplier", 1.0)
        self.power_bonus_per_zone_visited: int = modifiers.get("power_bonus_per_zone_visited", 0)
        self.qte_frequency_bonus = modifiers.get("qte_frequency_bonus", 0)
        self.minigame_xp_mult = modifiers.get("minigame_xp_mult", 1.0)
        self.minigame_money_mult = modifiers.get("minigame_money_mult", 1.0)
        self.hp_mult = modifiers.get("hp_mult", 1.0)
        self.hp_bonus = modifiers.get("hp_bonus", 0)
        self.damage = Damage.load_from_json(modifiers.get("damage", {}))
        self.resist = Damage.load_from_json(modifiers.get("resist", {}))
        self.discovery_bonus: int = modifiers.get("discovery_bonus", 0)
        self.lick_wounds: bool = modifiers.get("lick_wounds", False)
        self.passive_regeneration: int = modifiers.get("passive_regeneration", 0)
        self.combat_rewards_multiplier: float = modifiers.get("combat_rewards_multiplier", 1.0)
        self.quest_fail_rewards_multiplier: float = modifiers.get("quest_fail_rewards_multiplier", 0.0)
        self.gain_money_on_player_meet: bool = modifiers.get("gain_money_on_player_meet", False)
        self.can_buy_on_a_quest: bool = modifiers.get("can_buy_on_a_quest", False)
        self.can_craft_on_a_quest: bool = modifiers.get("can_craft_on_a_quest", False)
        self.revive_chance: float = modifiers.get("revive_chance", 0.0)
        self.reroll_cost_multiplier: float = modifiers.get("reroll_cost_multiplier", 1.0)
        self.xp_on_reroll: int = modifiers.get("xp_on_reroll", 0)
        self.reroll_stats_bonus: int = modifiers.get("reroll_stats_bonus", 0)
        self.perk_rarity_bonus: int = modifiers.get("perk_rarity_bonus", 0)
        self.hunt_sanity_loss: int = modifiers.get("hunt_sanity_loss", 0)
        self.combat_frequency: int = modifiers.get("combat_frequency", 0)
        self.money_loss_on_death: float = modifiers.get("money_loss_on_death", 1.0)
        # internal vars
        self.modifiers_applied = list(modifiers.keys())  # used to build descriptions
        self.damage_modifiers_applied = {
            "damage": list(modifiers.get("damage", {}).keys()),
            "resist": list(modifiers.get("resist", {}).keys()),
        }

    def __add__(self, other: Vocation) -> Vocation:
        if other.vocation_id in self.original_vocations:
            return self
        result = Vocation(0, 0, f"{self.name} {other.name}", "", {}, 1)
        result.name = result.name.lstrip()
        result.original_vocations = self.original_vocations
        if self.unique_id != 0:
            result.original_vocations.append(self)
        if other.unique_id != 0:
            result.original_vocations.append(other)
        result.general_xp_mult = self.general_xp_mult * other.general_xp_mult
        result.general_money_mult = self.general_money_mult * other.general_money_mult
        result.quest_xp_mult = self.quest_xp_mult * other.quest_xp_mult
        result.quest_money_mult = self.quest_money_mult * other.quest_money_mult
        result.event_xp_mult = self.event_xp_mult * other.event_xp_mult
        result.event_money_mult = self.event_money_mult * other.event_money_mult
        result.can_meet_players = self.can_meet_players or other.can_meet_players
        result.power_bonus = self.power_bonus + other.power_bonus
        result.roll_bonus = self.roll_bonus + other.roll_bonus
        result.quest_time_multiplier = self.quest_time_multiplier * other.quest_time_multiplier
        result.eldritch_resist = self.eldritch_resist or other.eldritch_resist
        result.artifact_drop_bonus = self.artifact_drop_bonus + other.artifact_drop_bonus
        result.upgrade_cost_multiplier = self.upgrade_cost_multiplier * other.upgrade_cost_multiplier
        result.power_bonus_per_zone_visited = self.power_bonus_per_zone_visited + other.power_bonus_per_zone_visited
        result.qte_frequency_bonus = self.qte_frequency_bonus + other.qte_frequency_bonus
        result.minigame_xp_mult = self.minigame_xp_mult * other.minigame_xp_mult
        result.minigame_money_mult = self.minigame_money_mult * other.minigame_money_mult
        result.hp_mult = self.hp_mult * other.hp_mult
        result.hp_bonus = self.hp_bonus + other.hp_bonus
        result.damage = self.damage + other.damage
        result.resist = self.resist + other.resist
        result.discovery_bonus = self.discovery_bonus + other.discovery_bonus
        result.passive_regeneration = self.passive_regeneration + other.passive_regeneration
        result.combat_rewards_multiplier = self.combat_rewards_multiplier * other.combat_rewards_multiplier
        result.lick_wounds = self.lick_wounds or other.lick_wounds
        result.quest_fail_rewards_multiplier = self.quest_fail_rewards_multiplier + other.quest_fail_rewards_multiplier
        result.gain_money_on_player_meet = self.gain_money_on_player_meet or other.gain_money_on_player_meet
        result.can_buy_on_a_quest = self.can_buy_on_a_quest or other.can_buy_on_a_quest
        result.can_craft_on_a_quest = self.can_craft_on_a_quest or other.can_craft_on_a_quest
        result.revive_chance = self.revive_chance + other.revive_chance
        result.reroll_cost_multiplier = self.reroll_cost_multiplier * other.reroll_cost_multiplier
        result.xp_on_reroll = self.xp_on_reroll + other.xp_on_reroll
        result.reroll_stats_bonus = self.reroll_stats_bonus + other.reroll_stats_bonus
        result.perk_rarity_bonus = self.perk_rarity_bonus + other.perk_rarity_bonus
        result.hunt_sanity_loss = self.hunt_sanity_loss + other.hunt_sanity_loss
        result.combat_frequency = self.combat_frequency + other.combat_frequency
        result.money_loss_on_death = self.money_loss_on_death * other.money_loss_on_death
        # setup applied modifiers
        result.modifiers_applied = copy(self.modifiers_applied)
        for modifier in other.modifiers_applied:
            if not modifier in result.modifiers_applied:
                result.modifiers_applied.append(modifier)
        return result

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Vocation):
            return self.unique_id == other.unique_id
        return False

    def get_rank_string(self) -> str:
        return {
            1: "Novice",
            2: "Journeyman",
            3: "Expert",
            4: "Master",
            5: "Legendary"
        }.get(self.level, "")

    def get_modifier_string(self):
        string = ""
        for modifier in self.modifiers_applied:
            name = Strings.modifier_names[modifier]
            value = self.__dict__[modifier]
            if type(value) is float:
                string += f"- *{name}*: {value * 100:.0f}%\n"
            elif type(value) is bool:
                string += f"- *{name}*: {'Yes' if value else 'No'}\n"
            elif type(value) is int:
                string += f"- *{name}*: {print_bonus(value)}\n"
            elif type(value) is Damage:
                string += f"- *{name}*:\n{'\n'.join([f"  > {x.capitalize()}: {print_bonus(value.__dict__[x])}" for x in self.damage_modifiers_applied[modifier]])}\n"
        return string

    def __str__(self) -> str:
        upgrade_cost_string = f"upgrade cost: {self.get_upgrade_cost()} {MONEY}" if self.level < self.MAX_LEVEL else "+--+ Max level +--+"
        string = f"{self.get_rank_string()} *{self.name}* (id: {self.vocation_id})\n_{self.description}_\n{upgrade_cost_string}\n"
        if self.modifiers_applied:
            string += self.get_modifier_string()
        else:
            string += "- *No modifiers*"
        return string

    @classmethod
    def create_from_json(cls, cults_json: dict[str, Any]) -> Vocation:
        return cls(
            cults_json.get("vocation_id"),
            cults_json.get("id"),
            cults_json.get("name"),
            cults_json.get("description"),
            cults_json.get("modifiers"),
            cults_json.get("level")
        )

    @classmethod
    def empty(cls):
        return cls(0, 0, "", "", {}, 0)

    @classmethod
    def get_correct_vocation_tier(cls, vocation_id: int, player: Player) -> Vocation:
        for vocation in Vocation.ALL_ITEMS:
            if (vocation.vocation_id == vocation_id) and (vocation.level == player.get_vocation_level(vocation_id)):
                return vocation
        raise ValueError(f"Vocation with id {vocation_id} does not exist")

    @classmethod
    def get_correct_vocation_tier_no_player(cls, vocation_id: int, vocation_progress: dict[int, int]) -> Vocation:
        for vocation in Vocation.ALL_ITEMS[1:]:
            if (vocation.vocation_id == vocation_id) and (vocation.level == vocation_progress.get(vocation_id, 1)):
                return vocation
        raise ValueError(f"Vocation with id {vocation_id} does not exist")

    def get_upgrade_cost(self) -> int:
        value = {
            1: 50000,
            2: 250000,
            3: 500000,
            4: 1000000
        }.get(self.level, -1)
        return int(value)

    def can_upgrade(self):
        return not (self.level == self.MAX_LEVEL)

    def get_next_rank(self) -> Vocation:
        return Vocation.get(self.unique_id + 1)


class Tourney:
    def __init__(self, edition: int, tourney_start: float, duration: int) -> None:
        """
        :param edition: the tourney edition
        :param tourney_start: the tourney start time
        :param duration: the tourney duration (in seconds)
        """
        self.tourney_edition = edition
        self.tourney_start = tourney_start
        self.duration = duration

    def has_tourney_ended(self) -> bool:
        return time() >= (self.tourney_start + self.duration)

    def get_days_left(self) -> int:
        current_datetime = datetime.now()
        tourney_end_date = datetime.fromtimestamp(self.tourney_start + self.duration)
        return (tourney_end_date - current_datetime).days

    def save(self) -> None:
        save_json_to_file(
            "tourney.json",
            {
                "edition": self.tourney_edition,
                "start": self.tourney_start,
                "duration": self.duration,
            },
        )

    @classmethod
    def load_from_file(cls, filename) -> Tourney:
        tourney_json = {}
        if os.path.isfile(filename):
            tourney_json = read_json_file(filename)
        tourney = cls(
            tourney_json.get("edition", 1),
            tourney_json.get("start", time()),
            tourney_json.get("duration", 1209600),
        )
        if not tourney_json:
            tourney.save()
        return tourney


class EnemyMeta:
    """holds zone, name, description & win/loss text related to an enemy."""

    def __init__(
        self,
        meta_id: int,
        zone: Zone,
        name: str,
        description: str,
        win_text: str,
        lose_text: str,
    ) -> None:
        self.meta_id = meta_id
        self.zone = zone
        self.name = name
        self.description = description
        self.win_text = win_text
        self.lose_text = lose_text

    def __str__(self) -> str:
        return f"{self.meta_id} - *{self.name}*\nFound in: {self.zone.zone_name}\n\n_{self.description}_"

    @classmethod
    def get_empty(cls, zone: Zone) -> EnemyMeta:
        return cls(0, zone, "enemy", "description", "win_text", "lose_text")


class Enemy(CombatActor):
    """the actual enemy object"""

    stance: str

    def __init__(
        self,
        meta: EnemyMeta,
        modifiers: list[m.Modifier],
        level_modifier: int,
        name_prefix: str = ""
    ) -> None:
        self.meta = meta
        self.modifiers = modifiers
        self.level_modifier = level_modifier + random.randint(-5, 2)
        self.delay = 7 + meta.zone.extra_data.get("delay", 0) + random.randint(-5, 5)
        self.stance = self.meta.zone.extra_data.get("stance", "r")
        self.name_prefix = name_prefix
        super().__init__(1.0, 1, Stats.generate_random(0, self.get_level()))

    def get_name(self) -> str:
        return "the " + self.name_prefix + self.meta.name.rstrip().lstrip("The ")

    def get_level(self) -> int:
        value = self.meta.zone.level + self.level_modifier
        return max(1, value)

    def get_base_max_hp(self) -> int:
        return (45 + self.get_stats().vitality + self.level_modifier) * self.meta.zone.level

    def get_base_attack_damage(self) -> Damage:
        stats = self.get_stats()
        return self.meta.zone.damage_modifiers.scale(stats.strength + stats.skill + stats.attunement + self.get_level()).apply_bonus(self.meta.zone.level)

    def get_base_attack_resistance(self) -> Damage:
        stats = self.get_stats()
        return self.meta.zone.resist_modifiers.scale(stats.toughness + stats.agility + stats.mind + self.get_level()).apply_bonus(self.meta.zone.level)

    def get_entity_modifiers(self, *type_filters: int) -> list[m.Modifier]:
        if not type_filters:
            return self.modifiers
        result: list[m.Modifier] = []
        for modifier in self.modifiers:
            if modifier.TYPE in type_filters:
                result.append(modifier)
        return result

    def get_delay(self) -> int:
        value = self.delay + random.randint(-3, 3)
        return max(value, 0)

    def get_stance(self) -> str:
        return self.stance

    def __str__(self) -> str:
        return f"*{self.get_name()}*\n{self.hp}/{self.get_base_max_hp()}"


class Pet(CombatActor):

    def __init__(
            self,
            pet_id: int,
            name: str,
            enemy_meta: EnemyMeta,
            level: int,
            xp: int,
            hp_percent: float,
            stats_seed: float,
            modifiers: list[m.Modifier]
    ) -> None:
        self.id = pet_id
        self.name = name
        self.modifiers = modifiers
        self.level = max(1, level)
        self.xp = xp
        self.stats_seed = stats_seed
        self.meta = enemy_meta
        self.delay = 7 + enemy_meta.zone.extra_data.get("delay", 0) + random.randint(-5, 5)
        super().__init__(hp_percent, 0, Stats.generate_random(1, level, seed=stats_seed))

    @classmethod
    def build_from_captured_enemy(cls, owner: Player, enemy: Enemy) -> Pet:
        return cls(
            0,
            f"{owner.name}'s pet {enemy.meta.name}",
            enemy.meta,
            max(1, enemy.level_modifier + enemy.meta.zone.level),
            0,
            1.0,
            time(),
            enemy.get_entity_modifiers()
        )

    def get_name(self) -> str:
        return self.name

    def get_level(self) -> int:
        return self.level

    def get_base_max_hp(self) -> int:
        return (45 + self.get_stats().vitality) * self.level

    def get_base_attack_damage(self) -> Damage:
        stats = self.get_stats()
        return self.meta.zone.damage_modifiers.scale(stats.strength + stats.skill + stats.attunement + self.get_level()).apply_bonus(self.meta.zone.level)

    def get_base_attack_resistance(self) -> Damage:
        stats = self.get_stats()
        return self.meta.zone.resist_modifiers.scale(stats.toughness + stats.agility + stats.mind + self.get_level()).apply_bonus(self.meta.zone.level)

    def get_entity_modifiers(self, *type_filters: int) -> list[m.Modifier]:
        if not type_filters:
            return self.modifiers
        result: list[m.Modifier] = []
        for modifier in self.modifiers:
            if modifier.TYPE in type_filters:
                result.append(modifier)
        return result

    def get_required_xp(self) -> int:
        lv = self.level
        return (100 * (lv * lv)) + (1000 * lv)

    def level_up(self, owner: Player or None) -> None:
        req_xp = self.get_required_xp()
        while self.xp >= req_xp:
            self.level += 1
            self.xp -= req_xp
            req_xp = self.get_required_xp()
            if owner is not None:
                InternalEventBus().notify(Event("pet level up", owner, {"level": self.level, "name": self.name}))

    def add_xp(self, amount: float, owner: Player or None = None) -> int:
        """adds xp to the player & returns how much was actually added to the player"""
        self.xp += int(amount)
        if self.xp >= self.get_required_xp():
            self.level_up(owner)
        return int(amount)

    def get_level_progress(self):
        return (self.xp / self.get_required_xp()) * 100

    def get_delay(self) -> int:
        value = self.delay + random.randint(-3, 3)
        return max(value, 0)

    def get_value(self) -> int:
        return self.level * 500 * (1 + len(self.get_entity_modifiers()))

    def heal(self):
        self.hp_percent = 1.0
        self.hp = self.get_max_hp()

    def __str__(self) -> str:
        max_hp = self.get_max_hp()
        string = f"*{self.get_name()}* ({self.meta.name.rstrip()}) | lv. {self.level}\n`{self.xp}/{self.get_required_xp()} xp ({self.get_level_progress():.2f}%)`\n"
        string += f"HP:  `{int(max_hp * self.hp_percent)}/{max_hp}`"
        string += f"\n\n_{self.meta.description}_"
        string += f"\n\n*Stats*:\n{self.get_stats()}"
        string += f"\n\n*Damage ({self.get_base_attack_damage().get_total_damage()})*:\n{str(self.get_base_attack_damage())}"
        string += f"\n\n*Resist ({self.get_base_attack_resistance().get_total_damage()})*:\n{str(self.get_base_attack_resistance())}"
        modifiers = self.get_modifiers()
        if not modifiers:
            return string
        return string + f"\n\n*Perks*:\n\n{'\n\n'.join(str(x) for x in modifiers)}"


class Auction:
    DURATION = timedelta(weeks=1)

    def __init__(
        self,
        auction_id: int,
        auctioneer: Player,
        item: Equipment,
        best_bidder: Player | None,
        best_bid: int,
        creation_date: datetime,
    ) -> None:
        self.auction_id = auction_id
        self.auctioneer = auctioneer
        self.item = item
        self.best_bidder = best_bidder
        self.best_bid = best_bid
        self.creation_date = creation_date

    def place_bid(self, bidder: Player, bid: int) -> bool:
        if bid <= self.best_bid:
            return False
        self.best_bid = bid
        self.best_bidder = bidder
        return True

    def is_expired(self) -> bool:
        return datetime.now() > (self.creation_date + self.DURATION)

    def _get_expires_string(self) -> str:
        if self.is_expired():
            return "Expired!"
        time_left = (self.creation_date + self.DURATION) - datetime.now()
        hours_left = int(time_left.seconds / 3600)
        return f"Expires in {time_left.days} days & {hours_left} hours"

    def verbose_string(self) -> str:
        return f"Seller: {self.auctioneer.name}\nBest bid: {self.best_bid} ({self.best_bidder.name if self.best_bidder else 'Starting Bid'})\n\nItem:\n{self.item}"

    def __str__(self) -> str:
        return f"(id: {self.auction_id}) - {Strings.get_item_icon(self.item.equipment_type.slot)} *{self.item.name}* (lv. {self.item.level})\n_Best bid: {self.best_bid}\n{self._get_expires_string()}_"

    @classmethod
    def create_default(
        cls, auctioneer: Player, item: Equipment, starting_bid: int
    ) -> Auction:
        return cls(0, auctioneer, item, None, starting_bid, datetime.now())


class Notification:

    def __init__(
            self,
            target: Player,
            text: str,
            notification_type: str = "notification",
    ) -> None:
        self.target = target
        self.text = text
        self.notification_type = notification_type

