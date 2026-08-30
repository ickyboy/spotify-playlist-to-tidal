# ABOUTME: Opens authenticated Spotify and TIDAL sessions with private token storage.
# ABOUTME: Uses browser-based OAuth and keeps reusable credentials outside the repository.

from __future__ import annotations

import os
import re
import secrets
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
    """Raised when local credentials cannot be configured."""


class AuthenticationError(RuntimeError):
    """Raised when cached authentication is absent or invalid."""


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


def _spotify_oauth(
    state_path: Path,
    *,
    state: str | None = None,
    open_browser: bool = False,
) -> SpotifyOAuth:
    client_id, client_secret = _spotify_credentials()
    token_file = state_path / "spotify-token.json"
    if token_file.exists():
        token_file.chmod(0o600)
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", _DEFAULT_REDIRECT_URI),
        state=state,
        scope=_SPOTIFY_SCOPES,
        cache_handler=CacheFileHandler(cache_path=token_file),
        open_browser=open_browser,
        requests_timeout=15,
    )


def spotify_authorization_code(callback_url: str, expected_state: str) -> str:
    """Validate a manually pasted Spotify callback and return its one-time code."""
    returned_state, code = SpotifyOAuth.parse_auth_response_url(callback_url.strip())
    if not returned_state or not secrets.compare_digest(returned_state, expected_state):
        raise AuthenticationError("Spotify callback state did not match")
    if not code:
        raise AuthenticationError("Spotify callback did not contain an authorization code")
    return code


def spotify_session(state_path: Path) -> spotipy.Spotify:
    """Open Spotify from cached credentials without starting an interactive login."""
    oauth = _spotify_oauth(state_path)
    token = oauth.validate_token(oauth.cache_handler.get_cached_token())
    if not token:
        raise AuthenticationError(
            "Spotify authentication required; run: spotify-playlist-to-tidal auth login"
        )
    return spotipy.Spotify(auth_manager=oauth, requests_timeout=15, retries=3)


def login_spotify(
    state_path: Path,
    *,
    manual: bool,
    report: Callable[[str], None],
    prompt: Callable[[str], str] = input,
) -> None:
    """Create a Spotify token using a local browser callback or pasted callback URL."""
    state = secrets.token_urlsafe(32)
    oauth = _spotify_oauth(state_path, state=state, open_browser=not manual)
    if oauth.validate_token(oauth.cache_handler.get_cached_token()):
        report("Spotify: authenticated")
        return

    authorization_url = oauth.get_authorize_url()
    if manual:
        report(f"Open this Spotify authorization URL:\n{authorization_url}")
        callback_url = prompt("Paste the complete redirected callback URL: ")
        code = spotify_authorization_code(callback_url, state)
        oauth.get_access_token(code=code, as_dict=False, check_cache=False)
    else:
        report(f"Opening Spotify authorization in a browser:\n{authorization_url}")
        oauth.get_access_token(as_dict=False, check_cache=False)
    report("Spotify: authenticated")


def tidal_session(state_path: Path) -> tidalapi.Session:
    """Open TIDAL from cached credentials without starting an interactive login."""
    session_file = state_path / "tidal-session.json"
    if not session_file.exists():
        raise AuthenticationError(
            "TIDAL authentication required; run: spotify-playlist-to-tidal auth login"
        )

    session = tidalapi.Session()
    if not session.load_session_from_file(session_file) or not session.check_login():
        raise AuthenticationError(
            "TIDAL authentication required; run: spotify-playlist-to-tidal auth login"
        )
    session.save_session_to_file(session_file)
    session_file.chmod(0o600)
    return session


def login_tidal(
    state_path: Path,
    *,
    manual: bool,
    report: Callable[[str], None],
) -> None:
    """Create a TIDAL token through its device authorization flow."""
    try:
        tidal_session(state_path)
    except AuthenticationError:
        pass
    else:
        report("TIDAL: authenticated")
        return

    session = tidalapi.Session()
    session_file = state_path / "tidal-session.json"

    def show_login(message: str) -> None:
        report(message)
        match = _URL.search(message)
        if match and not manual:
            webbrowser.open(match.group())

    if not session.login_session_file(session_file, fn_print=show_login):
        raise AuthenticationError("could not authenticate with TIDAL")
    session_file.chmod(0o600)
    report("TIDAL: authenticated")
