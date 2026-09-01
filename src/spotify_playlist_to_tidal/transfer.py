# ABOUTME: Contains playlist-copying rules and the Spotify-playlist-to-TIDAL workflow.
# ABOUTME: Preserves source order and duplicates while reporting tracks that cannot transfer.

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from itertools import islice
from typing import Any
from urllib.parse import urlparse

import spotipy
import tidalapi
from tidalapi.exceptions import InvalidISRC, ObjectNotFound

_SPOTIFY_ID = re.compile(r"[A-Za-z0-9]{22}")
_SPOTIFY_URI = re.compile(r"spotify:playlist:([A-Za-z0-9]{22})")
_NON_WORDS = re.compile(r"[^\w]+")


class TransferError(RuntimeError):
    """Raised when a playlist cannot be copied safely."""


@dataclass(frozen=True, slots=True)
class TrackMetadata:
    title: str
    artists: tuple[str, ...]
    duration_seconds: float
    explicit: bool | None = None


@dataclass(frozen=True, slots=True)
class SourceTrack:
    position: int
    spotify_uri: str
    isrc: str | None
    metadata: TrackMetadata

    @property
    def label(self) -> str:
        return f"{', '.join(self.metadata.artists)} — {self.metadata.title}"


@dataclass(frozen=True, slots=True)
class SkippedTrack:
    position: int
    label: str
    reason: str


@dataclass(frozen=True, slots=True)
class SourcePlaylist:
    name: str
    description: str
    item_count: int
    tracks: tuple[SourceTrack, ...]
    skipped: tuple[SkippedTrack, ...]


@dataclass(frozen=True, slots=True)
class TransferResult:
    tidal_uri: str
    playlist_name: str
    public: bool
    source_count: int
    copied_count: int
    skipped: tuple[SkippedTrack, ...]


def spotify_playlist_id(uri: str) -> str:
    """Return a playlist ID from a Spotify URI or share URL."""
    uri_match = _SPOTIFY_URI.fullmatch(uri)
    if uri_match:
        return uri_match.group(1)

    parsed = urlparse(uri)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme == "https"
        and parsed.hostname == "open.spotify.com"
        and len(parts) == 2
        and parts[0] == "playlist"
        and _SPOTIFY_ID.fullmatch(parts[1])
    ):
        return parts[1]

    raise ValueError("expected a Spotify playlist URI or URL")


def choose_playlist_name(source_name: str, existing_names: Iterable[str], today: date) -> str:
    """Choose a unique name, adding YYMMDD and then a counter on collisions."""
    names = set(existing_names)
    if source_name not in names:
        return source_name

    dated_name = f"{today:%y%m%d} {source_name}"
    if dated_name not in names:
        return dated_name

    counter = 2
    while f"{dated_name} ({counter})" in names:
        counter += 1
    return f"{dated_name} ({counter})"


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(_NON_WORDS.sub(" ", without_marks).split())


def metadata_matches(source: TrackMetadata, candidate: TrackMetadata) -> bool:
    """Conservatively match tracks when an exact ISRC match is unavailable."""
    source_artists = {_normalized(artist) for artist in source.artists}
    candidate_artists = {_normalized(artist) for artist in candidate.artists}
    explicit_matches = (
        source.explicit is None
        or candidate.explicit is None
        or source.explicit == candidate.explicit
    )
    return (
        _normalized(source.title) == _normalized(candidate.title)
        and bool(source_artists & candidate_artists)
        and abs(source.duration_seconds - candidate.duration_seconds) <= 3
        and explicit_matches
    )


def batched[T](values: Iterable[T], size: int = 100) -> Iterator[tuple[T, ...]]:
    """Yield fixed-size tuples without changing order or removing duplicates."""
    if size < 1:
        raise ValueError("batch size must be positive")

    iterator = iter(values)
    while batch := tuple(islice(iterator, size)):
        yield batch


def _track_label(track: Mapping[str, Any] | None, position: int) -> str:
    if not track:
        return f"Spotify item {position}"
    artists = ", ".join(artist["name"] for artist in track.get("artists", ()) if artist.get("name"))
    title = track.get("name") or f"Spotify item {position}"
    return f"{artists} — {title}" if artists else title


def _source_track(item: Mapping[str, Any], position: int) -> SourceTrack | SkippedTrack:
    track = item.get("item") or item.get("track")
    label = _track_label(track, position)
    if not track:
        return SkippedTrack(position, label, "unavailable on Spotify")
    if track.get("type") != "track":
        return SkippedTrack(position, label, "not a music track")
    if track.get("is_local"):
        return SkippedTrack(position, label, "local Spotify file")

    artists = tuple(artist["name"] for artist in track.get("artists", ()) if artist.get("name"))
    title = track.get("name")
    duration_ms = track.get("duration_ms")
    spotify_uri = track.get("uri")
    if not title or not artists or not isinstance(duration_ms, (int, float)) or not spotify_uri:
        return SkippedTrack(position, label, "incomplete Spotify metadata")

    external_ids = track.get("external_ids") or {}
    return SourceTrack(
        position=position,
        spotify_uri=spotify_uri,
        isrc=external_ids.get("isrc"),
        metadata=TrackMetadata(
            title,
            artists,
            duration_ms / 1000,
            explicit=track.get("explicit") if isinstance(track.get("explicit"), bool) else None,
        ),
    )


