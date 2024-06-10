from asyncio import sleep, run, gather
from datetime import timedelta

from orm.db import PilgramORMDatabase
from pilgram.generics import PilgramDatabase, PilgramNotifier
from pilgram.globals import GlobalSettings
from pilgram.manager import QuestManager, GeneratorManager
from ui.telegram_bot import PilgramBot


INTERVAL = 3600
UPDATE_INTERVAL = timedelta(hours=6)


async def run_periodically(database: PilgramDatabase, notifier: PilgramNotifier):
    quest_manager = QuestManager(database, notifier, UPDATE_INTERVAL)
    generator_manager = GeneratorManager(database)
    while True:
        updates = quest_manager.get_updates()
        for update in updates:
            quest_manager.process_update(update)
            await sleep(0.1)
        # TODO generate new quests and zone events with the GeneratorManager
        await sleep(INTERVAL)


def main():
    bot = PilgramBot(GlobalSettings.get("Telegram bot token"))
    database = PilgramORMDatabase
    gather(run_periodically(database, bot), bot.run())
    bot.stop()


if __name__ == '__main__':
    main()
