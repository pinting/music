import difflib
import re
import unicodedata
from itertools import product
from typing import Optional

from src.config import Config

_BRACKETS = re.compile(r"\s*[\(\[].*?[\)\]]")

def fold(text: str) -> str:
    """Normalizes a name, ignoring accents, punctuation and case."""

    decomposed = unicodedata.normalize("NFKD", text)

    return _normalize("".join(c for c in decomposed if not unicodedata.combining(c)))

def contains_words(a: str, b: str) -> bool:
    """Checks if either text is a run of whole words in the other, ignoring accents."""

    a, b = fold(a), fold(b)

    return bool(a) and bool(b) and (f" {a} " in f" {b} " or f" {b} " in f" {a} ")

def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

def _normalize(title: str) -> str:
    title = re.sub(r"[\-_\/]", " ", title)
    title = re.sub(r"[^\w\s]", "", title.lower())

    return re.sub(r"\s+", " ", title).strip()

class _Clutter:
    """Strips keyword-marked clutter from titles, such as "(2011 Remaster)" or "- Deluxe Edition"."""

    def __init__(self, keywords: tuple, dash_excludes: tuple):
        dash_keywords = [k for k in keywords if k not in dash_excludes]

        self.brackets = re.compile(rf"\s*[\(\[][^\)\]]*?(?:{'|'.join(keywords)})[^\)\]]*?[\)\]]", re.IGNORECASE)
        self.dash = re.compile(rf"\s*-\s*.*?(?:{'|'.join(dash_keywords)}).*", re.IGNORECASE)

    def strip(self, title: str) -> str:
        return self.dash.sub("", self.brackets.sub("", title))

class TitleMatcher:
    def __init__(self, config: Config):
        self.config = config
        self.search_clutter = _Clutter(config.search_keywords, config.dash_keyword_excludes)
        self.track_clutter = _Clutter(config.track_keywords, config.dash_keyword_excludes)
        self.album_clutter = _Clutter(config.album_keywords, config.dash_keyword_excludes)
        self.track_variants = {}

    def clean_for_search(self, title: str) -> str:
        return self.search_clutter.strip(title).strip()

    def _clean_track(self, title: str, strip_prefix: bool, dash_part: Optional[int], strip_brackets: bool) -> str:
        if strip_prefix and ":" in title:
            title = title.split(":", 1)[1].strip()

        if dash_part is not None and " - " in title:
            title = title.split(" - ")[dash_part].strip()

        if strip_brackets:
            title = _BRACKETS.sub("", title)

        return _normalize(self.track_clutter.strip(title))

    def _track_variants(self, title: str) -> set[str]:
        if title not in self.track_variants:
            # The dash separates a title from its suffix, or an album or artist prefix from the title
            flags = product((False, True), (None, 0, -1), (False, True))

            self.track_variants[title] = {self._clean_track(title, *f) for f in flags} - {""}

        return self.track_variants[title]

    def tracks_match(self, a: str, b: str) -> bool:
        variants = self._track_variants(b)

        return any(self._cleaned_tracks_match(x, y) for x in self._track_variants(a) for y in variants)

    def _cleaned_tracks_match(self, a: str, b: str) -> bool:
        if a == b:
            return True

        if a in b or b in a:
            if min(len(a), len(b)) / max(len(a), len(b)) >= self.config.track_min_containment:
                return True

        return 1.0 - _similarity(a, b) <= self.config.track_max_error

    def _artist_names(self, artists: str) -> set[str]:
        names = {fold(name) for name in re.split(self.config.artist_name_separators, artists, flags=re.IGNORECASE)}

        return (names | {fold(artists)}) - {""}

    def artists_match(self, a: str, b: str) -> bool:
        """Credits are written in many ways, such as "A, B", "A & B", or "A With B"."""

        return bool(self._artist_names(a) & self._artist_names(b)) or contains_words(a, b)

    def title_similarity(self, a: str, b: str) -> float:
        """Exact titles score the highest, then those only differing in edition clutter."""

        if _normalize(a) == _normalize(b):
            return 1.0

        stripped_a = _normalize(self.album_clutter.strip(a))
        stripped_b = _normalize(self.album_clutter.strip(b))

        if stripped_a and stripped_a == stripped_b:
            return 0.9

        return 0.9 * _similarity(stripped_a, stripped_b)

    def album_queries(self, artist: str, album: str, release_date: Optional[str] = None) -> list[str]:
        """Builds search queries, most specific first."""

        year = release_date[:4] if release_date and release_date[:4].isdigit() and len(release_date) >= 4 else ""
        clean = self.clean_for_search(album)
        titles = list(dict.fromkeys((album, clean)))
        name = artist.strip().lower()

        if name in self.config.various_artists:
            return _distinct(
                [f"{year} {title}" for title in titles if year]
                + titles
            )

        queries = []

        if name in (album.strip().lower(), clean.strip().lower()):
            queries += [f"{year} {artist}"] if year else []
            queries.append(artist)

        queries += _with_prefix(artist, titles, year)

        artists = [a.strip() for a in re.split(self.config.artist_separators, artist) if a.strip()]

        if len(artists) > 1:
            queries += _with_prefix(" ".join(artists), [album], year)

            for single in artists:
                queries += _with_prefix(single, titles, year)

        queries += [f"{year} {title}" for title in titles if year]

        return _distinct(queries + titles)

def _with_prefix(prefix: str, titles: list[str], year: str) -> list[str]:
    return [f"{year} {prefix} {title}" for title in titles if year] + [f"{prefix} {title}" for title in titles]

def _distinct(queries: list[str]) -> list[str]:
    distinct = {}

    for query in queries:
        query = query.strip()

        if query:
            distinct.setdefault(query.lower(), query)

    return list(distinct.values())
