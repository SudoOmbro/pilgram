import logging
import sys
import threading
from time import sleep

from AI.chatgpt import ChatGPTGenerator, ChatGPTAPI
from orm.db import PilgramORMDatabase
from pilgram.generics import PilgramDatabase, PilgramNotifier
from pilgram.globals import GlobalSettings
from pilgram.manager import QuestManager, GeneratorManager
from pilgram.utils import read_update_interval
from ui.admin_cli import ADMIN_INTERPRETER
from ui.telegram_bot import PilgramBot
from ui.utils import UserContext

INTERVAL = GlobalSettings.get("thread interval")
UPDATE_INTERVAL = read_update_interval(GlobalSettings.get("update interval"))

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
log.addHandler(logging.StreamHandler(sys.stderr))


def run_quest_manager(database: PilgramDatabase, notifier: PilgramNotifier):
    log.info("Running quest manager")
    quest_manager = QuestManager(database, notifier, UPDATE_INTERVAL)
    sleep(INTERVAL / 2)  # offset the starting of the process by half the interval so that the threads don't run at the same time.
    while True:
        log.info("Quest manager update")
        try:
            updates = quest_manager.get_updates()
            for update in updates:
                quest_manager.process_update(update)
                sleep(0.1)
            sleep(INTERVAL)
        except Exception as e:
            log.error(f"error in quest manager thread: {e}")


def run_generator_manager(database: PilgramDatabase):
    log.info("Running generator manager")
    generator_manager = GeneratorManager(
        database,
        ChatGPTGenerator(ChatGPTAPI(
            GlobalSettings.get("ChatGPT token"),
            "gpt-3.5-turbo"
        ))
    )
    while True:
        try:
            log.info("Generator manager update")
            generator_manager.run(1)
            sleep(INTERVAL)
        except Exception as e:
            log.error(f"error in generator manager thread: {e}")


def run_admin_cli():
    print("Admin CLI active!")
    user_context: UserContext = UserContext({"id": 69, "username": "God"})
    while True:
        try:
            command: str = input()
            result: str = ADMIN_INTERPRETER.context_aware_execute(user_context, command)
            print(result)
        except Exception as e:
            log.error(f"error in admin CLI thread: {e}")
            print(e)


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
