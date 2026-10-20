# ABOUTME: Tests the pure playlist-transfer rules without contacting either service.
# ABOUTME: Covers URI parsing, destination naming, matching, and ordered batching.

import inspect
from datetime import date
from types import SimpleNamespace

import pytest
import tidalapi

from spotify_playlist_to_tidal.transfer import (
    SkippedTrack,
    SourcePlaylist,
    SourceTrack,
    TrackMetadata,
    TransferError,
    _source_track,
    batched,
    choose_playlist_name,
    copy_playlist,
    copy_source_playlist,
    metadata_matches,
    spotify_playlist_id,
)

PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M"


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (f"spotify:playlist:{PLAYLIST_ID}", PLAYLIST_ID),
        (f"https://open.spotify.com/playlist/{PLAYLIST_ID}", PLAYLIST_ID),
        (f"https://open.spotify.com/playlist/{PLAYLIST_ID}?si=abc123", PLAYLIST_ID),
    ],
)
def test_spotify_playlist_id_accepts_playlist_uris(uri: str, expected: str) -> None:
    assert spotify_playlist_id(uri) == expected


@pytest.mark.parametrize(
    "uri",
    [
        "spotify:album:37i9dQZF1DXcBWIGoYBM5M",
        "spotify:playlist:not-an-id",
        f"https://open.spotify.com.evil.example/playlist/{PLAYLIST_ID}",
        f"https://open.spotify.com/track/{PLAYLIST_ID}",
    ],
)
def test_spotify_playlist_id_rejects_other_values(uri: str) -> None:
    with pytest.raises(ValueError, match="Spotify playlist"):
        spotify_playlist_id(uri)


def test_copy_playlist_is_private_unless_public_is_requested() -> None:
    public = inspect.signature(copy_playlist).parameters["public"]

    assert public.default is False
    assert public.kind is inspect.Parameter.KEYWORD_ONLY


def test_choose_playlist_name_keeps_an_unused_name() -> None:
    assert choose_playlist_name("Road Trip", {"Other"}, date(2026, 3, 7)) == "Road Trip"


def test_choose_playlist_name_dates_a_collision() -> None:
    assert choose_playlist_name("Road Trip", {"Road Trip"}, date(2026, 3, 7)) == "260307 Road Trip"


def test_choose_playlist_name_numbers_a_dated_collision() -> None:
    names = {"Road Trip", "260307 Road Trip", "260307 Road Trip (2)"}
    assert choose_playlist_name("Road Trip", names, date(2026, 3, 7)) == "260307 Road Trip (3)"


def test_source_track_reads_current_spotify_playlist_item_shape() -> None:
    playlist_item = {
        "item": {
            "type": "track",
            "is_local": False,
            "uri": "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
            "name": "Never Gonna Give You Up",
            "artists": [{"name": "Rick Astley"}],
            "duration_ms": 213_573,
            "explicit": False,
            "external_ids": {"isrc": "GBARL9300135"},
        }
    }

    track = _source_track(playlist_item, position=1)

    assert isinstance(track, SourceTrack)
    assert track.spotify_uri == "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
    assert track.isrc == "GBARL9300135"


def test_metadata_matches_equivalent_text_and_duration() -> None:
    spotify = TrackMetadata("Le temps de l'amour", ("Françoise Hardy",), 147.2)
    tidal = TrackMetadata("Le Temps de l’Amour", ("Francoise Hardy",), 149.0)

    assert metadata_matches(spotify, tidal)


def test_metadata_match_rejects_a_different_version() -> None:
    spotify = TrackMetadata("Midnight City", ("M83",), 244.0)
    tidal = TrackMetadata("Midnight City (Eric Prydz Private Remix)", ("M83",), 244.0)

    assert not metadata_matches(spotify, tidal)


def test_metadata_match_requires_an_artist_and_close_duration() -> None:
    spotify = TrackMetadata("Home", ("Caribou",), 345.0)

    assert not metadata_matches(spotify, TrackMetadata("Home", ("Four Tet",), 345.0))
    assert not metadata_matches(spotify, TrackMetadata("Home", ("Caribou",), 350.0))


