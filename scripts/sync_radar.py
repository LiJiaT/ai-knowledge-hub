"""Synchronize the rendered GitHub Radar page into the publishing directory."""
import argparse
import hashlib
from pathlib import Path
import shutil


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root.parent / "radar_project/radar_standalone/output/index.html")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    target = root / "docs/radar/index.html"
    if source.suffix.lower() != ".html" or not source.is_file():
        parser.error("source must be an HTML file")
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target:
        shutil.copy2(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"Synchronized {target.relative_to(root)} ({target.stat().st_size:,} bytes), SHA-256 {digest}")


if __name__ == "__main__":
    main()
