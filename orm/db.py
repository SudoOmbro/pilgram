import json
import logging
import random
import threading
from copy import copy
from datetime import datetime, timedelta
from time import sleep
from typing import Any

import numpy as np
from peewee import JOIN, fn, ModelSelect

from orm.migration import migrate_older_dbs
from orm.models import (
    ArtifactModel,
    AuctionModel,
    EnemyTypeModel,
    EquipmentModel,
    GuildModel,
    PlayerModel,
    QuestModel,
    QuestProgressModel,
    ZoneEventModel,
    ZoneModel,
    create_tables,
    PetModel,
    db,
)
from orm.utils import cache_sized_ttl_quick, cache_ttl_quick, cache_ttl_single_value
from pilgram.classes import (
    AdventureContainer,
    Artifact,
    Auction,
    Vocation,
    EnemyMeta,
    Guild,
    Player,
    Progress,
    Quest,
    Tourney,
    Zone,
    ZoneEvent,
    Notification,
    Anomaly,
    Pet,
)
from pilgram.combat_classes import Damage, Stats
from pilgram.equipment import ConsumableItem, Equipment, EquipmentType
from pilgram.generics import AlreadyExists, PilgramDatabase
from pilgram.globals import ContentMeta
from pilgram.modifiers import Modifier, get_modifier
from pilgram.utils import save_json_to_file, read_json_file

log = logging.getLogger(__name__)

_LOCK = threading.Lock()
_TOURNEY_LOCK = threading.Lock()
_NOTIFICATION_LOCK = threading.Lock()
_DUEL_LOCK = threading.Lock()

ENCODING = "cp437"  # we use this encoding since we are working with raw bytes & peewee doesn't seem to like raw bytes

NP_MD = np.dtype([('id', np.uint16), ('strength', np.uint32)])  # 'NumPy Modifiers Data'
NP_VP = np.dtype([('id', np.uint8), ('progress', np.uint8)])  # 'NumPy Vocations Progress'
NP_ED = np.dtype([('id', np.uint8), ('amount', np.uint16)])  # 'NumPy Essence Data'

_NOTIFICATIONS_LIST: list[Notification] = []

MAX_MARKET_ITEMS = ContentMeta.get("market.max_items")


def decode_progress(data: str | None) -> dict[int, int]:
    """
        decodes the bytestring saved in progress field to an integer map.
        Even bytes represent zone ids, odd bytes represent the progress in the associated zone.
    """
    if not data:
        return {}
    progress_dictionary: dict[int, int] = {}
    encoded_data = bytes(data, ENCODING)
    if len(encoded_data) == 4:
        # special case for progress with a single element, numpy returned the wrong array shape
        unpacked_array = np.frombuffer(encoded_data, dtype=np.uint16).reshape(2)
        return {unpacked_array[0].item(): unpacked_array[1].item()}
    unpacked_array = np.frombuffer(encoded_data, dtype=np.uint16).reshape((len(data) >> 2, 2))
    for zone_id, progress in unpacked_array:
        progress_dictionary[zone_id.item()] = progress.item()
    return progress_dictionary


def encode_progress(data: dict[int, int]) -> str:
    """ encodes the data dictionary contained in the progress object to a bytestring that can be saved on the db """
    dict_size = len(data)
    packed_array = np.empty(dict_size << 1, np.uint16)
    for i, (zone_id, progress) in enumerate(data.items()):
        j = i << 1
        packed_array[j] = zone_id
        packed_array[j + 1] = progress
    return packed_array.tobytes().decode(encoding=ENCODING)


def decode_satchel(data: str) -> list[ConsumableItem]:
    result: list[ConsumableItem] = []
    if not data:
        return result
    encoded_data = bytes(data, ENCODING)
    unpacked_array = np.frombuffer(encoded_data, dtype=np.uint8)
    for consumable_id in unpacked_array:
        result.append(ConsumableItem.get(consumable_id.item()))
    return result


def encode_satchel(satchel: list[ConsumableItem]) -> str:
    packed_array = np.empty(len(satchel), np.uint8)
    for i, consumable in enumerate(satchel):
        packed_array[i] = consumable.consumable_id
    return packed_array.tobytes().decode(encoding=ENCODING)


def decode_equipped_items_ids(data: str) -> list[int]:
    encoded_data = bytes(data, ENCODING)
    equipment_list: list[int] = []
    for item in np.frombuffer(encoded_data, dtype=np.uint32):
        equipment_list.append(item.item())
    return equipment_list


def encode_equipped_items(equipped_items: dict[int, Equipment]) -> str:
    packed_array = np.empty(len(list(equipped_items.keys())), np.uint32)
    for i, equipment in enumerate(list(equipped_items.values())):
        packed_array[i] = equipment.equipment_id
    return packed_array.tobytes().decode(encoding=ENCODING)


def decode_modifiers(data: str | None) -> list[Modifier]:
    if not data:
        return []
    encoded_data = bytes(data, ENCODING)
    modifiers_list: list[Modifier] = []
    for item in np.frombuffer(encoded_data, dtype=NP_MD):
        modifiers_list.append(get_modifier(item["id"].item(), item["strength"].item()))
    return modifiers_list


def encode_modifiers(modifiers: list[Modifier]) -> str:
    packed_array = np.empty(int(len(modifiers)), NP_MD)
    for i, modifier in enumerate(modifiers):
        packed_array[i]["id"] = modifier.ID
        packed_array[i]["strength"] = modifier.strength
    return packed_array.tobytes().decode(encoding=ENCODING)


