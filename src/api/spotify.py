from typing import Optional

from src.api.base import OAuthClient
from src.config import Config
from src.models import AlbumTrack, SpotifyAlbumDetails, SpotifyTrack
from src.utils import require_env

class SpotifyClient(OAuthClient):
    def __init__(self, config: Config):
        client_id, client_secret = require_env("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")

        super().__init__(config, config.spotify_delay, config.spotify_auth_url, client_id, client_secret)

    def get_tracks(self, track_ids: list[str]) -> list[Optional[SpotifyTrack]]:
        data = self._get(f"{self.config.spotify_base_url}/tracks", {"ids": ",".join(track_ids)})

        return [SpotifyTrack.parse(t) if t else None for t in data.get("tracks", [None] * len(track_ids))]

    def get_albums(self, album_ids: list[str]) -> list[SpotifyAlbumDetails]:
        data = self._get(f"{self.config.spotify_base_url}/albums", {"ids": ",".join(album_ids)})
        albums = [SpotifyAlbumDetails.parse(album) for album in data.get("albums", []) if album]

        for album in albums:
            while album.next_url:
                page = self._get(album.next_url)

                album.tracks += [AlbumTrack.parse(item) for item in page.get("items", [])]
                album.next_url = page.get("next")

        return albums
