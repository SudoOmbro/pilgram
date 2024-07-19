import logging
import math
import os
import random
import time
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Callable, Union, List, Type

import numpy as np

from pilgram.equipment import ConsumableItem, Equipment, EquipmentType
from pilgram.flags import HexedFlag, CursedFlag, AlloyGlitchFlag1, AlloyGlitchFlag2, AlloyGlitchFlag3, LuckFlag1, \
    LuckFlag2, Flag
from pilgram.globals import ContentMeta, GlobalSettings
from pilgram.listables import Listable
from pilgram.combat_classes import CombatActor, Modifier, Damage, CombatActions
from pilgram.utils import read_update_interval, FuncWithParam, save_json_to_file, read_json_file, print_bonus
from pilgram.strings import MONEY, Strings

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


BASE_QUEST_DURATION: timedelta = read_update_interval(GlobalSettings.get("quest.base duration"))
DURATION_PER_ZONE_LEVEL: timedelta = read_update_interval(GlobalSettings.get("quest.duration per level"))
DURATION_PER_QUEST_NUMBER: timedelta = read_update_interval(GlobalSettings.get("quest.duration per number"))
RANDOM_DURATION: timedelta = read_update_interval(GlobalSettings.get("quest.random duration"))

QTE_CACHE: Dict[int, "QuickTimeEvent"] = {}  # runtime cache that contains all users + quick time events pairs


class Zone:
    """ contains info about a zone. Zone 0 should be the town to reuse the zone event system """

    def __init__(
            self,
            zone_id: int,
            zone_name: str,
            level: int,
            zone_description: str,
            damage_modifiers: Damage,
            resist_modifiers: Damage,
            extra_data: dict
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
        return self.zone_id == other.zone_id

    def __str__(self):
        return f"*{self.zone_name}* | lv. {self.level}\n\n{self.zone_description}"

    def __hash__(self):
        return hash(self.zone_id)

    @classmethod
    def get_empty(cls) -> "Zone":
        return Zone(0, "", 1, "", Damage.get_empty(), Damage.get_empty(), {})


TOWN_ZONE: Zone = Zone(
    0,
    ContentMeta.get("world.city.name"),
    1,
    ContentMeta.get("world.city.description"),
    Damage.get_empty(),
    Damage.get_empty(),
    {}
)


class Quest:
    """ contains info about a human written or AI generated quest """
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
    ):
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

    def get_value_to_beat(self, player: "Player") -> int:
        sqrt_multiplier = (1.2 * self.zone.level) - ((player.level + player.gear_level) / 2)
        if sqrt_multiplier < 1:
            sqrt_multiplier = 1
        num_multiplier = 4 / self.zone.level
        offset = 6 + self.zone.level - player.level
        if offset < 0:
            offset = 0
        value_to_beat = int((sqrt_multiplier * math.sqrt(num_multiplier * self.number)) + offset)
        if value_to_beat > 19:
            value_to_beat = 19
        return value_to_beat

    def finish_quest(self, player: "Player") -> Tuple[bool, int, int]:  # win/lose, roll, roll to beat
        """ return true if the player has successfully finished the quest """
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

    def get_rewards(self, player: "Player") -> Tuple[int, int]:
        """ return the amount of xp & money the completion of the quest rewards """
        multiplier = (self.zone.level + self.number) + (player.guild.level if player.guild else 0)
        rand = random.randint(1, 50)
        return (
            int(((self.BASE_XP_REWARD * multiplier) + rand) * player.cult.quest_xp_mult),
            int(((self.BASE_MONEY_REWARD * multiplier) + rand) * player.cult.quest_money_mult)
        )  # XP, Money

    def get_duration(self, player: "Player") -> timedelta:
        return (
            BASE_QUEST_DURATION + (
                (DURATION_PER_ZONE_LEVEL * self.zone.level) +
                (DURATION_PER_QUEST_NUMBER * self.number) +
                (random.randint(0, self.zone.level) * RANDOM_DURATION)
            ) * player.cult.quest_time_multiplier
        )

    def get_prestige(self) -> int:
        return self.zone.level + self.number

    def __str__(self):
        return f"*{self.number + 1} - {self.name}*\n\n{self.description}"

    def __hash__(self):
        return hash(self.quest_id)

    @classmethod
    def get_empty(cls) -> "Quest":
        return Quest(0, Zone.get_empty(), 0, "", "", "", "")

    @classmethod
    def create_default(cls, zone: Zone, num: int, name: str, description: str, success: str, failure: str) -> "Quest":
        return Quest(0, zone, num, name, description, success, failure)


