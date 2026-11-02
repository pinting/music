from src.database import Database

class Tracks:
    def __init__(self, db: Database):
        self.db = db

    def run(self) -> None:
        print("[Tracks] Aggregating history into tracks")

        count = self.db.populate_tracks()

        self.db.commit()

        print(f"Unique tracks: {count:,}")
