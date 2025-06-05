import asyncio
import logging
import sys
import threading

from AI.chatgpt import ChatGPTAPI, ChatGPTGenerator
from orm.db import PilgramORMDatabase
from pilgram.generics import PilgramDatabase, PilgramNotifier
from pilgram.globals import GlobalSettings
from pilgram.manager import (
    GeneratorManager,
    QuestManager,
    TimedUpdatesManager,
    TourneyManager,
    NotificationsManager,
)
from pilgram.utils import read_update_interval
from ui.admin_cli import ADMIN_INTERPRETER
from ui.telegram_bot import PilgramBot
from ui.utils import UserContext

INTERVAL = GlobalSettings.get("thread interval")
UPDATE_INTERVAL = read_update_interval(GlobalSettings.get("update interval"))

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
log.addHandler(logging.StreamHandler(sys.stderr))

kill_signal = threading.Event()


def is_killed(sleep_interval: float):
    killed = kill_signal.wait(sleep_interval)
    return killed


def kill_all_threads():
    kill_signal.set()


def run_quest_manager(database: PilgramDatabase):
    log.info("Running quest manager")
    quest_manager = QuestManager(database, UPDATE_INTERVAL)
    # offset the starting of the process by half the interval so that the threads don't run at the same time.
    if is_killed(INTERVAL / 2):
        return
    while True:
        log.info("Quest manager update")
        try:
            quest_manager.run()
            if is_killed(INTERVAL):
                return
        except Exception as e:
            log.exception(f"error in quest manager thread: {e}")
            if is_killed(INTERVAL):
                return


def run_generator_manager(database: PilgramDatabase):
    log.info("Running generator manager")
    generator_manager = GeneratorManager(
        database,
        ChatGPTGenerator(ChatGPTAPI(
            GlobalSettings.get("ChatGPT token"),
            "gpt-4o-mini"
        ))
    )
    while True:
        try:
            log.info("Generator manager update")
            generator_manager.run(1)
            if is_killed(INTERVAL):
                return
        except Exception as e:
            log.exception(f"error in generator manager thread: {e}")
            if is_killed(INTERVAL):
                return


def run_tourney_manager(database: PilgramDatabase):
    log.info("Running tourney manager")
    tourney_manager = TourneyManager(database, 1)
    interval = INTERVAL * 4
    if is_killed(INTERVAL / 8):
        return
    while True:
        try:
            log.info("tourney manager update")
            tourney_manager.run()
            if is_killed(interval):
                return
        except Exception as e:
            log.exception(f"error in tourney manager thread: {e}")
            if is_killed(INTERVAL):
                return


def run_updates_manager(database: PilgramDatabase):
    log.info("Running updates manager")
    updates_manager = TimedUpdatesManager(database)
    if is_killed(INTERVAL / 6):
        return
    while True:
        try:
            log.info("updates manager update")
            updates_manager.run()
            if is_killed(INTERVAL):
                return
        except Exception as e:
            log.exception(f"error in updates manager thread: {e}")
            if is_killed(INTERVAL):
                return


def run_notifications_manager(database: PilgramDatabase, notifier: PilgramNotifier):
    log.info("Running notifications manager")
    notifications_manager = NotificationsManager(notifier, database)
    notifications_manager.load_pending_notifications()
    if is_killed(5):
        notifications_manager.save_pending_notifications()
        return
    while True:
        try:
            notifications_manager.run()
            if is_killed(5):
                notifications_manager.save_pending_notifications()
                return
        except Exception as e:
            log.exception(f"error in updates manager thread: {e}")
            if is_killed(30):
                notifications_manager.save_pending_notifications()
                return


def run_admin_cli():
    print("Admin CLI active!")
    user_context: UserContext = UserContext({"id": 69, "username": "God"})
    while True:
        try:
            command = input()  # this is blocking & causes the thread to never finish if joined.
            result: str = ADMIN_INTERPRETER.context_aware_execute(user_context, command)
            print(result)
            if kill_signal.is_set():
                return
        except EOFError:
            # silence all EOF errors
            if is_killed(5):
                # sleep for 5 seconds to avoid flooding the thread with exceptions
                return
        except Exception as e:
            log.error(f"error in admin CLI thread: {e}")
            print(e)


def main():
    bot = PilgramBot(GlobalSettings.get("Telegram bot token"))
    asyncio.run_coroutine_threadsafe(bot.set_bot_commands(), asyncio.get_event_loop())  # this seems to work, even if it's being deprecated, so whatever, it's fine
    database = PilgramORMDatabase
    threads = [
        threading.Thread(target=lambda: run_quest_manager(database), name="quest-manager"),
        threading.Thread(target=lambda: run_generator_manager(database), name="generator-manager"),
        threading.Thread(target=lambda: run_tourney_manager(database), name="tourney-manager"),
        threading.Thread(target=lambda: run_updates_manager(database), name="updates-manager"),
        threading.Thread(target=lambda: run_notifications_manager(database, bot), name="notifications-manager")
    ]
    cli_thread = threading.Thread(target=run_admin_cli, name="admin-CLI", daemon=True)
    for thread in threads:
        thread.start()
    cli_thread.start()
    # not joining the CLI thread is the only way I found to close the program "gracefully" (no SIGKILL).
    # It still causes a Fatal Python error and ends with 134, but since it only happens at program termination... 🤷‍♂️
    bot.run()
    bot.stop()
    kill_all_threads()
    for thread in threads:
        thread.join()


if __name__ == '__main__':
    main()