class Progress:
    """ stores the player quest progress for each zone """

    def __init__(self, zone_progress: Dict[int, int]):
        """
        :param zone_progress:
            dictionary that contains the player quest progress in the zone, stored like this: {zone: progress, ...}
        """
        self.zone_progress = zone_progress

    def get_zone_progress(self, zone: Zone) -> int:
        return self.zone_progress.get(zone.zone_id - 1, 0)

    def set_zone_progress(self, zone: Zone, progress: int):
        self.zone_progress[zone.zone_id - 1] = progress

    def __str__(self):
        return "\n".join(f"zone {zone}: progress {progress}" for zone, progress in self.zone_progress)

    def __repr__(self):
        return str(self.zone_progress)

    @classmethod
    def get_from_encoded_data(cls, progress_data: Any, parsing_function: Callable[[Any], Dict[int, int]]) -> "Progress":
        """
        :param progress_data:
            The data that contains the player quest progress.
            How it is stored on the database is independent of the implementation here.
        :param parsing_function:
            The function used to parse progress_data, must return the correct data format
        """
        zone_progress: Dict[int, int] = parsing_function(progress_data)
        return cls(zone_progress)


class SpellError(Exception):

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class Spell:

    def __init__(
            self,
            name: str,
            description: str,
            required_power: int,
            required_args: int,
            function: Callable[["Player", List[str]], str]
    ):
        self.name = name
        self.description = description
        self.required_power = required_power
        self.required_args = required_args
        self.function = function

    def can_cast(self, caster: "Player") -> bool:
        return caster.get_spell_charge() >= self.required_power

    def check_args(self, args: Tuple[str, ...]):
        if self.required_args == 0:
            return True
        return len(args) == self.required_args

    def cast(self, caster: "Player", args: Tuple[str, ...]) -> str:
        try:
            result = self.function(caster, args)
            caster.last_cast = datetime.now()
            return f"You cast {self.name}, " + result
        except SpellError as e:
            return e.message


