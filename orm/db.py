import logging
import random
import threading
from datetime import timedelta, datetime
from time import sleep

import numpy as np

from typing import Dict, Union, List, Tuple, Any

from peewee import fn, JOIN

from orm.migration import migrate_older_dbs
from orm.models import db, PlayerModel, GuildModel, ZoneModel, create_tables, ZoneEventModel, QuestModel, \
    QuestProgressModel, ArtifactModel, EquipmentModel, EnemyTypeModel
from pilgram.classes import Player, Progress, Guild, Zone, ZoneEvent, Quest, AdventureContainer, Artifact, Cult, \
    Tourney, EnemyMeta
from pilgram.combat_classes import Modifier
from pilgram.equipment import ConsumableItem, Equipment, EquipmentType
from pilgram.generics import PilgramDatabase, AlreadyExists
from orm.utils import cache_ttl_quick, cache_sized_ttl_quick, cache_ttl_single_value
from pilgram.modifiers import get_modifier

log = logging.getLogger(__name__)

_LOCK = threading.Lock()

NP_ED = np.dtype([('slot', np.uint8), ('id', np.uint32)])  # stands for 'numpy equipment data'
NP_MD = np.dtype([('id', np.uint16), ('strength', np.uint32)])  # stands for 'numpy modifiers data'


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
    unpacked_array = np.frombuffer(encoded_data, dtype=np.uint16).reshape((len(data) >> 2, 2))
    for zone_id, progress in unpacked_array:
        progress_dictionary[zone_id.item()] = progress.item()
    return progress_dictionary


def encode_progress(data: Dict[int, int]) -> bytes:
    """ encodes the data dictionary contained in the progress object to a bytestring that can be saved on the db """
    dict_size = len(data)
    packed_array = np.empty(dict_size << 1, np.uint16)
    for i, (zone_id, progress) in enumerate(data.items()):
        j = i << 1
        packed_array[j] = zone_id
        packed_array[j + 1] = progress
    return packed_array.tobytes()


def decode_satchel(data: str) -> List[ConsumableItem]:
    result: List[ConsumableItem] = []
    if not data:
        return result
    encoded_data = bytes(data, "UTF-8")
    unpacked_array = np.frombuffer(encoded_data, dtype=np.uint8)
    for consumable_id in unpacked_array:
        result.append(ConsumableItem.get(consumable_id.item()))
    return result


def encode_satchel(satchel: List[ConsumableItem]) -> bytes:
    packed_array = np.empty(len(satchel), np.uint8)
    for i, consumable in enumerate(satchel):
        packed_array[i] = consumable.consumable_id
    return packed_array.tobytes()


def decode_equipped_items_ids(data: Union[str]) -> Dict[int, int]:
    encoded_data = bytes(data, "UTF-8")
    equipment_dictionary: Dict[int, int] = {}
    for item in np.frombuffer(encoded_data, dtype=NP_ED):
        equipment_dictionary[item["slot"].item()] = item["id"].item()
    return equipment_dictionary


def encode_equipped_items(equipped_items: Dict[int, Equipment]) -> bytes:
    packed_array = np.empty(int(len(equipped_items)), NP_ED)
    for i, (slot, equipment) in enumerate(equipped_items.items()):
        packed_array[i]["slot"] = slot
        packed_array[i]["id"] = equipment.equipment_id
    return packed_array.tobytes()


def decode_modifiers(data: Union[str, None]) -> List[Modifier]:
    encoded_data = bytes(data, "UTF-8")
    modifiers_list: List[Modifier] = []
    for item in np.frombuffer(encoded_data, dtype=NP_MD):
        modifiers_list.append(get_modifier(item["id"].item(), item["strength"].item()))
    return modifiers_list


def encode_modifiers(modifiers: List[Modifier]) -> bytes:
    packed_array = np.empty(int(len(modifiers)), NP_MD)
    for i, modifier in enumerate(modifiers):
        packed_array[i]["id"] = modifier.ID
        packed_array[i]["strength"] = modifier.strength
    return packed_array.tobytes()


