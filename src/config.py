import argparse
import os
from dataclasses import dataclass, field, fields

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")
STAGES = ("history", "tracks", "albums", "favorites", "details", "tidal", "migrate", "genres", "export")

def option(default, help, **kwargs):
    return field(default=default, metadata={"help": help, **kwargs})

@dataclass(frozen=True)
class Config:
    """Every field is exposed as a command line flag, e.g. tidal_delay -> --tidal-delay."""

    # Run
    stages: tuple = option(STAGES, "Stages to run, always executed in pipeline order", choices=STAGES)
    limit: int = option(0, "Max items per API stage (albums, tidal, migrate, genres), 0 means no limit")
    progress_every: int = option(50, "Print progress after every N processed items")

    # Paths
    database: str = option(os.path.join(ROOT, "database.db"), "SQLite database file")
    schema: str = option(os.path.join(ROOT, "schema.sql"), "Schema file")
    favorites_sql: str = option(os.path.join(ROOT, "favorites.sql"), "Favorites extraction queries")
    history_dir: str = option(os.path.join(ROOT, "history"), "Streaming history directory")
    export_csv: str = option(os.path.join(ROOT, "docs", "albums.csv"), "CSV rendered by the website")
    export_tracks_csv: str = option(os.path.join(ROOT, "docs", "tracks.csv"), "CSV of the favorite tracks")
    tidal_token_file: str = option(os.path.join(ROOT, ".tidal_token.json"), "Refresh token of the Tidal login")
    tidal_album_url: str = option("https://tidal.com/browse/album/", "Tidal album page prefix")
    tidal_track_url: str = option("https://tidal.com/browse/track/", "Tidal track page prefix")
    spotify_track_url: str = option("https://open.spotify.com/track/", "Spotify track page prefix")
    history_glob: str = option("Streaming_History_Audio_*.json", "Streaming history file pattern")

    # Requests
    retries: int = option(5, "Attempts per API request")
    retry_backoff: float = option(2.0, "Linear backoff step between failed attempts, in seconds")
    retry_after: int = option(5, "Wait after a 429 without a Retry-After header, in seconds")
    timeout: float = option(30.0, "Request timeout in seconds")
    token_margin: int = option(60, "Refresh OAuth tokens this many seconds before they expire")

    # Spotify
    spotify_auth_url: str = option("https://accounts.spotify.com/api/token", "Spotify token endpoint")
    spotify_base_url: str = option("https://api.spotify.com/v1", "Spotify Web API base URL")
    spotify_delay: float = option(0.5, "Delay before each Spotify request, in seconds")
    spotify_batch_size: int = option(50, "Tracks per Spotify lookup")
    spotify_album_batch_size: int = option(20, "Albums per Spotify lookup")

    # Tidal
    tidal_auth_url: str = option("https://auth.tidal.com/v1/oauth2/token", "Tidal token endpoint")
    tidal_login_url: str = option("https://login.tidal.com/authorize", "Tidal user login page")
    tidal_redirect_uri: str = option(
        "http://localhost:8080/callback", "Redirect URI registered for the Tidal app"
    )
    tidal_scopes: tuple = option(("collection.write",), "Scopes requested at the Tidal login")
    tidal_base_url: str = option("https://openapi.tidal.com/v2", "Tidal OpenAPI base URL")
    tidal_delay: float = option(0.5, "Delay before each Tidal request, in seconds")
    tidal_country: str = option("HU", "Primary Tidal catalog region, TIDAL_COUNTRY_CODE overrides the default")
    tidal_fallback_countries: tuple = option(("US", "HU"), "Regions to try after the primary one")
    tidal_isrc_batch_size: int = option(20, "ISRCs per Tidal lookup")
    tidal_collection_batch_size: int = option(50, "Items per request adding to the Tidal collection")

    # Discogs
    discogs_base_url: str = option("https://api.discogs.com", "Discogs API base URL")
    discogs_delay: float = option(1.05, "Delay before each Discogs request, in seconds (policy is 60 req/min)")
    discogs_user_agent: str = option("MusicPipeline/1.0", "Discogs User-Agent")
    discogs_per_page: int = option(5, "Results per Discogs search")
    discogs_min_title_similarity: float = option(0.75, "Minimum title similarity of a searched release")
    discogs_min_artist_releases: int = option(2, "Releases of an artist that have to share a genre tag")

    # Favorites
    favorite_track_min_plays: float = option(5.0, "Minimum listening time of a track, in track lengths")
    favorite_album_min_plays: float = option(3.0, "Minimum listening time of an album, in album lengths")
    favorite_album_min_percentage: float = option(50.0, "Minimum percentage of an album's tracks played")
    favorite_album_min_tracks: int = option(3, "Minimum tracks on an album")

    # Title matching
    search_keywords: tuple = option(
        ("remaster", "deluxe", "expanded", "anniversary", "version", "edition", "mono", "stereo", "bonus"),
        "Regexes marking title clutter to strip from search queries"
    )
    track_keywords: tuple = option(
        (
            "remaster", "master", "deluxe", "expanded", "anniversary", "version", "edition", "mono", "stereo",
            "bonus", "live", "radio edit", r"feat\.", "explicit", "demo", "edit", "mix", "remiscelat"
        ),
        "Regexes marking title clutter to strip when comparing tracks"
    )
    album_keywords: tuple = option(
        ("remaster", "deluxe", "expanded", "anniversary", "version", "edition", "mono", "stereo", "bonus", "live", "collector"),
        "Regexes marking title clutter to strip when comparing albums"
    )
    dash_keyword_excludes: tuple = option(
        ("bonus", r"feat\.", "explicit"),
        "Keywords only stripped in brackets, never after a dash"
    )
    various_artists: tuple = option(
        ("various artists", "various", "v.a.", "va", ""),
        "Artist names treated as a compilation"
    )
    artist_separators: str = option("[,&]", "Regex splitting multiple artists in search queries")
    artist_name_separators: str = option(
        r",|&|/|\*|\+|\b(?:and|with|feat|featuring|ft|vs|versus)\b\.?",
        "Regex splitting artist credits when comparing them"
    )
    track_max_error: float = option(0.20, "Maximum title difference of matching tracks")
    track_min_containment: float = option(0.70, "Minimum length ratio when one track title contains the other")

    # Album scoring, see src/scoring.py
    album_confident_score: float = option(0.90, "Stop looking for candidates at this score")
    album_min_score: float = option(0.60, "Minimum score of a matching album")
    album_min_evidence: float = option(0.50, "Minimum track overlap of a matching album")
    album_min_coverage: float = option(0.90, "Spotify tracks to find on a larger edition to count as that album")
    album_coverage_evidence: float = option(0.70, "Track overlap credited to a larger edition with the same title")
    album_coverage_min_title: float = option(0.50, "Minimum title similarity to credit a larger edition")
    album_max_candidates: int = option(10, "Candidates compared per region and candidate source")
    album_weight_tracks: float = option(0.65, "Weight of the track overlap in the score")
    album_weight_title: float = option(0.20, "Weight of the title similarity in the score")
    album_weight_artist: float = option(0.10, "Weight of the artist match in the score")
    album_weight_year: float = option(0.05, "Weight of the release year match in the score")
    track_max_duration_difference: int = option(15, "Seconds two versions of a track may differ by")

def parse_args(argv=None) -> Config:
    load_dotenv(ENV_FILE)

    parser = argparse.ArgumentParser(
        prog="python -m src",
        description="Music streaming history ingestion and metadata enrichment pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False
    )

    for f in fields(Config):
        kwargs = {"default": f.default, "help": f.metadata["help"]}

        if "choices" in f.metadata:
            kwargs["choices"] = f.metadata["choices"]

        if isinstance(f.default, tuple):
            kwargs["nargs"] = "+"
        else:
            kwargs["type"] = type(f.default)

        parser.add_argument(f"--{f.name.replace('_', '-')}", **kwargs)

    parser.set_defaults(tidal_country=os.getenv("TIDAL_COUNTRY_CODE", Config.tidal_country))

    return Config(**vars(parser.parse_args(argv)))