class Player(CombatActor):
    """ contains all information about a player """
    MAXIMUM_POWER: int = 100
    MAX_HOME_LEVEL = 10

    def __init__(
            self,
            player_id: int,
            name: str,
            description: str,
            guild: Union["Guild", None],
            level: int,
            xp: int,
            money: int,
            progress: Progress,
            gear_level: int,
            home_level: int,
            artifact_pieces: int,
            last_cast: datetime,
            artifacts: List["Artifact"],
            flags: np.uint32,
            renown: int,
            cult: "Cult",
            satchel: List[ConsumableItem],
            equipped_items: Dict[int, Equipment],
            hp_percent: float,
            stance: str,
            completed_quests: int,
            last_guild_switch: datetime
    ):
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
        :param cult: the player's cult
        :param satchel: the player's satchel which holds consumable items
        :param equipped_items: the player's equipped items
        :param hp_percent: the player's hp percentage
        :param stance: the player's stance
        :param completed_quests: the player's completed quests
        :param last_guild_switch: The time in which the player last changed guild
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
        self.cult = cult
        self.satchel = satchel
        self.equipped_items = equipped_items
        super().__init__(hp_percent)
        self.stance = stance
        self.completed_quests = completed_quests
        self.last_guild_switch = last_guild_switch

    def get_name(self) -> str:
        return self.name

    def get_level(self) -> int:
        return self.level

    def get_required_xp(self) -> int:
        lv = self.level
        value = (100 * (lv * lv)) + (1000 * lv)
        return int(value * self.cult.upgrade_cost_multiplier)

    def get_gear_upgrade_required_money(self) -> int:
        lv = self.gear_level
        value = (50 * (lv * lv)) + (1000 * lv)
        return int(value * self.cult.upgrade_cost_multiplier)

    def get_home_upgrade_required_money(self) -> int:
        lv = self.home_level + 1
        value = (200 * (lv * lv)) + (600 * lv)
        return int(value * self.cult.upgrade_cost_multiplier)

    def can_upgrade_gear(self) -> bool:
        return True

    def can_upgrade_home(self) -> bool:
        return self.MAX_HOME_LEVEL > self.home_level

    def upgrade_gear(self):
        self.money -= self.get_gear_upgrade_required_money()
        self.gear_level += 1

    def upgrade_home(self):
        self.money -= self.get_home_upgrade_required_money()
        self.home_level += 1

    def level_up(self):
        req_xp = self.get_required_xp()
        while self.xp >= req_xp:
            self.level += 1
            self.xp -= req_xp
            req_xp = self.get_required_xp()

    def add_xp(self, amount: int) -> bool:
        """ adds xp to the player and returns true if the player leveled up """
        amount *= self.cult.general_xp_mult
        if self.cult.xp_mult_per_player_in_cult != 1.0:
            amount *= self.cult.xp_mult_per_player_in_cult ** self.cult.number_of_members
        self.xp += int(amount)
        if self.xp >= self.get_required_xp():
            self.level_up()
            return True
        return False

    def add_money(self, amount: int) -> int:
        """ adds money to the player & returns how much was actually added to the player """
        amount *= self.cult.general_money_mult
        if self.cult.money_mult_per_player_in_cult != 1.0:
            amount *= self.cult.money_mult_per_player_in_cult ** self.cult.number_of_members
        for flag in (AlloyGlitchFlag1, AlloyGlitchFlag2, AlloyGlitchFlag3):
            if flag.is_set(self.flags):
                amount = int(amount * 1.5)
                self.flags = flag.unset(self.flags)
        amount = int(amount)
        self.money += amount
        return amount

    def add_artifact_pieces(self, amount: int):
        self.artifact_pieces += amount

    def roll(self, dice_faces: int) -> int:
        """ roll a dice and apply all advantages / disadvantages """
        roll = random.randint(1, dice_faces) + self.cult.roll_bonus
        for modifier, flag in zip((-1, -1, 1, 2), (HexedFlag, CursedFlag, LuckFlag1, LuckFlag2)):
            if flag.is_set(self.flags):
                roll += modifier
                self.flags = flag.unset(self.flags)
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
        for zone, progress in self.progress.zone_progress.items():
            result += progress
        return result

    def print_username(self, mode: str = "telegram") -> str:
        if mode == "telegram":
            return f"[{self.name}](tg://user?id={self.player_id})"
        return self.name

    def get_max_charge(self) -> int:
        if self.cult.power_bonus == -100:
            return 0
        max_charge = (len(self.artifacts) * 10) + self.cult.power_bonus
        if self.cult.power_bonus_per_zone_visited:
            max_charge += len(self.progress.zone_progress) * self.cult.power_bonus_per_zone_visited
        if max_charge >= self.MAXIMUM_POWER:
            max_charge = self.MAXIMUM_POWER
        return max_charge

    def get_spell_charge(self) -> int:
        """
        returns spell charge of the player, calculated as the amount of time passed since the last spell cast.
        max charge = 10 * number of artifacts; 1 day = max charge; max charge possible = 100
        """
        max_charge = self.get_max_charge()
        charge = int(((datetime.now() - self.last_cast).total_seconds() / 86400) * max_charge)
        if charge > max_charge:
            return max_charge
        return charge

    def set_flag(self, flag: Type[Flag]):
        self.flags = flag.set(self.flags)

    def unset_flag(self, flag: Type[Flag]):
        self.flags = flag.unset(self.flags)

    def get_inventory_size(self) -> int:
        return 10 + self.home_level * 4

    def get_max_number_of_artifacts(self) -> int:
        return self.home_level * 2

    # combat stats

    def get_base_max_hp(self) -> int:
        return (((self.level + self.gear_level) * 10) * self.cult.hp_mult) + self.cult.hp_bonus

    def get_base_attack_damage(self) -> Damage:
        base_damage = self.cult.damage.scale(self.level)
        for _, item in self.equipped_items.items():
            base_damage += item.damage
        return base_damage

    def get_base_attack_resistance(self) -> Damage:
        base_resistance = self.cult.damage.scale(self.level)
        for _, item in self.equipped_items.items():
            base_resistance += item.resist
        return base_resistance

    def get_entity_modifiers(self, *type_filters: int) -> List["Modifier"]:
        result = []
        for _, item in self.equipped_items.items():
            result.extend(item.get_modifiers(type_filters))
        return result

    def __clamp_hp(self, max_hp: int):
        if self.hp > max_hp:
            self.hp = max_hp

    def use_consumable(self, position_in_satchel: int, add_you: bool = True) -> str:
        if position_in_satchel > len(self.satchel):
            return Strings.satchel_position_out_of_range.format(num=len(self.satchel))
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
        self.flags = item.buff_flag.set(self.flags)
        text = Strings.used_item.format(verb=item.verb, item=item.name)
        if add_you:
            return "You " + text
        return text

    def use_random_consumable(self, add_you: bool = True) -> str:
        pos = random.randint(0, len(self.satchel) - 1)
        return self.use_consumable(pos, add_you=add_you)

    def equip_item(self, item: Equipment):
        self.equipped_items[item.equipment_type.slot] = item

    def get_stance(self):
        return self.stance

    STANCE_POOL = {
        "b": (CombatActions.attack, CombatActions.attack, CombatActions.dodge, CombatActions.dodge, CombatActions.parry, CombatActions.use_consumable),
        "s": (CombatActions.attack, CombatActions.dodge, CombatActions.dodge, CombatActions.parry, CombatActions.use_consumable),
        "r": (CombatActions.attack, CombatActions.attack, CombatActions.attack, CombatActions.parry, CombatActions.dodge)
    }

    def choose_action(self, opponent: "CombatActor") -> int:
        selected_pool = self.STANCE_POOL.get(self.stance, (CombatActions.attack, CombatActions.dodge))
        if self.cult.lick_wounds:
            selected_pool += (CombatActions.lick_wounds, )
        return random.choice(selected_pool)

    # utility

    def __str__(self):
        max_hp = self.get_max_hp()
        guild = f" | {self.guild.name} (lv. {self.guild.level})" if self.guild else ""
        string = f"{self.print_username()} | lv. {self.level}{guild}\n_{self.xp} / {self.get_required_xp()} xp_\n"
        string += f"HP:  `{int(max_hp * self.hp_percent)}/{max_hp}`\n"
        string += f"{self.money} *{MONEY}*\n*Home* lv. {self.home_level}, *Gear* lv. {self.gear_level}\n"
        string += f"Stance: {Strings.stances[self.stance][0]}\nCult: {self.cult.name}\n_Renown: {self.renown}_"
        if (self.get_max_charge() > 0) or (len(self.artifacts) > 0):
            string += f"\n*Eldritch power*: {self.get_spell_charge()} / {self.get_max_charge()}"
            string += f"\n\n_{self.description}\n\nQuests: {self.get_number_of_tried_quests()}\nArtifact pieces: {self.artifact_pieces}_"
            string += f"\n\nArtifacts ({len(self.artifacts)}/{self.get_max_number_of_artifacts()}):\n" + ("\n".join(f"{a.artifact_id}. *{a.name}*" for a in self.artifacts)) if len(
                self.artifacts) > 0 else "\n\nNo artifacts yet."
        else:
            string += f"\n\n_{self.description}\n\nQuests: {self.get_number_of_tried_quests()} tried, {self.completed_quests} completed.\nArtifact pieces: {self.artifact_pieces}_"
        if self.equipped_items:
            string += f"\n\nEquipped items:\n{'\n'.join(f"{Strings.slots[slot]} - *{item.name}*" for slot, item in self.equipped_items.items())}"
        return string

    def __repr__(self):
        return str(self.__dict__)

    def __hash__(self):
        return hash(self.player_id)

    def __eq__(self, other):
        return (self.player_id == other.player_id) if other is not None else False

    @classmethod
    def create_default(cls, player_id: int, name: str, description: str) -> "Player":
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
            Cult.LIST[0],
            [],
            {},
            1.0,
            "b",
            0,
            datetime.now() - timedelta(days=1),
        )


