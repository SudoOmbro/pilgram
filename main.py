import logging
import sys
import threading
import time
from time import sleep
from datetime import timedelta

from orm.db import PilgramORMDatabase
from pilgram.generics import PilgramDatabase, PilgramNotifier
from pilgram.globals import GlobalSettings
from pilgram.manager import QuestManager, GeneratorManager
from ui.admin_cli import ADMIN_INTERPRETER
from ui.telegram_bot import PilgramBot
from ui.utils import UserContext

INTERVAL = 3600
UPDATE_INTERVAL = timedelta(hours=6)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
log.addHandler(logging.StreamHandler(sys.stderr))


def run_quest_manager(database: PilgramDatabase, notifier: PilgramNotifier):
    log.info("Running quest manager")
    quest_manager = QuestManager(database, notifier, UPDATE_INTERVAL)
    while True:
        updates = quest_manager.get_updates()
        for update in updates:
            quest_manager.process_update(update)
            sleep(0.1)
        sleep(INTERVAL)


def run_generator_manager(database: PilgramDatabase):
    log.info("Running generator manager")
    generator_manager = GeneratorManager(database)
    while True:
        # TODO generate new quests & events with generator_manager
        sleep(INTERVAL)


def run_admin_cli():
    print("Admin CLI active!")
    user_context: UserContext = UserContext({"id": 69, "username": "God"})
    while True:
        command: str = input()
        result: str = ADMIN_INTERPRETER.context_aware_execute(user_context, command)
        print(result)


def main():
    bot = PilgramBot(GlobalSettings.get("Telegram bot token"))
    database = PilgramORMDatabase
    threads = [
        threading.Thread(target=lambda: run_quest_manager(database, bot), name="quest-manager"),
        threading.Thread(target=lambda: run_generator_manager(database), name="generator-manager"),
        threading.Thread(target=run_admin_cli, name="admin-CLI"),
    ]
    for thread in threads:
        thread.start()
    bot.run()
    bot.stop()


if __name__ == '__main__':
    main()
