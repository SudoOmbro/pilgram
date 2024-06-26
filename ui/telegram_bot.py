import asyncio
import logging
from typing import Tuple, List, Dict
from urllib.parse import quote

import requests
from telegram import Update, Bot, BotCommand
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import TelegramError, NetworkError

from pilgram.classes import Player
from pilgram.generics import PilgramNotifier
from pilgram.globals import ContentMeta, GlobalSettings
from pilgram.utils import read_text_file, TempIntCache, has_recently_accessed_cache
from ui.functions import USER_COMMANDS, USER_PROCESSES
from ui.interpreter import CLIInterpreter
from ui.utils import UserContext
from pilgram.strings import Strings

log = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

DEV_NAME = GlobalSettings.get('dev contacts.telegram')
INFO_STRING = f"Made with ❤️ by {DEV_NAME}\n\n" + "\n\n".join(f"[{name}]({link})" for name, link in GlobalSettings.get("links").items())
START_STRING = read_text_file("intro.txt").format(wn=ContentMeta.get("world.name"), mn=ContentMeta.get("money.name"))


async def notify_with_id(bot: Bot, player_id: int, text: str):
    try:
        await bot.send_message(player_id, text, parse_mode=ParseMode.MARKDOWN)
    except TelegramError as e:
        log.error(f"An error occurred while trying to notify user {player_id}: {e}")


async def notify(bot: Bot, player: Player, text: str):
    try:
        await bot.send_message(player.player_id, text, parse_mode=ParseMode.MARKDOWN)
    except TelegramError as e:
        log.error(f"An error occurred while trying to notify user {player.player_id} ({player.name}): {e}")


def get_event_notification_string_and_targets(event: dict) -> Tuple[str, Player]:
    return {
        "donation": lambda: (Strings.donation_received.format(donor=event["donor"].print_username(), amm=event["amount"]), event["recipient"]),
        "player kicked": lambda: (Strings.you_have_been_kicked.format(guild=event["guild"].name), event["player"]),
        "guild joined": lambda: (Strings.player_joined_your_guild.format(player=event["player"].print_username(), guild=event["guild"].name), event["guild"].founder),
        "message": lambda: (event["text"].format(name=event["sender"].print_username()), None)
    }.get(event["type"])()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Telegram unhandled exception encountered:", exc_info=context.error)


async def start(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(chat_id=update.effective_chat.id, text=START_STRING, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def info(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(chat_id=update.effective_chat.id, text=INFO_STRING, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


def _delimit_markdown_entities(text: str) -> str:
    result = text
    for char in ["_", "*", "~"]:
        result = result.replace(char, f"\\{char}")
    return result


class PilgramBot(PilgramNotifier):

    def __init__(self, bot_token: str):
        self.__token: str = bot_token
        self.interpreter = CLIInterpreter(USER_COMMANDS, USER_PROCESSES, help_formatting="`{c}`{a}- _{d}_\n\n")
        self.__app = ApplicationBuilder().token(bot_token).build()
        self.__app.add_handler(CommandHandler("start", start))
        self.__app.add_handler(CommandHandler("info", info))
        self.__app.add_handler(CommandHandler("quit", self.quit))
        for command, args, _ in self.interpreter.commands_list:
            self.__app.add_handler(CommandHandler(command, self.handle_message, has_args=args))
        self.__app.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        self.__app.add_error_handler(error_handler)
        self.process_cache = TempIntCache()
        self.storage: Dict[int, float] = {}  # used to avoid message spam

    async def set_bot_commands(self):
        """ Set the commands for the running bot """
        commands: List[BotCommand] = [
            BotCommand("start", "start your adventure and show world lore"),
            BotCommand("info", "shows info about the bot & developer + useful links"),
            BotCommand("quit", "quits any ongoing process / minigame"),
        ]
        commands.extend([BotCommand(command, descr) for command, _, descr in self.interpreter.commands_list])
        await self.get_bot().set_my_commands(commands)
        log.info("Bot commands set")

    def get_user_context(self, update: Update) -> Tuple[UserContext, bool]:
        user_id: int = update.effective_user.id
        cached_value = self.process_cache.get(user_id)
        if cached_value:
            return cached_value, True
        return UserContext({
            "id": user_id,
            "username": _delimit_markdown_entities(update.effective_user.username if update.effective_user.username else update.effective_user.name),
            "env": "telegram"  # should be used to correctly format objects based on the environment
        }), False

    async def quit(self, update: Update, c: ContextTypes.DEFAULT_TYPE):
        if self.process_cache.get(update.effective_user.id):
            self.process_cache.drop(update.effective_user.id)
            await c.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Your context was cleared. Whatever minigame or process you were in, you are not in it anymore.",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await c.bot.send_message(
                chat_id=update.effective_chat.id,
                text="You are not doing anything that requires quitting",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )

    async def handle_message(self, update: Update, c: ContextTypes.DEFAULT_TYPE):
        if (update.message is None) or (update.message.text is None):
            log.error(f"Invalid update received: {update}")
            await c.bot.send_message(chat_id=update.effective_chat.id, text=f"An error occurred while trying to handle your message, try again")
            return
        user_context, was_cached = self.get_user_context(update)
        try:
            # get the commands sent by the user
            command: str = update.message.text
            if command[0] == "/":
                command = update.message.text.lstrip("/").replace("_", " ") + (" " + " ".join(c.args) if c.args else "")
            # execute the command
            result = self.interpreter.context_aware_execute(user_context, command)
            if (result is None) or (result == ""):
                result = f"The dev forgot to put a message here, report to {DEV_NAME}"
            event = user_context.get_event_data()
            if event:
                # if an event happened notify the target
                string, target = get_event_notification_string_and_targets(event)
                if not target:
                    cooldown = (2 + len(event["targets"])) * 2
                    if self.has_sent_a_message_too_recently(update.effective_chat.id, cooldown):
                        result = "You sent too many messages recently! Wait a few minutes then try again."  # override positive result
                    else:
                        await asyncio.create_task(self.notify_group(event["targets"], string))
                        await asyncio.sleep(0)
                else:
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

    async def notify_group(self, player_ids: List[int], text: str, timeout: int = 2):
        """ notify a group of players """
        for player_id in player_ids:
            await notify_with_id(self.get_bot(), player_id, text)
            await asyncio.sleep(timeout)

    def notify(self, player: Player, text: str):
        try:
            chat_id = player.player_id
            url = f"https://api.telegram.org/bot{self.__token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={quote(text)}"
            return requests.get(url).json()
        except Exception as e:
            log.error(f"An error occurred while trying to notify user {player.player_id} ({player.name}): {e}")

    def has_sent_a_message_too_recently(self, user_id: int, cooldown: int) -> bool:
        return has_recently_accessed_cache(self.storage, user_id, cooldown)

    def get_bot(self) -> Bot:
        return self.__app.bot

    def run(self):
        try:
            self.__app.run_polling()
        except NetworkError as e:
            log.error(f"encountered a network error: {str(e)}")

    def stop(self):
        self.__app.stop()