class Guild:
    """ Player created guilds that other players can join. Players get bonus xp & money from quests when in guilds """
    MAX_LEVEL = ContentMeta.get("guilds.max_level")
    PLAYERS_PER_LEVEL = ContentMeta.get("guilds.players_per_level")

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
            tax: int
    ):
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

    def can_add_member(self, current_members: int) -> bool:
        return current_members < self.level * self.PLAYERS_PER_LEVEL

    def can_upgrade(self) -> bool:
        return self.MAX_LEVEL > self.level

    def get_upgrade_required_money(self) -> int:
        lv = self.level
        return (10000 * (lv * lv)) + (1000 * lv)

    def upgrade(self):
        self.founder.money -= self.get_upgrade_required_money()
        self.level += 1

    def __eq__(self, other):
        return self.guild_id == other.guild_id

    def __str__(self):
        return f"*{self.name}* | lv. {self.level}\nPrestige: {self.prestige}\nFounder: {self.founder.print_username() if self.founder else '???'}\n_Since {self.creation_date.strftime("%d %b %Y")}_\n\n{self.description}\n\n_Tax: {self.tax}%\nTourney score: {self.tourney_score}_"

    def __hash__(self):
        return hash(self.guild_id)

    @classmethod
    def create_default(cls, founder: Player, name: str, description: str) -> "Guild":
        return Guild(
            0,
            name,
            1,
            description,
            founder,
            datetime.now(),
            0,
            0,
            5
        )

    @classmethod
    def print_members(cls, members: List[Tuple[int, str, int]]):
        return "\n".join(f"{name} | lv. {level}" for _, name, level in members)


