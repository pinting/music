import base64
import hashlib
import json
import os
import secrets
import select
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from src.api.base import OAuthClient
from src.config import Config
from src.models import TidalAlbum, TidalTrack
from src.utils import require_env

def _next_cursor(links: dict) -> Optional[str]:
    next_url = links.get("next")
    cursors = parse_qs(urlparse(next_url).query).get("page[cursor]") if next_url else None

    return cursors[0] if cursors else None

def _included(data: dict, kind: str) -> list[dict]:
    return [item for item in data.get("included", []) if item.get("type") == kind]

class TidalClient(OAuthClient):
    def __init__(self, config: Config):
        client_id, client_secret = require_env("TIDAL_CLIENT_ID", "TIDAL_CLIENT_SECRET")

        super().__init__(config, config.tidal_delay, config.tidal_auth_url, client_id, client_secret)
        self.albums = {}

    @staticmethod
    def is_configured() -> bool:
        return bool(os.getenv("TIDAL_CLIENT_ID") and os.getenv("TIDAL_CLIENT_SECRET"))

    def _headers(self) -> dict:
        return {**super()._headers(), "Accept": "application/vnd.api+json"}

    def _request(self, endpoint: str, params: dict, country: Optional[str] = None) -> dict:
        params = {**params, "countryCode": country or self.config.tidal_country}

        return self._get(f"{self.config.tidal_base_url}{endpoint}", params)

    def _pages(self, endpoint: str, params: dict, country: str) -> Iterator[dict]:
        while True:
            data = self._request(endpoint, params, country)

            yield data

            cursor = _next_cursor(data.get("links", {}))

            if not cursor:
                return

            params = {**params, "page[cursor]": cursor}

    def _search(self, query: str, kind: str, country: str) -> tuple[list[str], list[dict]]:
        """Returns the matched ids of a kind in relevance order, and the included resources."""

        data = self._request("/searchResults", {"filter[query]": query, "include": kind}, country)
        results = data.get("data", [])

        if not results:
            return [], []

        references = results[0].get("relationships", {}).get(kind, {}).get("data", [])

        return [r["id"] for r in references if r.get("id")], _included(data, kind)

    def search_tracks(self, query: str, country: str) -> list[TidalTrack]:
        ids, included = self._search(query, "tracks", country)
        tracks = {item["id"]: TidalTrack.parse(item) for item in included}

        return [tracks[i] for i in ids if i in tracks]

    def search_albums(self, query: str, country: str) -> list[TidalAlbum]:
        ids, included = self._search(query, "albums", country)
        albums = {item["id"]: TidalAlbum.parse(item) for item in included}

        return [albums.get(i, TidalAlbum(i, "")) for i in ids]

    def find_albums_by_barcode(self, barcode: str, country: str) -> list[TidalAlbum]:
        data = self._request("/albums", {"filter[barcodeId]": barcode}, country)

        return [TidalAlbum.parse(item) for item in data.get("data", [])]

    def find_tracks_by_isrc(self, isrcs: list[str], country: str) -> tuple[list[TidalTrack], dict[str, TidalAlbum]]:
        """Returns the tracks of the recordings, and the albums they appear on."""

        tracks, albums = [], {}

        for data in self._pages("/tracks", {"filter[isrc]": isrcs, "include": "albums"}, country):
            tracks += [TidalTrack.parse(item) for item in data.get("data", [])]
            albums |= {item["id"]: TidalAlbum.parse(item) for item in _included(data, "albums")}

        return tracks, albums

    def get_album(self, album_id: str, country: str) -> Optional[TidalAlbum]:
        """Returns an album with its artists and tracks, following the pagination of the tracks."""

        key = (album_id, country)

        if key not in self.albums:
            self.albums[key] = self._fetch_album(album_id, country)

        return self.albums[key]

    def _fetch_album(self, album_id: str, country: str) -> Optional[TidalAlbum]:
        data = self._request(f"/albums/{album_id}", {"include": "artists,items"}, country)

        if not data.get("data"):
            return None

        album = TidalAlbum.parse(data["data"])
        album.artists = [item.get("attributes", {}).get("name", "") for item in _included(data, "artists")]
        album.tracks = [TidalTrack.parse(item) for item in _included(data, "tracks")]
        items = data["data"].get("relationships", {}).get("items", {})
        cursor = _next_cursor(items.get("links", {}))

        if cursor:
            params = {"include": "items", "page[cursor]": cursor}

            for page in self._pages(f"/albums/{album_id}/relationships/items", params, country):
                album.tracks += [TidalTrack.parse(item) for item in _included(page, "tracks")]

        return album

    def get_track_artists(self, track_id: str, country: str) -> list[str]:
        data = self._request(f"/tracks/{track_id}", {"include": "artists"}, country)

        return [item.get("attributes", {}).get("name", "") for item in _included(data, "artists")]

    def get_album_genres(self, album_uri: str) -> list[str]:
        data = self._request(f"/albums/{album_uri.split(':')[-1]}", {"include": "genres"})
        names = (item.get("attributes", {}).get("name") for item in _included(data, "genres"))

        return [name.strip() for name in names if name]

