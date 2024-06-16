import logging
from abc import ABC
from datetime import timedelta, datetime
from typing import List, Tuple, Union, Any

from pilgram.classes import Player, Zone, Quest, Guild, ZoneEvent, AdventureContainer


log = logging.getLogger(__name__)


class AlreadyExists(Exception):
    pass


class PilgramDatabase(ABC):

    def acquire(self) -> "PilgramDatabase":
        """ generic method to get self, used to make the pilgram package implementation agnostic """
        raise NotImplementedError

    # players ----

    def get_player_data(self, player_id) -> Player:
        """
        returns a complete player object

        :raises KeyError: if player does not exist
        """
        raise NotImplementedError

    def get_player_id_from_name(self, player_name) -> int:
        raise NotImplementedError

    def get_player_from_name(self, player_name: str) -> Union[Player, None]:
        try:
            return self.get_player_data(self.get_player_id_from_name(player_name))
        except KeyError:
            return None

    def update_player_data(self, player: Player):
        """ this should also update the player progress, implement however you see fit """
        raise NotImplementedError

    def add_player(self, player: Player):
        """
        add a new player to the database. Happens at the end of character creation.
        Should also create the quest progress row related to the player.

        :raises AlreadyExists: if player already exists
        """
        raise NotImplementedError

    # guilds ---

    def get_guild(self, guild_id: int, calling_player_id: Union[int, None] = None) -> Guild:
        """
        get a guild given its id

        :raises KeyError: if the guild does not exist
        """
        raise NotImplementedError

    def get_guild_id_from_name(self, guild_name: str) -> int:
        """ get a guild id given its name """
        raise NotImplementedError

    def get_guild_id_from_founder(self, founder: Player) -> int:
        """ get a guild id given its founder """
        raise NotImplementedError

    def get_guild_from_name(self, guild_name: str) -> Union[Guild, None]:
        try:
            return self.get_guild(self.get_guild_id_from_name(guild_name))
        except KeyError:
            return None

    def get_owned_guild(self, player: Player) -> Union[Guild, None]:
        """ get a guild owned by a player """
        try:
            guild = self.get_guild(self.get_guild_id_from_founder(player), calling_player_id=player.player_id)
            guild.founder = player
            player.guild = guild
            return guild
        except KeyError:
            return None

    def get_guild_members_data(self, guild: Guild) -> List[Tuple[str, int]]:
        """
        return a list of all members name and level given a guild.
        We avoid creating the entire player object 'cause we don't need it.
        """
        raise NotImplementedError

    def get_guild_members_number(self, guild: Guild) -> int:
        """ get amount of members in a guild. """
        raise NotImplementedError

    def update_guild(self, guild: Guild):
        """ update guild information. Players will trigger this function """
        raise NotImplementedError

    def add_guild(self, guild: Guild):
        """
        create a new guild. Check if a player already has a guild before letting them create a new guild

        :raises AlreadyExists: if guild already exists
        """
        raise NotImplementedError

    def rank_top_guilds(self) -> List[Tuple[str, int]]:
        """ get top 20 guild names + prestige based on rank """
        raise NotImplementedError

    # zones ----

    def get_zone(self, zone_id: int) -> Zone:
        """ get a specific zone given its id, used basically everywhere """
        raise NotImplementedError

    def get_all_zones(self) -> List[Zone]:
        """ used by players when selecting quests. Players can always see all zones, even if their level is too low """
        raise NotImplementedError

    def update_zone(self, zone: Zone):
        """ only used by the admin on the server via CLI to update an existing zone """
        raise NotImplementedError

    def add_zone(self, zone: Zone):
        """ used by the generator or manually by the admin via CLI on the server to add a new zone """
        raise NotImplementedError

    # Zone events ----

    def get_zone_event(self, event_id: int) -> ZoneEvent:
        """ get a specific zone event given its id """
        raise NotImplementedError

    def get_random_zone_event(self, zone: Union[Zone, None]) -> ZoneEvent:
        """ get a random zone event given a zone. If zone is None then it's implied to be the town """
        raise NotImplementedError

    def add_zone_event(self, event: ZoneEvent):
        """ add a single zone event, generally used by the generator or manually by the admin """
        raise NotImplementedError

    def add_zone_events(self, events: List[ZoneEvent]):
        """ adds an entire list of zone events to the database, much more efficient for multiple values """
        raise NotImplementedError

    def update_zone_event(self, event: ZoneEvent):
        """ update a zone event, generally used by the generator or manually by the admin """
        raise NotImplementedError

    # quests ----

    def get_next_quest(self, zone: Zone, player: Player) -> Quest:
        """ returns the next quest the player has to do in the specified zone. """
        return self.get_quest_from_number(zone, player.progress.get_zone_progress(zone))

    def get_quest(self, quest_id: int) -> Quest:
        """ get a quest given a zone and the number of the quest """
        raise NotImplementedError

    def get_quest_from_number(self, zone: Zone, quest_number: int) -> Quest:
        """ get a quest given a zone and the number of the quest """
        raise NotImplementedError

    def update_quest(self, quest: Quest):
        """ only used by the admin on the server via CLI to update an existing quest """
        raise NotImplementedError

    def add_quest(self, quest: Quest):
        """ used by the generator or manually by the admin via CLI on the server to add a new quest """
        raise NotImplementedError

    def add_quests(self, quests: List[Quest]):
        """ adds more than one quest to the database, much more efficient for multiple values """
        raise NotImplementedError

    def get_quests_counts(self) -> List[int]:
        """ returns a list of quest amounts per zone, position in the list is determined by zone id """
        raise NotImplementedError

    # in progress quests management ----

    def get_player_adventure_container(self, player: Player) -> AdventureContainer:
        """ returns a player's adventure container. """
        raise NotImplementedError

    def get_player_current_quest(self, player: Player) -> Union[Quest, None]:
        """
        returns the quest the player is on if the player is currently on a quest.

        :raises KeyError: if no quest progress is found for the player.
        """
        raise NotImplementedError

    def is_player_on_a_quest(self, player: Player) -> bool:
        """ returns True if the player is currently on a quest. This will actually be called by players """
        try:
            return self.get_player_current_quest(player) is not None
        except KeyError as e:
            log.error(e)
            return False

    def get_all_pending_updates(self, delta: timedelta) -> List[AdventureContainer]:
        """ get all quest progress that was last updated timedelta hours ago or more """
        raise NotImplementedError

    def update_quest_progress(self, adventure_container: AdventureContainer, last_update: Union[datetime, None] = None):
        """ update quest player progress, either complete quests or just change last update """
        raise NotImplementedError


class PilgramGenerator(ABC):

    def generate_quests(self, zone: Zone, quest_data: Any) -> List[Quest]:
        raise NotImplementedError

    def generate_zone_events(self, zone: Zone) -> List[ZoneEvent]:
        raise NotImplementedError


class PilgramNotifier(ABC):

    def notify(self, player: Player, text: str):
        raise NotImplementedError
