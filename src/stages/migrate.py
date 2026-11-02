import requests

from src.api.tidal import TidalUserClient
from src.config import Config
from src.database import Database
from src.utils import is_progress

class Migrate:
    """Adds the favorites matched by the tidal stage to the Tidal collection of the user. Tidal
    skips what is already there, so the stage can be repeated."""

    def __init__(self, db: Database, api: TidalUserClient, config: Config):
        self.db = db
        self.api = api
        self.config = config

    def run(self) -> None:
        self._push("albums", self.db.get_favorite_tidal_album_uris())
        self._push("tracks", self.db.get_favorite_tidal_track_uris())

    def _push(self, kind: str, uris: list[str]) -> None:
        # Editions of different Spotify albums can share a Tidal album, as can tracks
        ids = list(dict.fromkeys(uri.split(":")[-1] for uri in uris))[:self.config.limit or None]
        size = self.config.tidal_collection_batch_size
        batches = [ids[i:i + size] for i in range(0, len(ids), size)]
        skipped, failed = {}, 0

        print(f"[Migrate] Adding {len(ids):,} {kind} to the Tidal collection")

        for index, batch in enumerate(batches, 1):
            try:
                for item in self.api.add_to_collection(kind, batch):
                    skipped[item["reason"]] = skipped.get(item["reason"], 0) + 1
            except requests.exceptions.RequestException as e:
                failed += len(batch)
                print(f"Tidal request failed for {len(batch)} {kind}: {e}")

            if is_progress(index, len(batches), self.config.progress_every):
                print(f"Batch {index}/{len(batches)}")

        added = len(ids) - sum(skipped.values()) - failed
        present, missing = skipped.get("ALREADY_PRESENT", 0), skipped.get("NOT_FOUND", 0)

        print(f"Added {added:,} {kind}, already there {present:,}, not found {missing:,}, failed {failed:,}")
