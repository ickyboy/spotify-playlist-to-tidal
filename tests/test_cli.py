# ABOUTME: Exercises the installed command-line boundary without substituting service clients.
# ABOUTME: Verifies input validation and the machine-readable stdout contract.

import os
import subprocess
import sys


def test_help_describes_uri_input_and_output() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "spotify_playlist_to_tidal", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "SPOTIFY_URI" in result.stdout
    assert "TIDAL playlist URI" in result.stdout
    assert result.stderr == ""


def test_invalid_uri_fails_without_stdout() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "spotify_playlist_to_tidal", "spotify:album:not-a-playlist"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "expected a Spotify playlist URI" in result.stderr


def test_missing_spotify_credentials_fail_without_stdout() -> None:
    environment = os.environ.copy()
    for name in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"):
        environment.pop(name, None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "spotify_playlist_to_tidal",
            "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "SPOTIPY_CLIENT_ID" in result.stderr
    assert "SPOTIPY_CLIENT_SECRET" in result.stderr
