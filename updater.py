"""Self-update support for Live Karaoke.

Checks the GitHub Releases API for a newer version and can update the app in
place - via `git pull` when running from a clone, or by downloading and
extracting the release zip otherwise. All network / parse failures are swallowed
so the app never breaks when offline or rate-limited.
"""
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

__version__ = "1.2.0"
REPO = "phurteau/live-karaoke"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
_UA = {"User-Agent": f"live-karaoke-updater/{__version__}"}
_NOWIN = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW (quiet under pythonw)


# ------------------------------------------------------------ version compare
def _parse_version(tag):
    """'v1.2.3' -> (1, 2, 3). Non-numeric input -> (0,)."""
    nums = re.findall(r"\d+", str(tag or ""))
    return tuple(int(n) for n in nums) if nums else (0,)


def is_newer(latest, current):
    a, b = _parse_version(latest), _parse_version(current)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


# ------------------------------------------------------------------ check API
def check_for_update(current=__version__, timeout=6):
    """Return {version, tag, url, notes, zip} if a newer release exists, else None.
    Never raises."""
    api = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        req = urllib.request.Request(api, headers=_UA)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            data = json.load(r)
    except Exception:
        return None
    tag = data.get("tag_name") or data.get("name") or ""
    if not tag or not is_newer(tag, current):
        return None
    zip_url = None
    for a in data.get("assets", []) or []:
        name = (a.get("name") or "").lower()
        if name.endswith(".zip") and a.get("browser_download_url"):
            zip_url = a["browser_download_url"]
            break
    if not zip_url:
        zip_url = data.get("zipball_url")
    return {
        "version": str(tag).lstrip("vV"),
        "tag": tag,
        "url": data.get("html_url", f"https://github.com/{REPO}/releases/latest"),
        "notes": (data.get("body") or "").strip(),
        "zip": zip_url,
    }


# --------------------------------------------------------------- git updating
def _is_git_clone(appdir=APP_DIR):
    return os.path.isdir(os.path.join(appdir, ".git")) and shutil.which("git") is not None


def _git(appdir, *args, timeout=120):
    return subprocess.run(["git", "-C", appdir, *args], capture_output=True,
                          text=True, timeout=timeout, creationflags=_NOWIN)


def _update_via_git(appdir, tag):
    _git(appdir, "fetch", "--tags", "--force", "origin")
    pull = _git(appdir, "pull", "--ff-only", "origin", "main")
    if pull.returncode == 0:
        return True, "Updated via git (fast-forward)."
    ref = f"tags/{tag}" if tag else "origin/main"
    reset = _git(appdir, "reset", "--hard", ref)
    if reset.returncode == 0:
        return True, "Updated via git (reset to release)."
    return False, (pull.stderr or reset.stderr or "git update failed").strip()


# --------------------------------------------------------------- zip updating
def _download(url, dest, timeout=120):
    req = urllib.request.Request(url, headers=_UA)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__"}


def _update_via_zip(appdir, zip_url):
    if not zip_url:
        return False, "No download URL in the release."
    tmp = tempfile.mkdtemp(prefix="karaoke_upd_")
    try:
        zpath = os.path.join(tmp, "update.zip")
        _download(zip_url, zpath)
        exdir = os.path.join(tmp, "x")
        os.makedirs(exdir)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(exdir)
        entries = [os.path.join(exdir, e) for e in os.listdir(exdir)]
        subdirs = [e for e in entries if os.path.isdir(e)]
        rootfiles = [e for e in entries if os.path.isfile(e)]
        root = subdirs[0] if (not rootfiles and len(subdirs) == 1) else exdir
        copied = 0
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            rel = os.path.relpath(base, root)
            for fn in files:
                dstdir = appdir if rel == "." else os.path.join(appdir, rel)
                os.makedirs(dstdir, exist_ok=True)
                shutil.copy2(os.path.join(base, fn), os.path.join(dstdir, fn))
                copied += 1
        if copied == 0:
            return False, "Downloaded package was empty."
        return True, f"Updated from release zip ({copied} files)."
    except Exception as e:
        return False, f"Zip update failed: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ apply/run
def apply_update(info, appdir=APP_DIR):
    """Update the app in place. Returns (ok, message). Prefers git, falls back to zip."""
    tag = info.get("tag") if isinstance(info, dict) else None
    zip_url = info.get("zip") if isinstance(info, dict) else None
    if _is_git_clone(appdir):
        ok, msg = _update_via_git(appdir, tag)
        if ok:
            return True, msg
        ok2, msg2 = _update_via_zip(appdir, zip_url)
        return (ok2, msg2 if ok2 else f"{msg}; {msg2}")
    return _update_via_zip(appdir, zip_url)


def sync_dependencies(appdir=APP_DIR):
    """Best-effort pip sync using the app's venv, in case requirements changed."""
    py = os.path.join(appdir, ".venv", "Scripts", "python.exe")
    req = os.path.join(appdir, "requirements.txt")
    if os.path.exists(py) and os.path.exists(req):
        try:
            subprocess.run([py, "-m", "pip", "install", "-r", req],
                           capture_output=True, text=True, timeout=600, creationflags=_NOWIN)
        except Exception:
            pass


def relaunch(appdir=APP_DIR):
    """Start a fresh instance of the app. Caller should then exit."""
    launcher = os.path.join(appdir, "run_karaoke.bat")
    try:
        if os.path.exists(launcher):
            subprocess.Popen(["cmd", "/c", "start", "", launcher], cwd=appdir)
        else:
            exe = os.path.join(appdir, ".venv", "Scripts", "pythonw.exe")
            py = exe if os.path.exists(exe) else sys.executable
            subprocess.Popen([py, os.path.join(appdir, "karaoke.py")], cwd=appdir)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    cur = sys.argv[1] if len(sys.argv) > 1 else __version__
    info = check_for_update(cur)
    print(f"current={cur}  latest={info['version'] if info else '(up to date / unreachable)'}")
    if info:
        print("update url:", info["url"])
