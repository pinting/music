import csv
import json
from collections.abc import Iterable
from typing import Optional

from src.config import Config
from src.database import Database

class Export:
    """Writes the favorite albums and tracks to CSV, ordered by listening time in descending order."""

    ALBUM_FIELDS = ("rank", "artists", "album", "year", "cover", "spotify_url", "tidal_url", "genres")
    TRACK_FIELDS = ("rank", "artist", "track", "album", "year", "cover", "spotify_url", "tidal_url")

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    def run(self) -> None:
        albums = self.db.get_favorite_albums_for_export()
        tracks = self.db.get_favorite_tracks_for_export()

        self._write(
            self.config.export_csv, self.ALBUM_FIELDS,
            (self._album_row(rank, album) for rank, album in enumerate(albums, 1))
        )
        self._write(
            self.config.export_tracks_csv, self.TRACK_FIELDS,
            (self._track_row(rank, track) for rank, track in enumerate(tracks, 1))
        )

        print(f"[Export] Wrote {len(albums):,} albums to {self.config.export_csv}")
        print(f"[Export] Wrote {len(tracks):,} tracks to {self.config.export_tracks_csv}")

    def _album_row(self, rank: int, album: dict) -> dict:
        return {
            "rank": rank,
            "artists": album["artists"],
            "album": album["album_name"],
            "year": (album["release_date"] or "")[:4],
            "cover": self._cover(album["images"]),
            "spotify_url": album["external_url"] or "",
            "tidal_url": self._url(self.config.tidal_album_url, album["tidal_album_uri"]),
            "genres": "|".join(json.loads(album["genres"] or "[]"))
        }

    def _track_row(self, rank: int, track: dict) -> dict:
        return {
            "rank": rank,
            "artist": track["artist"],
            "track": track["track_name"],
            "album": track["album"],
            "year": (track["release_date"] or "")[:4],
            "cover": self._cover(track["images"]),
            "spotify_url": self._url(self.config.spotify_track_url, track["spotify_track_uri"]),
            "tidal_url": self._url(self.config.tidal_track_url, track["tidal_track_uri"])
        }

    @staticmethod
    def _write(path: str, fields: tuple, rows: Iterable[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _url(prefix: str, uri: Optional[str]) -> str:
        """Builds a page URL from an URI like tidal:album:123."""
        item_id = (uri or "").split(":")[-1]

        return f"{prefix}{item_id}" if item_id else ""

    @staticmethod
    def _cover(images: Optional[str]) -> str:
        """Spotify lists the images from the largest, the middle one is 300x300."""
        covers = json.loads(images or "[]")

        return covers[len(covers) // 2]["url"] if covers else ""
