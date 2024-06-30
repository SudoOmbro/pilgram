import logging
import math
import random
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Callable, Union, List

import numpy as np

from pilgram.flags import HexedFlag, CursedFlag, AlloyGlitchFlag1, AlloyGlitchFlag2, AlloyGlitchFlag3, LuckFlag1, \
    LuckFlag2
from pilgram.globals import ContentMeta, GlobalSettings
from pilgram.utils import read_update_interval, FuncWithParam
from pilgram.strings import MONEY


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


BASE_QUEST_DURATION: timedelta = read_update_interval(GlobalSettings.get("quest.base duration"))
DURATION_PER_ZONE_LEVEL: timedelta = read_update_interval(GlobalSettings.get("quest.duration per level"))
DURATION_PER_QUEST_NUMBER: timedelta = read_update_interval(GlobalSettings.get("quest.duration per number"))
RANDOM_DURATION: timedelta = read_update_interval(GlobalSettings.get("quest.random duration"))


class Zone:
    """ contains info about a zone. Zone 0 should be the town to reuse the zone event system """

    def __init__(self, zone_id: int, zone_name: str, level: int, zone_description: str):
        """
        :param zone_id: zone id
        :param zone_name: zone name
        :param level: zone level, control the minimum level a player is required to be to accept quests in the zone
        :param zone_description: zone description
        """
        assert level > 0
        self.zone_id = zone_id
        self.zone_name = zone_name
        self.level = level
        self.zone_description = zone_description

    def __eq__(self, other):
        return self.zone_id == other.zone_id

    def __str__(self):
        return f"*{self.zone_name}* | lv. {self.level}\n\n{self.zone_description}"

    def __hash__(self):
        return hash(self.zone_id)

    @classmethod
    def get_empty(cls) -> "Zone":
        return Zone(0, "", 1, "")


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

    def finish_quest(self, player: "Player") -> bool:
        """ return true if the player has successfully finished the quest """
        roll = player.roll(20)
        if roll == 1:
            log.info(f"{player.name} rolled a critical failure on quest {self.name}")
            return False  # you can still get a critical failure
        if roll == 20:
            log.info(f"{player.name} rolled a critical success on quest {self.name}")
            return True  # you can also get a critical success
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
        log.info(f"{self.name}: to beat: {value_to_beat}, {player.name} rolled: {roll}")
        return roll >= value_to_beat

    def get_rewards(self, player: "Player") -> Tuple[int, int]:
        """ return the amount of xp & money the completion of the quest rewards """
        multiplier = (self.zone.level + self.number) + (player.guild.level if player.guild else 0)
        rand = random.randint(1, 50)
        return (self.BASE_XP_REWARD * multiplier) + rand, (self.BASE_MONEY_REWARD * multiplier) + rand  # XP, Money

    def get_duration(self) -> timedelta:
        return (BASE_QUEST_DURATION +
                (DURATION_PER_ZONE_LEVEL * self.zone.level) +
                (DURATION_PER_QUEST_NUMBER * self.number) +
                (random.randint(0, self.zone.level) * RANDOM_DURATION))

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


