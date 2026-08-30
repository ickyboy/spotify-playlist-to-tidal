# ABOUTME: Tests security-sensitive authentication parsing without contacting either service.
# ABOUTME: Ensures manual Spotify callbacks contain the expected state and authorization code.

import pytest

from spotify_playlist_to_tidal.auth import AuthenticationError, spotify_authorization_code


def test_spotify_authorization_code_accepts_the_expected_state() -> None:
    callback = "http://127.0.0.1:8888/callback?code=abc123&state=expected-state"

    assert spotify_authorization_code(callback, "expected-state") == "abc123"


def test_spotify_authorization_code_rejects_an_unexpected_state() -> None:
    callback = "http://127.0.0.1:8888/callback?code=abc123&state=other-state"

    with pytest.raises(AuthenticationError, match="state did not match"):
        spotify_authorization_code(callback, "expected-state")


def test_spotify_authorization_code_requires_a_code() -> None:
    callback = "http://127.0.0.1:8888/callback?state=expected-state"

    with pytest.raises(AuthenticationError, match="authorization code"):
        spotify_authorization_code(callback, "expected-state")
