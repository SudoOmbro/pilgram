import random
from typing import Tuple, Dict


class Zone:
    """ contains info about a zone. Zone 0 should be the town to reuse the event system """

    def __init__(self, zone_id: int, zone_name: str, level: int, zone_description: str):
        """
        :param zone_id: zone id
        :param zone_name: zone name
        :param level: zone level, control the minimum level a player is required to be to accept quests in the zone
        :param zone_description: zone description
        """
        self.zone_id = zone_id
        self.zone_name = zone_name
        self.level = level
        self.zone_description = zone_description


class Quest:
    """ contains info about a human written or AI generated quest """

    def __init__(
            self,
            quest_id: int,
            zone: Zone,
            number: int,
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
        self.description = description
        self.success_text = success_text
        self.failure_text = failure_text

    def finish_quest(self, player: "Player") -> bool:
        """ return true if the player has successfully finished the quest """
        # TODO quest success has to be influenced by player & zone level
        return True


class Progress:
    """ stores the player quest progress for each zone """

    def __init__(self, progress_tuple: Tuple[Tuple[int, int]]):
        """
        :param progress_tuple: tuple of the player quest progress
        """
        self.zone_progress: Dict[int, int] = {}
        for zp in progress_tuple:
            self.zone_progress[zp[0]] = zp[1]

    def get_zone_progress(self, zone: Zone) -> int:
        return self.zone_progress[zone.zone_id] if zone in self.zone_progress else 0

    def __str__(self):
        return "\n".join(f"zone {zone}: progress {progress}" for zone, progress in self.zone_progress)

    def __repr__(self):
        return str(self.zone_progress)


class Player:
    """ contains all information about a player """

    def __init__(
            self,
            player_id: int,
            name: str,
            description: str,
            guild: "Guild",
            level: int,
            xp: int,
            money: int,
            progress: Progress,
    ):
        """
        :param player_id (int): unique id of the player
        :param name (str): name of the player
        :param description (str): user written description of the player
        :param guild: the guild this player belongs to
        :param level (int): current player level, potentially unlimited
        :param xp (int): current xp of the player
        :param money (int): current money of the player
        :param progress (Progress): contains progress object, which tracks the player progress in each zone
        """
        self.player_id = player_id
        self.name = name
        self.description = description
        self.guild = guild
        self.progress = progress
        self.money = money
        self.level = level
        self.xp = xp
        self.required_xp: int = self.get_new_required_xp()

    def get_new_required_xp(self) -> int:
        return self.level * 150

    def level_up(self):
        self.level += 1
        self.xp -= self.required_xp
        self.required_xp = self.get_new_required_xp()

    def add_xp(self, amount: int) -> bool:
        """ adds xp to the player and returns true if the player leveled up """
        self.xp += amount
        if self.xp >= self.required_xp:
            self.level_up()
            return True
        return False

    def __str__(self):
        return f"{self.name} | lv. {self.level} | {self.guild}\n\n{self.description}"

    def __repr__(self):
        return str(self.__dict__)


class Guild:

    def __init__(self, guild_id: int, name: str, description: str, founder: Player):
        """
        :param guild_id: unique id of the guild
        :param name: player given name of the guild
        :param description: player given description of the guild
        :param founder: the player who found the guild
        """
        self.guild_id = guild_id
        self.name = name
        self.description = description
        self.founder = founder

    def __str__(self):
        return  f"*{self.name}*\nfounder: _{self.founder}_\n\n{self.description}"


class ZoneEvent:
    """ Events that happen during the day every X hours of which the player is notified """

    def __init__(self, event_id: int, zone: Zone, event_text: str):
        """
        :param event_id: unique id of the event
        :param zone: the zone that this event happens in
        :param event_text: a short text describing the event
        """
        self.event_id = event_id
        self.zone = zone
        self.event_text = event_text
        self.xp_value = (zone.level + 1) * random.randint(1, 10)
        self.money_value = (zone.level + 1) * random.randint(1, 10)

    def __str__(self):
        return f"{self.event_text}\n\nxp gained: {self.xp_value}\nmoney gained: {self.money_value}"
