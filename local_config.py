import os
from pathlib import Path


SECRETS_FILE = Path(__file__).resolve().with_name("secrets.txt")


def get_config(name):
    value = os.environ.get(name, "").strip()
    if value:
        return value

    try:
        with SECRETS_FILE.open(encoding="utf-8-sig") as secrets:
            for line in secrets:
                if line.lstrip().startswith("#"):
                    continue
                key, separator, value = line.partition("=")
                if separator and key.strip() == name:
                    return value.strip()
    except FileNotFoundError:
        pass
    return ""
