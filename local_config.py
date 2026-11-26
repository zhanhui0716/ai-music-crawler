import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile


APP_DIR = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
SECRETS_FILE = APP_DIR / "secrets.txt"
DEFAULT_PARALLEL_JOBS = 3
MAX_PARALLEL_JOBS = 10


def read_local_config():
    try:
        lines = SECRETS_FILE.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return {}

    config = {}
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator and key.strip():
            config.setdefault(key.strip(), value.strip())
    return config


def parse_parallel_jobs(value):
    try:
        return max(1, min(MAX_PARALLEL_JOBS, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_PARALLEL_JOBS


def get_config(name):
    return os.environ.get(name, "").strip() or read_local_config().get(name, "")


def write_local_text(path, contents):
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".music-crawler-", delete=False
    ) as temp:
        temp_path = Path(temp.name)
        try:
            temp.write(contents)
            temp.close()
            temp_path.replace(path)
        finally:
            temp.close()
            temp_path.unlink(missing_ok=True)


def save_credentials(cookie, *, download_dir=None, parallel_jobs=None):
    cookie = cookie.strip()
    if "\r" in cookie or "\n" in cookie:
        raise ValueError("Each credential must be on one line.")
    config = read_local_config()
    config["BILIBILI_COOKIE"] = cookie
    if download_dir is not None:
        config["DOWNLOAD_DIR"] = download_dir
    if parallel_jobs is not None:
        config["PARALLEL_JOBS"] = str(parse_parallel_jobs(parallel_jobs))
    write_local_text(SECRETS_FILE, "".join(f"{key}={value}\n" for key, value in config.items()))