def test_metadata_match_rejects_a_clean_or_explicit_mismatch() -> None:
    spotify = TrackMetadata("Bad Guy", ("Billie Eilish",), 194.1, explicit=False)
    tidal = TrackMetadata("Bad Guy", ("Billie Eilish",), 194.0, explicit=True)

    assert not metadata_matches(spotify, tidal)


def test_batched_preserves_order_and_duplicates() -> None:
    assert list(batched(["1", "1", "2", "3"], size=3)) == [("1", "1", "2"), ("3",)]


def test_copy_source_playlist_dry_run_reports_ordered_matches_without_creating(monkeypatch) -> None:
    source_track = SourceTrack(
        position=1,
        spotify_uri="spotify:track:4uLU6hMCjMI75M1A2tKUQC",
        isrc=None,
        metadata=TrackMetadata("Song", ("Artist",), 60),
    )
    source = SourcePlaylist("Test", "Description", 1, (source_track,), ())
    monkeypatch.setattr(
        "spotify_playlist_to_tidal.transfer._match_tidal_track",
        lambda session, track: SimpleNamespace(id="tidal-123"),
    )
    tidal = object()

    result = copy_source_playlist(source, tidal, dry_run=True)

    assert result.tidal_uri is None
    assert result.matched == ((1, "tidal-123"),)
    assert result.copied_count == 1


def test_copy_source_playlist_sets_private_before_adding_tracks(monkeypatch) -> None:
    source_track = SourceTrack(
        position=1,
        spotify_uri="spotify:track:4uLU6hMCjMI75M1A2tKUQC",
        isrc=None,
        metadata=TrackMetadata("Song", ("Artist",), 60),
    )
    monkeypatch.setattr(
        "spotify_playlist_to_tidal.transfer._match_tidal_track",
        lambda session, track: SimpleNamespace(id="tidal-123"),
    )
    events: list[str] = []
    destination = SimpleNamespace(public=True, num_tracks=0, share_url="tidal:test")

    def make_private() -> bool:
        events.append("private")
        destination.public = False
        return True

    def add_tracks(ids, *, allow_duplicates, limit) -> None:
        events.append("add")
        destination.num_tracks += len(ids)

    destination.set_playlist_private = make_private
    destination.set_playlist_public = lambda: True
    destination.add = add_tracks

    class FakeUser(tidalapi.LoggedInUser):
        pass

    user = object.__new__(FakeUser)
    user.playlists = lambda: ()
    user.create_playlist = lambda name, description: destination

    copy_source_playlist(
        SourcePlaylist("Test", "Description", 1, (source_track,), ()), SimpleNamespace(user=user)
    )

    assert events == ["private", "add"]


def test_copy_source_playlist_refuses_to_create_when_nothing_matches(monkeypatch) -> None:
    source_track = SourceTrack(
        position=1,
        spotify_uri="spotify:track:4uLU6hMCjMI75M1A2tKUQC",
        isrc=None,
        metadata=TrackMetadata("Song", ("Artist",), 60),
    )
    monkeypatch.setattr(
        "spotify_playlist_to_tidal.transfer._match_tidal_track",
        lambda session, track: None,
    )

    with pytest.raises(TransferError, match="refusing to create"):
        copy_source_playlist(SourcePlaylist("Test", "", 1, (source_track,), ()), object())


def test_copy_source_playlist_dry_run_reports_all_skips_when_nothing_matches(monkeypatch) -> None:
    source_track = SourceTrack(
        position=1,
        spotify_uri="spotify:track:4uLU6hMCjMI75M1A2tKUQC",
        isrc=None,
        metadata=TrackMetadata("Song", ("Artist",), 60),
    )
    monkeypatch.setattr(
        "spotify_playlist_to_tidal.transfer._match_tidal_track",
        lambda session, track: None,
    )

    result = copy_source_playlist(
        SourcePlaylist("Test", "", 1, (source_track,), ()), object(), dry_run=True
    )

    assert result.tidal_uri is None
    assert result.matched == ()
    assert result.copied_count == 0
    assert result.skipped == (SkippedTrack(1, "Artist — Song", "no TIDAL match"),)