class ZoneEvent:
    """
        Events that happen during the day every X hours of which the player is notified.
        Players get bonus xp & money from events depending on their home level.
    """

    def __init__(self, event_id: int, zone: Union[Zone, None], event_text: str):
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

    def __val(self, player: Player):
        """ get base event reward value """
        if player.level >= (self.zone_level - 3):
            return ((self.base_value + self.zone_level + player.home_level) * random.randint(1, 10)) + self.bonus
        return ((self.base_value + player.home_level) * random.randint(1, 10)) + self.bonus

    def get_rewards(self, player: Player) -> Tuple[int, int]:
        """ returns xp & money rewards for the event. Influenced by player home level """
        return int(self.__val(player) * player.cult.event_xp_mult), int(self.__val(player) * player.cult.event_money_mult)

    def __str__(self):
        return self.event_text

    def __hash__(self):
        return hash(self.event_id)

    @classmethod
    def get_empty(cls) -> "ZoneEvent":
        return ZoneEvent(0, Zone.get_empty(), "")

    @classmethod
    def create_default(cls, zone: Zone, event_text: str) -> "ZoneEvent":
        return ZoneEvent(0, zone, event_text)


class AdventureContainer:
    """ Utility class to help manage player updates """

    def __init__(self, player: Player, quest: Union[Quest, None], finish_time: Union[datetime, None]):
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

    def is_quest_finished(self) -> bool:
        """ returns whether the current quest is finished by checking the finish time """
        return datetime.now() > self.finish_time

    def is_on_a_quest(self) -> bool:
        """ returns whether the player is on a quest """
        return self.quest is not None

    def player_id(self):
        """ non-verbose way to get player id """
        return self.player.player_id

    def quest_id(self):
        """ non-verbose way to get quest id """
        return self.quest.quest_id if self.quest else None

    def zone(self) -> Union[Zone, None]:
        """ returns Zone if player is on a quest, None if player is in town """
        return self.quest.zone if self.quest else None

    def __str__(self):
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

    def __hash__(self):
        return hash(self.player_id())


class Artifact:
    """
    rare & unique items player can acquire by combining fragments they find while questing.
    Each artifact should be unique, owned by a single player.
    """

    def __init__(self, artifact_id: int, name: str, description: str, owner: Union[Player, None], owned_by_you: bool = False):
        self.artifact_id = artifact_id
        self.name = name
        self.description = description
        if owned_by_you:
            self.owner = "you"
        elif owner:
            self.owner = owner.name
        else:
            self.owner = None

    def __str__(self):
        if self.owner:
            return f"n. {self.artifact_id} - *{self.name}*\nOwned by {self.owner}\n\n_{self.description}_\n\n"
        return f"n. {self.artifact_id} - *{self.name}*\n\n_{self.description}_"

    @classmethod
    def get_empty(cls) -> "Artifact":
        return Artifact(0, "", "", None)


