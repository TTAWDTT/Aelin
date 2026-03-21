from __future__ import annotations

from pathlib import Path


def main() -> None:
    p = Path("app/services/media_ingest.py")
    lines = p.read_text(encoding="utf-8").splitlines()
    for idx, line in enumerate(lines, start=1):
        if "def _sanitize_description_text" in line:
            for j in range(idx, idx + 60):
                print(f"{j:4}: {lines[j-1]}")
            print()
        if "def _sanitize_asr_text" in line:
            for j in range(idx, idx + 60):
                print(f"{j:4}: {lines[j-1]}")
            print()


if __name__ == "__main__":
    main()

