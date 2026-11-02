from typing import Callable, Iterator, Optional

import requests

from src.api.tidal import TidalClient
from src.config import Config
from src.database import Database
from src.matching import TitleMatcher
from src.models import AlbumMatch, AlbumTrack, FavoriteAlbum, FavoriteTrack, TidalAlbum, TidalTrack
from src.scoring import AlbumScorer
from src.utils import barcode_variants, is_progress

class Tidal:
    def __init__(self, db: Database, api: TidalClient, matcher: TitleMatcher, config: Config):
        self.db = db
        self.api = api
        self.matcher = matcher
        self.config = config
        self.scorer = AlbumScorer(matcher, config)
        self.countries = list(dict.fromkeys((config.tidal_country, *config.tidal_fallback_countries)))

    def run(self) -> None:
        # Albums go first, as tracks prefer their recording on the matched album
        self._match_albums()
        self._match_tracks()

    def _safely(self, description: str, call: Callable, default=None):
        try:
            return call()
        except requests.exceptions.RequestException as e:
            print(f"Tidal request failed for {description}: {e}")

            return default

    def _match_albums(self) -> None:
        albums = self.db.get_favorite_albums(unmatched_only=True, limit=self.config.limit)
        matched = 0

        print(f"[Tidal] Matching {len(albums):,} favorite albums")

        for index, album in enumerate(albums, 1):
            match = self._find_album(album) if album.album_name else None

            if match:
                self.db.update_favorite_album_tidal_uri(album.spotify_album_uri, match)
                self.db.commit()
                matched += 1

            if is_progress(index, len(albums), self.config.progress_every):
                print(f"Albums: {index}/{len(albums)}, matched {matched}")

    def _find_album(self, album: FavoriteAlbum) -> Optional[AlbumMatch]:
        tracks = self.db.get_album_tracks(album.spotify_album_uri)

        for country in self.countries:
            match = self._find_album_in(album, tracks, country)

            if match:
                return match

        return None

    def _find_album_in(self, album: FavoriteAlbum, tracks: list[AlbumTrack], country: str) -> Optional[AlbumMatch]:
        """Looks for the same barcode, then for the same recordings, then for the title, and
        returns the best scoring candidate. A barcode is the exact edition, so it is final."""
        tested = set()
        best, best_key = None, None

        for method, candidates in self._candidates(album, tracks, country):
            for candidate in self._shortlist(album, candidates, tested, method):
                tested.add(candidate.id)

                details = self._safely(f"album {candidate.id}", lambda: self.api.get_album(candidate.id, country))

                if details is None:
                    continue

                score = self.scorer.score(album.album_name, album.artists or "", album.release_date, tracks, details)

                if not self.scorer.is_match(score):
                    continue

                if method == "upc":
                    return AlbumMatch(candidate.id, score.total, method, country)

                if best_key is None or (score.total, score.isrc) > best_key:
                    best, best_key = AlbumMatch(candidate.id, score.total, method, country), (score.total, score.isrc)

            if best and best.score >= self.config.album_confident_score:
                break

        return best

    def _candidates(self, album: FavoriteAlbum, tracks: list[AlbumTrack], country: str) -> Iterator[tuple[str, list[TidalAlbum]]]:
        for barcode in barcode_variants(album.upc):
            yield "upc", self._safely(
                f"barcode {barcode}", lambda: self.api.find_albums_by_barcode(barcode, country), []
            )

        isrcs = list(dict.fromkeys(t.isrc for t in tracks if t.isrc))[:self.config.tidal_isrc_batch_size]

        if isrcs:
            yield "isrc", self._albums_of_recordings(isrcs, country)

        for query in self.matcher.album_queries(album.artists or "", album.album_name, album.release_date):
            yield "search", self._safely(f"'{query}'", lambda: self.api.search_albums(query, country), [])

    def _albums_of_recordings(self, isrcs: list[str], country: str) -> list[TidalAlbum]:
        """Returns the albums containing the recordings, the ones with the most of them first."""
        found, albums = self._safely(f"ISRCs {isrcs}", lambda: self.api.find_tracks_by_isrc(isrcs, country), ([], {}))
        hits = {}

        for track in found:
            for album_id in track.album_ids:
                hits[album_id] = hits.get(album_id, 0) + 1

        return [albums.get(i, TidalAlbum(i, "")) for i in sorted(hits, key=hits.get, reverse=True)]

    def _shortlist(self, album: FavoriteAlbum, candidates: list[TidalAlbum], tested: set, method: str) -> list[TidalAlbum]:
        """Limits the candidates to compare, as each one takes a request. Search results are
        picked by both title and track count, as other editions can be titled differently."""
        size = self.config.album_max_candidates
        candidates = [candidate for candidate in candidates if candidate.id not in tested]

        if method != "search":
            return candidates[:size]

        by_title = sorted(candidates, key=lambda c: -self.matcher.title_similarity(album.album_name, c.title))
        by_tracks = sorted(candidates, key=lambda c: abs((c.tracks_count or 0) - (album.total_tracks or 0)))

        return list({c.id: c for c in by_title[:size // 2] + by_tracks[:size - size // 2]}.values())

    def _match_tracks(self) -> None:
        tracks = self.db.get_unmatched_favorite_tracks(self.config.limit)

        print(f"[Tidal] Matching {len(tracks):,} favorite tracks")

        remaining = self._match_tracks_by_isrc(tracks)

        print(f"Matched {len(tracks) - len(remaining):,} tracks by ISRC, looking for {len(remaining):,}")

        matched = 0

        for index, track in enumerate(remaining, 1):
            uri, method = self._find_track(track)

            if uri:
                self.db.update_favorite_track_tidal_uri(track.spotify_track_uri, uri, method)
                self.db.commit()
                matched += 1

            if is_progress(index, len(remaining), self.config.progress_every):
                print(f"Tracks: {index}/{len(remaining)}, matched {matched}")

    def _match_track_on_album_by_isrc(self, track: FavoriteTrack) -> bool:
        """The lookup by ISRC does not always return the copy on the matched album, so its tracklist comes first."""
        if not track.isrc or not track.tidal_album_uri:
            return False

        album_id = track.tidal_album_uri.split(":")[-1]

        for country in self.countries:
            album = self._safely(f"album {album_id}", lambda: self.api.get_album(album_id, country))

            for candidate in album.tracks if album else []:
                if candidate.isrc == track.isrc:
                    self.db.update_favorite_track_tidal_uri(
                        track.spotify_track_uri, f"tidal:track:{candidate.id}", "isrc:album"
                    )
                    return True

        return False

    def _match_tracks_by_isrc(self, tracks: list[FavoriteTrack]) -> list[FavoriteTrack]:
        remaining = [track for track in tracks if not self._match_track_on_album_by_isrc(track)]
        self.db.commit()
        size = self.config.tidal_isrc_batch_size

        for country in self.countries:
            pending = [track for track in remaining if track.isrc]
            batches = [pending[i:i + size] for i in range(0, len(pending), size)]
            matched = set()

            for batch in batches:
                isrcs = list({track.isrc for track in batch})
                found, _ = self._safely("ISRCs", lambda: self.api.find_tracks_by_isrc(isrcs, country), ([], {}))
                recordings = {}

                for result in found:
                    recordings.setdefault(result.isrc, []).append(result)

                for track in batch:
                    if track.isrc in recordings:
                        best = self._best_recording(track, recordings[track.isrc])
                        method = "isrc:album" if track.tidal_album_uri and self._is_on_album(best, track) else "isrc"

                        self.db.update_favorite_track_tidal_uri(track.spotify_track_uri, f"tidal:track:{best.id}", method)
                        matched.add(track.spotify_track_uri)

                self.db.commit()

            remaining = [track for track in remaining if track.spotify_track_uri not in matched]

        return remaining

    def _is_on_album(self, recording: TidalTrack, track: FavoriteTrack) -> bool:
        return bool(track.tidal_album_uri) and track.tidal_album_uri.split(":")[-1] in recording.album_ids

    def _best_recording(self, track: FavoriteTrack, recordings: list[TidalTrack]) -> TidalTrack:
        """One recording can be on many albums, the matched album wins, then the popular one."""
        return max(recordings, key=lambda r: (self._is_on_album(r, track), r.popularity, r.id))

    def _find_track(self, track: FavoriteTrack) -> tuple[Optional[str], Optional[str]]:
        if not track.track_name:
            return None, None

        return self._find_track_on_album(track) or self._find_track_by_search(track) or (None, None)

    def _find_track_on_album(self, track: FavoriteTrack) -> Optional[tuple[str, str]]:
        if not track.tidal_album_uri:
            return None

        album_id = track.tidal_album_uri.split(":")[-1]

        for country in self.countries:
            album = self._safely(f"album {album_id}", lambda: self.api.get_album(album_id, country))

            for candidate in album.tracks if album else []:
                if self._is_same_track(track, candidate):
                    return f"tidal:track:{candidate.id}", "album"

        return None

    def _find_track_by_search(self, track: FavoriteTrack) -> Optional[tuple[str, str]]:
        artist = track.artist or ""
        names = dict.fromkeys((track.track_name, self.matcher.clean_for_search(track.track_name)))

        for country in self.countries:
            for name in names:
                query = f"{artist} {name}"
                results = self._safely(f"'{query}'", lambda: self.api.search_tracks(query, country), [])

                for result in results:
                    if self._is_same_track(track, result) and self._has_artist(track, result, country):
                        return f"tidal:track:{result.id}", "search"

        return None

    def _is_same_track(self, track: FavoriteTrack, result: TidalTrack) -> bool:
        if not self.matcher.tracks_match(track.track_name, result.title):
            return False

        if track.length is None or result.duration_ms is None:
            return True

        return abs(track.length - result.duration_ms) <= self.config.track_max_duration_difference * 1000

    def _has_artist(self, track: FavoriteTrack, result: TidalTrack, country: str) -> bool:
        artists = self._safely(f"track {result.id}", lambda: self.api.get_track_artists(result.id, country), [])

        return any(self.matcher.artists_match(track.artist or "", artist) for artist in artists)