class QuickTimeEvent(Listable, meta_name="quick time events"):
    LIST: List["QuickTimeEvent"]

    def __init__(
            self,
            description: str,
            successes: List[str],
            failures: List[str],
            options: List[Tuple[str, int]],
            rewards: List[List[Callable[[Player], None]]]
    ):
        """
        :param description: description of the quick time event
        :param successes: descriptions of the quick time event successful completions
        :param failures: descriptions of the quick time event failures
        :param options: the options to give the player
        :param rewards: the functions used to give rewards to the players
        """
        assert len(options) == len(rewards) == len(successes) == len(failures)
        self.description = description
        self.successes = successes
        self.failures = failures
        self.options = options
        self.rewards = rewards

    def __get_reward(self, index: int) -> Callable[[Player], None]:
        reward_functions = self.rewards[index]

        def execute_funcs(player: Player):
            for func in reward_functions:
                func(player)

        return execute_funcs

    def resolve(self, chosen_option: int) -> Tuple[Union[Callable[[Player], None], None], str]:
        """ return if the qte succeeded and the string associated """
        option = self.options[chosen_option]
        roll = random.randint(1, 100)
        if roll <= option[1]:
            return self.__get_reward(chosen_option), self.successes[chosen_option]
        return None, self.failures[chosen_option]

    @staticmethod
    def _add_money(player: Player, amount: int):
        player.add_money(amount)

    @staticmethod
    def _add_xp(player: Player, amount: int):
        player.add_xp(amount)

    @staticmethod
    def _add_artifact_pieces(player: Player, amount: int):
        player.add_artifact_pieces(amount)

    @staticmethod
    def _add_item(player: Player, rarity_str: str):
        if not rarity_str:
            rarity = random.randint(0, 3)
        else:
            rarity = {
                f"({Strings.rarities[0]})": 0,
                f"({Strings.rarities[1]})": 1,
                f"({Strings.rarities[2]})": 2,
                f"({Strings.rarities[3]})": 3
            }.get(rarity_str, 0)
        return Equipment.generate(player.level, EquipmentType.get_random(), rarity)

    @classmethod
    def __get_rewards_from_string(cls, reward_string: str) -> List[FuncWithParam]:
        split_reward_str = reward_string.split(", ")
        funcs_list: List[FuncWithParam] = []
        for reward_func_components in split_reward_str:
            components = reward_func_components.split(" ")
            if components[0] == "xp":
                funcs_list.append(FuncWithParam(cls._add_xp, int(components[1])))
            elif components[0] == "mn":
                funcs_list.append(FuncWithParam(cls._add_money, int(components[1])))
            elif components[0] == "ap":
                funcs_list.append(FuncWithParam(cls._add_artifact_pieces, int(components[1])))
            elif components[0] == "item":
                funcs_list.append(FuncWithParam(cls._add_item, components[1]))
        return funcs_list

    @classmethod
    def create_from_json(cls, qte_json: Dict[str, str]) -> "QuickTimeEvent":
        # get object
        choices = qte_json.get("choices")
        # init empty lists
        options: List[Tuple[str, int]] = []
        successes: List[str] = []
        failures: List[str] = []
        rewards: List[List[Callable[[Player], None]]] = []
        for choice in choices:
            # get params
            option = choice.get("option")
            chance = choice.get("chance")
            rewards_str = choice.get("rewards")
            success = choice.get("success") + "\n\nYou gain " + rewards_str.replace("xp", "XP:").replace("mn", "MN:").replace("ap", "Artifact pieces:").replace("item", "an item")
            failure = choice.get("failure")
            # add params to struct
            options.append((option, chance))
            successes.append(success)
            failures.append(failure)
            rewards.append(cls.__get_rewards_from_string(rewards_str))
        return cls(
            qte_json.get("description"),
            successes,
            failures,
            options,
            rewards
        )

    def __str__(self):
        return f"{self.description}\n{'\n'.join(f'{i+1}. {s} ({p}% chance)' for i, (s, p) in enumerate(self.options))}"


