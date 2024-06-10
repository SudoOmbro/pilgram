from datetime import timedelta

from pilgram.generics import PilgramDatabase, PilgramNotifier


class QuestManager:

    def __init__(self, database: PilgramDatabase, notifier: PilgramNotifier, update_interval: timedelta):
        self.database = database
        self.notifier = notifier
        self.update_interval = update_interval
