import logging
import os
from datetime import timedelta, datetime

import numpy as np

from typing import Dict, Union, List, Tuple, Any

from peewee import fn, JOIN, IntegrityError

from orm.models import PlayerModel, GuildModel, ZoneModel, DB_FILENAME, create_tables, ZoneEventModel, QuestModel, \
    QuestProgressModel, db
from pilgram.classes import Player, Progress, Guild, Zone, ZoneEvent, Quest, AdventureContainer
from pilgram.generics import PilgramDatabase, AlreadyExists
from orm.utils import cache_ttl_quick, cache_sized_quick, cache_sized_ttl_quick, cache_ttl_single_value

log = logging.getLogger(__name__)


def decode_progress(data: Union[str, None]) -> Dict[int, int]:
    """
        decodes the bytestring saved in progress field to an integer map.
        Even bytes represent zone ids, odd bytes represent the progress in the associated zone.
    """
    if not data:
        return {}
    progress_dictionary: Dict[int, int] = {}
    encoded_data = bytes(data, "UTF-8")
    if len(encoded_data) == 4:
        # special case for progress with a single element, numpy returned the wrong array shape
        unpacked_array = np.frombuffer(encoded_data, dtype=np.uint16).reshape(2)
        return {unpacked_array[0].item(): unpacked_array[1].item()}
    unpacked_array = np.frombuffer(encoded_data, dtype=np.uint16).reshape((2, len(data) >> 2))
    for zone_id, progress in unpacked_array:
        progress_dictionary[zone_id.item()] = progress.item()
    return progress_dictionary


def encode_progress(data: Dict[int, int]) -> bytes:
    """ encodes the data dictionary contained in the progress object to a bytestring that can be saved on the db """
    dict_size = len(data)
    packed_array = np.empty(dict_size << 1, np.uint16)
    i: int = 0
    for zone_id, progress in data.items():
        j = i << 1
        packed_array[j] = zone_id
        packed_array[j + 1] = progress
        i += 1
    return packed_array.tobytes()