def _thread_safe():
    def decorator(func):
        def wrapper(*args, **kwargs):
            with _LOCK:
                return func(*args, **kwargs)
        return wrapper
    return decorator


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
            pls = PlayerModel.get(PlayerModel.id == player_id)
            guild = self.get_guild(pls.guild.id, calling_player_id=pls.id) if pls.guild else None
            artifacts = self.get_player_artifacts(player_id)
            items = self.get_player_items(player_id)
            equipped_items_ids = decode_equipped_items_ids(pls.equipped_items)
            equipped_items = {}
            for item in items:
                if item.equipment_id in equipped_items_ids:
                    equipped_items[item.equipment_type.slot] = item
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
                Cult.get(pls.cult_id),
                decode_satchel(pls.satchel),
                equipped_items,
                pls.hp_percent,
                pls.stance,
                pls.completed_quests
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

    @_thread_safe()
    def update_player_data(self, player: Player):
        try:
            with db.atomic():
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
                pls.last_spell_cast = player.last_cast
                pls.artifact_pieces = player.artifact_pieces
                pls.flags = player.flags
                pls.renown = player.renown
                pls.cult_id = player.cult.faction_id
                pls.satchel = encode_satchel(player.satchel)
                pls.equipped_items = encode_equipped_items(player.equipped_items)
                pls.hp_percent = player.hp_percent
                pls.stance = player.stance
                pls.completed_quests = player.completed_quests
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
    def rank_top_players(self) -> List[Tuple[str, int]]:
        ps = PlayerModel.select(
            PlayerModel.name, PlayerModel.renown
        ).order_by(PlayerModel.renown.desc()).limit(20).namedtuples()
        return [(player_row.name, player_row.renown) for player_row in ps]

    # guilds ----

    def build_guild_object(self, gs: GuildModel, calling_player_id: Union[int, None]):
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
            gs.tax
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

    @cache_sized_ttl_quick(size_limit=100)
    def get_guild_id_from_founder(self, player: Player) -> int:
        try:
            return GuildModel.get(GuildModel.founder == player.player_id).id
        except GuildModel.DoesNotExist:
            raise KeyError(f'Guild founded by player with id {player.player_id} not found')

    @cache_sized_ttl_quick(size_limit=50, ttl=300)
    def __get_guild_members_data(self, guild_id: int) -> List[Tuple[int, str, int]]:
        """ cache based on the id should work a bit better """
        gms = GuildModel.get(guild_id == GuildModel.id).members
        return [(x.id, x.name, x.level) for x in gms]

    def get_guild_members_data(self, guild: Guild) -> List[Tuple[int, str, int]]:  # id, name, level
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
            gs.save()

    @_thread_safe()
    def add_guild(self, guild: Guild):
        try:
            with db.atomic():
                GuildModel.create(
                    name=guild.name,
                    description=guild.description,
                    founder_id=guild.founder.player_id,
                    creation_date=guild.creation_date,
                    tax=guild.tax
                )
        except Exception as e:
            log.error(e)
            raise AlreadyExists(f"Guild with name {guild.name} already exists")

    @cache_ttl_single_value(ttl=14400)
    def rank_top_guilds(self) -> List[Tuple[str, int]]:
        gs = GuildModel.select(
            GuildModel.name, GuildModel.prestige
        ).order_by(GuildModel.prestige.desc()).limit(20).namedtuples()
        return [(guild_row.name, guild_row.prestige) for guild_row in gs]

    @cache_ttl_quick(ttl=600)
    def get_top_n_guilds_by_score(self, n: int) -> List[Guild]:
        gs = GuildModel.select().order_by(GuildModel.tourney_score.desc()).limit(n)
        return [self.build_guild_object(g, None) for g in gs]

    def reset_all_guild_scores(self):
        gs = GuildModel.select()
        for g in gs:
            g.tourney_score = 0
            g.save()

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

    @_thread_safe()
    def update_zone(self, zone: Zone):  # this will basically never be called, but it's good to have
        zs = ZoneModel.get(ZoneModel.id == zone.zone_id)
        if not zs:
            raise KeyError(f"Could not find zone with id {zone.zone_id}")
        with db.atomic():
            zs.name = zone.zone_name
            zs.level = zone.level
            zs.description = zone.zone_description
            zs.save()

    @_thread_safe()
    def add_zone(self, zone: Zone):
        with db.atomic():
            ZoneModel.create(
                name=zone.zone_name,
                level=zone.level,
                description=zone.zone_description
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
    def add_zone_events(self, events: List[ZoneEvent]):
        data_to_insert = [{"zone_id": e.zone.zone_id if e.zone else 0, "event_text": e.event_text} for e in events]
        with db.atomic():
            ZoneEventModel.insert_many(data_to_insert).execute()

    # quests ----

    def build_quest_object(self, qs: QuestModel, zone: Union[Zone, None] = None) -> Quest:
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

    def build_adventure_container(self, qps: QuestProgressModel, owner: Union[Player, None] = None) -> AdventureContainer:
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
            with db.atomic():
                qps = QuestProgressModel.get(QuestProgressModel.player_id == adventure_container.player_id())
                qps.quest_id = adventure_container.quest_id()
                # stagger updates using randomness
                qps.last_update = datetime.now() + timedelta(minutes=random.randint(0, 40)) if last_update is None else last_update
                qps.end_time = adventure_container.finish_time
                qps.save()
        except QuestProgressModel.DoesNotExist:
            raise KeyError(f"Could not find quest progress for player with id {adventure_container.player_id()}")

    @cache_sized_ttl_quick(size_limit=200, ttl=86400)
    def get_artifact(self, artifact_id: int) -> Artifact:
        try:
            arse = ArtifactModel.get(ArtifactModel.id == artifact_id)
            return Artifact(arse.id, arse.name, arse.description, self.get_player_data(arse.owner_id) if arse.owner_id else None)
        except ArtifactModel.DoesNotExist:
            raise KeyError(f"Could not find any artifact with id {artifact_id}")

    @cache_sized_ttl_quick(size_limit=200, ttl=300)
    def get_player_artifacts(self, player_id: int) -> List[Artifact]:
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
    def add_artifacts(self, artifacts: List[Artifact]):
        data_to_insert: List[Dict[str, Any]] = [
            {
                "name": a.name,
                "description": a.description,
                "owner": None
            } for a in artifacts
        ]
        with db.atomic():
            ArtifactModel.insert_many(data_to_insert).execute()

    @_thread_safe()
    def update_artifact(self, artifact: Artifact, owner: Union[Player, None]):
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
    def get_cults_members_number(self) -> List[Tuple[int, int]]:  # cult id, number of members
        query = (PlayerModel.select(PlayerModel.cult_id, fn.Count(PlayerModel.id).alias('player_count')).
                 group_by(PlayerModel.cult_id).
                 order_by(PlayerModel.cult_id.asc()))
        return [(x.cult_id, x.player_count) for x in query]

    # tourney ----

    @cache_ttl_single_value(ttl=86000)
    def get_tourney(self) -> Tourney:
        return Tourney.load_from_file("tourney.json")

    def update_tourney(self, tourney: Tourney):
        tourney.save()

    # enemy meta ----

    def __build_enemy_meta(self, ems: EnemyTypeModel) -> EnemyMeta:
        return EnemyMeta(
            ems.id,
            self.get_zone(ems.zone_id),
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

    @cache_sized_ttl_quick(size_limit=20, ttl=300)
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
    def get_all_zone_enemies(self, zone: Zone) -> List[EnemyMeta]:
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
        result: List[EnemyMeta] = []
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
        _, damage, resist = Equipment.get_modifiers_and_damage(its.damage_seed, its.level, equipment_type.is_weapon)
        return Equipment(
            its.id,
            its.level,
            equipment_type,
            its.name,
            its.damage_seed,
            damage,
            resist,
            decode_modifiers(its.modifiers)
        )

    def get_item(self, item_id: int) -> Equipment:
        try:
            its = EquipmentModel.get(EquipmentModel.id == item_id)
            return self.__build_item(its)
        except EquipmentModel.DoesNotExist:
            raise KeyError(f"Could not find item with id {item_id}")

    def get_player_items(self, player_id: int) -> List[Equipment]:
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
                its = EquipmentModel.get(EquipmentModel.id == item.equipment_id)
                its.owner = owner.player_id
                its.name = item.name
                its.save()
        except EquipmentModel.DoesNotExist:
            raise KeyError(f"Could not find item with id {item.equipment_id}")

    @_thread_safe()
    def add_item(self, item: Equipment, owner: Player):
        with db.atomic():
            EquipmentModel.create(
                name=item.name,
                owner=owner.player_id,
                level=item.level,
                equipment_type=item.equipment_type.equipment_type_id,
                damage_seed=item.seed,
                modifiers=encode_modifiers(item.modifiers)
            )
