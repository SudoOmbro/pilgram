from abc import ABC
from typing import List

from pilgram.classes import Player, Zone, Quest, Guild


class PilgramDatabase(ABC):

    # players ----

    def get_player_data(self, player_id) -> Player:
        raise NotImplementedError

    def update_player_data(self, player: Player):
        """ this should also update the player progress, implement however you see fit """
        raise NotImplementedError

    def add_player(self, player: Player):
        raise NotImplementedError

    # guilds ---

    def get_guild(self, guild_id: int) -> Guild:
        raise NotImplementedError

    def update_guild(self, guild: Guild):
        raise NotImplementedError

    def add_guild(self, guild: Guild):
        raise NotImplementedError

    # zones ----

    def get_all_zones(self) -> List[Zone]:
        """ this should return a list of all zones, convenient since we are not going to have thousands of zones """
        raise NotImplementedError

    def get_zone(self, zone_id: int) -> Zone:
        raise NotImplementedError

    def update_zone(self, zone: Zone):
        """ only used by the admin on the server via CLI to update an existing zone """
        raise NotImplementedError

    def add_zone(self, zone: Zone):
        """ used by the generator or manually by the admin via CLI on the server to add a new zone """
        raise NotImplementedError

    # quests ---

    def get_next_quest(self, zone: Zone, player: Player) -> Quest:
        player_zone_progress = player.progress.get_zone_progress(zone)
        return self.get_quest(zone, player_zone_progress + 1)

    def get_quest(self, zone: Zone, quest_number: int) -> Quest:
        raise NotImplementedError

    def update_quest(self, zone: Zone, quest: Quest):
        """ only used by the admin on the server via CLI to update an existing quest """
        raise NotImplementedError

    def add_quest(self, zone: Zone, quest: Quest):
        """ used by the generator or manually by the admin via CLI on the server to add a new quest """
        raise NotImplementedError
