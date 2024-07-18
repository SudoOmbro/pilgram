import logging
import os
from datetime import datetime, timedelta
from time import sleep
from typing import Dict, Callable

from peewee import IntegerField, DateTimeField, AutoField, CharField, ForeignKeyField, FloatField, FixedCharField

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


__OLD_DATABASE_VERSIONS: Dict[str, Callable] = {}


def __add_to_migration_list(db_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        __OLD_DATABASE_VERSIONS[db_name] = func
        return func
    return decorator


# check if older db versions exist
def migrate_older_dbs() -> bool:
    for filename, migration_function in __OLD_DATABASE_VERSIONS.items():
        if os.path.isfile(filename):
            log.info(f"Starting migration...")
            migration_function()
            return True
    return False


@__add_to_migration_list("pilgram.db")
def __migrate_v0_to_v1():
    from playhouse.migrate import SqliteMigrator, migrate
    from ._models_v0 import db as previous_db, BaseModel, PlayerModel

    class ArtifactModel(BaseModel):
        id = AutoField(primary_key=True)
        name = CharField(null=False, unique=True)
        description = CharField(null=False)
        owner = ForeignKeyField(PlayerModel, backref="artifacts", index=True, null=True)

    log.info(f"Migrating v0 to v1...")
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
    log.info(f"Migrating v1 to v2...")
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
    log.info(f"Migrating v2 to v3...")
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
    from ._models_v3 import db as previous_db, BaseModel, PlayerModel, ZoneModel

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

    log.info(f"Migrating v3 to v4...")
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
    log.info(f"Migrating v4 to v5...")
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
    log.info(f"Migrating v5 to v6...")
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