class Cult(Listable, meta_name="cults"):
    """ a horrible way to implement modifiers but it works """

    def __init__(
            self,
            faction_id: int,
            name: str,
            description: str,
            modifiers: dict
    ):
        # generic vars
        self.faction_id = faction_id
        self.name = name
        self.description = description
        # stats modifiers
        self.general_xp_mult: float = modifiers.get("general_xp_mult", 1)
        self.general_money_mult: float = modifiers.get("general_money_mult", 1)
        self.quest_xp_mult: float = modifiers.get("quest_xp_mult", 1)
        self.quest_money_mult: float = modifiers.get("quest_money_mult", 1)
        self.event_xp_mult: float = modifiers.get("event_xp_mult", 1)
        self.event_money_mult: float = modifiers.get("event_money_mult", 1)
        self.can_meet_players: bool = modifiers.get("can_meet_players", True)
        self.power_bonus: int = modifiers.get("power_bonus", 0)
        self.roll_bonus: int = modifiers.get("roll_bonus", 0)
        self.quest_time_multiplier: float = modifiers.get("quest_time_multiplier", 1.0)
        self.eldritch_resist: bool = modifiers.get("eldritch_resist", False)
        self.artifact_drop_bonus: int = modifiers.get("artifact_drop_bonus", 0)
        self.upgrade_cost_multiplier: float = modifiers.get("upgrade_cost_multiplier", 1.0)
        self.xp_mult_per_player_in_cult: float = modifiers.get("xp_mult_per_player_in_cult", 1.0)
        self.money_mult_per_player_in_cult: float = modifiers.get("money_mult_per_player_in_cult", 1.0)
        self.randomizer_delay: int = modifiers.get("randomizer_delay", 0)
        self.stats_to_randomize: Dict[str, list] = modifiers.get("stats_to_randomize", {})
        self.power_bonus_per_zone_visited: int = modifiers.get("power_bonus_per_zone_visited", 0)
        self.qte_frequency_bonus = modifiers.get("qte_frequency_bonus", 0)
        self.minigame_xp_mult = modifiers.get("minigame_xp_mult", 1)
        self.minigame_money_mult = modifiers.get("minigame_money_mult", 1)
        self.hp_mult = modifiers.get("hp_mult", 1)
        self.hp_bonus = modifiers.get("hp_bonus", 0)
        self.damage = Damage.load_from_json(modifiers.get("damage", {}))
        self.resistance = Damage.load_from_json(modifiers.get("resistance", {}))
        self.discovery_bonus: int = modifiers.get("discovery_bonus", 0)
        self.lick_wounds: bool = modifiers.get("discovery_bonus", False)
        # internal vars
        self.modifiers_applied = list(modifiers.keys())  # used to build descriptions
        if self.stats_to_randomize:
            self.modifiers_applied.extend(list(self.stats_to_randomize.keys()))
        self.damage_modifiers_applied = {
            "damage": list(modifiers.get("damage", {}).keys()),
            "resistance": list(modifiers.get("resistance", {}).keys())
        }
        self.last_update: datetime = datetime.now() - timedelta(days=2)
        self.number_of_members: int = 0  # has to be set every hour by the timed updates manager

    def can_randomize(self) -> bool:
        return (self.randomizer_delay != 0) and self.stats_to_randomize and ((datetime.now() - self.last_update) >= timedelta(hours=self.randomizer_delay))

    def randomize(self):
        for stat_name, choices in self.stats_to_randomize.items():
            self.__dict__[stat_name] = random.choice(choices)

    def __eq__(self, other):
        return self.faction_id == other.faction_id

    def __str__(self):
        string = f"{self.faction_id} - *{self.name}* ({self.number_of_members} members)\n_{self.description}_\n"
        if self.modifiers_applied:
            for modifier in self.modifiers_applied:
                name = Strings.modifier_names[modifier]
                value = self.__dict__[modifier]
                if modifier == "randomizer_delay":
                    string += f"- *{name.format(hr=value)}*:\n"
                    continue
                if type(value) is float:
                    string += f"- *{name}*: {value * 100:.0f}%\n"
                elif type(value) is bool:
                    string += f"- *{name}*: {'Yes' if value else 'No'}\n"
                elif type(value) is int:
                    string += f"- *{name}*: {print_bonus(value)}\n"
                elif type(value) is Damage:
                    string += f"- *{name}*:\n{'\n'.join([f"  > {x.capitalize()}: {print_bonus(value.__dict__[x])}" for x in self.damage_modifiers_applied[modifier]])}\n"
        else:
            string += "- *No modifiers*"
        return string

    @classmethod
    def create_from_json(cls, cults_json: Dict[str, Any]) -> "Cult":
        return cls(
            cults_json.get("id"),
            cults_json.get("name"),
            cults_json.get("description"),
            cults_json.get("modifiers"),
        )

    @classmethod
    def update_number_of_members(cls, members_number: List[Tuple[int, int]]):
        for cult_id, number in members_number:
            cls.LIST[cult_id].number_of_members = number


