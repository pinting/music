from src.database import Database

class Favorites:
    def __init__(self, db: Database):
        self.db = db

    def run(self) -> None:
        print("[Favorites] Extracting favorite tracks and albums")

        tracks, albums = self.db.extract_favorites()

        self.db.commit()

        print(f"Favorite tracks: {tracks:,}, favorite albums: {albums:,}")