def decode_vocation_ids(data: int) -> list[int]:
    result: list[int] = []
    array = np.frombuffer(data.to_bytes(4), dtype=np.uint8)
    for i in range(4):
        result.append(array[i].item())
    return result


def encode_vocation_ids(vocations: list[Vocation]) -> int:
    packed_array = np.zeros(4, np.uint8)
    for i, vocation in enumerate(vocations):
        packed_array[i] = vocation.vocation_id
    return int.from_bytes(packed_array.tobytes())


def decode_vocation_progress(data: str | None) -> dict[int, int]:
    if not data:
        return {}
    encoded_data = bytes(data, ENCODING)
    vocations_progress: dict[int, int] = {}
    for item in np.frombuffer(encoded_data, dtype=NP_VP):
        vocations_progress[item["id"].item()] = item["progress"].item()
    return vocations_progress


def encode_vocation_progress(vocation_progress: dict[int, int]) -> str:
    progress_list = list(vocation_progress.items())
    packed_array = np.zeros(len(progress_list), NP_VP)
    for i, (vocation_id, progress) in enumerate(progress_list):
        packed_array[i]["id"] = vocation_id
        packed_array[i]["progress"] = progress
    return packed_array.tobytes().decode(encoding=ENCODING)


def encode_essences(essences: dict[int, int]) -> str:
    packed_array = np.empty(int(len(essences)), NP_ED)
    for i, (zone_id, amount) in enumerate(essences.items()):
        packed_array[i]["id"] = zone_id
        packed_array[i]["amount"] = amount
    return packed_array.tobytes().decode(encoding=ENCODING)


def decode_essences(data: str | None) -> dict[int, int]:
    if not data:
        return {}
    encoded_data = bytes(data, ENCODING)
    essences_dict: dict[int, int] = {}
    for item in np.frombuffer(encoded_data, dtype=NP_ED):
        essences_dict[item["id"].item()] = item["amount"].item()
    return essences_dict


def _load_json(json_string: str) -> dict:
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        log.error(e)
        return {}


def _thread_safe(lock: threading.Lock = _LOCK):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper
    return decorator


