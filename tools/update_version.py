import argparse
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Update SerrebiTorrent version file.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        raise SystemExit(f"Version file not found: {path}")

    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r"^APP_VERSION\s*=.*$",
        f'APP_VERSION = "{args.version}"',
        content,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit("Failed to update APP_VERSION in version file.")

    path.write_text(updated, encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