class Tourney:

    def __init__(self, edition: int, tourney_start: float, duration: int):
        """
        :param edition: the tourney edition
        :param tourney_start: the tourney start time
        :param duration: the tourney duration (in seconds)
        """
        self.tourney_edition = edition
        self.tourney_start = tourney_start
        self.duration = duration

    def has_tourney_ended(self) -> bool:
        return time.time() >= (self.tourney_start + self.duration)

    def get_days_left(self) -> int:
        current_datetime = datetime.now()
        tourney_end_date = datetime.fromtimestamp(self.tourney_start + self.duration)
        return (tourney_end_date - current_datetime).days

    def save(self):
        save_json_to_file(
            "tourney.json",
            {
                "edition": self.tourney_edition,
                "start": self.tourney_start,
                "duration": self.duration
            }
        )

    @classmethod
    def load_from_file(cls, filename) -> "Tourney":
        tourney_json = {}
        if os.path.isfile(filename):
            tourney_json = read_json_file(filename)
        tourney = cls(
            tourney_json.get("edition", 1),
            tourney_json.get("start", time.time()),
            tourney_json.get("duration", 1209600)
        )
        if not tourney_json:
            tourney.save()
        return tourney


class EnemyMeta:
    """ holds zone, name, description & win/loss text related to an enemy. """

    def __init__(self, meta_id: int, zone: Zone, name: str, description: str, win_text: str, lose_text: str):
        self.meta_id = meta_id
        self.zone = zone
        self.name = name
        self.description = description
        self.win_text = win_text
        self.lose_text = lose_text

    def __str__(self):
        return f"{self.meta_id} - *{self.name}*\nFound in: {self.zone.zone_name}\n\n_{self.description}_"

    @classmethod
    def get_empty(cls, zone: Zone) -> "EnemyMeta":
        return cls(0, zone, "enemy", "description", "win_text", "lose_text")


class Enemy(CombatActor):
    """ the actual enemy object """

    def __init__(self, meta: EnemyMeta, modifiers: List[Modifier], hp_modifier: int):
        self.meta = meta
        self.modifiers = modifiers
        self.hp_modifier = hp_modifier + random.randint(-2, 4)
        self.delay = meta.zone.extra_data.get("delay", 0) + random.randint(-5, 5)
        self.stance = self.meta.zone.extra_data.get("stance", "r")
        super().__init__(self.get_max_hp())

    def get_name(self) -> str:
        return "the " + self.meta.name

    def get_level(self) -> int:
        return self.meta.zone.level

    def get_base_max_hp(self) -> int:
        return (20 + self.hp_modifier) * self.meta.zone.level

    def get_base_attack_damage(self) -> Damage:
        return self.meta.zone.damage_modifiers

    def get_base_attack_resistance(self) -> Damage:
        return self.meta.zone.resist_modifiers

    def get_entity_modifiers(self, *type_filters: int) -> List["Modifier"]:
        result = []
        for modifier in self.modifiers:
            if modifier.TYPE in type_filters:
                result.append(modifier)
        return result

    def get_delay(self) -> int:
        return self.delay

    def get_stance(self):
        return self.stance

    def choose_action(self, opponent: "CombatActor") -> int:
        return random.choice((CombatActions.attack, CombatActions.dodge, CombatActions.lick_wounds))
