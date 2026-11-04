import re
from collections import Counter
from typing import Optional

import requests

from src.api.discogs import DiscogsClient
from src.api.tidal import TidalClient
from src.config import Config
from src.database import Database
from src.matching import TitleMatcher, contains_words, fold
from src.models import DiscogsRelease, FavoriteAlbum
from src.utils import barcode_variants, is_progress, merge_distinct

VARIOUS_ARTISTS = {fold("Various"), fold("Various Artists")}

class Genres:
    def __init__(
        self,
        db: Database,
        discogs: DiscogsClient,
        tidal: Optional[TidalClient],
        matcher: TitleMatcher,
        config: Config
    ):
        self.db = db
        self.discogs = discogs
        self.tidal = tidal
        self.matcher = matcher
        self.config = config

    def run(self) -> None:
        albums = self.db.get_favorite_albums(limit=self.config.limit)
        populated = 0

        print(f"[Genres] Enriching {len(albums):,} favorite albums")

        for index, album in enumerate(albums, 1):
            genres = merge_distinct(album.genres, self._discogs_genres(album) + self._tidal_genres(album))

            self.db.update_favorite_album_genres(album.spotify_album_uri, genres)
            self.db.commit()

            if genres:
                populated += 1

            if is_progress(index, len(albums), self.config.progress_every):
                print(f"Albums: {index}/{len(albums)}, with genres {populated}")

    def _discogs_genres(self, album: FavoriteAlbum) -> list[str]:
        """A barcode identifies the release, searches by name have to return the album."""

        artist = album.artists or ""
        name = album.album_name or ""
        clean = self.matcher.clean_for_search(name)
        first_artist = re.split(self.config.artist_separators, artist)[0].strip()
        searches = [{"release_title": title, "artist": first_artist} for title in dict.fromkeys((clean, name))]

        searches.append({"q": f"{artist} {clean}"})

        for barcode in barcode_variants(album.upc):
            for release in self._search_discogs({"barcode": barcode}):
                if release.genres:
                    return release.genres

        for params in searches:
            for release in self._search_discogs(params):
                if release.genres and self._is_same_album(release, artist, clean):
                    return release.genres

        return self._discogs_artist_genres(first_artist)

    def _discogs_artist_genres(self, artist: str) -> list[str]:
        """Without the album, the tags shared by the releases of the exact artist describe it."""

        if fold(artist) in VARIOUS_ARTISTS:
            return []

        releases = [
            release for release in self._search_discogs({"artist": artist})
            if fold(release.title.partition(" - ")[0].rstrip("*")) == fold(artist)
        ]
        counts = Counter(genre for release in releases for genre in release.genres)
        required = max(self.config.discogs_min_artist_releases, (len(releases) + 1) // 2)

        return [genre for genre, count in counts.most_common() if count >= required]

    def _search_discogs(self, params: dict) -> list[DiscogsRelease]:
        try:
            return self.discogs.search_releases(params)
        except requests.exceptions.RequestException as e:
            print(f"Discogs search failed for {params}: {e}")

            return []

    def _is_same_album(self, release: DiscogsRelease, artist: str, name: str) -> bool:
        """Discogs titles are formatted as "Artist (2) - Album", with compilations by "Various"."""

        release_artist, _, release_name = release.title.partition(" - ")
        release_artist = re.sub(r"\s*\(\d+\)", "", release_artist)

        if fold(release.title) == fold(f"{artist} {name}"):
            return True

        if not self.matcher.artists_match(artist, release_artist) and fold(release_artist) not in VARIOUS_ARTISTS:
            return False

        return (
            contains_words(name, release_name)
            or self.matcher.title_similarity(name, release_name) >= self.config.discogs_min_title_similarity
        )

    def _tidal_genres(self, album: FavoriteAlbum) -> list[str]:
        if self.tidal is None or not album.tidal_album_uri:
            return []

        try:
            return self.tidal.get_album_genres(album.tidal_album_uri)
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch Tidal genres of {album.tidal_album_uri}: {e}")

            return []