class TidalUserClient(TidalClient):
    """Acts on the collection of a user, which takes a login instead of the client credentials.
    The login runs once when the client is created, later runs reuse its saved refresh token."""

    def __init__(self, config: Config):
        super().__init__(config)
        self._authenticate()

    def add_to_collection(self, kind: str, ids: list[str]) -> list[dict]:
        """Adds albums or tracks and returns the skipped ones, with the reason they were skipped.
        The idempotency key makes it safe to retry the request."""

        return self._post(
            f"{self.config.tidal_base_url}/userCollection{kind.capitalize()}/me/relationships/items",
            {"data": [{"id": i, "type": kind} for i in ids]},
            {"Content-Type": "application/vnd.api+json", "Idempotency-Key": uuid.uuid4().hex}
        ).get("meta", {}).get("skipped", [])

    def _authenticate(self) -> None:
        data = self._refresh() or self._login()

        self.token = data["access_token"]
        self.token_expires_at = time.time() + data.get("expires_in", 3600) - self.config.token_margin

        if data.get("refresh_token"):
            self._save_refresh_token(data["refresh_token"])

    def _refresh(self) -> Optional[dict]:
        """Returns nothing without a usable refresh token, as that takes a new login."""

        token = self._load_refresh_token()

        if not token:
            return None

        response = self.session.post(
            self.auth_url,
            data={"grant_type": "refresh_token", "client_id": self.credentials[0], "refresh_token": token},
            timeout=self.config.timeout
        )

        if response.status_code in (400, 401):
            return None

        response.raise_for_status()

        return response.json()

    def _login(self) -> dict:
        """Authorization Code flow with PKCE. The redirect is caught by listening on the redirect
        URI when it is local, pasting the address the browser ends up on works too."""

        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        state = secrets.token_urlsafe(16)
        query = urlencode({
            "response_type": "code",
            "client_id": self.credentials[0],
            "redirect_uri": self.config.tidal_redirect_uri,
            "scope": " ".join(self.config.tidal_scopes),
            "code_challenge_method": "S256",
            "code_challenge": base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"),
            "state": state
        })

        print(f"Log in to Tidal: {self.config.tidal_login_url}?{query}")

        redirect = parse_qs(urlparse(self._wait_for_redirect()).query)

        if "error" in redirect:
            raise RuntimeError(f"Tidal login failed: {(redirect.get('error_description') or redirect['error'])[0]}")

        if "code" not in redirect:
            raise RuntimeError(
                f"Tidal login failed: no code in the address, paste the one starting with "
                f"{self.config.tidal_redirect_uri} instead of the login link"
            )

        if redirect.get("state") != [state]:
            raise RuntimeError("Tidal login failed: the address belongs to an earlier login link")

        response = self.session.post(
            self.auth_url,
            data={
                "grant_type": "authorization_code",
                "client_id": self.credentials[0],
                "code": redirect["code"][0],
                "redirect_uri": self.config.tidal_redirect_uri,
                "code_verifier": verifier
            },
            timeout=self.config.timeout
        )

        if not response.ok:
            raise RuntimeError(f"Tidal login failed: {response.status_code} {response.text}")

        return response.json()

    def _wait_for_redirect(self) -> str:
        """Returns the redirect address, from the browser or pasted into the terminal."""
        
        server = self._redirect_server()

        if server is None:
            return input("Paste the address you were redirected to: ").strip()

        print(f"Waiting for the login, or paste the address you were redirected to: ", end="", flush=True)

        try:
            while not server.redirect:
                readable, _, _ = select.select([server.socket, sys.stdin], [], [])

                if sys.stdin in readable:
                    return sys.stdin.readline().strip()

                server.handle_request()
        finally:
            server.server_close()

        print()

        return server.redirect

    def _redirect_server(self) -> Optional[HTTPServer]:
        """Listens on the redirect URI when it points to this machine and stdin can be waited on."""

        uri = urlparse(self.config.tidal_redirect_uri)

        if uri.hostname not in ("localhost", "127.0.0.1") or os.name == "nt":
            return None

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if urlparse(self.path).path != uri.path:
                    self.send_error(404)

                    return

                self.server.redirect = f"{uri.scheme}://{uri.netloc}{self.path}"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write("Tidal login received, you can close this tab.".encode("utf-8"))

            def log_message(self, *args):
                pass

        try:
            server = HTTPServer((uri.hostname, uri.port or 80), Handler)
        except OSError as e:
            print(f"Cannot listen on {uri.netloc} ({e}), the address has to be pasted")

            return None

        server.redirect = None

        return server

    def _load_refresh_token(self) -> Optional[str]:
        try:
            with open(self.config.tidal_token_file, "r", encoding="utf-8") as f:
                return json.load(f).get("refresh_token")
        except FileNotFoundError:
            return None

    def _save_refresh_token(self, token: str) -> None:
        descriptor = os.open(self.config.tidal_token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            json.dump({"refresh_token": token}, f)
