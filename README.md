# [pinting.github.io/music](https://pinting.github.io/music)

Streaming history ingestion, aggregation and metadata enrichment pipeline for Spotify, Tidal and Discogs.

Requires [UV](https://docs.astral.sh/uv/getting-started/installation)!

## Setup

Create a copy of `.env.template` as `.env` and put in your API credentials!

Setup the virtual environment and install dependencies.

```bash
uv venv
uv sync
```

Activate the environment.

```bash
source .venv/bin/activate
# or on Windows: .venv\Scripts\activate
```

## Running

Execute from the root directory of this repository after activating the virtual environment.

```bash
# Run all stages, the migrate stage writes to your Tidal collection
python -m src

# Run selected stages, always executed in pipeline order
python -m src --stages favorites tidal genres

# Process at most 20 items per API stage
python -m src --stages tidal --limit 20
```

| Stage       | Requires                  | Description                                                                  |
| ----------- | ------------------------- | ---------------------------------------------------------------------------- |
| `history`   |                           | Loads `history/Streaming_History_Audio_*.json`, skipping already loaded files |
| `tracks`    |                           | Aggregates history into tracks                                               |
| `albums`    | Spotify                   | Fetches lengths and albums of the tracks, computes album statistics          |
| `favorites` |                           | Syncs favorites with `favorites.sql`, keeping Tidal URIs and genres          |
| `details`   | Spotify                   | Fetches the barcode and full tracklist of favorite albums                    |
| `tidal`     | Tidal                     | Matches favorites by barcode, ISRC, then scored search                       |
| `migrate`   | Tidal login               | Adds the favorite albums and tracks matched by `tidal` to your Tidal collection |
| `genres`    | Discogs, Tidal (optional) | Merges album genres from Discogs and Tidal, falling back to tags shared by releases of the exact artist |
| `export`    |                           | Writes `docs/albums.csv` for the website and `docs/tracks.csv`              |

Every parameter (paths, endpoints, delays, retries, favorite criteria, matching thresholds and keywords) has its default in `src/config.py` and can be overridden from the command line, see `python -m src --help`.

```bash
python -m src --stages favorites --favorite-track-min-plays 10 --favorite-album-min-tracks 5
```

## Migrating to Tidal

The `migrate` stage writes to your own collection, which takes a login instead of the app credentials. Add the `collection.write` scope and the redirect URI `http://localhost:8080/callback` to your app on the [Tidal developer portal](https://developer.tidal.com/dashboard), or pass your own with `--tidal-redirect-uri`.

```bash
python -m src --stages migrate --limit 5
```

The first run prints a login link. Open it in a browser on the same machine and log in. The stage listens on the redirect URI and picks up the login by itself. If the browser runs elsewhere and ends up on a page that does not load, paste that page's address (starting with `http://localhost:8080/callback?code=`) into the terminal. The refresh token is saved to `.tidal_token.json`, so later runs do not ask again. Items already in the collection are skipped, so the stage can be repeated. Favorites without a Tidal match are left out.

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).

The AGPL-3.0 is a strong copyleft license that requires you to release the source code of any modified versions of this software, including when used over a network.
