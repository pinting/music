from src.api.base import APIClient
from src.config import Config
from src.models import DiscogsRelease
from src.utils import merge_distinct, require_env

class DiscogsClient(APIClient):
    def __init__(self, config: Config):
        super().__init__(config, config.discogs_delay)
        [self.api_key] = require_env("DISCOGS_API_KEY")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Discogs token={self.api_key}",
            "User-Agent": self.config.discogs_user_agent,
            "Accept": "application/json"
        }

    def search_releases(self, params: dict) -> list[DiscogsRelease]:
        data = self._get(
            f"{self.config.discogs_base_url}/database/search",
            {**params, "type": "release", "per_page": self.config.discogs_per_page}
        )

        return [
            DiscogsRelease(result.get("title", ""), merge_distinct([], result.get("genre", []) + result.get("style", [])))
            for result in data.get("results", [])
        ]
