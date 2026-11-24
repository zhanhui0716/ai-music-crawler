import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile


APP_DIR = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
SECRETS_FILE = APP_DIR / "secrets.txt"


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


def save_credentials(api_key, cookie):
    values = (api_key.strip(), cookie.strip())
    if any("\r" in value or "\n" in value for value in values):
        raise ValueError("Each credential must be on one line.")
    config = read_local_config()
    config.update(zip(("DEEPSEEK_API_KEY", "BILIBILI_COOKIE"), values))
    write_local_text(SECRETS_FILE, "".join(f"{key}={value}\n" for key, value in config.items()))
