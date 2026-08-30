# ABOUTME: Defines the one-input, one-output command-line interface for playlist copying.
# ABOUTME: Sends human-readable status to stderr and only the new TIDAL URI to stdout.

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from spotipy.exceptions import SpotifyBaseException
from tidalapi.exceptions import TidalAPIError

from .auth import (
    ConfigurationError,
    spotify_session,
    state_directory,
    tidal_session,
    validate_spotify_configuration,
)
from .transfer import TransferError, TransferResult, copy_playlist, spotify_playlist_id


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy one Spotify playlist to a newly created TIDAL playlist.",
        epilog="On success, stdout contains only the new TIDAL playlist URI.",
    )
    parser.add_argument(
        "spotify_uri",
        metavar="SPOTIFY_URI",
        help="spotify:playlist:... URI or https://open.spotify.com/playlist/... URL",
    )
    return parser


def _report(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _report_result(result: TransferResult) -> None:
    if result.skipped:
        _report(f"Skipped {len(result.skipped)} track(s):")
        for skipped in result.skipped:
            label = " ".join(skipped.label.splitlines())
            _report(f"  {skipped.position}. {label} ({skipped.reason})")
    visibility = "public" if result.public else "private"
    _report(
        f'Created "{result.playlist_name}" as a {visibility} playlist with '
        f"{result.copied_count}/{result.source_count} track(s)."
    )


def run(arguments: Sequence[str] | None = None) -> int:
    """Run the command and return a process exit status."""
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        spotify_playlist_id(args.spotify_uri)
    except ValueError as error:
        parser.error(str(error))

    try:
        validate_spotify_configuration()
        state_path = state_directory()
        spotify = spotify_session(state_path)
        tidal = tidal_session(state_path, _report)
        result = copy_playlist(args.spotify_uri, spotify, tidal, report=_report)
    except (
        ConfigurationError,
        TransferError,
        SpotifyBaseException,
        TidalAPIError,
        OSError,
    ) as error:
        _report(f"error: {error}")
        return 1

    _report_result(result)
    print(result.tidal_uri, flush=True)
    return 0


def main() -> NoReturn:
    """Console-script entry point."""
    raise SystemExit(run())
