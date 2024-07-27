import logging
from abc import ABC
from datetime import timedelta, datetime
from typing import List, Tuple, Union, Any

from pilgram.classes import Player, Zone, Quest, Guild, ZoneEvent, AdventureContainer, Artifact, Tourney, EnemyMeta, \
    Auction
from pilgram.equipment import Equipment, ConsumableItem, EquipmentType

log = logging.getLogger(__name__)


class AlreadyExists(Exception):
    pass


class NoArtifactsError(Exception):
    pass


class PilgramDatabase(ABC):

    def acquire(self) -> "PilgramDatabase":
        """ generic method to get self, used to make the pilgram package implementation agnostic """
        raise NotImplementedError

    # players ----------------------------------

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

    def rank_top_players(self) -> List[Tuple[str, int]]:
        """ get top 20 guild names + prestige based on rank """
        raise NotImplementedError

    # guilds ----------------------------------

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

    def get_guild_members_data(self, guild: Guild) -> List[Tuple[int, str, int]]:  # id, name, level
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

    def get_top_n_guilds_by_score(self, n: int) -> List[Guild]:
        """ get top n guilds based on score """
        raise NotImplementedError

    def reset_all_guild_scores(self):
        """ reset the tourney scores of all guilds """
        raise NotImplementedError

    # zones ----------------------------------

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

    # Zone events ----------------------------------

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

    # quests ----------------------------------

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

    # in progress quests management ----------------------------------

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

    # artifacts ----------------------------------

    def get_artifact(self, artifact_id: int) -> Artifact:
        """ returns an artifact given its id """
        raise NotImplementedError

    def get_player_artifacts(self, player_id: int) -> List[Artifact]:
        """
        get all artifacts owned by the specified player

        :raises NoArtifactsError if player has no artifacts, KeyError if player does not exist
        """
        raise NotImplementedError

    def get_unclaimed_artifact(self) -> Artifact:
        """ get the first unclaimed artifact in the db """
        raise NotImplementedError

    def get_number_of_unclaimed_artifacts(self) -> int:
        """
        get the number of unclaimed artifacts in the db, useful for the generator to see if it has to generate new ones
        """
        raise NotImplementedError

    def add_artifact(self, artifacts: Artifact):
        """ add the given artifact to the database """
        raise NotImplementedError

    def add_artifacts(self, artifacts: List[Artifact]):
        """ add the given list of artifacts to the database """
        raise NotImplementedError

    def update_artifact(self, artifacts: Artifact, owner: Union[Player, None]):
        """ save the given artifact to the database (used when assigning an owner basically) """
        raise NotImplementedError

    # cults ----------------------------------

    def get_cults_members_number(self) -> List[Tuple[int, int]]:  # cult id, number of members
        """ get the number of members for each cult """
        raise NotImplementedError

    # tourney ----------------------------------

    def get_tourney(self) -> Tourney:
        """ get the biweekly guild tourney object """
        raise NotImplementedError

    def update_tourney(self, tourney: Tourney):
        """ update the tourney object """
        raise NotImplementedError

    # enemy meta ----------------------------------

    def get_enemy_meta(self, enemy_meta_id: int) -> EnemyMeta:
        """ get a specific enemy meta (for updating most likely) """
        raise NotImplementedError

    def get_all_zone_enemies(self, zone: Zone) -> List[EnemyMeta]:
        """ get all enemies from given a zone """
        raise NotImplementedError

    def get_random_enemy_meta(self, zone: Zone) -> EnemyMeta:
        """ get a random enemy meta from the specified zone """
        raise NotImplementedError

    def update_enemy_meta(self, enemy_meta: EnemyMeta):
        """ update the enemy meta on the database (mainly used by admin CLI) """
        raise NotImplementedError

    def add_enemy_meta(self, enemy_meta: EnemyMeta):
        """ add a new AI-generated (or human made) enemy meta to the database """
        raise NotImplementedError

    # items ----------------------------------

    def get_item(self, item_id: int) -> Equipment:
        """ return a specific item given its id """
        raise NotImplementedError

    def get_player_items(self, player_id: int) -> List[Equipment]:
        """ get all items owned by the specified player """
        raise NotImplementedError

    def update_item(self, item: Equipment, owner: Player):
        """ update an item on the database """
        raise NotImplementedError

    def add_item(self, item: Equipment, owner: Player):
        """ add a new item on the database """
        raise NotImplementedError

    def delete_item(self, item: Equipment):
        """ delete a specific item on the database """
        raise NotImplementedError

    # shops ----------------------------------

    def get_market_items(self) -> List[ConsumableItem]:
        """ gets daily consumable items to buy """
        raise NotImplementedError

    def get_smithy_items(self) -> List[EquipmentType]:
        """ gets daily equipment to buy """
        raise NotImplementedError

    # auctions ----------------------------------

    def get_auctions(self) -> List[Auction]:
        """ gets all auctions """
        raise NotImplementedError

    def get_auction_from_id(self, auction_id: int) -> Auction:
        """ get the auction that has the given id """
        raise NotImplementedError

    def get_auction_id_from_item(self, item: Equipment) -> int:
        """ get the auction for the given item """
        raise NotImplementedError

    def get_auction_from_item(self, item: Equipment) -> Union[Auction, None]:
        try:
            auction_id = self.get_auction_id_from_item(item)
            return self.get_auction_from_id(auction_id)
        except KeyError:
            return None

    def get_player_auctions(self, player: Player) -> List[Auction]:
        """ gets auctions started by the given player """
        raise NotImplementedError

    def get_expired_auctions(self):
        """ gets all expired auctions """
        raise NotImplementedError

    def update_auction(self, auction: Auction):
        """ update the auction db row """
        raise NotImplementedError

    def add_auction(self, auction: Auction):
        """ creates a new auction """
        raise NotImplementedError

    def delete_auction(self, auction: Auction):
        """ removes the auction db row """
        raise NotImplementedError


class PilgramGenerator(ABC):

    def generate_quests(self, zone: Zone, quest_data: Any) -> List[Quest]:
        raise NotImplementedError

    def generate_zone_events(self, zone: Zone) -> List[ZoneEvent]:
        raise NotImplementedError

    def generate_artifacts(self) -> List[Artifact]:
        raise NotImplementedError

    def generate_enemy_metas(self, zone: Zone) -> List[EnemyMeta]:
        raise NotImplementedError


class PilgramNotifier(ABC):

    def notify(self, player: Player, text: str, notification_type: str = "notification"):
        raise NotImplementedError
