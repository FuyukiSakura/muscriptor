"""Fetch the audio track of a YouTube video with yt-dlp.

yt-dlp is called as an external program (it must be on PATH, along with the
ffmpeg it uses to convert the audio). The audio is converted to MP3: it is
decodable both by soundfile on our side and by every browser, which plays the
original audio back next to the transcription.
"""

import subprocess
from pathlib import Path
from urllib.parse import urlparse

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
}

_DOWNLOAD_TIMEOUT_S = 10 * 60


class YouTubeDownloadError(RuntimeError):
    """yt-dlp could not fetch the audio (unavailable or private video, network
    problem, yt-dlp missing, …). The message is meant to be shown to the user
    as-is."""


class YouTubeVideoTooLongError(YouTubeDownloadError):
    """The video is longer than the allowed duration, or is a live stream."""


def is_youtube_url(s: str) -> bool:
    """Whether `s` is an http(s) URL pointing at YouTube."""
    try:
        parsed = urlparse(s.strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and (
        (parsed.hostname or "").lower() in _YOUTUBE_HOSTS
    )


def download_youtube_audio(
    url: str, dest_dir: str | Path, max_duration_s: float | None = None
) -> Path:
    """Download the audio of the YouTube video at `url` into `dest_dir` as MP3.

    The file is named after the video title. Only single videos are fetched:
    a playlist link (`watch?v=…&list=…`) downloads just the video it points at.

    Args:
        url: A YouTube URL (see `is_youtube_url`).
        dest_dir: Directory to write the MP3 into; must exist.
        max_duration_s: Refuse videos longer than this (and live streams),
            checked before anything is downloaded.

    Returns:
        Path to the downloaded MP3.
    """
    if not is_youtube_url(url):
        raise YouTubeDownloadError(f"not a YouTube URL: {url}")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        # Only ever the YouTube extractor, never the generic one: the URL may
        # come from a web client, and must not turn into arbitrary fetches.
        "--use-extractors",
        "youtube",
        "--format",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--windows-filenames",
        "--output",
        str(Path(dest_dir) / "%(title).150B [%(id)s].%(ext)s"),
        # Prints the final path after conversion, and implies --quiet.
        "--print",
        "after_move:filepath",
        "--no-simulate",
    ]
    if max_duration_s is not None:
        cmd += ["--match-filters", f"!is_live & duration <= {int(max_duration_s)}"]
    # "--" so a URL can never be parsed as an option.
    cmd += ["--", url.strip()]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_DOWNLOAD_TIMEOUT_S,
        )
    except FileNotFoundError as e:
        raise YouTubeDownloadError(
            "yt-dlp is not installed or not on PATH; "
            "see https://github.com/yt-dlp/yt-dlp#installation"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise YouTubeDownloadError(
            f"downloading from YouTube took longer than {_DOWNLOAD_TIMEOUT_S // 60} minutes"
        ) from e

    if proc.returncode != 0:
        errors = [
            line for line in proc.stderr.splitlines() if line.startswith("ERROR:")
        ]
        detail = (errors[-1] if errors else proc.stderr.strip()[-500:]) or (
            f"yt-dlp exited with status {proc.returncode}"
        )
        raise YouTubeDownloadError(
            f"could not download from YouTube: {detail.removeprefix('ERROR:').strip()}"
        )

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        # A video rejected by --match-filters is skipped with a zero exit
        # status and nothing printed.
        if max_duration_s is not None:
            limit = (
                f"{max_duration_s / 60:g} minutes"
                if max_duration_s >= 60
                else f"{max_duration_s:g} seconds"
            )
            raise YouTubeVideoTooLongError(
                f"the video is longer than {limit}, or is a live stream"
            )
        raise YouTubeDownloadError("yt-dlp finished without downloading anything")
    path = Path(lines[-1].strip())
    if not path.is_file():
        raise YouTubeDownloadError(f"yt-dlp reported {path}, but it does not exist")
    return path
