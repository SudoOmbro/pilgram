from __future__ import annotations

import logging
from abc import ABC
from datetime import datetime, timedelta
from typing import Any

from pilgram.classes import (
    AdventureContainer,
    Artifact,
    Auction,
    EnemyMeta,
    Guild,
    Player,
    Quest,
    Tourney,
    Zone,
    ZoneEvent, Notification, Anomaly, Pet,
)
from pilgram.equipment import ConsumableItem, Equipment, EquipmentType
from pilgram.flags import Raiding
from pilgram.strings import Strings

log = logging.getLogger(__name__)


class AlreadyExists(Exception):
    pass


class NoArtifactsError(Exception):
    pass


class PilgramDatabase(ABC):
    def acquire(self) -> PilgramDatabase:
        """generic method to get self, used to make the pilgram package implementation agnostic"""
        raise NotImplementedError

    # players ----------------------------------

    def get_player_data(self, player_id) -> Player:
        """
        returns a complete player object

        :raises KeyError: if player does not exist
        """
        raise NotImplementedError

    def get_random_player_data(self) -> Player:
        """ returns a random complete player object """
        raise NotImplementedError

    def get_player_id_from_name(self, player_name) -> int:
        raise NotImplementedError

    def get_player_ids_from_name_case_insensitive(self, player_name: str) -> list[int]:
        """get player ids with matching names (case insensitive)"""
        raise NotImplementedError

    def get_player_from_name(self, player_name: str) -> Player | None:
        try:
            return self.get_player_data(self.get_player_id_from_name(player_name))
        except KeyError:
            return None

    def update_player_data(self, player: Player) -> None:
        """this should also update the player progress, implement however you see fit"""
        raise NotImplementedError

    def add_player(self, player: Player) -> None:
        """
        add a new player to the database. Happens at the end of character creation.
        Should also create the quest progress row related to the player.

        :raises AlreadyExists: if player already exists
        """
        raise NotImplementedError

    def rank_top_players(self) -> list[tuple[str, int]]:
        """get top 20 guild names + prestige based on rank"""
        raise NotImplementedError

    # guilds ----------------------------------

    def get_guild(self, guild_id: int, calling_player_id: int | None = None) -> Guild:
        """
        get a guild given its id

        :raises KeyError: if the guild does not exist
        """
        raise NotImplementedError

    def get_guild_id_from_name(self, guild_name: str) -> int:
        """get a guild id given its name"""
        raise NotImplementedError

    def get_guild_ids_from_name_case_insensitive(self, guild_name: str) -> list[int]:
        """get guild ids with matching guild names (case insensitive)"""
        raise NotImplementedError

    def get_guild_id_from_founder(self, founder: Player) -> int:
        """get a guild id given its founder"""
        raise NotImplementedError

    def get_guild_from_name(self, guild_name: str) -> Guild | None:
        try:
            return self.get_guild(self.get_guild_id_from_name(guild_name))
        except KeyError:
            return None

    def get_owned_guild(self, player: Player) -> Guild | None:
        """get a guild owned by a player"""
        try:
            guild = self.get_guild(
                self.get_guild_id_from_founder(player),
                calling_player_id=player.player_id,
            )
            if guild.deleted:
                return None
            guild.founder = player
            player.guild = guild
            return guild
        except KeyError:
            return None

    def get_guild_members_data(
        self, guild: Guild
    ) -> list[tuple[int, str, int]]:  # id, name, level
        """
        return a list of all members name and level given a guild.
        We avoid creating the entire player object 'cause we don't need it.
        """
        raise NotImplementedError

    def get_bank_data(self, guild: Guild) -> str:
        """
        return a string with the bank's logs
        """
        raise NotImplementedError

    def get_guild_members_number(self, guild: Guild) -> int:
        """get amount of members in a guild."""
        raise NotImplementedError

    def update_guild(self, guild: Guild) -> None:
        """update guild information. Players will trigger this function"""
        raise NotImplementedError

    def add_guild(self, guild: Guild) -> int:
        """
        create a new guild. Check if a player already has a guild before letting them create a new guild.
        Returns the id of the new guild.

        :raises AlreadyExists: if guild already exists
        """
        raise NotImplementedError

    def rank_top_guilds(self) -> list[tuple[str, int]]:
        """get top 20 guild names + prestige based on rank"""
        raise NotImplementedError

    def get_top_n_guilds_by_score(self, n: int) -> list[Guild]:
        """get top n guilds based on score"""
        raise NotImplementedError

    def reset_all_guild_scores(self) -> None:
        """reset the tourney scores of all guilds"""
        raise NotImplementedError

    def delete_guild(self, guild: Guild) -> None:
        """ delete the guild with the given id """
        raise NotImplementedError

    def get_avaible_players_for_raid(self, guild: Guild) -> list[Player]:
        guild_members_data = self.get_guild_members_data(guild)
        available_members: list[Player] = []
        for member_id, _, _ in guild_members_data:
            member = self.get_player_data(member_id)
            if not self.is_player_on_a_quest(member):
                available_members.append(member)
        return available_members

    def get_raid_participants(self, guild: Guild) -> list[Player]:
        guild_members_data = self.get_guild_members_data(guild)
        participants: list[Player] = []
        for member_id, _, _ in guild_members_data:
            member = self.get_player_data(member_id)
            if Raiding.is_set(member.flags):
                participants.append(member)
        return participants

    # zones ----------------------------------

    def get_zone(self, zone_id: int) -> Zone:
        """get a specific zone given its id, used basically everywhere"""
        raise NotImplementedError

    def get_all_zones(self) -> list[Zone]:
        """used by players when selecting quests. Players can always see all zones, even if their level is too low"""
        raise NotImplementedError

    def update_zone(self, zone: Zone) -> None:
        """only used by the admin on the server via CLI to update an existing zone"""
        raise NotImplementedError

    def add_zone(self, zone: Zone) -> None:
        """used by the generator or manually by the admin via CLI on the server to add a new zone"""
        raise NotImplementedError

    # Zone events ----------------------------------

    def get_zone_event(self, event_id: int) -> ZoneEvent:
        """get a specific zone event given its id"""
        raise NotImplementedError

    def get_random_zone_event(self, zone: Zone | None) -> ZoneEvent:
        """get a random zone event given a zone. If zone is None then it's implied to be the town"""
        raise NotImplementedError

    def add_zone_event(self, event: ZoneEvent) -> None:
        """add a single zone event, generally used by the generator or manually by the admin"""
        raise NotImplementedError

    def add_zone_events(self, events: list[ZoneEvent]) -> None:
        """adds an entire list of zone events to the database, much more efficient for multiple values"""
        raise NotImplementedError

    def update_zone_event(self, event: ZoneEvent) -> None:
        """update a zone event, generally used by the generator or manually by the admin"""
        raise NotImplementedError

    # quests ----------------------------------

    def get_next_quest(self, zone: Zone, player: Player) -> Quest:
        """returns the next quest the player has to do in the specified zone."""
        return self.get_quest_from_number(zone, player.progress.get_zone_progress(zone))

    def get_quest_internal(self, quest_id: int) -> Quest:
        """get a quest given a zone and the number of the quest"""
        raise NotImplementedError

    def get_quest(self, quest_id: int) -> Quest:
        """get a quest given a zone and the number of the quest. If the zone id is negative return a raid"""
        if quest_id >= 0:
            return self.get_quest_internal(quest_id)
        zone = self.get_zone(-quest_id)
        return Quest(
            quest_id,
            zone,
            -quest_id,
            f"Raid: {zone.zone_name}",
            Strings.raid_description.format(zone=zone.zone_name),
            "",
            "",
            is_raid=True
        )

    def get_quest_from_number(self, zone: Zone, quest_number: int) -> Quest:
        """get a quest given a zone and the number of the quest"""
        raise NotImplementedError

    def update_quest(self, quest: Quest) -> None:
        """only used by the admin on the server via CLI to update an existing quest"""
        raise NotImplementedError

    def add_quest(self, quest: Quest) -> None:
        """used by the generator or manually by the admin via CLI on the server to add a new quest"""
        raise NotImplementedError

    def add_quests(self, quests: list[Quest]) -> None:
        """adds more than one quest to the database, much more efficient for multiple values"""
        raise NotImplementedError

    def get_quests_counts(self) -> list[int]:
        """returns a list of quest amounts per zone, position in the list is determined by zone id"""
        raise NotImplementedError

    # in progress quests management ----------------------------------

    def get_player_adventure_container(self, player: Player) -> AdventureContainer:
        """returns a player's adventure container."""
        raise NotImplementedError

    def get_player_current_quest(self, player: Player) -> Quest | None:
        """
        returns the quest the player is on if the player is currently on a quest.

        :raises KeyError: if no quest progress is found for the player.
        """
        raise NotImplementedError

    def is_player_on_a_quest(self, player: Player) -> bool:
        """returns True if the player is currently on a quest. This will actually be called by players"""
        try:
            return self.get_player_current_quest(player) is not None
        except KeyError as e:
            log.error(e)
            return False

    def get_all_pending_updates(self, delta: timedelta) -> list[AdventureContainer]:
        """get all quest progress that was last updated timedelta hours ago or more"""
        raise NotImplementedError

    def update_quest_progress(
        self,
        adventure_container: AdventureContainer,
        last_update: datetime | None = None,
    ) -> None:
        """update quest player progress, either complete quests or just change last update"""
        raise NotImplementedError

    # artifacts ----------------------------------

    def get_artifact(self, artifact_id: int) -> Artifact:
        """returns an artifact given its id"""
        raise NotImplementedError

    def get_player_artifacts(self, player_id: int) -> list[Artifact]:
        """
        get all artifacts owned by the specified player

        :raises NoArtifactsError if player has no artifacts, KeyError if player does not exist
        """
        raise NotImplementedError

    def get_unclaimed_artifact(self) -> Artifact:
        """get the first unclaimed artifact in the db"""
        raise NotImplementedError

    def get_number_of_unclaimed_artifacts(self) -> int:
        """
        get the number of unclaimed artifacts in the db, useful for the generator to see if it has to generate new ones
        """
        raise NotImplementedError

    def add_artifact(self, artifacts: Artifact) -> None:
        """add the given artifact to the database"""
        raise NotImplementedError

    def add_artifacts(self, artifacts: list[Artifact]) -> None:
        """add the given list of artifacts to the database"""
        raise NotImplementedError

    def update_artifact(self, artifacts: Artifact, owner: Player | None) -> None:
        """save the given artifact to the database (used when assigning an owner basically)"""
        raise NotImplementedError

    # cults ----------------------------------

    def get_cults_members_number(
        self,
    ) -> list[tuple[int, int]]:  # cult id, number of members
        """get the number of members for each cult"""
        raise NotImplementedError

    # tourney ----------------------------------

    def get_tourney(self) -> Tourney:
        """get the biweekly guild tourney object"""
        raise NotImplementedError

    def update_tourney(self, tourney: Tourney) -> None:
        """update the tourney object"""
        raise NotImplementedError

    # enemy meta ----------------------------------

    def get_enemy_meta(self, enemy_meta_id: int) -> EnemyMeta:
        """get a specific enemy meta (for updating most likely)"""
        raise NotImplementedError

    def get_all_zone_enemies(self, zone: Zone) -> list[EnemyMeta]:
        """get all enemies from given a zone"""
        raise NotImplementedError

    def get_random_enemy_meta(self, zone: Zone) -> EnemyMeta:
        """get a random enemy meta from the specified zone"""
        raise NotImplementedError

    def update_enemy_meta(self, enemy_meta: EnemyMeta) -> None:
        """update the enemy meta on the database (mainly used by admin CLI)"""
        raise NotImplementedError

    def add_enemy_meta(self, enemy_meta: EnemyMeta) -> None:
        """add a new AI-generated (or human made) enemy meta to the database"""
        raise NotImplementedError

    # items ----------------------------------

    def get_item(self, item_id: int) -> Equipment:
        """return a specific item given its id"""
        raise NotImplementedError

    def get_player_items(self, player_id: int) -> list[Equipment]:
        """get all items owned by the specified player"""
        raise NotImplementedError

    def update_item(self, item: Equipment, owner: Player) -> None:
        """update an item on the database"""
        raise NotImplementedError

    def add_item(self, item: Equipment, owner: Player) -> int:
        """ add a new item on the database & returns the id """
        raise NotImplementedError

    def delete_item(self, item: Equipment) -> None:
        """delete a specific item on the database"""
        raise NotImplementedError

    # shops ----------------------------------

    def get_market_items(self) -> list[ConsumableItem]:
        """gets daily consumable items to buy"""
        raise NotImplementedError

    def get_smithy_items(self) -> list[EquipmentType]:
        """gets daily equipment to buy"""
        raise NotImplementedError

    # auctions ----------------------------------

    def get_auctions(self) -> list[Auction]:
        """gets all auctions"""
        raise NotImplementedError

    def get_auction_from_id(self, auction_id: int) -> Auction:
        """get the auction that has the given id"""
        raise NotImplementedError

    def get_auction_id_from_item(self, item: Equipment) -> int:
        """get the auction for the given item"""
        raise NotImplementedError

    def get_auction_from_item(self, item: Equipment) -> Auction | None:
        try:
            auction_id = self.get_auction_id_from_item(item)
            return self.get_auction_from_id(auction_id)
        except KeyError:
            return None

    def get_player_auctions(self, player: Player) -> list[Auction]:
        """gets auctions started by the given player"""
        raise NotImplementedError

    def get_expired_auctions(self) -> list[Auction]:
        """gets all expired auctions"""
        raise NotImplementedError

    def update_auction(self, auction: Auction) -> None:
        """update the auction db row"""
        raise NotImplementedError

    def add_auction(self, auction: Auction) -> None:
        """creates a new auction"""
        raise NotImplementedError

    def delete_auction(self, auction: Auction) -> None:
        """removes the auction db row"""
        raise NotImplementedError

    # notifications ----------------------------------

    def get_pending_notifications(self) -> list[Notification]:
        """get all pending notifications, clear the pending notifications list"""
        raise NotImplementedError

    def add_notification(self, notification: Notification) -> None:
        """add a new notification"""
        raise NotImplementedError

    def create_and_add_notification(
            self,
            player: Player,
            text: str,
            notification_type: str = "notification"
    ) -> None:
        self.add_notification(
            Notification(
                player,
                text,
                notification_type=notification_type)
        )

    # duels ----------------------------------

    def add_duel_invite(self, sender: Player, target: Player):
        """Add a duel invite"""
        raise NotImplementedError

    def delete_duel_invite(self, sender: Player, target: Player):
        """Delete a duel invite"""
        raise NotImplementedError

    def duel_invite_exists(self, sender: Player, target: Player) -> bool:
        """returns whether the specified duel invite exists"""
        raise NotImplementedError

    # anomalies ----------------------------------

    def get_current_anomaly(self) -> Anomaly:
        """ returns the current active anomaly """
        raise NotImplementedError

    def update_anomaly(self, anomaly: Anomaly) -> None:
        """ sets the current anomaly as the active anomaly """
        raise NotImplementedError

    # notice board ----------------------------------

    def get_message_board(self) -> list[str]:
        raise NotImplementedError

    def update_notice_board(self, author: Player, message: str) -> bool:
        raise NotImplementedError

    # pets ---------------------------------------------

    def get_pet_from_id(self, pet_id: int) -> Pet | None:
        """return a specific pet given its id"""
        raise NotImplementedError

    def get_player_pets(self, player_id: int) -> list[Pet]:
        """get all pets owned by the specified player"""
        raise NotImplementedError

    def update_pet(self, pet: Pet, owner: Player) -> None:
        """update a pet on the database"""
        raise NotImplementedError

    def add_pet(self, pet: Pet, owner: Player) -> int:
        """ add a new pet on the database & returns the id """
        raise NotImplementedError

    def delete_pet(self, pet: Pet) -> None:
        """delete a specific pet on the database"""
        raise NotImplementedError

    # utility functions ----------------------------------

    def reset_caches(self):
        """ resets all caches """
        raise NotImplementedError


class PilgramGenerator(ABC):
    def generate_quests(self, zone: Zone, quest_data: Any) -> list[Quest]:
        raise NotImplementedError

    def generate_zone_events(self, zone: Zone) -> list[ZoneEvent]:
        raise NotImplementedError

    def generate_artifacts(self) -> list[Artifact]:
        raise NotImplementedError

    def generate_enemy_metas(self, zone: Zone) -> list[EnemyMeta]:
        raise NotImplementedError

    def generate_anomaly(self, zone: Zone) -> Anomaly:
        raise NotImplementedError


class PilgramNotifier(ABC):
    def notify(self, notification: Notification) -> dict:
        raise NotImplementedError
