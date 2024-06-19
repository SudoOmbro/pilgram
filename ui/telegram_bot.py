import asyncio
import logging
from typing import Tuple
from urllib.parse import quote

import requests
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import TelegramError

from pilgram.classes import Player
from pilgram.generics import PilgramNotifier
from pilgram.globals import ContentMeta, GlobalSettings
from pilgram.utils import read_text_file, TempIntCache
from ui.functions import USER_COMMANDS, USER_PROCESSES
from ui.interpreter import CLIInterpreter
from ui.utils import UserContext
from ui.strings import Strings

log = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

DEV_NAME = GlobalSettings.get('dev contacts.telegram')
INFO_STRING = f"Made with ❤️ by {DEV_NAME}\n\n" + "\n\n".join(f"[{name}]({link})" for name, link in GlobalSettings.get("links").items())
START_STRING = read_text_file("intro.txt").format(wn=ContentMeta.get("world.name"), mn=ContentMeta.get("money.name"))


async def notify(bot: Bot, player: Player, text: str):
    try:
        await bot.send_message(player.player_id, text, parse_mode=ParseMode.MARKDOWN)
    except TelegramError as e:
        log.error(f"An error occurred while trying to notify user {player.player_id} ({player.name}): {e}")


def get_event_notification_string(event: dict) -> Tuple[str, Player]:
    return {
        "donation": lambda: (Strings.donation_received.format(donor=event["donor"].name, amm=event["amount"]), event["recipient"]),
        "player kicked": lambda: (Strings.you_have_been_kicked.format(guild=event["guild"].name), event["player"]),
        "guild joined": lambda: (Strings.player_joined_your_guild.format(player=event["player"].name, guild=event["guild"].name), event["guild"].founder),
    }.get(event["type"])()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Telegram unhandled exception encountered:", exc_info=context.error)


async def start(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(chat_id=update.effective_chat.id, text=START_STRING, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def info(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(chat_id=update.effective_chat.id, text=INFO_STRING, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


def _delimit_markdown_entities(text: str) -> str:
    result = text
    for char in ["_", "*"]:
        result = result.replace(char, f"\\{char}")
    return result


class PilgramBot(PilgramNotifier):

    def __init__(self, bot_token: str):
        self.__token: str = bot_token
        self.__app = ApplicationBuilder().token(bot_token).build()
        self.__app.add_handler(CommandHandler("start", start))
        self.__app.add_handler(CommandHandler("info", info))
        self.__app.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        self.__app.add_error_handler(error_handler)
        self.process_cache = TempIntCache()
        self.interpreter = CLIInterpreter(USER_COMMANDS, USER_PROCESSES, help_formatting="`{c}`{a}- _{d}_\n\n")

    def get_user_context(self, update: Update) -> Tuple[UserContext, bool]:
        user_id: int = update.effective_user.id
        cached_value = self.process_cache.get(user_id)
        if cached_value:
            return cached_value, True
        return UserContext({
            "id": user_id,
            "username": _delimit_markdown_entities(update.effective_user.username if update.effective_user.username else update.effective_user.name),
        }), False

    async def handle_message(self, update: Update, c: ContextTypes.DEFAULT_TYPE):
        if (update.message is None) or (update.message.text is None):
            log.error(f"Invalid update received: {update}")
            await c.bot.send_message(chat_id=update.effective_chat.id, text=f"An error occurred while trying to handle your message, try again")
            return
        user_context, was_cached = self.get_user_context(update)
        try:
            result = self.interpreter.context_aware_execute(user_context, update.message.text)
            if (result is None) or (result == ""):
                result = f"The dev forgot to put a message here, report to {DEV_NAME}"
            event = user_context.get_event_data()
            if event:
                # if an event happened notify the target
                string, target = get_event_notification_string(event)
                await notify(c.bot, target, string)
            if user_context.is_in_a_process():
                # if user is in a process then save the context to use later
                self.process_cache.set(update.effective_user.id, user_context)
            elif was_cached:
                # if the context was retrieved from cache and the process is finished then remove context from cache
                self.process_cache.drop(update.effective_user.id)
            try:
                await c.bot.send_message(chat_id=update.effective_chat.id, text=result, parse_mode=ParseMode.MARKDOWN)
            except TelegramError as e:
                if e.message.startswith("Can't parse entities"):
                    # if the message sending fails because of a markdown error, try sending it again without markdown
                    log.error(f"Markdown error: {e.message} in message: '{result}'")
                    await c.bot.send_message(chat_id=update.effective_chat.id, text=result)
                    return
                # if was not a markdown error then raise it again and let the main error handler handle it
                raise e
        except TelegramError as e:
            log.error(f"TelegramError encountered while executing '{update.message}' for user with id {update.effective_user.id} {e.message}")
        except Exception as e:
            await c.bot.send_message(chat_id=update.effective_chat.id, text=f"An error occured: {str(e)}.\n\nContact the developer: {DEV_NAME}")
            log.exception(e)

    def notify(self, player: Player, text: str):
        try:
            chat_id = player.player_id
            url = f"https://api.telegram.org/bot{self.__token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={quote(text)}"
            return requests.get(url).json()
        except Exception as e:
            log.error(f"An error occurred while trying to notify user {player.player_id} ({player.name}): {e}")

    def get_bot(self) -> Bot:
        return self.__app.bot

    def run(self):
        self.__app.run_polling()

    def stop(self):
        self.__app.stop()
