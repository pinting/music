import sys

from src.api.discogs import DiscogsClient
from src.api.spotify import SpotifyClient
from src.api.tidal import TidalClient, TidalUserClient
from src.config import STAGES, Config, parse_args
from src.database import Database
from src.matching import TitleMatcher
from src.stages.albums import Albums
from src.stages.details import Details
from src.stages.export import Export
from src.stages.favorites import Favorites
from src.stages.genres import Genres
from src.stages.history import History
from src.stages.migrate import Migrate
from src.stages.tidal import Tidal
from src.stages.tracks import Tracks

def create_stage(name: str, db: Database, config: Config):
    match name:
        case "history":
            return History(db, config)
        case "tracks":
            return Tracks(db)
        case "albums":
            return Albums(db, SpotifyClient(config), config)
        case "favorites":
            return Favorites(db)
        case "details":
            return Details(db, SpotifyClient(config), config)
        case "tidal":
            return Tidal(db, TidalClient(config), TitleMatcher(config), config)
        case "migrate":
            return Migrate(db, TidalUserClient(config), config)
        case "genres":
            tidal = TidalClient(config) if TidalClient.is_configured() else None

            return Genres(db, DiscogsClient(config), tidal, TitleMatcher(config), config)
        case "export":
            return Export(db, config)

def main() -> None:
    config = parse_args()
    names = [name for name in STAGES if name in config.stages]

    print(f"Database: {config.database}")
    print(f"Stages: {', '.join(names)}")
    print(f"Limit: {config.limit or 'none'}\n")

    db = Database(config)

    try:
        db.setup()

        # All stages are created upfront, so missing credentials fail before any work is done
        for stage in [create_stage(name, db, config) for name in names]:
            stage.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    finally:
        db.close()

    print("\nDone.")

if __name__ == "__main__":
    main()
