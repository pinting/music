from dataclasses import dataclass
from typing import Optional

from src.config import Config
from src.matching import TitleMatcher
from src.models import AlbumTrack, TidalAlbum, TidalTrack

@dataclass
class AlbumScore:
    total: float
    evidence: float
    isrc: float
    tracks: float
    title: float
    artist: float
    year: float

class AlbumScorer:
    """Scores how likely a Tidal album is the same edition as a Spotify album.

    The score is dominated by the track overlap, which penalizes other editions in both
    directions. Recordings are identified by ISRC, or by title and duration without one."""

    def __init__(self, matcher: TitleMatcher, config: Config):
        self.matcher = matcher
        self.config = config

    def score(self, name: str, artists: str, release_date: Optional[str], tracks: list[AlbumTrack], candidate: TidalAlbum) -> AlbumScore:
        config = self.config
        isrc = self._isrc_overlap(tracks, candidate.tracks)
        overlap, coverage = self._track_overlap(tracks, candidate.tracks)
        title = self.matcher.title_similarity(name, candidate.title)
        evidence = max(isrc, overlap)

        if coverage >= config.album_min_coverage and title >= config.album_coverage_min_title:
            evidence = max(evidence, config.album_coverage_evidence)

        artist = 1.0 if any(self.matcher.artists_match(artists, a) for a in candidate.artists) else 0.0
        year = 1.0 if (release_date or "")[:4] == (candidate.release_date or "")[:4] else 0.0
        total = (
            config.album_weight_tracks * evidence
            + config.album_weight_title * title
            + config.album_weight_artist * artist
            + config.album_weight_year * year
        )

        return AlbumScore(round(total, 4), evidence, isrc, overlap, title, artist, year)

    def is_match(self, score: AlbumScore) -> bool:
        return score.evidence >= self.config.album_min_evidence and score.total >= self.config.album_min_score

    @staticmethod
    def _isrc_overlap(tracks: list[AlbumTrack], candidate_tracks: list[TidalTrack]) -> float:
        isrcs = {t.isrc for t in tracks if t.isrc}
        candidate_isrcs = {t.isrc for t in candidate_tracks if t.isrc}

        if not isrcs or not candidate_isrcs:
            return 0.0

        return 2 * len(isrcs & candidate_isrcs) / (len(isrcs) + len(candidate_isrcs))

    def _track_overlap(self, tracks: list[AlbumTrack], candidate_tracks: list[TidalTrack]) -> tuple[float, float]:
        """Pairs up the tracks one-to-one, so ten versions of a song only count once. Returns
        the overlap of both tracklists, and the rate of the tracks found on the candidate."""
        if not tracks or not candidate_tracks:
            return 0.0, 0.0

        remaining = list(candidate_tracks)
        matched = 0.0
        found = 0

        for track in tracks:
            pair = self._pair(track, remaining)

            if pair is not None:
                remaining.remove(pair)
                found += 1
                matched += 1.0 if self._same_length(track.duration_ms, pair.duration_ms) else 0.75

        return 2 * matched / (len(tracks) + len(candidate_tracks)), found / len(tracks)

    def _pair(self, track: AlbumTrack, candidates: list[TidalTrack]) -> Optional[TidalTrack]:
        same_recording = next((c for c in candidates if track.isrc and c.isrc == track.isrc), None)

        if same_recording is not None:
            return same_recording

        titled = [c for c in candidates if self.matcher.tracks_match(track.name, c.title)]

        return next((c for c in titled if self._same_length(track.duration_ms, c.duration_ms)), titled[0] if titled else None)

    def _same_length(self, a: Optional[int], b: Optional[int]) -> bool:
        return a is not None and b is not None and abs(a - b) <= self.config.track_max_duration_difference * 1000