def _get_daily_seed():
    return (datetime.now() - datetime(1998, 10, 1)).days


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
            while migrate_older_dbs():  # automatically migrate any DB to the newest version
                log.info("migration done.")
                sleep(0.05)
            if not db.get_tables():
                log.info("Db file does not exist. Creating one.")
                create_tables()
                sleep(0.1)
                log.info("tables created")
            cls._instance.is_connected = False
        return cls._instance

    @classmethod
    def acquire(cls) -> "PilgramORMDatabase":
        return cls.instance()

    # player ----

    @cache_sized_ttl_quick(size_limit=2000, ttl=3600)
    def get_player_data(self, player_id) -> Player:
        # we are using a cache in front of this function since it's going to be called a lot, because of how the
        # function is structured the cache will store the Player objects which will always be updated in memory along
        # with their database record; Thus making it always valid.
        try:
            pls: PlayerModel = PlayerModel.get(PlayerModel.id == player_id)
            guild = self.get_guild(pls.guild.id, calling_player_id=pls.id) if pls.guild else None
            artifacts = self.get_player_artifacts(player_id)
            items = self.get_player_items(player_id)
            equipped_items_ids: list[int] = decode_equipped_items_ids(pls.equipped_items)
            equipped_items = {}
            # vocations
            vocation_ids = decode_vocation_ids(pls.vocations)
            vocations_progress = decode_vocation_progress(pls.vocation_progress)
            vocations = []
            for vocation_id in vocation_ids:
                if vocation_id != 0:
                    vocations.append(Vocation.get_correct_vocation_tier_no_player(vocation_id, vocations_progress))
            # items
            for item in items:
                if item.equipment_id in equipped_items_ids:
                    equipped_items[item.equipment_type.slot] = item
            # create actual object
            player = Player(
                pls.id,
                pls.name,
                pls.description,
                guild,
                pls.level,
                pls.xp,
                pls.money,
                Progress.get_from_encoded_data(pls.progress, decode_progress),
                pls.gear_level,
                pls.home_level,
                pls.artifact_pieces,
                pls.last_spell_cast,
                artifacts,
                pls.flags,
                pls.renown,
                vocations,
                decode_satchel(pls.satchel),
                equipped_items,
                pls.hp_percent,
                pls.stance,
                pls.completed_quests,
                pls.last_guild_switch,
                vocations_progress,
                pls.sanity,
                pls.ascension,
                Stats(pls.vitality, pls.strength, pls.skill, pls.toughness, pls.attunement, pls.mind, pls.agility),
                decode_essences(pls.essences),
                pls.max_level_reached,
                pls.max_money_reached,
                pls.max_renown_reached,
                None if pls.pet is None else self.get_pet_from_id(pls.pet.id)
            )
            if guild and (guild.founder is None):
                # if guild has no founder it means the founder is the player currently being retrieved
                guild.founder = player
            return player
        except PlayerModel.DoesNotExist:
            raise KeyError(f'Player with id {player_id} not found')  # raising exceptions makes sure invalid queries aren't cached

    def get_random_player_data(self) -> Player:
        pls = PlayerModel.select(PlayerModel.id).order_by(fn.Random()).limit(1).namedtuples()
        for p in pls:
            return self.get_player_data(p.id)

    @cache_sized_ttl_quick(size_limit=200, ttl=3600)
    def get_player_id_from_name(self, name: str) -> int:
        try:
            return PlayerModel.get(PlayerModel.name == name).id
        except PlayerModel.DoesNotExist:
            raise KeyError(f'Player with name {name} not found')

    @cache_sized_ttl_quick(size_limit=200, ttl=3600)
    def get_player_ids_from_name_case_insensitive(self, player_name: str) -> list[int]:
        try:
            ps = PlayerModel.select(PlayerModel.id).filter(PlayerModel.name.ilike(player_name))
            return [x.id for x in ps]
        except PlayerModel.DoesNotExist:
            raise KeyError(f'Player with name {player_name} not found')

    @_thread_safe()
    def update_player_data(self, player: Player):
        try:
            with db.atomic():
                pls: PlayerModel = PlayerModel.get(PlayerModel.id == player.player_id)
                pls.name = player.name
                pls.description = player.description
                pls.guild = player.guild.guild_id if player.guild else None
                pls.level = player.level
                pls.xp = player.xp
                pls.money = player.money
                pls.progress = encode_progress(player.progress.zone_progress) if player.progress else None
                pls.home_level = player.home_level
                pls.gear_level = player.gear_level
                pls.last_spell_cast = player.last_cast
                pls.artifact_pieces = player.artifact_pieces
                pls.flags = player.flags
                pls.renown = player.renown
                pls.vocations = encode_vocation_ids(player.vocation.original_vocations)
                pls.satchel = encode_satchel(player.satchel)
                pls.equipped_items = encode_equipped_items(player.equipped_items)
                pls.hp_percent = player.hp_percent
                pls.stance = player.stance
                pls.completed_quests = player.completed_quests
                pls.last_guild_switch = player.last_guild_switch
                pls.vocation_progress = encode_vocation_progress(player.vocations_progress)
                pls.ascension = player.ascension
                pls.vitality = player.stats.vitality
                pls.strength = player.stats.strength
                pls.skill = player.stats.skill
                pls.toughness = player.stats.toughness
                pls.attunement = player.stats.attunement
                pls.mind = player.stats.mind
                pls.agility = player.stats.agility
                pls.essences = encode_essences(player.essences)
                pls.max_level_reached = player.max_level_reached
                pls.max_money_reached = player.max_money_reached
                pls.max_renown_reached = player.max_renown_reached
                pls.pet = player.pet.id if player.pet else None
                pls.save()
        except PlayerModel.DoesNotExist:
            raise KeyError(f'Player with id {player.player_id} not found')

    @_thread_safe()
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
        except Exception as e:  # catching the specific exception wasn't working so here we are
            log.error(e)
            raise AlreadyExists(f"Player with name {player.name} already exists")

    @cache_ttl_single_value(ttl=600)
    def rank_top_players(self) -> list[tuple[str, int]]:
        ps = PlayerModel.select(
            PlayerModel.name, PlayerModel.renown
        ).order_by(PlayerModel.renown.desc()).limit(20).namedtuples()
        return [(player_row.name, player_row.renown) for player_row in ps]

    # guilds ----

    def build_guild_object(self, gs: GuildModel, calling_player_id: int | None):
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
            gs.prestige,
            gs.tourney_score,
            gs.tax,
            gs.bank,
            gs.last_raid
        )

    @cache_sized_ttl_quick(size_limit=400, ttl=28800)
    def get_guild(self, guild_id: int, calling_player_id: int | None = None) -> Guild:
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

    @cache_sized_ttl_quick(size_limit=200, ttl=3600)
    def get_guild_ids_from_name_case_insensitive(self, guild_name: str) -> list[int]:
        try:
            gs = GuildModel.select(GuildModel.id).filter(GuildModel.name.ilike(guild_name))
            return [x.id for x in gs]
        except GuildModel.DoesNotExist:
            raise KeyError(f'Guild with name {guild_name} not found')

    @cache_sized_ttl_quick(size_limit=100)
    def get_guild_id_from_founder(self, player: Player) -> int:
        try:
            return GuildModel.get(GuildModel.founder == player.player_id).id
        except GuildModel.DoesNotExist:
            raise KeyError(f'Guild founded by player with id {player.player_id} not found')

    @cache_sized_ttl_quick(size_limit=50, ttl=300)
    def __get_guild_members_data(self, guild_id: int) -> list[tuple[int, str, int]]:
        """ cache based on the id should work a bit better """
        gms = GuildModel.get(guild_id == GuildModel.id).members
        return [(x.id, x.name, x.level) for x in gms]

    def get_guild_members_data(self, guild: Guild) -> list[tuple[int, str, int]]:  # id, name, level
        return self.__get_guild_members_data(guild.guild_id)

    @cache_ttl_quick(ttl=60)
    def get_guild_members_number(self, guild: Guild) -> int:
        return GuildModel.get(guild.guild_id == GuildModel.id).members.count()

    @_thread_safe()
    def update_guild(self, guild: Guild):
        gs = GuildModel.get(GuildModel.id == guild.guild_id)
        if not gs:
            raise KeyError(f'Guild with id {guild.guild_id} not found')
        with db.atomic():
            gs.name = guild.name
            gs.description = guild.description
            gs.level = guild.level
            gs.prestige = guild.prestige
            gs.tourney_score = guild.tourney_score
            gs.tax = guild.tax
            gs.bank = guild.bank
            gs.last_raid = guild.last_raid
            gs.save()

    @_thread_safe()
    def add_guild(self, guild: Guild) -> int:
        try:
            with db.atomic():
                guild_model: GuildModel = GuildModel.create(
                    name=guild.name,
                    description=guild.description,
                    founder_id=guild.founder.player_id,
                    creation_date=guild.creation_date,
                    tax=guild.tax
                )
                return guild_model.id
        except Exception as e:
            log.error(e)
            raise AlreadyExists(f"Guild with name {guild.name} already exists")

    @cache_ttl_single_value(ttl=14400)
    def rank_top_guilds(self) -> list[tuple[str, int]]:
        gs = GuildModel.select(
            GuildModel.name, GuildModel.prestige
        ).order_by(GuildModel.prestige.desc()).limit(20).namedtuples()
        return [(guild_row.name, guild_row.prestige) for guild_row in gs]

    @cache_ttl_quick(ttl=600)
    def get_top_n_guilds_by_score(self, n: int) -> list[Guild]:
        gs = GuildModel.select().order_by(GuildModel.tourney_score.desc()).limit(n)
        return [self.build_guild_object(g, None) for g in gs]

    def reset_all_guild_scores(self):
        for _ in range(2):
            # do it twice idk at this point
            for g in GuildModel.select():
                guild = self.get_guild(g.id, None)
                guild.tourney_score = 0
                self.update_guild(guild)
                sleep(1)

    @_thread_safe()
    def delete_guild(self, guild: Guild) -> None:
        try:
            GuildModel.get(GuildModel.id == guild.guild_id).delete_instance()
            guild.deleted = True
        except GuildModel.DoesNotExist:
            raise KeyError(f'Guild with id {guild.guild_id} not found')

    # zones ----

    @staticmethod
    def build_zone_object(zs: ZoneModel):
        return Zone(
            zs.id,
            zs.name,
            zs.level,
            zs.description,
            Damage.load_from_json(_load_json(zs.damage_json)),
            Damage.load_from_json(_load_json(zs.resist_json)),
            _load_json(zs.extra_data_json)
        )

    @cache_ttl_quick(ttl=604800)  # cache lasts a week since I don't ever plan to change zones, but you never know
    def get_zone(self, zone_id: int) -> Zone:
        try:
            zs = ZoneModel.get(ZoneModel.id == zone_id)
            return self.build_zone_object(zs)
        except ZoneModel.DoesNotExist:
            raise KeyError(f"Could not find zone with id {zone_id}")

    @cache_ttl_single_value(ttl=86400)
    def get_all_zones(self) -> list[Zone]:
        try:
            zs = ZoneModel.select().namedtuples()
        except ZoneModel.DoesNotExist:
            return []
        return [self.build_zone_object(x) for x in zs]

    @_thread_safe()
    def update_zone(self, zone: Zone):  # this will basically never be called, but it's good to have
        zs = ZoneModel.get(ZoneModel.id == zone.zone_id)
        if not zs:
            raise KeyError(f"Could not find zone with id {zone.zone_id}")
        with db.atomic():
            zs.name = zone.zone_name
            zs.level = zone.level
            zs.description = zone.zone_description
            zs.damage_json = json.dumps(zone.damage_modifiers.__dict__)
            zs.resist_json = json.dumps(zone.resist_modifiers.__dict__)
            zs.extra_data_json = json.dumps(zone.extra_data)
            zs.save()

    @_thread_safe()
    def add_zone(self, zone: Zone):
        with db.atomic():
            ZoneModel.create(
                name=zone.zone_name,
                level=zone.level,
                description=zone.zone_description,
                damage_json=json.dumps(zone.damage_modifiers.__dict__),
                resist_jsonn=json.dumps(zone.resist_modifiers.__dict__),
                extra_data_json=json.dumps(zone.extra_data)
            )

    # zone events ----

    def build_zone_event_object(self, zes: ZoneEventModel) -> ZoneEvent:
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
    def get_random_zone_event(self, zone: Zone | None) -> ZoneEvent:
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

    @_thread_safe()
    def update_zone_event(self, event: ZoneEvent):
        try:
            with db.atomic():
                zes = ZoneEventModel.get(ZoneEventModel.id == event.event_id)
                zes.event_text = event.event_text
                zes.save()
        except ZoneEventModel.DoesNotExist:
            raise KeyError(f"Could not find zone event with id {event.event_id}")

    @_thread_safe()
    def add_zone_event(self, event: ZoneEvent):
        with db.atomic():
            ZoneEventModel.create(
                zone_id=event.zone.zone_id,
                event_text=event.event_text
            )

    @_thread_safe()
    def add_zone_events(self, events: list[ZoneEvent]):
        data_to_insert = [{"zone_id": e.zone.zone_id if e.zone else 0, "event_text": e.event_text} for e in events]
        with db.atomic():
            ZoneEventModel.insert_many(data_to_insert).execute()

    # quests ----

    def build_quest_object(self, qs: QuestModel, zone: Zone | None = None) -> Quest:
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
    def get_quest_internal(self, quest_id: int) -> Quest:
        try:
            qs = QuestModel.get(QuestModel.id == quest_id)
            return self.build_quest_object(qs)
        except QuestModel.DoesNotExist:
            raise KeyError(f"Could not find quest with id {quest_id}")

    @cache_sized_ttl_quick(size_limit=200)
    def get_quest_from_number(self, zone: Zone, quest_number: int) -> Quest:
        try:
            qs = QuestModel.get((QuestModel.zone_id == zone.zone_id) & (QuestModel.number == quest_number))
            return self.build_quest_object(qs, zone=zone)
        except QuestModel.DoesNotExist:
            raise KeyError(f"Could not find quest number {quest_number} in zone {zone.zone_id}")

    @_thread_safe()
    def update_quest(self, quest: Quest):
        try:
            with db.atomic():
                qs = QuestModel.get(QuestModel.id == quest.quest_id)
                qs.number = quest.number
                qs.name = quest.name
                qs.description = quest.description
                qs.failure_text = quest.failure_text
                qs.success_text = quest.success_text
                qs.save()
        except QuestModel.DoesNotExist:
            raise KeyError(f"Could not find quest with id {quest.quest_id}")

    @_thread_safe()
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

    @_thread_safe()
    def add_quests(self, quests: list[Quest]):
        data_to_insert: list[dict[str, Any]] = [
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
    def get_quests_counts(self) -> list[int]:
        """ returns a list of quest amounts per zone, position in the list is determined by zone id """
        query = (ZoneModel.select(fn.Count(QuestModel.id).alias('quest_count')).
                 join(QuestModel, JOIN.LEFT_OUTER).
                 group_by(ZoneModel.id).
                 order_by(ZoneModel.id.asc()))
        return [x.quest_count for x in query]

    # in progress quest management ----

    def build_adventure_container(self, qps: QuestProgressModel, owner: Player | None = None) -> AdventureContainer:
        player = self.get_player_data(int(qps.player_id)) if owner is None else owner
        quest = self.get_quest(int(qps.quest_id)) if qps.is_on_a_quest() else None
        return AdventureContainer(player, quest, qps.end_time, qps.last_update)

    @cache_sized_ttl_quick(size_limit=200, ttl=60)
    def get_player_adventure_container(self, player: Player) -> AdventureContainer:
        try:
            qps = QuestProgressModel.get(QuestProgressModel.player_id == player.player_id)
            return self.build_adventure_container(qps, owner=player)
        except QuestProgressModel.DoesNotExist:
            raise KeyError(f"Could not find quest progress for player with id {player.player_id}")

    def get_player_current_quest(self, player: Player) -> Quest | None:
        adventure_container = self.get_player_adventure_container(player)
        return adventure_container.quest

    def get_all_pending_updates(self, delta: timedelta) -> list[AdventureContainer]:
        try:
            qps: ModelSelect = QuestProgressModel.select().where(QuestProgressModel.last_update <= datetime.now() - delta)
            return [self.build_adventure_container(x) for x in qps]
        except QuestProgressModel.DoesNotExist:
            return []

    @_thread_safe()
    def update_quest_progress(self, adventure_container: AdventureContainer, last_update: datetime | None = None):
        try:
            with db.atomic():
                qps = QuestProgressModel.get(QuestProgressModel.player_id == adventure_container.player_id())
                qps.quest_id = adventure_container.quest_id()
                # stagger updates using randomness
                qps.last_update = (datetime.now() + timedelta(minutes=random.randint(0, 40))) if last_update is None else last_update
                qps.end_time = adventure_container.finish_time
                qps.save()
        except QuestProgressModel.DoesNotExist:
            raise KeyError(f"Could not find quest progress for player with id {adventure_container.player_id()}")

    @cache_sized_ttl_quick(size_limit=200, ttl=300)
    def get_artifact(self, artifact_id: int) -> Artifact:
        try:
            arse = ArtifactModel.get(ArtifactModel.id == artifact_id)
            return Artifact(arse.id, arse.name, arse.description, self.get_player_data(arse.owner_id) if arse.owner_id else None)
        except ArtifactModel.DoesNotExist:
            raise KeyError(f"Could not find any artifact with id {artifact_id}")

    @cache_sized_ttl_quick(size_limit=200, ttl=300)
    def get_player_artifacts(self, player_id: int) -> list[Artifact]:
        try:
            ps = PlayerModel.get(PlayerModel.id == player_id)
            arse = ps.artifacts  # ARtifact SElection.  :)
            return [Artifact(x.id, x.name, x.description, None, owned_by_you=True) for x in arse]
        except PlayerModel.DoesNotExist:
            raise KeyError(f"Could not find player with id {player_id}")
        except ArtifactModel.DoesNotExist:
            return []

    def get_unclaimed_artifact(self) -> Artifact:
        try:
            arse = ArtifactModel.select(
                ArtifactModel.id, ArtifactModel.name, ArtifactModel.description
            ).where(ArtifactModel.owner_id == None).order_by(ArtifactModel.id).limit(1).namedtuples()
            for a in arse:
                return Artifact(a.id, a.name, a.description, None)
        except ArtifactModel.DoesNotExist:
            raise KeyError("No artifacts in database")

    def get_number_of_unclaimed_artifacts(self) -> int:
        try:
            return ArtifactModel.select().where(ArtifactModel.owner_id == None).count()
        except ArtifactModel.DoesNotExist:
            raise KeyError("No artifacts in database")

    @_thread_safe()
    def add_artifact(self, artifact: Artifact):
        with db.atomic():
            ArtifactModel.create(name=artifact.name, description=artifact.description, owner=None)

    @_thread_safe()
    def add_artifacts(self, artifacts: list[Artifact]):
        data_to_insert: list[dict[str, Any]] = [
            {
                "name": a.name,
                "description": a.description,
                "owner": None
            } for a in artifacts
        ]
        with db.atomic():
            ArtifactModel.insert_many(data_to_insert).execute()

    @_thread_safe()
    def update_artifact(self, artifact: Artifact, owner: Player | None):
        try:
            with db.atomic():
                arse = ArtifactModel.get(ArtifactModel.id == artifact.artifact_id)
                arse.name = artifact.name
                arse.description = artifact.description
                if owner is not None:
                    arse.owner = owner.player_id
                arse.save()
        except ArtifactModel.DoesNotExist:
            raise KeyError(f"Could not find artifact with id {artifact.artifact_id}")

    # cults ----

    @cache_ttl_single_value(ttl=1200)
    def get_cults_members_number(self) -> list[tuple[int, int]]:  # cult id, number of members
        query = (PlayerModel.select(PlayerModel.cult_id, fn.Count(PlayerModel.id).alias('player_count')).
                 group_by(PlayerModel.cult_id).
                 order_by(PlayerModel.cult_id.asc()))
        return [(x.cult_id, x.player_count) for x in query]

    # tourney ----

    @cache_ttl_single_value(ttl=86000)
    def get_tourney(self) -> Tourney:
        return Tourney.load_from_file("tourney.json")

    @_thread_safe(lock=_TOURNEY_LOCK)
    def update_tourney(self, tourney: Tourney):
        tourney.save()

    # enemy meta ----

    def __build_enemy_meta(self, ems: EnemyTypeModel) -> EnemyMeta:
        return EnemyMeta(
            ems.id,
            self.get_zone(ems.zone),
            ems.name,
            ems.description,
            ems.win_text,
            ems.lose_text
        )

    @cache_sized_ttl_quick(size_limit=100, ttl=300)
    def get_enemy_meta(self, enemy_meta_id: int) -> EnemyMeta:
        try:
            ems = EnemyTypeModel.get(EnemyTypeModel.id == enemy_meta_id)
            return self.__build_enemy_meta(ems)
        except EnemyTypeModel.DoesNotExist:
            raise KeyError(f"Enemey meta with id {enemy_meta_id} does not exist")

    def get_random_enemy_meta(self, zone: Zone) -> EnemyMeta:
        ems = EnemyTypeModel.select(
            EnemyTypeModel.id,
            EnemyTypeModel.zone_id,
            EnemyTypeModel.name,
            EnemyTypeModel.description,
            EnemyTypeModel.win_text,
            EnemyTypeModel.lose_text
        ).where(
            EnemyTypeModel.zone_id == zone.zone_id
        ).order_by(fn.Random()).limit(1).namedtuples()
        for em in ems:
            return self.__build_enemy_meta(em)

    @cache_sized_ttl_quick(size_limit=20, ttl=300)
    def get_all_zone_enemies(self, zone: Zone) -> list[EnemyMeta]:
        ems = EnemyTypeModel.select(
            EnemyTypeModel.id,
            EnemyTypeModel.zone_id,
            EnemyTypeModel.name,
            EnemyTypeModel.description,
            EnemyTypeModel.win_text,
            EnemyTypeModel.lose_text
        ).where(
            EnemyTypeModel.zone_id == zone.zone_id
        ).namedtuples()
        result: list[EnemyMeta] = []
        for em in ems:
            result.append(self.__build_enemy_meta(em))
        return result

    @_thread_safe()
    def update_enemy_meta(self, enemy_meta: EnemyMeta):
        try:
            with db.atomic():
                ems = EnemyTypeModel.get(EnemyTypeModel.id == enemy_meta.meta_id)
                ems.name = enemy_meta.name
                ems.description = enemy_meta.description
                ems.win_text = enemy_meta.win_text
                ems.lose_text = enemy_meta.lose_text
                ems.save()
        except EnemyTypeModel.DoesNotExist:
            raise KeyError(f"Enemey meta with id {enemy_meta.meta_id} does not exist")

    @_thread_safe()
    def add_enemy_meta(self, enemy_meta: EnemyMeta):
        with db.atomic():
            EnemyTypeModel.create(
                zone_id=enemy_meta.zone.zone_id,
                name=enemy_meta.name,
                description=enemy_meta.description,
                win_text=enemy_meta.win_text,
                lose_text=enemy_meta.lose_text
            )

    # items ----

    def __build_item(self, its: EquipmentModel) -> Equipment:
        equipment_type = EquipmentType.get(its.equipment_type)
        _, damage, resist = Equipment.generate_dmg_and_resist_values(its.level, its.damage_seed, equipment_type.is_weapon)
        return Equipment(
            its.id,
            its.level,
            equipment_type,
            its.name,
            its.damage_seed,
            damage,
            resist,
            decode_modifiers(its.modifiers),
            its.rerolls
        )

    def get_item(self, item_id: int) -> Equipment:
        try:
            its = EquipmentModel.get(EquipmentModel.id == item_id)
            return self.__build_item(its)
        except EquipmentModel.DoesNotExist:
            raise KeyError(f"Could not find item with id {item_id}")

    @cache_sized_ttl_quick(size_limit=100, ttl=300)
    def get_player_items(self, player_id: int) -> list[Equipment]:
        try:
            its = PlayerModel.get(PlayerModel.id == player_id).items
            return [self.__build_item(x) for x in its]
        except PlayerModel.DoesNotExist:
            raise KeyError(f"Could not find player with id {player_id}")
        except EquipmentModel.DoesNotExist:
            return []

    @_thread_safe()
    def update_item(self, item: Equipment, owner: Player):
        try:
            with db.atomic():
                its: EquipmentModel = EquipmentModel.get(EquipmentModel.id == item.equipment_id)
                its.owner = owner.player_id
                its.name = item.name
                its.modifiers = encode_modifiers(item.modifiers)
                its.damage_seed = item.seed
                its.level = item.level
                its.rerolls = item.rerolls
                its.save()
        except EquipmentModel.DoesNotExist:
            raise KeyError(f"Could not find item with id {item.equipment_id}")

    @_thread_safe()
    def add_item(self, item: Equipment, owner: Player) -> int:
        with db.atomic():
            item = EquipmentModel.create(
                name=item.name,
                owner=owner.player_id,
                level=item.level,
                equipment_type=item.equipment_type.equipment_type_id,
                damage_seed=item.seed,
                modifiers=encode_modifiers(item.modifiers)
            )
            return item.id

    @_thread_safe()
    def delete_item(self, item: Equipment):
        try:
            with db.atomic():
                EquipmentModel.get(EquipmentModel.id == item.equipment_id).delete_instance()
        except EquipmentModel.DoesNotExist:
            raise KeyError(f"Could not find item with id {item.equipment_id}")

    # shops ----

    @cache_ttl_single_value(ttl=3600)
    def get_market_items(self) -> list[ConsumableItem]:
        return ConsumableItem.get_random_selection(_get_daily_seed(), MAX_MARKET_ITEMS)

    @cache_ttl_single_value(ttl=3600)
    def get_smithy_items(self) -> list[EquipmentType]:
        return EquipmentType.get_random_selection(_get_daily_seed(), MAX_MARKET_ITEMS)

    # auctions ----

    def __build_auction(self, ass: AuctionModel):
        player = self.get_player_data(ass.auctioneer_id)
        best_bidder = self.get_player_data(ass.best_bidder_id) if ass.best_bidder_id else None
        item = self.get_item(ass.item_id)
        return Auction(
            ass.id,
            player,
            item,
            best_bidder,
            ass.best_bid,
            ass.creation_date
        )

    @cache_sized_ttl_quick()
    def get_auction_from_id(self, auction_id: int) -> Auction:
        try:
            ass = AuctionModel.get(AuctionModel.id == auction_id)  # ASS = Auction SelectionS :)
            return self.__build_auction(ass)
        except AuctionModel.DoesNotExist:
            raise KeyError(f"Could not find auction with id {auction_id}")

    @cache_sized_ttl_quick()
    def get_auction_id_from_item(self, item: Equipment) -> int:
        try:
            ass = AuctionModel.get(AuctionModel.item_id == item.equipment_id)
            return int(ass.id)
        except AuctionModel.DoesNotExist:
            raise KeyError(f"Could not find auction id associated with item {item.equipment_id}")

    @cache_ttl_single_value(ttl=600)
    def get_auctions(self) -> list[Auction]:
        try:
            ass = AuctionModel.select()
            return [self.__build_auction(x) for x in ass]
        except AuctionModel.DoesNotExist:
            return []

    @cache_sized_ttl_quick()
    def get_player_auctions(self, player: Player) -> list[Auction]:
        try:
            ass = PlayerModel.get(PlayerModel.id == player.player_id).auctions
            return [self.__build_auction(x) for x in ass]
        except AuctionModel.DoesNotExist:
            return []

    def get_expired_auctions(self):
        try:
            ass = AuctionModel.select().where(AuctionModel.creation_date < (datetime.now() - Auction.DURATION))
            return [self.__build_auction(x) for x in ass]
        except AuctionModel.DoesNotExist:
            return []

    @_thread_safe()
    def update_auction(self, auction: Auction):
        try:
            with db.atomic():
                ass: AuctionModel = AuctionModel.get(AuctionModel.id == auction.auction_id)
                ass.best_bid = auction.best_bid
                ass.best_bidder = auction.best_bidder.player_id
                ass.save()
        except AuctionModel.DoesNotExist:
            raise KeyError("Could not find auction to update")

    @_thread_safe()
    def add_auction(self, auction: Auction):
        with db.atomic():
            AuctionModel.create(
                auctioneer_id=auction.auctioneer.player_id,
                best_bid=auction.best_bid,
                item_id=auction.item.equipment_id
            )

    @_thread_safe()
    def delete_auction(self, auction: Auction):
        try:
            with db.atomic():
                AuctionModel.get(AuctionModel.id == auction.auction_id).delete_instance()
        except AuctionModel.DoesNotExist:
            raise KeyError(f"Could not find auction with id {auction.auction_id} to delete")

    # notifications ----

    @_thread_safe(lock=_NOTIFICATION_LOCK)
    def get_pending_notifications(self) -> list[Notification]:
        notifications = copy(_NOTIFICATIONS_LIST)
        _NOTIFICATIONS_LIST.clear()
        return notifications

    @_thread_safe(lock=_NOTIFICATION_LOCK)
    def add_notification(self, notification: Notification) -> None:
        _NOTIFICATIONS_LIST.append(notification)

    # duels ----

    _DUEL_INVITES: dict[int, list[int]] = {}
    # I can't be bothered to make these persistent, if the bot is turned off they disappear. Just invite again :)

    @_thread_safe(lock=_DUEL_LOCK)
    def add_duel_invite(self, sender: Player, target: Player):
        if self._DUEL_INVITES.get(sender.player_id, None) is None:
            self._DUEL_INVITES[sender.player_id] = []
        if target.player_id not in self._DUEL_INVITES[sender.player_id]:
            self._DUEL_INVITES[sender.player_id].append(target.player_id)

    @_thread_safe(lock=_DUEL_LOCK)
    def delete_duel_invite(self, sender: Player, target: Player):
        if self._DUEL_INVITES.get(sender.player_id, None) is None:
            return
        if target.player_id in self._DUEL_INVITES[sender.player_id]:
            self._DUEL_INVITES[sender.player_id].remove(target.player_id)
        if len(self._DUEL_INVITES[sender.player_id]) == 0:
            del self._DUEL_INVITES[sender.player_id]  # save memory

    def duel_invite_exists(self, sender: Player, target: Player) -> bool:
        if self._DUEL_INVITES.get(sender.player_id, None) is None:
            return False
        if target.player_id in self._DUEL_INVITES[sender.player_id]:
            return True
        return False

    # anomalies ----

    ANOMALY: dict[str, Anomaly] = {}
    ANOMALY_FILENAME: str = "anomaly.json"

    def get_current_anomaly(self) -> Anomaly:
        if "current" not in self.ANOMALY:
            try:
                anomaly_json = read_json_file(self.ANOMALY_FILENAME)
            except:
                anomaly_json = {}
            if not anomaly_json:
                self.ANOMALY["current"] = Anomaly.get_empty()
            else:
                self.ANOMALY["current"] = Anomaly(
                    anomaly_json["name"],
                    anomaly_json["description"],
                    self.get_zone(anomaly_json["zone_id"]),
                    anomaly_json["effects"],
                    datetime.strptime(anomaly_json["expire_date"], Anomaly.DATE_FORMAT),
                )
        return self.ANOMALY["current"]

    def update_anomaly(self, anomaly: Anomaly):
        self.ANOMALY["current"] = anomaly
        save_json_to_file(self.ANOMALY_FILENAME, anomaly.get_json())

    # notice board ----

    NOTICE_BOARD: list[str] = []
    NOTICE_BOARD_MAX_SIZE: int = 20
    NOTICE_BOARD_MAX_MESSAGE_LENGTH: int = 240

    def get_message_board(self) -> list[str]:
        return self.NOTICE_BOARD

    def update_notice_board(self, author: Player, message: str) -> bool:
        if len(message) > self.NOTICE_BOARD_MAX_SIZE:
            return False
        self.NOTICE_BOARD.append(f"{author.name}:\n{message}")
        if len(self.NOTICE_BOARD) > self.NOTICE_BOARD_MAX_SIZE:
            self.NOTICE_BOARD.pop(0)
        return True

    # pets

    def __build_pet(self, ps: PetModel) -> Pet:
        enemy_meta = self.get_enemy_meta(ps.enemy_type)
        return Pet(
            ps.id,
            ps.name,
            enemy_meta,
            ps.level,
            ps.xp,
            ps.hp_percent,
            ps.stats_seed,
            decode_modifiers(ps.modifiers)
        )

    def get_pet_from_id(self, pet_id: int) -> Pet | None:
        try:
            ps = PetModel.get(PetModel.id == pet_id)
            return self.__build_pet(ps)
        except PetModel.DoesNotExist:
            raise KeyError(f"Could not find pet with id {pet_id}")

    @cache_sized_ttl_quick(size_limit=100, ttl=3600)
    def get_player_pets(self, player_id: int) -> list[Pet]:
        try:
            ps = PlayerModel.get(PlayerModel.id == player_id).pets
            return [self.__build_pet(x) for x in ps]
        except PlayerModel.DoesNotExist:
            raise KeyError(f"Could not find player with id {player_id}")
        except PetModel.DoesNotExist:
            return []

    @_thread_safe()
    def update_pet(self, pet: Pet, owner: Player) -> None:
        try:
            with db.atomic():
                ps: PetModel = PetModel.get(PetModel.id == pet.id)
                ps.name = pet.name
                ps.enemy_type = pet.meta.meta_id
                ps.owner = owner.player_id
                ps.level = pet.level
                ps.xp = pet.xp
                ps.hp_percent = pet.hp_percent
                ps.stats_seed = pet.stats_seed
                ps.modifiers = encode_modifiers(pet.modifiers)
                ps.save()
        except PetModel.DoesNotExist:
            raise KeyError(f"Could not find pet with id {pet.id}")

    @_thread_safe()
    def add_pet(self, pet: Pet, owner: Player) -> int:
        with db.atomic():
            item = PetModel.create(
                name=pet.name,
                enemy_type=pet.meta.meta_id,
                owner=owner.player_id,
                level=pet.level,
                xp=pet.xp,
                hp_percent=pet.hp_percent,
                stats_seed=pet.stats_seed,
                modifiers=encode_modifiers(pet.modifiers)
            )
            return item.id

    @_thread_safe()
    def delete_pet(self, pet: Pet) -> None:
        try:
            with db.atomic():
                PetModel.get(PetModel.id == pet.id).delete_instance()
        except PetModel.DoesNotExist:
            raise KeyError(f"Could not find pet with id {pet.id} to delete")

    # utility functions ----

    @_thread_safe()
    def reset_caches(self):
        log.info("Recreating DB Singleton instance")
        self.__class__._instance = self.__class__.__new__(self.__class__)
        self.__class__._instance.is_connected = False
        log.info("DB Instance recreated successfully")
