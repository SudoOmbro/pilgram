import logging
import os

import numpy as np

from typing import Dict, Union

from orm.models import PlayerModel, GuildModel, ZoneModel, DB_FILENAME, create_tables
from pilgram.classes import Player, Progress, Guild, Zone
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
    """ singleton object which contains the instance that handles connections to the database and the caches """
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
        gs.name = guild.name
        gs.description = guild.description
        gs.save()

    def add_guild(self, guild: Guild):
        # TODO autogenerate id & update object
        GuildModel.create(
            id=guild.guild_id,
            name=guild.name,
            description=guild.description,
            founder_id=guild.founder.player_id,
            creation_date=guild.creation_date
        )

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
        zs.name = zone.zone_name
        zs.level = zone.level
        zs.description = zone.zone_description
        zs.save()

    def add_zone(self, zone: Zone):
        # TODO autogenerate id & update object
        ZoneModel.create(
            id=zone.zone_id,
            name=zone.zone_name,
            level=zone.level,
            description=zone.zone_description
        )
