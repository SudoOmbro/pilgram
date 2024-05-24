from telegram.ext import ApplicationBuilder


class PilgramBot:

    def __init__(self, bot_token: str):
        self.app = ApplicationBuilder().token(bot_token).build()

    def run(self):
        self.app.run_polling()