class Player:
    """ contains all information about a player """
    MAXIMUM_POWER: int = 100

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
            renown: int
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

    def get_required_xp(self) -> int:
        lv = self.level
        return (100 * (lv * lv)) + (1000 * lv)

    def get_gear_upgrade_required_money(self) -> int:
        lv = self.gear_level
        return (50 * (lv * lv)) + (1000 * lv)

    def get_home_upgrade_required_money(self) -> int:
        lv = self.home_level + 1
        return (100 * (lv * lv)) + (5000 * lv)

    def can_upgrade_gear(self) -> bool:
        return self.money >= self.get_gear_upgrade_required_money()

    def can_upgrade_home(self) -> bool:
        return self.money >= self.get_home_upgrade_required_money()

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
        self.xp += amount
        if self.xp >= self.get_required_xp():
            self.level_up()
            return True
        return False

    def add_money(self, amount: int) -> int:
        """ adds money to the player & returns how much was actually added to the player """
        for flag in (AlloyGlitchFlag1, AlloyGlitchFlag2, AlloyGlitchFlag3):
            if flag.is_set(self.flags):
                amount = int(amount * 1.5)
                self.flags = flag.unset(self.flags)
        self.money += amount
        return amount

    def add_artifact_pieces(self, amount: int):
        self.artifact_pieces += amount

    def roll(self, dice_faces: int) -> int:
        """ roll a dice and apply all advantages / disadvantages """
        roll = random.randint(1, dice_faces)
        for modifier, flag in zip((-1, -1, 1, 2), (HexedFlag, CursedFlag, LuckFlag1, LuckFlag2)):
            if flag.is_set(self.flags):
                roll += modifier
                self.flags = flag.unset(self.flags)
        if roll < 1:
            return 1
        return roll

    def get_number_of_completed_quests(self) -> int:
        result: int = 0
        for zone, progress in self.progress.zone_progress.items():
            result += progress
        return result

    def print_username(self, mode: str = "telegram") -> str:
        if mode == "telegram":
            return f"[{self.name}](tg://user?id={self.player_id})"
        return self.name

    def get_max_charge(self) -> int:
        max_charge = len(self.artifacts) * 10
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

    def __str__(self):
        guild = f" | {self.guild.name} (lv. {self.guild.level})" if self.guild else ""
        string = f"{self.print_username()} | lv. {self.level}{guild}\n_{self.xp}/{self.get_required_xp()} xp_\n"
        string += f"{self.money} *{MONEY}*\n*Home* lv. {self.home_level}, *Gear* lv. {self.gear_level}\n"
        string += f"_Renown: {self.renown}_"
        if self.artifacts:
            string += f"\n*Eldritch power*: {self.get_spell_charge()} / {self.get_max_charge()}"
            string += f"\n\n_{self.description}\n\nQuests completed: {self.get_number_of_completed_quests()}\nArtifact pieces: {self.artifact_pieces}_"
            string += f"\n\nArtifacts:\n" + "\n".join(f"{a.artifact_id}. *{a.name}*" for a in self.artifacts)
        else:
            string += f"\n\n_{self.description}\n\nQuests completed: {self.get_number_of_completed_quests()}\nArtifact pieces: {self.artifact_pieces}_"
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
            0
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
        return (self.level < self.MAX_LEVEL) and (self.founder.money >= self.get_upgrade_required_money())

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
        if player.level >= (self.zone_level - 3):
            return ((self.base_value + self.zone_level + player.home_level) * random.randint(1, 10)) + self.bonus
        return ((self.base_value + player.home_level) * random.randint(1, 10)) + self.bonus

    def get_rewards(self, player: Player) -> Tuple[int, int]:
        """ returns xp & money rewards for the event. Influenced by player home level """
        return self.__val(player), self.__val(player)

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


def _add_money(player: Player, amount: int):
    player.add_money(amount)


def _add_xp(player: Player, amount: int):
    player.add_xp(amount)


def _add_artifact_pieces(player: Player, amount: int):
    player.add_artifact_pieces(amount)


class QuickTimeEvent:
    LIST: List["QuickTimeEvent"] = []

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
        assert len(options) == len(rewards)
        self.description = description
        self.successes = successes
        self.failures = failures
        self.options = options
        self.rewards = rewards
        self.LIST.append(self)

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

    @classmethod
    def create_from_json(cls, qte_json: Dict[str, str]) -> "QuickTimeEvent":
        # generate options
        options: List[Tuple[str, int]] = []
        split_options: List[str] = qte_json.get("options").split(" | ")
        for option in split_options:
            components = option.split(" ")
            options.append((components[0].replace("_", " "), int(components[1])))
        # generate rewards
        rewards: List[List[Callable[[Player], None]]] = []
        split_rewards: List[str] = qte_json.get("rewards").split(" | ")
        for reward_str in split_rewards:
            split_reward_str = reward_str.split(", ")
            funcs_list: List[Callable[[Player], None]] = []
            for reward_func_components in split_reward_str:
                components = reward_func_components.split(" ")
                if components[0] == "xp":
                    funcs_list.append(FuncWithParam(_add_xp, int(components[1])))
                elif components[0] == "mn":
                    funcs_list.append(FuncWithParam(_add_money, int(components[1])))
                elif components[0] == "ap":
                    funcs_list.append(FuncWithParam(_add_artifact_pieces, int(components[1])))
            rewards.append(funcs_list)
        # return complete object
        return QuickTimeEvent(
            qte_json.get("description"),
            qte_json.get("successes").split(" | "),
            qte_json.get("failures").split(" | "),
            options,
            rewards
        )

    def __str__(self):
        return f"{self.description}\n{'\n'.join(f'{i+1}. {s} ({p}% chance)' for i, (s, p) in enumerate(self.options))}"


__qte_jsons = ContentMeta.get("quick time events")
for qte_json in __qte_jsons:
    QuickTimeEvent.LIST.append(QuickTimeEvent.create_from_json(qte_json))


QTE_CACHE: Dict[int, QuickTimeEvent] = {}  # runtime cache that contains all users + quick time events pairs
TOWN_ZONE: Zone = Zone(0, ContentMeta.get("world.city.name"), 1, ContentMeta.get("world.city.description"))
