# AGENTS.md

## Purpose

This project copies one Spotify playlist into one newly created TIDAL playlist. Keep the
implementation focused on that single operation; do not add account-wide synchronization,
favorites migration, persistent match databases, or unrelated media-management features.

## Project layout

- `src/spotify_playlist_to_tidal/cli.py` owns command parsing and stdout/stderr behavior.
- `src/spotify_playlist_to_tidal/auth.py` owns Spotify and TIDAL authentication and token storage.
- `src/spotify_playlist_to_tidal/transfer.py` owns playlist reading, matching, naming, and creation.
- `tests/` contains pure unit tests and subprocess-level CLI tests.

## Behavioral invariants

- The transfer interface accepts one Spotify playlist URI or share URL.
- A successful transfer prints exactly one TIDAL playlist URI to stdout.
- Human-readable progress, skipped tracks, and errors go to stderr.
- Transfers are non-interactive. Authentication happens only through explicit `auth` commands.
- Preserve playlist description, source order, and duplicate tracks.
- Mirror Spotify public/private visibility. Unknown visibility defaults to private.
- Publish a public playlist only after all matched tracks have been added successfully.
- A missing catalog match is logged and skipped; it must not abort the transfer or publication.
- Authentication, network, rate-limit, and playlist-write failures must abort rather than masquerade
  as catalog misses.
- Always create a new playlist. Name collisions use a local `YYMMDD` prefix and then `(2)`, `(3)`,
  and so on.

## Authentication and security

- Never commit Spotify app secrets, OAuth tokens, callback URLs, or TIDAL session data.
- Never place credentials in tests, fixtures, documentation examples, logs, agent memory, or skill
  instructions.
- Keep the state directory at mode `700` and token files at mode `600`.
- Preserve OAuth state validation in the manual Spotify callback flow.
- `auth status` must remain non-interactive.
- Token transfer between machines is manual and must use an encrypted transport such as SSH.
- Live transfers and visibility changes modify a real TIDAL account and require explicit permission.

## Development

- Use Python 3.12 or newer.
- Use `uv` for dependency management, environments, running tools, locking, and builds.
- Do not use pip, Poetry, Conda, npm, or ad hoc virtual environments.
- Keep `uv.lock` synchronized with `pyproject.toml`.
- Practice TDD: add a failing test, confirm the failure, implement the smallest change, then refactor.
- Do not add mock service modes. Test pure rules directly and validate service integrations against
  real APIs only when credentials and explicit permission are available.
- Every Python code file starts with two `ABOUTME:` comment lines describing its responsibility.
- Prefer small, readable changes over abstractions that do not serve current behavior.

## Required verification

Run all of the following before considering a change complete:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check src
uv lock --check
uv sync --check
uv build
```

Test output must be clean. Remove generated build output, caches, and `.venv` after final verification
when preparing a clean repository snapshot.
