import asyncio
import logging
from urllib.parse import quote

import requests
from telegram import Bot, BotCommand, Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from pilgram.classes import Player, Notification
from pilgram.generics import PilgramNotifier
from pilgram.globals import ContentMeta, GlobalSettings
from pilgram.utils import TempIntCache, has_recently_accessed_cache, read_text_file
from ui.functions import USER_COMMANDS, USER_PROCESSES, ALIASES
from ui.interpreter import CLIInterpreter
from ui.utils import UserContext

log = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

DEV_NAME = GlobalSettings.get("dev contacts.telegram")
INFO_STRING = f"Made with ❤️ by {DEV_NAME}\n\n" + "\n\n".join(
    f"[{name}]({link})" for name, link in GlobalSettings.get("links").items()
)
START_STRING = read_text_file("intro.txt").format(
    wn=ContentMeta.get("world.name"), mn=ContentMeta.get("money.name")
)
PRIVACY_STRING = read_text_file("privacy.txt")


async def notify_with_id(bot: Bot, player_id: int, text: str):
    try:
        if not len(text) > 4096:
            await bot.send_message(player_id, text, parse_mode=ParseMode.MARKDOWN)
            return
        await bot.send_document(
            player_id,
            document=text.encode(),
            caption="You message was too long, here it is in message form:",
        )
    except TelegramError as e:
        log.error(f"An error occurred while trying to notify user {player_id}: {e}")


