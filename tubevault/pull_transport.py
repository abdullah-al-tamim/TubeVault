"""YouTube transport for single-video, local downloads."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FORMATS = ("source", "mp4", "audio", "m4a", "mp3")
HEIGHTS = (144, 240, 360, 480, 720, 1080, 1440, 2160, 4320)


def video_id(url):
    try:
        link = urlsplit(url.strip())
        host = link.netloc.lower()
        parts = link.path.strip("/").split("/")
        if link.scheme not in {"http", "https"}:
            raise ValueError
        if host == "youtu.be" and len(parts) == 1:
            candidate = parts[0]
        elif host in {"www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parts == ["watch"]:
                candidate, = parse_qs(link.query).get("v", [])
            elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
                candidate = parts[1]
            else:
                raise ValueError
        else:
            raise ValueError
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", candidate):
            return candidate
    except ValueError:
        pass
    raise ValueError("Paste a link to one YouTube video or Short.")


def selection(kind, height):
    if kind not in FORMATS or (height is not None and height not in HEIGHTS):
        raise ValueError("Choose a supported format and height.")
    if kind in {"audio", "m4a", "mp3"}:
        if height is not None:
            raise ValueError("Height applies only to video.")
        if kind == "audio":
            return ["-f", "bestaudio/best", "-x"]
        return ["-f", "bestaudio/best", "-x", "--audio-format", kind, "--audio-quality", "0"]
    cap = f"[height<={height}]" if height else ""
    if kind == "mp4":
        return ["-f", f"bv[ext=mp4][vcodec^=avc1]{cap}+ba[ext=m4a]/b[ext=mp4][vcodec^=avc1]{cap}",
                "--merge-output-format", "mp4"]
    return ["-f", f"bv*{cap}+ba/b{cap}", "--merge-output-format", "mkv"]


def tool_path():
    paths = [os.environ.get("PATH", "")]
    if os.name == "nt":
        import winreg
        for hive, key in [(winreg.HKEY_CURRENT_USER, "Environment"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")]:
            try:
                with winreg.OpenKey(hive, key) as entry:
                    paths.append(os.path.expandvars(winreg.QueryValueEx(entry, "Path")[0]))
            except OSError:
                pass
        if local := os.environ.get("LOCALAPPDATA"):
            paths.append(str(Path(local) / "Microsoft" / "WinGet" / "Links"))
    return os.pathsep.join(p for p in paths if p)


def download(folder: Path, source_id, kind, height):
    search = tool_path()
    tools = {name: shutil.which(name, path=search) for name in ("yt-dlp", "ffmpeg", "ffprobe")}
    missing = [name for name, path in tools.items() if not path]
    if missing:
        raise RuntimeError(f"Missing {', '.join(missing)}. Open Repair Video Pull Tools in the Windows Start menu, then retry.")
    binary = tools["yt-dlp"]
    args = [binary, "--ignore-config", "--no-plugin-dirs", "--no-playlist", "--no-progress",
            "--no-cache-dir", "--js-runtimes", "node", "--match-filter", "!is_live & !is_upcoming",
            "--windows-filenames", "--socket-timeout", "30", "--no-simulate",
            "--encoding", "utf-8", "--print", "after_move:%(.{title,filepath,height,fps})j", "-o", "%(id)s.%(ext)s",
            *selection(kind, height), "--", f"https://www.youtube.com/watch?v={source_id}"]
    result = subprocess.run(args, cwd=folder, env={**os.environ, "PATH": search}, stdin=subprocess.DEVNULL, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=6 * 3600,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        if "requested format is not available" in result.stderr.lower():
            raise RuntimeError("This format is unavailable. Try best available or another height.")
        raise RuntimeError("Download failed. Check video access, network, free space and your yt-dlp version.")
    output = result.stdout.strip().splitlines()
    if not output:
        raise RuntimeError("No finished media was returned. Select a published, on-demand video.")
    info = json.loads(output[-1])
    path = (folder / info["filepath"]).resolve()
    if path.parent != folder or path.stem != source_id or not path.is_file() or not path.stat().st_size:
        raise RuntimeError("The downloader did not produce a complete media file.")
    return dict(path=str(path), title=info.get("title"), actual_height=info.get("height"), fps=info.get("fps"))
