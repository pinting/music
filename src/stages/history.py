import glob
import json
import os

from src.config import Config
from src.database import Database
from src.models import HistoryEntry

class History:
    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    def run(self) -> None:
        pattern = os.path.join(self.config.history_dir, self.config.history_glob)
        paths = sorted(glob.glob(pattern))
        loaded = self.db.get_history_files()

        print(f"[History] Found {len(paths)} files matching {pattern}")

        for path in paths:
            filename = os.path.basename(path)

            if filename in loaded:
                print(f"Skipping {filename}, already loaded")

                continue

            with open(path, "r", encoding="utf-8") as f:
                entries = [HistoryEntry.parse(entry, filename) for entry in json.load(f)]

            self.db.insert_history(entries)
            self.db.commit()

            print(f"Loaded {len(entries):,} entries from {filename}")
