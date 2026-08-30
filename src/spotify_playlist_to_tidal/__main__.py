# ABOUTME: Enables the package to run through `python -m spotify_playlist_to_tidal`.
# ABOUTME: Delegates all command behavior and exit handling to the CLI module.

from .cli import main

if __name__ == "__main__":
    main()
