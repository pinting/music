import json
import re
from dataclasses import dataclass, field, fields
from typing import Optional

@dataclass
class HistoryEntry:
    ts: str = None
    platform: str = None
    ms_played: int = None
    conn_country: str = None
    ip_addr: str = None
    master_metadata_track_name: str = None
    master_metadata_album_artist_name: str = None
    master_metadata_album_album_name: str = None
    spotify_track_uri: str = None
    episode_name: str = None
    episode_show_name: str = None
    spotify_episode_uri: str = None
    audiobook_title: str = None
    audiobook_uri: str = None
    audiobook_chapter_uri: str = None
    audiobook_chapter_title: str = None
    reason_start: str = None
    reason_end: str = None
    shuffle: bool = None
    skipped: bool = None
    offline: bool = None
    offline_timestamp: int = None
    incognito_mode: bool = None
    source_file: str = None

    @classmethod
    def parse(cls, data: dict, source_file: str) -> "HistoryEntry":
        names = (f.name for f in fields(cls))

        return cls(**{**{name: data.get(name) for name in names}, "source_file": source_file})

@dataclass
class SpotifyAlbum:
    album_uri: str
    album_id: str
    album_name: str
    album_type: str
    total_tracks: Optional[int]
    release_date: str
    release_date_precision: str
    artists: str
    artist_uris: str
    images: str
    external_url: str
    href: str

    @classmethod
    def parse(cls, data: dict) -> "SpotifyAlbum":
        artists = data.get("artists", [])

        return cls(
            album_uri=data["uri"],
            album_id=data["id"],
            album_name=data["name"],
            album_type=data.get("album_type", ""),
            total_tracks=data.get("total_tracks"),
            release_date=data.get("release_date", ""),
            release_date_precision=data.get("release_date_precision", ""),
            artists=", ".join(a.get("name", "") for a in artists),
            artist_uris=", ".join(a.get("uri", "") for a in artists),
            images=json.dumps(data.get("images", []), ensure_ascii=False),
            external_url=data.get("external_urls", {}).get("spotify", ""),
            href=data.get("href", "")
        )

@dataclass
class SpotifyTrack:
    duration_ms: Optional[int]
    isrc: Optional[str]
    album: Optional[SpotifyAlbum]

    @classmethod
    def parse(cls, data: dict) -> "SpotifyTrack":
        album = data.get("album")

        return cls(
            duration_ms=data.get("duration_ms"),
            isrc=parse_isrc(data.get("external_ids", {}).get("isrc")),
            album=SpotifyAlbum.parse(album) if album and album.get("uri") else None
        )

@dataclass
class AlbumTrack:
    track_uri: str
    name: str
    disc_number: Optional[int] = None
    track_number: Optional[int] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None

    @classmethod
    def parse(cls, data: dict) -> "AlbumTrack":
        return cls(
            track_uri=data["uri"],
            name=data.get("name"),
            disc_number=data.get("disc_number"),
            track_number=data.get("track_number"),
            duration_ms=data.get("duration_ms")
        )

@dataclass
class SpotifyAlbumDetails:
    album_uri: str
    upc: Optional[str]
    tracks: list[AlbumTrack]
    next_url: Optional[str] = None

    @classmethod
    def parse(cls, data: dict) -> "SpotifyAlbumDetails":
        tracks = data.get("tracks", {})

        return cls(
            album_uri=data["uri"],
            upc=data.get("external_ids", {}).get("upc"),
            tracks=[AlbumTrack.parse(item) for item in tracks.get("items", [])],
            next_url=tracks.get("next")
        )

def parse_isrc(value: Optional[str]) -> Optional[str]:
    """Returns a valid ISRC in its canonical form, as Tidal rejects a batch with an invalid one."""
    isrc = (value or "").replace("-", "").strip().upper()

    return isrc if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}\d{7}", isrc) else None

def _parse_duration(value: Optional[str]) -> Optional[int]:
    """Parses an ISO 8601 duration, such as PT1H5M54S, into milliseconds."""
    parts = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value or "")

    if not parts:
        return None

    hours, minutes, seconds = parts.groups()

    return int((int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0)) * 1000)

@dataclass
class TidalTrack:
    id: str
    title: str
    isrc: Optional[str] = None
    duration_ms: Optional[int] = None
    popularity: float = 0.0
    album_ids: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict) -> "TidalTrack":
        attributes = data.get("attributes", {})
        albums = data.get("relationships", {}).get("albums", {}).get("data", [])
        version = attributes.get("version")
        title = attributes.get("title", "")

        return cls(
            id=data["id"],
            title=f"{title} ({version})" if version else title,
            isrc=parse_isrc(attributes.get("isrc")),
            duration_ms=_parse_duration(attributes.get("duration")),
            popularity=attributes.get("popularity") or 0.0,
            album_ids=[album["id"] for album in albums]
        )

@dataclass
class TidalAlbum:
    id: str
    title: str
    tracks_count: Optional[int] = None
    barcode: Optional[str] = None
    release_date: Optional[str] = None
    artists: list[str] = field(default_factory=list)
    tracks: list[TidalTrack] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict) -> "TidalAlbum":
        attributes = data.get("attributes", {})

        return cls(
            id=data["id"],
            title=attributes.get("title", ""),
            tracks_count=attributes.get("numberOfItems"),
            barcode=attributes.get("barcodeId"),
            release_date=attributes.get("releaseDate")
        )

@dataclass
class AlbumMatch:
    id: str
    score: float
    method: str
    country: str

    @property
    def uri(self) -> str:
        return f"tidal:album:{self.id}"

@dataclass
class DiscogsRelease:
    title: str
    genres: list[str]

@dataclass
class FavoriteTrack:
    spotify_track_uri: str
    artist: Optional[str]
    track_name: Optional[str]
    isrc: Optional[str] = None
    length: Optional[int] = None
    tidal_album_uri: Optional[str] = None

@dataclass
class FavoriteAlbum:
    spotify_album_uri: str
    tidal_album_uri: Optional[str]
    release_date: Optional[str]
    artists: Optional[str]
    album_name: Optional[str]
    total_tracks: Optional[int]
    genres: list[str]
    upc: Optional[str] = None

    @classmethod
    def parse(cls, row) -> "FavoriteAlbum":
        return cls(**{**dict(row), "genres": json.loads(row["genres"] or "[]")})
