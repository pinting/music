-- Schema definition for music pipeline database

CREATE TABLE IF NOT EXISTS history (
    id                                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                                  TEXT,
    platform                            TEXT,
    ms_played                           INTEGER,
    conn_country                        TEXT,
    ip_addr                             TEXT,
    master_metadata_track_name          TEXT,
    master_metadata_album_artist_name   TEXT,
    master_metadata_album_album_name    TEXT,
    spotify_track_uri                   TEXT,
    episode_name                        TEXT,
    episode_show_name                   TEXT,
    spotify_episode_uri                 TEXT,
    audiobook_title                     TEXT,
    audiobook_uri                       TEXT,
    audiobook_chapter_uri               TEXT,
    audiobook_chapter_title             TEXT,
    reason_start                        TEXT,
    reason_end                          TEXT,
    shuffle                             INTEGER,
    skipped                             INTEGER,
    offline                             INTEGER,
    offline_timestamp                   INTEGER,
    incognito_mode                      INTEGER,
    source_file                         TEXT
);

CREATE TABLE IF NOT EXISTS tracks (
    spotify_track_uri                   TEXT PRIMARY KEY,
    master_metadata_track_name          TEXT,
    master_metadata_album_artist_name   TEXT,
    master_metadata_album_album_name    TEXT,
    ms_played                           INTEGER,
    length                              INTEGER,
    earliest_played_at                  TEXT,
    album_uri                           TEXT,
    isrc                                TEXT
);

CREATE TABLE IF NOT EXISTS albums (
    album_uri                TEXT PRIMARY KEY,
    album_id                 TEXT,
    album_name               TEXT,
    album_type               TEXT,
    total_tracks             INTEGER,
    release_date             TEXT,
    release_date_precision   TEXT,
    artists                  TEXT,
    artist_uris              TEXT,
    images                   TEXT,
    external_url             TEXT,
    href                     TEXT,
    actual_length            INTEGER,
    total_listening_time     INTEGER,
    percentage_played        REAL,
    upc                      TEXT
);

CREATE TABLE IF NOT EXISTS album_tracks (
    album_uri      TEXT,
    track_uri      TEXT,
    name           TEXT,
    disc_number    INTEGER,
    track_number   INTEGER,
    duration_ms    INTEGER,
    isrc           TEXT,
    PRIMARY KEY (album_uri, track_uri)
);

CREATE TABLE IF NOT EXISTS favorite_tracks (
    spotify_track_uri   TEXT,
    tidal_track_uri     TEXT,
    tidal_track_method  TEXT,
    artist              TEXT,
    album               TEXT,
    track_name          TEXT,
    added_at            TEXT
);

CREATE TABLE IF NOT EXISTS favorite_albums (
    spotify_album_uri      TEXT,
    tidal_album_uri        TEXT,
    tidal_album_method     TEXT,
    tidal_album_score      REAL,
    tidal_album_country    TEXT,
    release_date           TEXT,
    artists                TEXT,
    album_name             TEXT,
    total_tracks           INTEGER,
    actual_length          INTEGER,
    total_listening_time   INTEGER,
    percentage_played      REAL,
    genres                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_track_uri ON history(spotify_track_uri);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts);
CREATE INDEX IF NOT EXISTS idx_tracks_ms_played ON tracks(ms_played DESC);
CREATE INDEX IF NOT EXISTS idx_tracks_earliest ON tracks(earliest_played_at);
CREATE INDEX IF NOT EXISTS idx_tracks_album_uri ON tracks(album_uri);
CREATE INDEX IF NOT EXISTS idx_albums_type ON albums(album_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_favorite_tracks_uri ON favorite_tracks(spotify_track_uri);
CREATE INDEX IF NOT EXISTS idx_favorite_tracks_added ON favorite_tracks(added_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_favorite_albums_uri ON favorite_albums(spotify_album_uri);
CREATE INDEX IF NOT EXISTS idx_favorite_albums_listening ON favorite_albums(total_listening_time DESC);
