from importlib import metadata
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP_NAME = "AI-Music-Crawler"


def add_license_files(package):
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    package.write(python_license, "licenses/Python/LICENSE.txt")

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pending = [Requirement(line) for line in requirements if line.strip() and not line.lstrip().startswith("#")]
    included = set()
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        if name in included or (requirement.marker and not requirement.marker.evaluate()):
            continue

        distribution = metadata.distribution(requirement.name)
        included.add(name)
        pending.extend(Requirement(dependency) for dependency in distribution.requires or [])
        for file in distribution.files or []:
            parts = file.parts
            if len(parts) > 1 and parts[0].endswith(".dist-info"):
                if parts[1].lower() == "licenses" or parts[-1].upper().startswith(
                    ("LICENSE", "LICENCE", "COPYING", "NOTICE")
                ):
                    package.write(distribution.locate_file(file), f"licenses/{name}/{'/'.join(parts[1:])}")


def main():
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise SystemExit("Build this release using 64-bit Python on Windows.")

    template = ROOT / "secrets.example.txt"
    if template.read_text(encoding="utf-8-sig").splitlines() != ["BILIBILI_COOKIE="]:
        raise SystemExit("The release requires an empty secrets.example.txt template.")

    DIST.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="music-build-", dir=DIST) as temp:
        build = Path(temp)
        subprocess.run([
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--onefile", "--windowed", "--noupx",
            "--name", APP_NAME,
            "--icon", str(ROOT / "assets" / "app.ico"),
            "--distpath", str(build),
            "--workpath", str(build / "work"),
            "--specpath", str(build),
            "--add-data", f"{ROOT / 'assets' / 'app.ico'}:assets",
            "--add-data", f"{ROOT / 'assets' / 'app.png'}:assets",
            str(ROOT / "desktop_app.pyw"),
        ], cwd=ROOT, check=True)

        executable = build / f"{APP_NAME}.exe"
        archive = build / f"{APP_NAME}-Windows-x64.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
            package.write(executable, executable.name)
            package.write(template, template.name)
            package.writestr("keywords.txt", "")
            package.write(ROOT / "README.md", "README.md")
            add_license_files(package)

        executable.replace(DIST / executable.name)
        archive.replace(DIST / archive.name)
    print(DIST / archive.name)


if __name__ == "__main__":
    main()
