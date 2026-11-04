import json
import sqlite3
from dataclasses import asdict
from typing import Iterable

from src.config import Config
from src.models import AlbumMatch, AlbumTrack, FavoriteAlbum, FavoriteTrack, HistoryEntry, SpotifyAlbum, SpotifyAlbumDetails

class Database:
    def __init__(self, config: Config):
        self.config = config
        self.connection = sqlite3.connect(config.database)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

        self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute("PRAGMA synchronous=NORMAL")

    def setup(self) -> None:
        with open(self.config.schema, "r", encoding="utf-8") as f:
            self.cursor.executescript(f.read())

        self.connection.commit()

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _count(self, table: str) -> int:
        return self.cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def get_history_files(self) -> set[str]:
        rows = self.cursor.execute("SELECT DISTINCT source_file FROM history").fetchall()

        return {row[0] for row in rows}

    def insert_history(self, entries: Iterable[HistoryEntry]) -> None:
        query = """
            INSERT INTO history (
                ts, platform, ms_played, conn_country, ip_addr,
                master_metadata_track_name, master_metadata_album_artist_name,
                master_metadata_album_album_name, spotify_track_uri,
                episode_name, episode_show_name, spotify_episode_uri,
                audiobook_title, audiobook_uri, audiobook_chapter_uri, audiobook_chapter_title,
                reason_start, reason_end, shuffle, skipped, offline, offline_timestamp,
                incognito_mode, source_file
            ) VALUES (
                :ts, :platform, :ms_played, :conn_country, :ip_addr,
                :master_metadata_track_name, :master_metadata_album_artist_name,
                :master_metadata_album_album_name, :spotify_track_uri,
                :episode_name, :episode_show_name, :spotify_episode_uri,
                :audiobook_title, :audiobook_uri, :audiobook_chapter_uri, :audiobook_chapter_title,
                :reason_start, :reason_end, :shuffle, :skipped, :offline, :offline_timestamp,
                :incognito_mode, :source_file
            )
        """

        self.cursor.executemany(query, map(vars, entries))

    def populate_tracks(self) -> int:
        query = """
            INSERT INTO tracks (
                spotify_track_uri, master_metadata_track_name, master_metadata_album_artist_name,
                master_metadata_album_album_name, ms_played, earliest_played_at
            )
            SELECT
                spotify_track_uri, master_metadata_track_name, master_metadata_album_artist_name,
                master_metadata_album_album_name, SUM(ms_played), MIN(ts)
            FROM history
            WHERE spotify_track_uri IS NOT NULL
            GROUP BY spotify_track_uri
            ON CONFLICT(spotify_track_uri) DO UPDATE SET
                master_metadata_track_name=excluded.master_metadata_track_name,
                master_metadata_album_artist_name=excluded.master_metadata_album_artist_name,
                master_metadata_album_album_name=excluded.master_metadata_album_album_name,
                ms_played=excluded.ms_played,
                earliest_played_at=excluded.earliest_played_at
        """

        self.cursor.execute(query)

        return self._count("tracks")

    def get_track_uris(self, limit: int = 0) -> list[str]:
        query = "SELECT spotify_track_uri FROM tracks ORDER BY ms_played DESC LIMIT ?"

        return [row[0] for row in self.cursor.execute(query, (limit or -1,)).fetchall()]

    def insert_albums(self, albums: Iterable[SpotifyAlbum]) -> None:
        query = """
            INSERT INTO albums (
                album_uri, album_id, album_name, album_type, total_tracks,
                release_date, release_date_precision, artists, artist_uris, images,
                external_url, href
            ) VALUES (
                :album_uri, :album_id, :album_name, :album_type, :total_tracks,
                :release_date, :release_date_precision, :artists, :artist_uris, :images,
                :external_url, :href
            )
            ON CONFLICT(album_uri) DO UPDATE SET
                album_id=excluded.album_id,
                album_name=excluded.album_name,
                album_type=excluded.album_type,
                total_tracks=excluded.total_tracks,
                release_date=excluded.release_date,
                release_date_precision=excluded.release_date_precision,
                artists=excluded.artists,
                artist_uris=excluded.artist_uris,
                images=excluded.images,
                external_url=excluded.external_url,
                href=excluded.href
        """

        self.cursor.executemany(query, map(asdict, albums))

    def update_track_albums(self, track_albums: dict[str, str]) -> None:
        query = "UPDATE tracks SET album_uri=? WHERE spotify_track_uri=?"

        self.cursor.executemany(query, [(album, track) for track, album in track_albums.items()])

    def update_track_details(self, track_details: dict[str, tuple]) -> None:
        query = "UPDATE tracks SET length=?, isrc=? WHERE spotify_track_uri=?"

        self.cursor.executemany(query, [(*details, track) for track, details in track_details.items()])

    def update_album_statistics(self) -> int:
        query = """
            UPDATE albums SET
                actual_length=stats.actual_length,
                total_listening_time=stats.total_listening_time,
                percentage_played=stats.percentage_played
            FROM (
                SELECT
                    t.album_uri,
                    SUM(t.length) AS actual_length,
                    SUM(t.ms_played) AS total_listening_time,
                    CAST(SUM(t.length IS NOT NULL AND t.ms_played >= t.length) AS REAL)
                        / a.total_tracks * 100.0 AS percentage_played
                FROM tracks t
                JOIN albums a ON a.album_uri = t.album_uri
                GROUP BY t.album_uri
            ) stats
            WHERE albums.album_uri = stats.album_uri
        """

        self.cursor.execute(query)

        return self._count("albums")

    def extract_favorites(self) -> tuple[int, int]:
        params = {
            "track_min_plays": self.config.favorite_track_min_plays,
            "album_min_plays": self.config.favorite_album_min_plays,
            "album_min_percentage": self.config.favorite_album_min_percentage,
            "album_min_tracks": self.config.favorite_album_min_tracks
        }

        with open(self.config.favorites_sql, "r", encoding="utf-8") as f:
            statements = [statement for statement in f.read().split(";") if statement.strip()]

        for statement in statements:
            self.cursor.execute(statement, params)

        return self._count("favorite_tracks"), self._count("favorite_albums")

    def get_albums_without_details(self, limit: int = 0) -> list[str]:
        query = """
            SELECT f.spotify_album_uri
            FROM favorite_albums f
            JOIN albums a ON a.album_uri = f.spotify_album_uri
            WHERE NOT EXISTS (SELECT 1 FROM album_tracks t WHERE t.album_uri = f.spotify_album_uri)
            ORDER BY f.total_listening_time DESC
            LIMIT ?
        """

        return [row[0] for row in self.cursor.execute(query, (limit or -1,)).fetchall()]

    def insert_album_details(self, details: SpotifyAlbumDetails) -> None:
        query = """
            INSERT INTO album_tracks (album_uri, track_uri, name, disc_number, track_number, duration_ms, isrc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(album_uri, track_uri) DO UPDATE SET
                name=excluded.name,
                disc_number=excluded.disc_number,
                track_number=excluded.track_number,
                duration_ms=excluded.duration_ms,
                isrc=excluded.isrc
        """

        self.cursor.execute("UPDATE albums SET upc=? WHERE album_uri=?", (details.upc, details.album_uri))
        self.cursor.executemany(
            query,
            [
                (details.album_uri, t.track_uri, t.name, t.disc_number, t.track_number, t.duration_ms, t.isrc)
                for t in details.tracks
            ]
        )

    def get_album_tracks(self, album_uri: str) -> list[AlbumTrack]:
        """Returns the full tracklist, or the listened tracks of an album without details."""

        query = """
            SELECT track_uri, name, disc_number, track_number, duration_ms, isrc
            FROM album_tracks
            WHERE album_uri = ?
            ORDER BY disc_number, track_number
        """
        fallback = """
            SELECT spotify_track_uri AS track_uri, master_metadata_track_name AS name,
                   NULL AS disc_number, NULL AS track_number, length AS duration_ms, isrc
            FROM tracks
            WHERE album_uri = ? AND master_metadata_track_name IS NOT NULL
            ORDER BY earliest_played_at ASC
        """
        rows = self.cursor.execute(query, (album_uri,)).fetchall()

        return [AlbumTrack(**dict(row)) for row in rows or self.cursor.execute(fallback, (album_uri,)).fetchall()]

    def get_unmatched_favorite_tracks(self, limit: int = 0) -> list[FavoriteTrack]:
        query = """
            SELECT f.spotify_track_uri, f.artist, f.track_name, t.isrc, t.length, a.tidal_album_uri
            FROM favorite_tracks f
            JOIN tracks t ON t.spotify_track_uri = f.spotify_track_uri
            LEFT JOIN favorite_albums a ON a.spotify_album_uri = t.album_uri
            WHERE f.tidal_track_uri IS NULL OR f.tidal_track_uri = ''
            ORDER BY f.added_at DESC
            LIMIT ?
        """

        return [FavoriteTrack(**row) for row in map(dict, self.cursor.execute(query, (limit or -1,)).fetchall())]

    def update_favorite_track_tidal_uri(self, spotify_uri: str, tidal_uri: str, method: str) -> None:
        query = "UPDATE favorite_tracks SET tidal_track_uri=?, tidal_track_method=? WHERE spotify_track_uri=?"

        self.cursor.execute(query, (tidal_uri, method, spotify_uri))

    def get_favorite_albums(self, unmatched_only: bool = False, limit: int = 0) -> list[FavoriteAlbum]:
        query = f"""
            SELECT f.spotify_album_uri, f.tidal_album_uri, f.release_date, f.artists, f.album_name,
                   f.total_tracks, f.genres, a.upc
            FROM favorite_albums f
            LEFT JOIN albums a ON a.album_uri = f.spotify_album_uri
            {"WHERE f.tidal_album_uri IS NULL OR f.tidal_album_uri = ''" if unmatched_only else ""}
            ORDER BY f.total_listening_time DESC
            LIMIT ?
        """

        return [FavoriteAlbum.parse(row) for row in self.cursor.execute(query, (limit or -1,)).fetchall()]

    def update_favorite_album_tidal_uri(self, spotify_uri: str, match: AlbumMatch) -> None:
        query = """
            UPDATE favorite_albums
            SET tidal_album_uri=?, tidal_album_method=?, tidal_album_score=?, tidal_album_country=?
            WHERE spotify_album_uri=?
        """

        self.cursor.execute(query, (match.uri, match.method, match.score, match.country, spotify_uri))

    def get_favorite_tidal_album_uris(self) -> list[str]:
        query = """
            SELECT tidal_album_uri
            FROM favorite_albums
            WHERE tidal_album_uri IS NOT NULL AND tidal_album_uri != ''
            ORDER BY total_listening_time DESC
        """

        return [row[0] for row in self.cursor.execute(query).fetchall()]

    def get_favorite_tidal_track_uris(self) -> list[str]:
        query = """
            SELECT tidal_track_uri
            FROM favorite_tracks
            WHERE tidal_track_uri IS NOT NULL AND tidal_track_uri != ''
            ORDER BY added_at DESC
        """

        return [row[0] for row in self.cursor.execute(query).fetchall()]

    def update_favorite_album_genres(self, spotify_uri: str, genres: list[str]) -> None:
        query = "UPDATE favorite_albums SET genres=? WHERE spotify_album_uri=?"

        self.cursor.execute(query, (json.dumps(genres, ensure_ascii=False), spotify_uri))

    def get_favorite_albums_for_export(self) -> list[dict]:
        query = """
            SELECT f.artists, f.album_name, f.release_date,
                   f.tidal_album_uri, f.genres, a.images, a.external_url
            FROM favorite_albums f
            LEFT JOIN albums a ON a.album_uri = f.spotify_album_uri
            ORDER BY f.total_listening_time DESC
        """

        return [dict(row) for row in self.cursor.execute(query).fetchall()]

    def get_favorite_tracks_for_export(self) -> list[dict]:
        query = """
            SELECT f.spotify_track_uri, f.tidal_track_uri, f.artist, f.album, f.track_name,
                   a.release_date, a.images
            FROM favorite_tracks f
            LEFT JOIN tracks t ON t.spotify_track_uri = f.spotify_track_uri
            LEFT JOIN albums a ON a.album_uri = t.album_uri
            ORDER BY t.ms_played DESC, f.spotify_track_uri
        """

        return [dict(row) for row in self.cursor.execute(query).fetchall()]
