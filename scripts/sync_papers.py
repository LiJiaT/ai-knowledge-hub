"""Snapshot the current paper library and stage HTML/images for GitHub Pages."""
import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import tempfile
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
REPO = "LiJiaT/ai-knowledge-hub"

class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in ("href", "src") and value)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT.parent / "paper_library_site")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    def local_path(parent, value):
        parts = urllib.parse.urlsplit(html.unescape(value))
        if parts.scheme or parts.netloc or not parts.path:
            return None
        path = (parent.parent / urllib.parse.unquote(parts.path)).resolve()
        if not path.is_relative_to(source):
            raise RuntimeError("Reference escapes paper source: " + value)
        return path
    def stable_read(path):
        for attempt in range(3):
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns) and len(data) == after.st_size:
                return data
        raise RuntimeError("Source changing during snapshot: " + str(path))
    pending = [source / "index.html"]
    pages = {}
    reachable = set()
    while pending:
        path = pending.pop()
        if path in reachable:
            continue
        if not path.is_file():
            raise RuntimeError("Missing paper dependency: " + str(path))
        if path.suffix.lower() not in (".html", ".png", ".pdf"):
            raise RuntimeError("Unexpected paper dependency: " + str(path))
        reachable.add(path)
        if path.suffix.lower() == ".html":
            data = stable_read(path)
            pages[path] = data
            refs = References()
            refs.feed(data.decode("utf-8"))
            pending.extend(p for value in refs.links if (p := local_path(path, value)) is not None)
    snapshots = ROOT / ".paper_snapshots"
    snapshots.mkdir(exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix="build-", dir=snapshots) as work:
        capture = Path(work) / "source"
        for number, path in enumerate(sorted(reachable), 1):
            relative = path.relative_to(source)
            data = pages[path] if path in pages else stable_read(path)
            target = capture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            records.append({"path": relative.as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            if number % 500 == 0:
                print(f"Captured {number}/{len(reachable)} files", flush=True)
        identity = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        destination = snapshots / identity
        if destination.exists():
            for record in records:
                path = destination / "source" / record["path"]
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                    raise RuntimeError("Existing snapshot differs: " + record["path"])
        else:
            capture.rename(destination)
            # Keep originals under a source subdirectory for a stable manifest.
            moved = destination.with_name(destination.name + ".new")
            destination.rename(moved)
            destination.mkdir()
            moved.rename(destination / "source")
        tag = "papers-20261014-" + identity[:12]
        previous_path = ROOT / "PAPER_SNAPSHOT_LOCAL.json"
        if previous_path.exists():
            previous = json.loads(previous_path.read_text())
            old_pdfs = {p["source_path"]: p["sha256"] for p in previous.get("pdfs", [])}
            new_pdfs = {r["path"]: r["sha256"] for r in records if r["path"].endswith(".pdf")}
            if old_pdfs == new_pdfs and previous.get("tag"):
                tag = previous["tag"]
        pdfs = []
        pdf_urls = {}
        for record in records:
            if record["path"].endswith(".pdf"):
                path = Path(record["path"])
                name = path.parent.name + ".pdf"
                if path.name != "paper.pdf" or not re.fullmatch(r"[ap]\d+\.pdf", name) or record["bytes"] >= 2 * 1024**3:
                    raise RuntimeError("Unsupported PDF layout or size: " + record["path"])
                url = "https://github.com/" + REPO + "/releases/download/" + tag + "/" + name
                pdf_urls[(source / path).resolve()] = url
                pdfs.append({"source_path": record["path"], "local_path": str(destination / "source" / path), "asset_name": name, "bytes": record["bytes"], "sha256": record["sha256"], "url": url})
        if len(pdfs) > 1000 or len({p["asset_name"] for p in pdfs}) != len(pdfs):
            raise RuntimeError("PDF release asset count or names invalid")
        staged = ROOT / "docs/papers"
        site_files = []
        replacements = [0]
        for record in records:
            if record["path"].endswith(".pdf"):
                continue
            original = source / record["path"]
            data = (destination / "source" / record["path"]).read_bytes()
            if original.suffix == ".html":
                def replace(match):
                    local = local_path(original, match.group(2))
                    if local in pdf_urls:
                        replacements[0] += 1
                        fragment = urllib.parse.urlsplit(html.unescape(match.group(2))).fragment
                        return "href=" + match.group(1) + pdf_urls[local] + ("#" + fragment if fragment else "") + match.group(1)
                    return match.group(0)
                data = re.sub(r"href=([\"\'])(.*?)\1", replace, data.decode("utf-8")).encode("utf-8")
            target = staged / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != data:
                target.write_bytes(data)
            site_files.append({"path": record["path"], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        site_bytes = sum(p["bytes"] for p in site_files)
        if site_bytes >= 950_000_000:
            raise RuntimeError("Paper website is too large for GitHub Pages")
        if replacements[0] != len(pdfs):
            raise RuntimeError("PDF href count differs from PDF file count")
        manifest = {"schema_version": 1, "snapshot_id": identity, "tag": tag, "snapshot_dir": str(destination), "source": str(source), "site_bytes": site_bytes, "html_count": len(pages), "png_count": sum(r["path"].endswith(".png") for r in records), "pdf_count": len(pdfs), "pdfs": pdfs, "site_files": site_files}
        manifest_path = ROOT / "PAPER_SNAPSHOT_LOCAL.json"
        temp = manifest_path.with_suffix(".tmp")
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        temp.replace(manifest_path)
        print(f"Staged {len(pages)} HTML pages, {manifest['png_count']} images ({site_bytes:,} bytes), {len(pdfs)} PDF release assets ({sum(p['bytes'] for p in pdfs):,} bytes).", flush=True)
        print("Release tag:", tag, flush=True)

if __name__ == "__main__":
    main()
