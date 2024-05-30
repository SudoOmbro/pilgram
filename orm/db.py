import logging
import os

import numpy as np

from typing import Dict, Union

from peewee import fn

from orm.models import PlayerModel, GuildModel, ZoneModel, DB_FILENAME, create_tables, ZoneEventModel, QuestModel
from pilgram.classes import Player, Progress, Guild, Zone, ZoneEvent, Quest
from pilgram.generics import PilgramDatabase, NotFoundException
from orm.utils import cache_ttl_quick, cache_sized_quick

log = logging.getLogger(__name__)


def decode_progress(data: Union[bytes, None]) -> Dict[int, int]:
    """
        decodes the bytestring saved in progress field to an integer map.
        Even bytes represent zone ids, odd bytes represent the progress in the associated zone.
    """
    if not data:
        return {}
    progress_dictionary: Dict[int, int] = {}
    unpacked_array = np.frombuffer(data, dtype=np.uint16).reshape((2, len(data) >> 2))
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
    """ singleton object which contains the instance that handles connections to the database """
    _instance = None

    def __init__(self):
        raise RuntimeError("This class is a singleton, call instance() instead.")

    @classmethod
    def instance(cls):
        if cls._instance is None:
            print('Creating new instance')
            cls._instance = cls.__new__(cls)
            if not os.path.isfile(DB_FILENAME):
                create_tables()
        return cls._instance

    # player ----

    @cache_sized_quick(size_limit=2000)
    def get_player_data(self, player_id) -> Player:
        # we are using a cache in front of this function since it's going to be called a lot, because of how the
        # function is structured the cache will store the Player objects which will always be updated in memory along
        # with their database record; Thus making it always valid.
        pls = PlayerModel.get(PlayerModel.id == player_id)
        if not pls:
            raise NotFoundException(f'Player with id {player_id} not found')
        guild = self.get_guild(pls.guild_id)
        progress = Progress(pls.progress, decode_progress)
        return Player(
            pls.player_id,
            pls.name,
            pls.description,
            guild,
            pls.level,
            pls.xp,
            pls.money,
            progress,
            pls.gear_level
        )

    def update_player_data(self, player: Player):
        pls = PlayerModel.get(PlayerModel.id == player.player_id)
        if not pls:
            raise NotFoundException(f'Player with id {player.player_id} not found')
        pls.name = player.name,
        pls.description = player.description,
        pls.guild = player.guild,
        pls.level = player.level,
        pls.xp = player.xp,
        pls.money = player.money,
        pls.gear_level = player.gear_level
        pls.progress = encode_progress(player.progress.zone_progress)
        pls.save()

    def create_player_data(self, player: Player):
        PlayerModel.create(
            id=player.player_id,
            name=player.name,
            description=player.description,
            guild=player.guild.guild_id,
            level=player.level,
            xp=player.xp,
            money=player.money,
            progress=player.progress.zone_progress,
            gear_level=player.gear_level
        )

    # guilds ----

    def get_guild(self, guild_id: int) -> Guild:
        gs = GuildModel.get(GuildModel.id == guild_id)
        if not gs:
            raise NotFoundException(f'Guild with id {guild_id} not found')
        founder = self.get_player_data(gs.founder_id)
        return Guild(
            gs.id,
            gs.name,
            gs.description,
            founder,
            gs.creation_date,
        )

    def update_guild(self, guild: Guild):
        gs = GuildModel.get(GuildModel.id == guild.guild_id)
        if not gs:
            raise NotFoundException(f'Guild with id {guild.guild_id} not found')
        gs.name = guild.name
        gs.description = guild.description
        gs.save()

    def add_guild(self, guild: Guild):
        gs = GuildModel.create(
            name=guild.name,
            description=guild.description,
            founder_id=guild.founder.player_id,
            creation_date=guild.creation_date
        )
        guild.guild_id = gs.guild_id

    # zones ----

    @cache_ttl_quick(ttl=604800)  # cache lasts a week since I don't ever plan to change zones, but you never know
    def get_zone(self, zone_id: int) -> Zone:
        zs = ZoneModel.get(ZoneModel.id == zone_id)
        if not zs:
            raise NotFoundException(f"Could not find zone with id {zone_id}")
        return Zone(
            zs.id,
            zs.name,
            zs.level,
            zs.description
        )

    def update_zone(self, zone: Zone):  # this will basically never be called, but it's good to have
        zs = ZoneModel.get(ZoneModel.id == zone.zone_id)
        if not zs:
            raise NotFoundException(f"Could not find zone with id {zone.zone_id}")
        zs.name = zone.zone_name
        zs.level = zone.level
        zs.description = zone.zone_description
        zs.save()

    def add_zone(self, zone: Zone):
        zs = ZoneModel.create(
            name=zone.zone_name,
            level=zone.level,
            description=zone.zone_description
        )
        zone.zone_id = zs.id

    # zone events ----

    def build_zone_event_object(self, zes) -> ZoneEvent:
        zone = self.get_zone(zes.zone_id)
        return ZoneEvent(
            zes.id,
            zone,
            zes.event_text
        )

    def get_zone_event(self, event_id: int) -> ZoneEvent:  # this is unlikely to ever be used
        zes = ZoneEventModel.get(ZoneEventModel.id == event_id)
        if not zes:
            raise NotFoundException(f"Could not find zone event with id {event_id}")
        return self.build_zone_event_object(zes)

    @cache_ttl_quick(ttl=10)
    def get_random_zone_event(self, zone: Zone) -> ZoneEvent:
        # cache lasts only 10 seconds to optimize the most frequent use case
        zes = ZoneEventModel.select().where(ZoneEventModel.id == zone.zone_id).order_by(fn.Random()).limit(1)
        return self.build_zone_event_object(zes)

    def update_zone_event(self, event: ZoneEvent):
        zes = ZoneEventModel.get(ZoneEventModel.id == event.event_id)
        if not zes:
            raise NotFoundException(f"Could not find zone event with id {event.event_id}")
        zes.event_text = event.event_text
        zes.save()

    def add_zone_event(self, event: ZoneEvent):
        zes = ZoneEventModel.create(
            zone_id=event.zone.zone_id,
            event_text=event.event_text
        )
        event.event_id = zes.id

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

    def get_quest(self, quest_id: int) -> Quest:  # this is unlikely to ever be used
        qs = QuestModel.get(QuestModel.id == quest_id)
        if not qs:
            raise NotFoundException(f"Could not find quest with id {quest_id}")
        return self.build_quest_object(qs)

    def get_quest_from_number(self, zone: Zone, quest_number: int) -> Quest:
        qs = QuestModel.get(QuestModel.zone_id == zone.zone_id and QuestModel.number == quest_number)
        if not qs:
            raise NotFoundException(f"Could not find quest number {quest_number} in zone {zone.zone_id}")
        return self.build_quest_object(qs, zone=zone)

    def update_quest(self, quest: Quest):
        qs = QuestModel.get(QuestModel.id == quest.quest_id)
        if not qs:
            raise NotFoundException(f"Could not find quest with id {quest.quest_id}")
        qs.number = quest.number
        qs.name = quest.name
        qs.description = quest.description
        qs.failure_text = quest.failure_text
        qs.success_text = quest.success_text
        qs.save()

    def add_quest(self, quest: Quest):
        qs = QuestModel.create(
            name=quest.name,
            description=quest.description,
            success_text=quest.success_text,
            failure_text=quest.failure_text,
        )
        quest.quest_id = qs.id

    def get_quest_count(self, zone: Zone) -> int:
        return QuestModel.select().where(QuestModel.id == zone.zone_id).count()

    # in progress quest management ----

    # TODO
