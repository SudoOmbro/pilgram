import logging
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import TelegramError

from pilgram.classes import Player
from pilgram.generics import PilgramNotifier
from pilgram.utils import read_text_file
from ui.interpreter import context_aware_execute
from ui.utils import UserContext

log = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


INFO_STRING = "Made with ❤️ by @LordOmbro\n\n[github](https://github.com/SudoOmbro)\n[offer me a beer](https://www.paypal.com/donate?hosted_button_id=UBNSEND5E96H2)"
START_STRING = read_text_file("intro.txt")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!", parse_mode=ParseMode.MARKDOWN_V2)


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=INFO_STRING, parse_mode=ParseMode.MARKDOWN_V2)


async def handle_message(update: Update, c: ContextTypes.DEFAULT_TYPE):
    user_context = UserContext({
        "id": update.effective_user.id,
        "username": update.effective_user.username,
    })
    result = context_aware_execute(user_context, update.message.text)
    event = user_context.get_event_data()
    if event:
        # TODO handle events
        pass
    c.bot.send_message(chat_id=update.effective_chat.id, text=result, parse_mode=ParseMode.MARKDOWN_V2)


class PilgramBot(PilgramNotifier):

    def __init__(self, bot_token: str):
        self.__app = ApplicationBuilder().token(bot_token).build()
        self.__app.add_handler(CommandHandler("start", start))
        self.__app.add_handler(CommandHandler("info", info))
        self.__app.add_handler(MessageHandler(filters.TEXT, handle_message))

    def notify(self, player: Player, text: str):
        try:
            self.get_bot().send_message(player.player_id, text, parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramError as e:
            log.error(f"An error occurred while trying to notify user {player.player_id} ({player.name}): {e}")

    def get_bot(self) -> Bot:
        return self.__app.bot

    def run(self):
        self.__app.run_polling()

    def stop(self):
        self.__app.stop()
