from pilgram.globals import GlobalSettings
from ui.telegram_bot import PilgramBot


def main():
    bot = PilgramBot(GlobalSettings.get("Telegram bot token"))
    bot.run()
    bot.stop()


if __name__ == '__main__':
    main()
