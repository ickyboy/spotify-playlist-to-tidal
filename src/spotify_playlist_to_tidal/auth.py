# ABOUTME: Opens authenticated Spotify and TIDAL sessions with private token storage.
# ABOUTME: Uses browser-based OAuth and keeps reusable credentials outside the repository.

from __future__ import annotations

import os
import re
import webbrowser
from collections.abc import Callable
from pathlib import Path

import spotipy
import tidalapi
from platformdirs import user_state_path
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth

_APP_NAME = "spotify-playlist-to-tidal"
_DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
_SPOTIFY_SCOPES = "playlist-read-private playlist-read-collaborative"
_URL = re.compile(r"https://\S+")


class ConfigurationError(RuntimeError):
    """Raised when local credentials or authentication cannot be configured."""


def state_directory() -> Path:
    """Return a private platform-appropriate directory for reusable OAuth tokens."""
    path = user_state_path(_APP_NAME, appauthor=False)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def _spotify_credentials() -> tuple[str, str]:
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        missing = [
            name
            for name, value in (
                ("SPOTIPY_CLIENT_ID", client_id),
                ("SPOTIPY_CLIENT_SECRET", client_secret),
            )
            if not value
        ]
        raise ConfigurationError(f"missing environment variable(s): {', '.join(missing)}")
    return client_id, client_secret


def validate_spotify_configuration() -> None:
    """Fail before filesystem changes when required Spotify credentials are absent."""
    _spotify_credentials()


def spotify_session(state_path: Path) -> spotipy.Spotify:
    """Authenticate Spotify with scopes that permit reading private playlists."""
    client_id, client_secret = _spotify_credentials()
    oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", _DEFAULT_REDIRECT_URI),
        scope=_SPOTIFY_SCOPES,
        cache_handler=CacheFileHandler(cache_path=state_path / "spotify-token.json"),
        open_browser=True,
        requests_timeout=15,
    )
    oauth.get_access_token(as_dict=False)
    return spotipy.Spotify(auth_manager=oauth, requests_timeout=15, retries=3)


def tidal_session(state_path: Path, report: Callable[[str], None]) -> tidalapi.Session:
    """Load a reusable TIDAL session, running device OAuth when one is unavailable."""
    session = tidalapi.Session()
    session_file = state_path / "tidal-session.json"

    def show_login(message: str) -> None:
        report(message)
        match = _URL.search(message)
        if match:
            webbrowser.open(match.group())

    if not session.login_session_file(session_file, fn_print=show_login):
        raise ConfigurationError("could not authenticate with TIDAL")
    session_file.chmod(0o600)
    return session
