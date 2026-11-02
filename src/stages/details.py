from src.api.spotify import SpotifyClient
from src.config import Config
from src.database import Database
from src.utils import is_progress

class Details:
    """Fetches the barcode and the full tracklist of the favorite albums, used for matching."""

    def __init__(self, db: Database, api: SpotifyClient, config: Config):
        self.db = db
        self.api = api
        self.config = config

    def run(self) -> None:
        uris = self.db.get_albums_without_details(self.config.limit)
        size = self.config.spotify_album_batch_size
        batches = [uris[i:i + size] for i in range(0, len(uris), size)]

        print(f"[Details] Fetching {len(uris):,} favorite albums from Spotify")

        for index, batch in enumerate(batches, 1):
            for details in self.api.get_albums([uri.split(":")[-1] for uri in batch]):
                self._add_isrcs(details.tracks)
                self.db.insert_album_details(details)

            self.db.commit()

            if is_progress(index, len(batches), self.config.progress_every):
                print(f"Batch {index}/{len(batches)}")

    def _add_isrcs(self, tracks: list) -> None:
        size = self.config.spotify_batch_size

        for i in range(0, len(tracks), size):
            batch = tracks[i:i + size]
            results = self.api.get_tracks([track.track_uri.split(":")[-1] for track in batch])

            for track, result in zip(batch, results):
                if result is not None:
                    track.isrc = result.isrc
