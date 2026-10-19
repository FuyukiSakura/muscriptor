"""Tests for the yt-dlp wrapper in utils/youtube.py (yt-dlp itself is faked)."""

import subprocess

import pytest

import muscriptor.utils.youtube as yt


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "http://youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw",
        "https://music.youtube.com/watch?v=jNQXAC9IVRw",
        "https://M.YouTube.com/watch?v=jNQXAC9IVRw",
        "  https://youtu.be/jNQXAC9IVRw\n",
    ],
)
def test_is_youtube_url_accepts(url):
    assert yt.is_youtube_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "song.mp3",
        "C:\\music\\song.mp3",
        "https://example.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com.evil.example/watch?v=x",
        "file:///etc/passwd",
        "ftp://youtube.com/x",
        "--exec=rm",
    ],
)
def test_is_youtube_url_rejects(url):
    assert not yt.is_youtube_url(url)


def _fake_run(monkeypatch, stdout="", stderr="", returncode=0):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    monkeypatch.setattr(yt.subprocess, "run", run)
    return calls


def test_download_returns_printed_path(monkeypatch, tmp_path):
    out = tmp_path / "Me at the zoo [jNQXAC9IVRw].mp3"
    out.write_bytes(b"mp3")
    calls = _fake_run(monkeypatch, stdout=f"{out}\n")
    url = "https://youtu.be/jNQXAC9IVRw"
    assert yt.download_youtube_audio(url, tmp_path, max_duration_s=900) == out
    cmd = calls[0]
    # The URL comes last, after "--", so it can never be read as an option.
    assert cmd[-2:] == ["--", url]
    assert "--no-playlist" in cmd
    assert cmd[cmd.index("--use-extractors") + 1] == "youtube"
    assert "duration <= 900" in cmd[cmd.index("--match-filters") + 1]


def test_download_rejects_non_youtube_without_running(monkeypatch, tmp_path):
    calls = _fake_run(monkeypatch)
    with pytest.raises(yt.YouTubeDownloadError):
        yt.download_youtube_audio("https://example.com/a.mp3", tmp_path)
    assert calls == []


def test_download_reports_yt_dlp_error(monkeypatch, tmp_path):
    _fake_run(
        monkeypatch,
        stderr="WARNING: something\nERROR: [youtube] xxx: Video unavailable\n",
        returncode=1,
    )
    with pytest.raises(yt.YouTubeDownloadError, match="Video unavailable"):
        yt.download_youtube_audio("https://youtu.be/xxx", tmp_path)


def test_download_filtered_out_is_too_long(monkeypatch, tmp_path):
    _fake_run(monkeypatch, stdout="")
    with pytest.raises(yt.YouTubeVideoTooLongError, match="15 minutes"):
        yt.download_youtube_audio("https://youtu.be/x", tmp_path, max_duration_s=900)


def test_download_missing_yt_dlp(monkeypatch, tmp_path):
    def run(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(yt.subprocess, "run", run)
    with pytest.raises(yt.YouTubeDownloadError, match="not installed"):
        yt.download_youtube_audio("https://youtu.be/x", tmp_path)
