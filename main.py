from asyncio import sleep, gather
from datetime import timedelta

from orm.db import PilgramORMDatabase
from pilgram.generics import PilgramDatabase, PilgramNotifier
from pilgram.globals import GlobalSettings
from pilgram.manager import QuestManager, GeneratorManager
from ui.telegram_bot import PilgramBot


INTERVAL = 3600
UPDATE_INTERVAL = timedelta(hours=6)


async def run_quest_manager(database: PilgramDatabase, notifier: PilgramNotifier):
    quest_manager = QuestManager(database, notifier, UPDATE_INTERVAL)
    while True:
        updates = quest_manager.get_updates()
        for update in updates:
            quest_manager.process_update(update)
            await sleep(0.1)
        await sleep(INTERVAL)


async def run_generator_manager(database: PilgramDatabase):
    generator_manager = GeneratorManager(database)
    while True:
        # TODO generate new quests & events with generator_manager
        await sleep(INTERVAL)


def main():
    bot = PilgramBot(GlobalSettings.get("Telegram bot token"))
    database = PilgramORMDatabase
    gather(run_quest_manager(database, bot), run_generator_manager(database), bot.run())
    bot.stop()


if __name__ == '__main__':
    main()
