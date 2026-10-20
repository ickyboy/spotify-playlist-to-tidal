# spotify-playlist-to-tidal

Copy one Spotify playlist—including a private playlist—into a new TIDAL playlist.
The command takes one Spotify URI and prints one TIDAL URI:

```text
spotify:playlist:...  →  https://tidal.com/browse/playlist/...
```

Status and skipped-track details go to stderr, so stdout is safe to capture from a
script.

## Requirements

- Python 3.12 or newer, managed by [uv](https://docs.astral.sh/uv/)
- Spotify and TIDAL accounts
- A Spotify application that you control
- A browser for normal OAuth setup, or any browser-enabled device for manual setup

## Install

From a project checkout:

```sh
uv sync --locked
```

The transfer command can then be run with `uv run`. A server installation may instead
install the project as a uv tool and invoke `spotify-playlist-to-tidal` directly.

## Spotify application setup

Create an app in the
[Spotify developer dashboard](https://developer.spotify.com/dashboard). Add this exact
redirect URI to the app:

```text
http://127.0.0.1:8888/callback
```

Provide the app credentials through the process environment:

```sh
export SPOTIPY_CLIENT_ID='...'
export SPOTIPY_CLIENT_SECRET='...'
```

Alternatively, place those lines in a local `.env` file and pass it to uv with
`--env-file .env`. The file is ignored by Git and should have `600` permissions. Set
`SPOTIPY_REDIRECT_URI` too if you registered a different loopback URI.

## Authentication

Authentication is an explicit setup step. Playlist transfers never launch browsers or
wait for interactive input.

### Workstation login

On a machine with a browser:

```sh
uv run --env-file .env spotify-playlist-to-tidal auth login
```

Spotify opens its consent page and returns through the loopback callback. TIDAL displays
a device-login link. Both services store reusable refresh tokens in the platform-specific
user state directory.

### Headless login

On a server without a browser:

```sh
uv run --env-file .env spotify-playlist-to-tidal auth login --manual
```

The command guides the complete flow:

1. Open the printed Spotify authorization URL on another device.
2. Approve access. The browser may report that it cannot connect to the loopback address.
3. Copy the complete callback URL from the browser address bar and paste it into the
   waiting command.
4. Open the printed TIDAL device-login URL and approve access.

The Spotify callback URL contains a short-lived, single-use authorization code. Treat it
as sensitive and paste it only into the waiting command.

### Inspect authentication

```sh
spotify-playlist-to-tidal auth status
spotify-playlist-to-tidal auth path
```

`auth status` validates both cached sessions without starting a login. `auth path` prints
the directory containing `spotify-token.json` and `tidal-session.json`.

### Transfer authentication to a server

A locally authenticated session can be provisioned to a trusted server without repeating
the browser flow:

1. Run `auth path` on both machines to find their platform-specific state directories.
2. Configure the same Spotify app credentials for the server process.
3. Copy `spotify-token.json` and `tidal-session.json` over SSH into the server's state
   directory.
4. Make the directory owned by the account that runs the service, with mode `700`.
5. Make both token files owned by that account, with mode `600`.
6. Run `auth status` as that same service account.

Never place app secrets or token files in the skill, source repository, command history,
or agent memory.

## Run

```sh
uv run spotify-playlist-to-tidal 'spotify:playlist:37i9dQZF1DXcBWIGoYBM5M'
```

Spotify share URLs are accepted as well:

```sh
uv run spotify-playlist-to-tidal 'https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M'
```

Authenticate explicitly with `auth login` before transferring; transfers never open
browsers or prompt for login. A successful run prints only the new TIDAL share URI to stdout:

```sh
tidal_uri=$(uv run spotify-playlist-to-tidal "$spotify_uri")
```

### Public-web extraction input

For a public playlist, an agent-assisted browser/web extraction can save the complete
page Markdown to a local file. Pass that file together with the same Spotify URL or URI;
the file is parsed locally and is never fetched by this command:

```sh
uv run spotify-playlist-to-tidal \
  --web-file ./public-playlist-page.md \
  'https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M'
```

This path does not need Spotify app configuration or Spotify authentication, but it still
needs TIDAL authentication for matching and copying. The parser fails closed unless the
page has one declared track total, contiguous numbered rows, valid Spotify track links,
complete title/artist/album/duration metadata, and a count matching the declared total.
A page identity link, when present, must match the supplied Spotify URL/URI. Recommended
tracks and page footer content are excluded. Web extraction is a snapshot; this command
does not imply that the saved page is fresh. Matching from web input has no ISRC and uses
normalized title/artist plus a three-second duration tolerance, so catalog versions can
be skipped.

Use `--dry-run` with either API or web-file input to perform real TIDAL matching without
creating or changing a destination playlist. It writes one stable JSON report to stdout,
including ordered source positions, matched TIDAL IDs, and skips; progress remains on
stderr. A normal successful transfer still writes exactly one TIDAL playlist URI to stdout.

## Transfer behavior

- The playlist title, description, track order, and duplicate tracks are preserved.
- Tracks are matched by ISRC first, then by exact normalized title and artist with a
  three-second duration tolerance.
- Local files, podcast episodes, unavailable items, and tracks without a conservative
  TIDAL match are skipped and reported.
- Playlist artwork is generated by TIDAL rather than copied from Spotify.
- The new TIDAL playlist is private unless `--public` is passed, regardless of the
  Spotify playlist's visibility. A `--public` playlist is published only after its
  tracks have been added successfully.
- A new TIDAL playlist is always created.
- If its name already exists, the new name is prefixed with the local date as `YYMMDD`.
  A same-day collision receives `(2)`, `(3)`, and so on.

Spotify and TIDAL have different catalogs, so skipped tracks are unavoidable in some
playlists.

## Troubleshooting

### `Spotify authentication required` or `TIDAL authentication required`

Run `auth status`, then use `auth login` or `auth login --manual`. On a server, run the
commands as the same Unix account that runs the playlist transfer.

### Spotify reports a redirect URI mismatch

Register the exact URI shown above in the Spotify dashboard. If you override
`SPOTIPY_REDIRECT_URI`, the environment value and registered URI must match exactly.

### A headless callback page cannot connect

That is expected in manual mode. Copy the complete URL from the browser address bar and
paste it into the waiting command.

### Some tracks are absent from the TIDAL playlist

Review the skipped-track report on stderr. Catalog misses do not prevent the remaining
tracks from transferring or a public playlist from being published.

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check src
```
