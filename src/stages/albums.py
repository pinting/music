from src.api.spotify import SpotifyClient
from src.config import Config
from src.database import Database
from src.utils import is_progress

class Albums:
    def __init__(self, db: Database, api: SpotifyClient, config: Config):
        self.db = db
        self.api = api
        self.config = config

    def run(self) -> None:
        uris = self.db.get_track_uris(self.config.limit)
        size = self.config.spotify_batch_size
        batches = [uris[i:i + size] for i in range(0, len(uris), size)]

        print(f"[Albums] Fetching {len(uris):,} tracks from Spotify")

        albums, track_albums, track_details = {}, {}, {}
        skipped = 0

        for index, batch in enumerate(batches, 1):
            tracks = self.api.get_tracks([uri.split(":")[-1] for uri in batch])

            for uri, track in zip(batch, tracks):
                if track is None or track.album is None:
                    skipped += 1

                if track is None:
                    continue

                track_details[uri] = (track.duration_ms, track.isrc)

                if track.album is not None:
                    track_albums[uri] = track.album.album_uri
                    albums.setdefault(track.album.album_uri, track.album)

            if is_progress(index, len(batches), self.config.progress_every):
                print(f"Batch {index}/{len(batches)}")

        self.db.insert_albums(albums.values())
        self.db.update_track_albums(track_albums)
        self.db.update_track_details(track_details)

        count = self.db.update_album_statistics()

        self.db.commit()

        print(f"Updated {len(albums):,} albums, skipped {skipped} tracks, total albums: {count:,}")