def read_spotify_playlist(session: spotipy.Spotify, playlist_id: str) -> SourcePlaylist:
    """Read playlist metadata and every transferable Spotify track in source order."""
    summary = session.playlist(playlist_id, fields="id,name,description")
    name = summary.get("name")
    if not name:
        raise TransferError("Spotify returned a playlist without a name")

    fields = (
        "items(item(type,is_local,uri,name,artists(name),duration_ms,explicit,"
        "external_ids(isrc))),next"
    )
    page = session.playlist_items(
        playlist_id,
        fields=fields,
        limit=100,
        additional_types=("track", "episode"),
    )
    tracks: list[SourceTrack] = []
    skipped: list[SkippedTrack] = []
    position = 0

    while page:
        for item in page.get("items", ()):
            position += 1
            parsed = _source_track(item, position)
            if isinstance(parsed, SourceTrack):
                tracks.append(parsed)
            else:
                skipped.append(parsed)
        page = session.next(page) if page.get("next") else None

    return SourcePlaylist(
        name=name,
        description=summary.get("description") or "",
        item_count=position,
        tracks=tuple(tracks),
        skipped=tuple(skipped),
    )


def _tidal_metadata(track: tidalapi.Track) -> TrackMetadata:
    title = track.full_name or track.name
    return TrackMetadata(
        title=title,
        artists=tuple(artist.name for artist in (track.artists or ()) if artist.name),
        duration_seconds=float(track.duration),
        explicit=track.explicit,
    )


def _available(tracks: Iterable[tidalapi.Track]) -> list[tidalapi.Track]:
    return [track for track in tracks if track.available]


def _match_tidal_track(session: tidalapi.Session, source: SourceTrack) -> tidalapi.Track | None:
    if source.isrc:
        try:
            isrc_matches = _available(session.get_tracks_by_isrc(source.isrc))
        except (InvalidISRC, ObjectNotFound):
            isrc_matches = []
        if isrc_matches:
            return min(
                isrc_matches,
                key=lambda track: abs(track.duration - source.metadata.duration_seconds),
            )

    query = f"{source.metadata.title} {source.metadata.artists[0]}"
    search_results = session.search(query, models=[tidalapi.Track], limit=20)
    metadata_matches_ = [
        track
        for track in _available(search_results["tracks"])
        if metadata_matches(source.metadata, _tidal_metadata(track))
    ]
    if not metadata_matches_:
        return None
    return min(
        metadata_matches_,
        key=lambda track: abs(track.duration - source.metadata.duration_seconds),
    )


def _set_tidal_visibility(playlist: tidalapi.UserPlaylist, public: bool) -> None:
    if playlist.public is public:
        return

    updated = playlist.set_playlist_public() if public else playlist.set_playlist_private()
    if not updated or playlist.public is not public:
        visibility = "public" if public else "private"
        raise TransferError(
            f"TIDAL could not make the playlist {visibility}; playlist: {playlist.share_url}"
        )


def copy_playlist(
    spotify_uri: str,
    spotify: spotipy.Spotify,
    tidal: tidalapi.Session,
    report: Callable[[str], None] | None = None,
    *,
    public: bool = False,
) -> TransferResult:
    """Copy one Spotify playlist into a newly created TIDAL playlist.

    The new playlist stays private unless ``public`` is set, and is published
    only after every matched track has been added.
    """
    notify = report or (lambda _message: None)
    source = read_spotify_playlist(spotify, spotify_playlist_id(spotify_uri))
    notify(f'Matching {len(source.tracks)} track(s) from "{source.name}"...')

    tidal_ids: list[str] = []
    match_cache: dict[str, tidalapi.Track | None] = {}
    skipped = list(source.skipped)
    total = len(source.tracks)
    for index, source_track in enumerate(source.tracks, start=1):
        if source_track.spotify_uri not in match_cache:
            match_cache[source_track.spotify_uri] = _match_tidal_track(tidal, source_track)
        match = match_cache[source_track.spotify_uri]
        if match:
            tidal_ids.append(str(match.id))
        else:
            skipped.append(
                SkippedTrack(source_track.position, source_track.label, "no TIDAL match")
            )
        if index == 1 or index % 10 == 0 or index == total:
            notify(f"Checked {index}/{total} track(s)")

    user = tidal.user
    if not isinstance(user, tidalapi.LoggedInUser):
        raise TransferError("TIDAL session is not logged in")
    existing_names = (playlist.name for playlist in user.playlists() if playlist.name)
    destination_name = choose_playlist_name(source.name, existing_names, date.today())
    notify(f'Creating TIDAL playlist "{destination_name}"...')
    destination = user.create_playlist(destination_name, source.description)

    for batch in batched(tidal_ids):
        expected_count = destination.num_tracks + len(batch)
        destination.add(list(batch), allow_duplicates=True, limit=len(batch))
        if destination.num_tracks != expected_count:
            raise TransferError(
                f"TIDAL did not add every track; partial playlist: {destination.share_url}"
            )

    _set_tidal_visibility(destination, public)
    return TransferResult(
        tidal_uri=destination.share_url,
        playlist_name=destination_name,
        public=public,
        source_count=source.item_count,
        copied_count=len(tidal_ids),
        skipped=tuple(sorted(skipped, key=lambda track: track.position)),
    )
