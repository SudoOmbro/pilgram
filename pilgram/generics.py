from abc import ABC
from typing import List

from pilgram.classes import Player, Zone, Quest, Guild, ZoneEvent


class NotFoundException(Exception):
    pass


class PilgramDatabase(ABC):

    # players ----

    def get_player_data(self, player_id) -> Player:
        raise NotImplementedError

    def update_player_data(self, player: Player):
        """ this should also update the player progress, implement however you see fit """
        raise NotImplementedError

    def add_player(self, player: Player):
        """ add a new player to the database. Happens at the end of character creation """
        raise NotImplementedError

    # guilds ---

    def get_guild(self, guild_id: int) -> Guild:
        """ get a guild given its id """
        raise NotImplementedError

    def update_guild(self, guild: Guild):
        """ update guild information. Players will trigger this function """
        raise NotImplementedError

    def add_guild(self, guild: Guild):
        """ create a new guild. Check if a player already has a guild before letting them create a new guild """
        raise NotImplementedError

    # zones ----

    def get_zone(self, zone_id: int) -> Zone:
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

    def get_random_zone_event(self, zone: Zone) -> ZoneEvent:
        """ get a random zone event given a zone """
        raise NotImplementedError

    def add_zone_event(self, event: ZoneEvent):
        """ add a zone event, generally used by the generator or manually by the admin """
        raise NotImplementedError

    def update_zone_event(self, event: ZoneEvent):
        """ update a zone event, generally used by the generator or manually by the admin """
        raise NotImplementedError

    # quests ----

    def get_next_quest(self, zone: Zone, player: Player) -> Quest:
        """ returns the next quest the player has to do in the specified zone. """
        player_zone_progress = player.progress.get_zone_progress(zone)
        return self.get_quest_from_number(zone, player_zone_progress)

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

    def get_quest_count(self, zone: Zone) -> int:
        """ used to determine the quest number at creation time """
        raise NotImplementedError
