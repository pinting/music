-- Keeps the favorites in sync with their criteria, without losing the Tidal URIs and
-- genres of the albums and tracks that are still favorites. Parameters come from the config.

CREATE TEMP TABLE qualifying_tracks AS
SELECT spotify_track_uri,
       master_metadata_album_artist_name AS artist,
       master_metadata_album_album_name AS album,
       master_metadata_track_name AS track_name,
       earliest_played_at AS added_at
FROM tracks
WHERE length > 0 AND ms_played >= :track_min_plays * length;

DELETE FROM favorite_tracks
WHERE spotify_track_uri NOT IN (SELECT spotify_track_uri FROM qualifying_tracks);

INSERT INTO favorite_tracks (spotify_track_uri, tidal_track_uri, artist, album, track_name, added_at)
SELECT spotify_track_uri, '', artist, album, track_name, added_at
FROM qualifying_tracks
WHERE TRUE
ON CONFLICT(spotify_track_uri) DO UPDATE SET
    artist=excluded.artist,
    album=excluded.album,
    track_name=excluded.track_name,
    added_at=excluded.added_at;

DROP TABLE temp.qualifying_tracks;

-- Editions of an album share their artists and name, only the most listened one is kept
CREATE TEMP TABLE qualifying_albums AS
SELECT spotify_album_uri,
       release_date,
       artists,
       album_name,
       total_tracks,
       actual_length,
       total_listening_time,
       percentage_played
FROM (
    SELECT album_uri AS spotify_album_uri,
           release_date,
           artists,
           album_name,
           total_tracks,
           actual_length,
           total_listening_time,
           ROUND(percentage_played, 2) AS percentage_played,
           ROW_NUMBER() OVER (
               PARTITION BY LOWER(artists), LOWER(album_name)
               ORDER BY total_listening_time DESC, album_uri
           ) AS edition
    FROM albums
    WHERE actual_length > 0
      AND total_listening_time >= :album_min_plays * actual_length
      AND percentage_played >= :album_min_percentage
      AND total_tracks >= :album_min_tracks
)
WHERE edition = 1;

DELETE FROM favorite_albums
WHERE spotify_album_uri NOT IN (SELECT spotify_album_uri FROM qualifying_albums);

INSERT INTO favorite_albums (
    spotify_album_uri, tidal_album_uri, release_date, artists, album_name,
    total_tracks, actual_length, total_listening_time, percentage_played, genres
)
SELECT spotify_album_uri, '', release_date, artists, album_name,
       total_tracks, actual_length, total_listening_time, percentage_played, '[]'
FROM qualifying_albums
WHERE TRUE
ON CONFLICT(spotify_album_uri) DO UPDATE SET
    release_date=excluded.release_date,
    artists=excluded.artists,
    album_name=excluded.album_name,
    total_tracks=excluded.total_tracks,
    actual_length=excluded.actual_length,
    total_listening_time=excluded.total_listening_time,
    percentage_played=excluded.percentage_played;

DROP TABLE temp.qualifying_albums;