async def notify(bot: Bot, player: Player, text: str):
    try:
        await bot.send_message(player.player_id, text, parse_mode=ParseMode.MARKDOWN)
    except TelegramError as e:
        log.error(
            f"An error occurred while trying to notify user {player.player_id} ({player.name}): {e}"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Telegram unhandled exception encountered:", exc_info=context.error)


async def start(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(
        chat_id=update.effective_chat.id,
        text=START_STRING,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def info(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(
        chat_id=update.effective_chat.id,
        text=INFO_STRING,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def privacy(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(
        chat_id=update.effective_chat.id,
        text=PRIVACY_STRING,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def menu(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(
        chat_id=update.effective_chat.id,
        text="TODO",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


def _delimit_markdown_entities(text: str) -> str:
    result = text
    for char in ("_", "*", "~"):
        result = result.replace(char, f"\\{char}")
    return result


class PilgramBot(PilgramNotifier):
    def __init__(self, bot_token: str):
        self.__token: str = bot_token
        self.interpreter = CLIInterpreter(
            USER_COMMANDS,
            USER_PROCESSES,
            help_formatting="`{c}`{a}- _{d}_\n\n",
            aliases=ALIASES
        )
        self.__app = ApplicationBuilder().token(bot_token).build()
        self.__app.add_handler(CommandHandler("start", start))
        self.__app.add_handler(CommandHandler("info", info))
        # self.__app.add_handler(CommandHandler("menu", menu))
        self.__app.add_handler(CommandHandler("privacy", privacy))
        self.__app.add_handler(CommandHandler("quit", self.quit))
        for command, args, _ in self.interpreter.commands_list:
            self.__app.add_handler(
                CommandHandler(command, self.handle_message, has_args=args)
            )
        self.__app.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        self.__app.add_error_handler(error_handler)
        self.process_cache = TempIntCache()
        self.storage: dict[int, float] = {}  # used to avoid message spam

    async def set_bot_commands(self):
        """Set the commands for the running bot"""
        commands: list[BotCommand] = [
            BotCommand("start", "start your adventure and show world lore"),
            BotCommand("info", "shows info about the bot & developer + useful links"),
            BotCommand("quit", "quits any ongoing process / minigame"),
            BotCommand("privacy", "shows privacy & data handling information"),
            # BotCommand("menu", "opens button menu"),
        ]
        commands.extend(
            [
                BotCommand(command, descr)
                for command, _, descr in self.interpreter.commands_list
            ]
        )
        await self.get_bot().set_my_commands(commands)
        log.info("Bot commands set")

    def get_user_context(self, update: Update) -> tuple[UserContext, bool]:
        user_id: int = update.effective_user.id
        cached_value = self.process_cache.get(user_id)
        if cached_value:
            return cached_value, True
        return (
            UserContext(
                {
                    "id": user_id,
                    "username": _delimit_markdown_entities(
                        update.effective_user.username or update.effective_user.name
                    ),
                    "env": "telegram",  # should be used to correctly format objects based on the environment
                }
            ),
            False,
        )

    async def quit(self, update: Update, c: ContextTypes.DEFAULT_TYPE):
        if self.process_cache.get(update.effective_user.id):
            self.process_cache.drop(update.effective_user.id)
            await c.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Your context was cleared. Whatever minigame or process you were in, you are not in it anymore.",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        else:
            await c.bot.send_message(
                chat_id=update.effective_chat.id,
                text="You are not doing anything that requires quitting",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )

    async def handle_message(self, update: Update, c: ContextTypes.DEFAULT_TYPE):
        if (update.message is None) or (update.message.text is None):
            log.error(f"Invalid update received: {update}")
            await c.bot.send_message(
                chat_id=update.effective_chat.id,
                text="An error occurred while trying to handle your message, try again",
            )
            return
        user_context, was_cached = self.get_user_context(update)
        try:
            # get the commands sent by the user
            command: str = update.message.text
            if command[0] == "/":
                command = update.message.text.lstrip("/").replace("_", " ")
            # execute the command
            result = self.interpreter.context_aware_execute(user_context, command)
            if (result is None) or (result == ""):
                result = f"The dev forgot to put a message here, report to {DEV_NAME}"
            if user_context.is_in_a_process():
                # if user is in a process then save the context to use later
                self.process_cache.set(update.effective_user.id, user_context)
            elif was_cached:
                # if the context was retrieved from cache and the process is finished then remove context from cache
                self.process_cache.drop(update.effective_user.id)
            try:
                await c.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=result,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except TelegramError as e:
                if e.message.startswith("Can't parse entities"):
                    # if the message sending fails because of a markdown error, try sending it again without markdown
                    log.error(f"Markdown error: {e.message} in message: '{result}'")
                    await c.bot.send_message(
                        chat_id=update.effective_chat.id, text=result
                    )
                    return
                # if was not a markdown error then raise it again and let the main error handler handle it
                raise e
        except TelegramError as e:
            log.error(
                f"TelegramError encountered while executing '{update.message}' for user with id {update.effective_user.id} {e.message}"
            )
        except Exception as e:
            await c.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"An error occured: {str(e)}.\n\nContact the developer: {DEV_NAME}",
            )
            log.exception(e)

    async def notify_group(self, player_ids: list[int], text: str, timeout: int = 2):
        """notify a group of players"""
        for player_id in player_ids:
            await notify_with_id(self.get_bot(), player_id, text)
            await asyncio.sleep(timeout)

    def notify(self, notification: Notification) -> dict:
        # if notification.target.name != "Ombro":
        #     return {"ok": True}
        if len(notification.text) > 4096:
            log.info(f"Text too long, seding notification to {notification.target.name} as file")
            return self.send_file(
                notification.target,
                f"{notification.notification_type}.txt",
                notification.text.encode("utf-8"),
                f"Your {notification.notification_type} was too long for a message, here's a text file containing it.",
            )
        try:
            chat_id = notification.target.player_id
            url = f"https://api.telegram.org/bot{self.__token}/sendMessage?chat_id={chat_id}&parse_mode=Markdown&text={quote(notification.text)}"
            result = requests.get(url)
            if result.ok:
                return {"ok": True}
            if result.status_code == 403:
                # ignore unauthorized requests
                return {"ok": False, "reason": "blocked"}
            raise Exception(result.text)
        except Exception as e:
            log.error(
                f"An error occurred while trying to notify user {notification.target.player_id} ({notification.target.name}): {e}\nMessage ({len(notification.text)} chars): {notification.text}"
            )
            return {"ok": False, "reason": str(e)}

    def send_file(
        self, player: Player, file_name: str, file_bytes: bytes, caption: str
    ):
        try:
            payload = {"chat_id": player.player_id, "caption": caption}
            url = f"https://api.telegram.org/bot{self.__token}/sendDocument"
            result = requests.post(
                url, data=payload, files={"document": (file_name, file_bytes)}
            )
            if result.ok:
                return {"ok": True}
            if result.status_code == 403:
                # ignore unauthorized requests
                return {"ok": False, "reason": "blocked"}
            raise Exception(result.text)
        except Exception as e:
            log.error(f"Error while sending file to player {player.name}: {e}")
            return {"ok": False, "reason": str(e)}

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
