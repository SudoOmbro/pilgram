import logging
from typing import Tuple

from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import TelegramError

from pilgram.classes import Player
from pilgram.generics import PilgramNotifier
from pilgram.globals import ContentMeta
from pilgram.utils import read_text_file, TempIntCache
from ui.functions import USER_COMMANDS, USER_PROCESSES
from ui.interpreter import CLIInterpreter
from ui.utils import UserContext
from ui.strings import Strings

log = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARN
)


INFO_STRING = "Made with ❤️ by @LordOmbro\n\n--> [visit my github](https://github.com/SudoOmbro)\n\n--> [offer me a beer](https://www.paypal.com/donate?hosted_button_id=UBNSEND5E96H2)"
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


async def start(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(chat_id=update.effective_chat.id, text=START_STRING, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def info(update: Update, c: ContextTypes.DEFAULT_TYPE):
    await c.bot.send_message(chat_id=update.effective_chat.id, text=INFO_STRING, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


class PilgramBot(PilgramNotifier):

    def __init__(self, bot_token: str):
        self.__app = ApplicationBuilder().token(bot_token).build()
        self.__app.add_handler(CommandHandler("start", start))
        self.__app.add_handler(CommandHandler("info", info))
        self.__app.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        self.process_cache = TempIntCache()
        self.interpreter = CLIInterpreter(USER_COMMANDS, USER_PROCESSES, help_formatting="`{c}`{a}- _{d}_\n\n")

    def get_user_context(self, update: Update) -> Tuple[UserContext, bool]:
        user_id: int = update.effective_user.id
        cached_value = self.process_cache.get(user_id)
        if cached_value:
            return cached_value, True
        return UserContext({
            "id": user_id,
            "username": update.effective_user.username,
        }), False

    async def handle_message(self, update: Update, c: ContextTypes.DEFAULT_TYPE):
        user_context, was_cached = self.get_user_context(update)
        result = self.interpreter.context_aware_execute(user_context, update.message.text)
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
        await c.bot.send_message(chat_id=update.effective_chat.id, text=result, parse_mode=ParseMode.MARKDOWN)

    def notify(self, player: Player, text: str):
        notify(self.get_bot(), player, text)

    def get_bot(self) -> Bot:
        return self.__app.bot

    def run(self):
        self.__app.run_polling()

    def stop(self):
        self.__app.stop()