class PilgramORMDatabase(PilgramDatabase):
    """ Singleton object which contains the instance that handles connections to the database """
    _instance = None

    def __init__(self):
        raise RuntimeError("This class is a singleton, call instance() instead.")

    @classmethod
    def instance(cls) -> "PilgramORMDatabase":
        if cls._instance is None:
            log.info('Creating new database instance')
            cls._instance = cls.__new__(cls)
            if not os.path.isfile(DB_FILENAME):
                create_tables()
                log.info("tables created")
            cls._instance.is_connected = False
        return cls._instance

    @classmethod
    def acquire(cls) -> "PilgramORMDatabase":
        return cls.instance()

    # player ----

    @cache_sized_quick(size_limit=2000)
    def get_player_data(self, player_id) -> Player:
        # we are using a cache in front of this function since it's going to be called a lot, because of how the
        # function is structured the cache will store the Player objects which will always be updated in memory along
        # with their database record; Thus making it always valid.
        try:
            pls = PlayerModel.get(PlayerModel.id == player_id)
            guild = self.get_guild(pls.guild, calling_player_id=pls.id) if pls.guild else None
            progress = Progress.get_from_encoded_data(pls.progress, decode_progress)
            player = Player(
                pls.id,
                pls.name,
                pls.description,
                guild,
                pls.level,
                pls.xp,
                pls.money,
                progress,
                pls.gear_level,
                pls.home_level
            )
            if guild and (guild.founder is None):
                # if guild has no founder it means the founder is the player currently being retrieved
                guild.founder = player
            return player
        except PlayerModel.DoesNotExist:
            raise KeyError(f'Player with id {player_id} not found')  # raising exceptions makes sure invalid queries aren't cached

    @cache_sized_ttl_quick(size_limit=200, ttl=3600)
    def get_player_id_from_name(self, name: str) -> int:
        try:
            return PlayerModel.get(PlayerModel.name == name).id
        except PlayerModel.DoesNotExist:
            raise KeyError(f'Player with name {name} not found')

    def update_player_data(self, player: Player):
        try:
            pls = PlayerModel.get(PlayerModel.id == player.player_id)
            pls.name = player.name
            pls.description = player.description
            pls.guild = player.guild.guild_id if player.guild else None
            pls.level = player.level
            pls.xp = player.xp
            pls.money = player.money
            pls.progress = encode_progress(player.progress.zone_progress) if player.progress else None
            pls.home_level = player.home_level
            pls.gear_level = player.gear_level
            pls.save()
        except PlayerModel.DoesNotExist:
            raise KeyError(f'Player with id {player.player_id} not found')

    def add_player(self, player: Player):
        try:
            with db.atomic():
                PlayerModel.create(
                    id=player.player_id,
                    name=player.name,
                    description=player.description,
                    guild=player.guild.guild_id if player.guild else None,
                    level=player.level,
                    xp=player.xp,
                    money=player.money,
                    progress=encode_progress(player.progress.zone_progress) if player.progress else None,
                    gear_level=player.gear_level
                )
                # also create quest progress model related to the player
                QuestProgressModel.create(
                    player_id=player.player_id
                )
        except IntegrityError:
            raise AlreadyExists(f"Player with name {player.name} already exists")

    # guilds ----

    def build_guild_object(self, gs, calling_player_id: Union[int, None]):
        """
            build the guild object, also check if the player requesting the guild is the founder of said guild
            to avoid an infinite recursion loop.
        """
        if (calling_player_id is not None) and (calling_player_id == gs.founder.id):
            founder = None
        else:
            founder = self.get_player_data(gs.founder)
        return Guild(
            gs.id,
            gs.name,
            gs.level,
            gs.description,
            founder,
            gs.creation_date,
            gs.prestige
        )

    @cache_sized_ttl_quick(size_limit=400, ttl=3600)
    def get_guild(self, guild_id: int, calling_player_id: Union[int, None] = None) -> Guild:
        try:
            gs = GuildModel.get(GuildModel.id == guild_id)
            return self.build_guild_object(gs, calling_player_id)
        except GuildModel.DoesNotExist:
            raise KeyError(f'Guild with id {guild_id} not found')

    @cache_sized_ttl_quick(size_limit=200, ttl=3600)
    def get_guild_id_from_name(self, guild_name: str) -> int:
        try:
            return GuildModel.get(GuildModel.name == guild_name).id
        except GuildModel.DoesNotExist:
            raise KeyError(f'Guild with name {guild_name} not found')

    @cache_sized_quick(size_limit=100)
    def get_guild_id_from_founder(self, player: Player) -> int:
        try:
            return GuildModel.get(GuildModel.founder == player.player_id).id
        except GuildModel.DoesNotExist:
            raise KeyError(f'Guild founded by player with id {player.player_id} not found')

    @cache_sized_ttl_quick(size_limit=50, ttl=3600)
    def __get_guild_members_data(self, guild_id: int) -> List[Tuple[str, int]]:
        """ cache based on the id should work a bit better """
        gms = GuildModel.get(guild_id == GuildModel.id).members
        return [(x.name, x.level) for x in gms]

    def get_guild_members_data(self, guild: Guild) -> List[Tuple[str, int]]:
        return self.__get_guild_members_data(guild.guild_id)

    @cache_ttl_quick(ttl=60)
    def get_guild_members_number(self, guild: Guild) -> int:
        return GuildModel.get(guild.guild_id == GuildModel.id).members.count()

    def update_guild(self, guild: Guild):
        gs = GuildModel.get(GuildModel.id == guild.guild_id)
        if not gs:
            raise KeyError(f'Guild with id {guild.guild_id} not found')
        gs.name = guild.name
        gs.description = guild.description
        gs.level = guild.level
        gs.prestige = guild.prestige
        gs.save()

    def add_guild(self, guild: Guild):
        try:
            with db.atomic():
                GuildModel.create(
                    name=guild.name,
                    description=guild.description,
                    founder_id=guild.founder.player_id,
                    creation_date=guild.creation_date
                )
        except IntegrityError:
            raise AlreadyExists(f"Guild with name {guild.name} already exists")

    @cache_ttl_single_value(ttl=14400)
    def rank_top_guilds(self) -> List[Tuple[str, int]]:
        gs = GuildModel.select(
            GuildModel.name, GuildModel.prestige
        ).order_by(GuildModel.prestige.desc()).limit(20).namedtuples()
        return [(guild_row.name, guild_row.prestige) for guild_row in gs]

    # zones ----

    @staticmethod
    def build_zone_object(zs):
        return Zone(
            zs.id,
            zs.name,
            zs.level,
            zs.description
        )

    @cache_ttl_quick(ttl=604800)  # cache lasts a week since I don't ever plan to change zones, but you never know
    def get_zone(self, zone_id: int) -> Zone:
        try:
            zs = ZoneModel.get(ZoneModel.id == zone_id)
            return self.build_zone_object(zs)
        except ZoneModel.DoesNotExist:
            raise KeyError(f"Could not find zone with id {zone_id}")

    @cache_ttl_single_value(ttl=86400)
    def get_all_zones(self) -> List[Zone]:
        try:
            zs = ZoneModel.select().namedtuples()
        except ZoneModel.DoesNotExist:
            return []
        return [self.build_zone_object(x) for x in zs]

    def update_zone(self, zone: Zone):  # this will basically never be called, but it's good to have
        zs = ZoneModel.get(ZoneModel.id == zone.zone_id)
        if not zs:
            raise KeyError(f"Could not find zone with id {zone.zone_id}")
        zs.name = zone.zone_name
        zs.level = zone.level
        zs.description = zone.zone_description
        zs.save()

    def add_zone(self, zone: Zone):
        with db.atomic():
            ZoneModel.create(
                name=zone.zone_name,
                level=zone.level,
                description=zone.zone_description
            )

    # zone events ----

    def build_zone_event_object(self, zes) -> ZoneEvent:
        return ZoneEvent(
            zes.id,
            self.get_zone(zes.zone_id) if zes.zone_id != 0 else None,
            zes.event_text
        )

    def get_zone_event(self, event_id: int) -> ZoneEvent:  # this is unlikely to ever be used
        try:
            zes = ZoneEventModel.get(ZoneEventModel.id == event_id)
            return self.build_zone_event_object(zes)
        except ZoneEventModel.DoesNotExist:
            raise KeyError(f"Could not find zone event with id {event_id}")

    @cache_ttl_quick(ttl=10)
    def get_random_zone_event(self, zone: Union[Zone, None]) -> ZoneEvent:
        # cache lasts only 10 seconds to optimize the most frequent use case
        try:
            if zone:
                zes = ZoneEventModel.select(
                    ZoneEventModel.id, ZoneEventModel.zone_id, ZoneEventModel.event_text
                ).where(ZoneEventModel.zone_id == zone.zone_id).order_by(fn.Random()).limit(1).namedtuples()
            else:
                zes = ZoneEventModel.select(
                    ZoneEventModel.id, ZoneEventModel.zone_id, ZoneEventModel.event_text
                ).where(ZoneEventModel.zone_id == 0).order_by(fn.Random()).limit(1).namedtuples()
            for ze in zes:
                return self.build_zone_event_object(ze)
        except ZoneEventModel.DoesNotExist:
            raise KeyError(f"Could not find any zone events within zone {zone.zone_id}")

    def update_zone_event(self, event: ZoneEvent):
        try:
            zes = ZoneEventModel.get(ZoneEventModel.id == event.event_id)
            zes.event_text = event.event_text
            zes.save()
        except ZoneEventModel.DoesNotExist:
            raise KeyError(f"Could not find zone event with id {event.event_id}")

    def add_zone_event(self, event: ZoneEvent):
        with db.atomic():
            ZoneEventModel.create(
                zone_id=event.zone.zone_id,
                event_text=event.event_text
            )

    def add_zone_events(self, events: List[ZoneEvent]):
        data_to_insert = [{"zone_id": e.zone.zone_id if e.zone else 0, "event_text": e.event_text} for e in events]
        with db.atomic():
            ZoneEventModel.insert_many(data_to_insert).execute()

    # quests ----

    def build_quest_object(self, qs, zone: Union[Zone, None] = None) -> Quest:
        if not zone:
            zone = self.get_zone(qs.zone_id)
        return Quest(
            qs.id,
            zone,
            qs.number,
            qs.name,
            qs.description,
            qs.success_text,
            qs.failure_text,
        )

    @cache_sized_ttl_quick(size_limit=200, ttl=86400)
    def get_quest(self, quest_id: int) -> Quest:
        try:
            qs = QuestModel.get(QuestModel.id == quest_id)
            return self.build_quest_object(qs)
        except QuestModel.DoesNotExist:
            raise KeyError(f"Could not find quest with id {quest_id}")

    @cache_sized_ttl_quick(size_limit=200)
    def get_quest_from_number(self, zone: Zone, quest_number: int) -> Quest:
        try:
            qs = QuestModel.get((QuestModel.zone_id == zone.zone_id) and (QuestModel.number == quest_number))
            return self.build_quest_object(qs, zone=zone)
        except QuestModel.DoesNotExist:
            raise KeyError(f"Could not find quest number {quest_number} in zone {zone.zone_id}")

    def update_quest(self, quest: Quest):
        try:
            qs = QuestModel.get(QuestModel.id == quest.quest_id)
            qs.number = quest.number
            qs.name = quest.name
            qs.description = quest.description
            qs.failure_text = quest.failure_text
            qs.success_text = quest.success_text
            qs.save()
        except QuestModel.DoesNotExist:
            raise KeyError(f"Could not find quest with id {quest.quest_id}")

    def add_quest(self, quest: Quest):
        with db.atomic():
            QuestModel.create(
                name=quest.name,
                zone_id=quest.zone.zone_id,
                number=quest.number,
                description=quest.description,
                success_text=quest.success_text,
                failure_text=quest.failure_text,
            )

    def add_quests(self, quests: List[Quest]):
        data_to_insert: List[Dict[str, Any]] = [
            {
                "name": q.name,
                "zone_id": q.zone.zone_id,
                "number": q.number,
                "description": q.description,
                "success_text": q.success_text,
                "failure_text": q.failure_text
            } for q in quests
        ]
        with db.atomic():
            QuestModel.insert_many(data_to_insert).execute()

    @cache_ttl_single_value(ttl=30)
    def get_quests_counts(self) -> List[int]:
        """ returns a list of quest amounts per zone, position in the list is determined by zone id """
        query = (ZoneModel.select(fn.Count(QuestModel.id).alias('quest_count')).
                 join(QuestModel, JOIN.LEFT_OUTER).
                 group_by(ZoneModel.id).
                 order_by(ZoneModel.id.asc()))
        return [x.quest_count for x in query]

    # in progress quest management ----

    def build_adventure_container(self, qps, owner: Union[Player, None] = None) -> AdventureContainer:
        player = self.get_player_data(int(qps.player_id)) if owner is None else owner
        quest = self.get_quest(qps.quest_id) if qps.quest_id else None
        return AdventureContainer(player, quest, qps.end_time)

    @cache_sized_ttl_quick(size_limit=200, ttl=60)
    def get_player_adventure_container(self, player: Player) -> AdventureContainer:
        try:
            qps = QuestProgressModel.get(QuestProgressModel.player_id == player.player_id)
            return self.build_adventure_container(qps, owner=player)
        except QuestProgressModel.DoesNotExist:
            raise KeyError(f"Could not find quest progress for player with id {player.player_id}")

    def get_player_current_quest(self, player: Player) -> Union[Quest, None]:
        adventure_container = self.get_player_adventure_container(player)
        return adventure_container.quest

    def get_all_pending_updates(self, delta: timedelta) -> List[AdventureContainer]:
        try:
            qps = QuestProgressModel.select().where(QuestProgressModel.last_update <= datetime.now() - delta).namedtuples()
            return [self.build_adventure_container(x) for x in qps]
        except QuestProgressModel.DoesNotExist:
            return []

    def update_quest_progress(self, adventure_container: AdventureContainer, last_update: Union[datetime, None] = None):
        try:
            qps = QuestProgressModel.get(QuestProgressModel.player_id == adventure_container.player_id())
            qps.quest_id = adventure_container.quest_id()
            qps.last_update = datetime.now() if last_update is None else last_update
            qps.end_time = adventure_container.finish_time
            qps.save()
        except QuestProgressModel.DoesNotExist:
            raise KeyError(f"Could not find quest progress for player with id {adventure_container.player_id()}")
