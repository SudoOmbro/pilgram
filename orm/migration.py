import logging
import os
from collections.abc import Callable
from datetime import datetime, timedelta

from peewee import (
    AutoField,
    CharField,
    DateTimeField,
    FixedCharField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    DeferredForeignKey
)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


__OLD_DATABASE_VERSIONS: dict[str, Callable] = {}


def __add_to_migration_list(db_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        __OLD_DATABASE_VERSIONS[db_name] = func
        return func
    return decorator


# check if older db versions exist
def migrate_older_dbs() -> bool:
    for filename, migration_function in __OLD_DATABASE_VERSIONS.items():
        if os.path.isfile(filename):
            log.info("Starting migration...")
            migration_function()
            return True
    return False


@__add_to_migration_list("pilgram.db")
def __migrate_v0_to_v1():
    from playhouse.migrate import SqliteMigrator, migrate

    from ._models_v0 import BaseModel, PlayerModel
    from ._models_v0 import db as previous_db

    class ArtifactModel(BaseModel):
        id = AutoField(primary_key=True)
        name = CharField(null=False, unique=True)
        description = CharField(null=False)
        owner = ForeignKeyField(PlayerModel, backref="artifacts", index=True, null=True)

    log.info("Migrating v0 to v1...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'last_spell_cast', DateTimeField(default=datetime.now)),
        migrator.add_column('playermodel', 'artifact_pieces', IntegerField(default=0)),
        migrator.add_column('playermodel', 'flags', IntegerField(default=0))
    )
    previous_db.create_tables([ArtifactModel])
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram.db", "pilgram_v1.db")


@__add_to_migration_list("pilgram_v1.db")
def __migrate_v1_to_v2():
    from playhouse.migrate import SqliteMigrator, migrate

    from ._models_v1 import db as previous_db
    log.info("Migrating v1 to v2...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'renown', IntegerField(default=0)),
        migrator.add_column('guildmodel', 'tourney_score', IntegerField(default=0)),
        migrator.add_column('guildmodel', 'tax', IntegerField(default=5))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v1.db", "pilgram_v2.db")


@__add_to_migration_list("pilgram_v2.db")
def __migrate_v2_to_v3():
    from playhouse.migrate import SqliteMigrator, migrate

    from ._models_v2 import db as previous_db
    log.info("Migrating v2 to v3...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'cult_id', IntegerField(default=0))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v2.db", "pilgram_v3.db")


@__add_to_migration_list("pilgram_v3.db")
def __migrate_v3_to_v4():
    from playhouse.migrate import SqliteMigrator, migrate

    from ._models_v3 import BaseModel, PlayerModel, ZoneModel
    from ._models_v3 import db as previous_db

    class EquipmentModel(BaseModel):
        id = AutoField(primary_key=True)
        name = CharField(null=False, max_length=50)
        equipment_type = IntegerField(null=False)
        owner = ForeignKeyField(PlayerModel, backref="equipment", index=True)
        damage_seed = FloatField(null=False)
        modifiers = CharField(null=False, default="")

    class EnemyTypeModel(BaseModel):
        id = AutoField(primary_key=True)
        zone_id = ForeignKeyField(ZoneModel, backref="enemies", index=True, null=False)
        name = CharField(null=False, unique=True)
        description = CharField(null=False)
        win_text = CharField(null=False)
        lose_text = CharField(null=False)

    log.info("Migrating v3 to v4...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'hp_percent', FloatField(null=False, default=1.0)),
        migrator.add_column('playermodel', 'satchel', CharField(null=False, default="")),
        migrator.add_column('playermodel', 'equipped_items', CharField(null=False, default="")),
        # can't add constraints to SQLite Databases :(
        # migrator.add_constraint('playermodel', 'name', max_length=40),
        # migrator.add_constraint('playermodel', 'description', max_length=320),
        # migrator.add_constraint('guildmodel', 'name', max_length=40),
        # migrator.add_constraint('guildmodel', 'description', max_length=320)
    )
    previous_db.create_tables([EquipmentModel, EnemyTypeModel])
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v3.db", "pilgram_v4.db")


@__add_to_migration_list("pilgram_v4.db")
def __migrate_v4_to_v5():
    from playhouse.migrate import SqliteMigrator, migrate

    from ._models_v4 import db as previous_db
    log.info("Migrating v4 to v5...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'stance', FixedCharField(max_length=1, default="b")),
        migrator.add_column('playermodel', 'completed_quests', IntegerField(default=0)),
        migrator.add_column('equipmentmodel', 'level', IntegerField(default=1))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v4.db", "pilgram_v5.db")


@__add_to_migration_list("pilgram_v5.db")
def __migrate_v5_to_v6():
    from playhouse.migrate import SqliteMigrator, migrate

    from ._models_v5 import db as previous_db
    log.info("Migrating v5 to v6...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('zonemodel', 'damage_json', CharField(null=False, default="{}")),
        migrator.add_column('zonemodel', 'resist_json', CharField(null=False, default="{}")),
        migrator.add_column('zonemodel', 'extra_data_json', CharField(null=False, default="{}")),
        migrator.add_column('playermodel', 'last_guild_switch', DateTimeField(default=datetime.now() - timedelta(days=1)))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v5.db", "pilgram_v6.db")


@__add_to_migration_list("pilgram_v6.db")
def __migrate_v6_to_v7():
    from ._models_v6 import BaseModel, EquipmentModel, PlayerModel
    from ._models_v6 import db as previous_db

    class AuctionModel(BaseModel):
        id = AutoField(primary_key=True)
        auctioneer_id = ForeignKeyField(PlayerModel, backref="auctions", index=True, null=False)
        item_id = ForeignKeyField(EquipmentModel, null=False)
        best_bidder_id = ForeignKeyField(PlayerModel, index=True, null=True, default=None)
        best_bid = IntegerField(null=False, default=0)
        creation_date = DateTimeField(default=datetime.now)

    log.info("Migrating v6 to v7...")
    previous_db.connect()
    previous_db.create_tables([AuctionModel])
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v6.db", "pilgram_v7.db")


@__add_to_migration_list("pilgram_v7.db")
def __migrate_v7_to_v8():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v7 import PlayerModel
    from ._models_v7 import db as previous_db
    log.info("Migrating v7 to v8...")
    previous_db.connect()
    with previous_db.atomic():
        for ps in PlayerModel.select():
            ps.cult_id = 0
            ps.save()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'vocation_progress', CharField(null=False, default="")),
        migrator.rename_column('playermodel', 'cult_id', 'vocations')
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v7.db", "pilgram_v8.db")


@__add_to_migration_list("pilgram_v8.db")
def __migrate_v8_to_v9():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v8 import db as previous_db
    log.info("Migrating v8 to v9...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('guildmodel', 'bank', IntegerField(default=0))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v8.db", "pilgram_v9.db")


@__add_to_migration_list("pilgram_v9.db")
def __migrate_v9_to_v10():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v9 import db as previous_db
    log.info("Migrating v9 to v10...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'sanity', IntegerField(default=100))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v9.db", "pilgram_v10.db")


@__add_to_migration_list("pilgram_v10.db")
def __migrate_v10_to_v11():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v10 import db as previous_db
    log.info("Migrating v10 to v11...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('equipmentmodel', 'rerolls', IntegerField(default=0))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v10.db", "pilgram_v11.db")


@__add_to_migration_list("pilgram_v11.db")
def __migrate_v11_to_v12():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v11 import db as previous_db
    log.info("Migrating v11 to v12...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('playermodel', 'ascension', IntegerField(default=0)),
        migrator.add_column('playermodel', 'vitality', IntegerField(default=1)),
        migrator.add_column('playermodel', 'strength', IntegerField(default=1)),
        migrator.add_column('playermodel', 'skill', IntegerField(default=1)),
        migrator.add_column('playermodel', 'toughness', IntegerField(default=1)),
        migrator.add_column('playermodel', 'attunement', IntegerField(default=1)),
        migrator.add_column('playermodel', 'mind', IntegerField(default=1)),
        migrator.add_column('playermodel', 'agility', IntegerField(default=1)),
        migrator.add_column('playermodel', 'essences', CharField(null=False, default="")),
        migrator.add_column('playermodel', 'max_level_reached', IntegerField(default=0)),
        migrator.add_column('playermodel', 'max_money_reached', IntegerField(default=0)),
        migrator.add_column('playermodel', 'max_renown_reached', IntegerField(default=0))
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v11.db", "pilgram_v12.db")
    from .models import db, PlayerModel
    db.connect()
    with db.atomic():
        for ps in PlayerModel.select():
            ps.max_level_reached = ps.level
            ps.max_money_reached = ps.money
            ps.max_renown_reached = ps.renown
            ps.equipped_items = ""
            ps.save()
    db.commit()
    db.close()


@__add_to_migration_list("pilgram_v12.db")
def __migrate_v12_to_v13():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v12 import db as previous_db
    log.info("Migrating v12 to v13...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('guildmodel', 'last_raid', DateTimeField(default=datetime.now() - timedelta(days=8))),
    )
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v12.db", "pilgram_v13.db")


@__add_to_migration_list("pilgram_v13.db")
def __migrate_v13_to_v14():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v13 import db as previous_db
    from ._models_v13 import BaseModel, PlayerModel, EnemyTypeModel

    class PetModel(BaseModel):
        id = AutoField(primary_key=True)
        name = CharField(null=True, unique=False, default=None)
        enemy_type = ForeignKeyField(EnemyTypeModel, null=False)
        owner = ForeignKeyField(PlayerModel, backref="pets", index=True, null=False)
        level = IntegerField(default=1)
        xp = IntegerField(default=0)
        hp_percent = FloatField(null=False, default=1.0)
        stats_seed = FloatField(null=False)
        modifiers = CharField(null=False, default="")

    log.info("Migrating v13 to v14...")
    previous_db.connect()
    migrator = SqliteMigrator(previous_db)
    migrate(
        migrator.add_column('PlayerModel', 'pet_id', DeferredForeignKey("PetModel", null=True, default=None)),
    )
    previous_db.create_tables([PetModel])
    previous_db.commit()
    previous_db.close()
    os.rename("pilgram_v13.db", "pilgram_v14.db")
