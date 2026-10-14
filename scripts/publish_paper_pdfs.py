"""Publish immutable paper PDF assets with resumable GitHub Release uploads."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "LiJiaT/ai-knowledge-hub"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--background", action="store_true", help="Start a detached resumable upload")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    if args.background:
        pid_file = ROOT / "PDF_UPLOAD_LOCAL.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), 0)
                print("PDF upload process is already running:", pid_file.read_text().strip())
                return
            except (ProcessLookupError, ValueError):
                pass
        with (ROOT / "PDF_UPLOAD_LOCAL.log").open("a") as log:
            process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "--workers", str(args.workers)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        pid_file.write_text(str(process.pid))
        print("Detached PDF upload PID:", process.pid)
        return
    manifest = json.loads((ROOT / "PAPER_SNAPSHOT_LOCAL.json").read_text())
    state_file = ROOT / "PAPER_ASSETS_LOCAL.json"
    checkpoint = Path(manifest["snapshot_dir"]) / "ASSETS_STATE.json"
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {"snapshot_id": manifest["snapshot_id"], "tag": manifest["tag"], "stage": "preparing", "assets": {}}
    if state["snapshot_id"] != manifest["snapshot_id"]:
        raise SystemExit("PDF checkpoint differs from current snapshot")
    if args.status:
        print(json.dumps({"tag": state["tag"], "stage": state["stage"], "uploaded": len(state["assets"]), "total": len(manifest["pdfs"]), "uploaded_bytes": sum(a["bytes"] for a in state["assets"].values()), "release_url": state.get("release_url"), "last_error": state.get("last_error")}, ensure_ascii=False, indent=2))
        return
    token_path = Path.home() / ".config/github-pages/token"
    token = token_path.read_text().strip() if token_path.exists() else (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "")
    if not token:
        raise SystemExit("No GitHub Token configured")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ai-knowledge-hub-pdf-publisher"}
    lock = threading.RLock()
    failed = threading.Event()
    def save():
        with lock:
            text = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
            for path in (checkpoint, state_file):
                temp = path.with_name(path.name + ".tmp")
                temp.write_text(text)
                temp.replace(path)
    def api(method, path=None, payload=None, file=None, url=None, missing=False):
        endpoint = url or "https://api.github.com" + path
        if not endpoint.startswith(("https://api.github.com/", "https://uploads.github.com/")):
            raise RuntimeError("Unexpected API endpoint")
        for attempt in range(40):
            request_headers = headers.copy()
            data = None if payload is None else json.dumps(payload).encode()
            stream = None
            if file is not None:
                stream = Path(file).open("rb")
                data = stream
                request_headers.update({"Content-Type": "application/pdf", "Content-Length": str(Path(file).stat().st_size)})
            elif payload is not None:
                request_headers["Content-Type"] = "application/json"
            delay = None
            try:
                client = urllib.request.build_opener(urllib.request.ProxyHandler({"https": "http://127.0.0.1:7897"}))
                request = urllib.request.Request(endpoint, data=data, headers=request_headers, method=method)
                with client.open(request, timeout=180 if file else 40) as response:
                    body = response.read()
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as error:
                try:
                    message = str(json.loads(error.read()).get("message", "")).replace(token, "[REDACTED]")[:240]
                except Exception:
                    message = ""
                if missing and error.code == 404:
                    return None
                retry = error.code in (429, 500, 502, 503, 504) or (error.code == 403 and ("rate limit" in message.lower() or error.headers.get("Retry-After")))
                if not retry:
                    raise RuntimeError(f"GitHub {method}: HTTP {error.code} {message}") from None
                delay = max(15, min(300, 2 ** min(attempt + 3, 9)), int(error.headers.get("Retry-After", "0")))
                if error.headers.get("X-RateLimit-Remaining") == "0":
                    delay = max(delay, int(error.headers.get("X-RateLimit-Reset", "0")) - int(time.time()) + 5)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                delay = min(120, 5 * (attempt + 1))
            finally:
                if stream:
                    stream.close()
            with lock:
                state["last_error"] = f"Transient GitHub network or rate limit; retry in {delay}s"
                save()
            print(state["last_error"], flush=True)
            time.sleep(delay)
        raise RuntimeError("Repeated connection failures; rerun this script to resume")
    prefix = "/repos/" + REPO
    repo = api("GET", prefix)
    if repo.get("private") or repo.get("full_name", "").lower() != REPO.lower():
        raise SystemExit("Expected authorized public repository")
    if state.get("release_id"):
        release = api("GET", prefix + "/releases/" + str(state["release_id"]))
    else:
        release = next((r for r in api("GET", prefix + "/releases?per_page=100") if r["tag_name"] == manifest["tag"]), None)
        if release is None:
            release = api("POST", prefix + "/releases", {"tag_name": manifest["tag"], "target_commitish": "main", "name": "论文库 PDF · " + manifest["tag"], "body": "现成论文库的完整 PDF 快照，共 " + str(len(manifest["pdfs"])) + " 个文件，与 AI Knowledge Hub 论文页配套。", "draft": True, "prerelease": False})
    release_id = release["id"]
    state.update({"release_id": release_id, "release_url": release["html_url"], "stage": "uploading"})
    state.pop("last_error", None)
    state.pop("fatal_error", None)
    save()
    def assets():
        found = {}
        page = 1
        while True:
            batch = api("GET", prefix + f"/releases/{release_id}/assets?per_page=100&page={page}")
            found.update({a["name"]: a for a in batch})
            if len(batch) < 100:
                return found
            page += 1
    def validate(pdf, asset):
        if asset.get("state") != "uploaded" or asset.get("size") != pdf["bytes"] or (asset.get("digest") and asset["digest"] != "sha256:" + pdf["sha256"]):
            raise RuntimeError("Release asset differs: " + pdf["asset_name"])
        return {"id": asset["id"], "bytes": pdf["bytes"], "sha256": pdf["sha256"], "github_digest": asset.get("digest"), "url": asset["browser_download_url"]}
    def preserve_incomplete(pdf, asset):
        if asset.get("state") != "starter":
            raise RuntimeError("Unexpected release asset state: " + pdf["asset_name"])
        name = "incomplete-" + str(asset["id"]) + "-" + pdf["asset_name"] + ".failed-upload"
        api("PATCH", prefix + "/releases/assets/" + str(asset["id"]), {"name": name, "label": "Interrupted upload placeholder; preserved for inspection"})
        print("Preserved incomplete upload placeholder:", name, flush=True)
    current = assets()
    pending = []
    for pdf in manifest["pdfs"]:
        if pdf["asset_name"] in current and current[pdf["asset_name"]].get("state") == "starter":
            preserve_incomplete(pdf, current[pdf["asset_name"]])
            state["assets"].pop(pdf["asset_name"], None)
            pending.append(pdf)
        elif pdf["asset_name"] in current:
            state["assets"][pdf["asset_name"]] = validate(pdf, current[pdf["asset_name"]])
        else:
            pending.append(pdf)
    save()
    print(f"PDFs: {len(state['assets'])}/{len(manifest['pdfs'])} already uploaded, {sum(p['bytes'] for p in pending):,} bytes pending", flush=True)
    pacing = threading.Lock()
    next_start = [0.0]
    def upload(pdf):
        if failed.is_set():
            return
        path = Path(pdf["local_path"])
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != pdf["sha256"]:
            failed.set()
            raise RuntimeError("Immutable PDF changed: " + pdf["asset_name"])
        with pacing:
            time.sleep(max(0, next_start[0] - time.monotonic()))
            next_start[0] = time.monotonic() + 0.9
        try:
            url = release["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(pdf["asset_name"])
            asset = api("POST", file=path, url=url)
        except RuntimeError:
            asset = assets().get(pdf["asset_name"])
            if asset is None:
                failed.set()
                raise
        if asset.get("state") == "starter":
            preserve_incomplete(pdf, asset)
            asset = api("POST", file=path, url=url)
        record = validate(pdf, asset)
        with lock:
            state["assets"][pdf["asset_name"]] = record
            state.pop("last_error", None)
            save()
            done = len(state["assets"])
            if done % 20 == 0 or done == len(manifest["pdfs"]):
                print(f"Uploaded {done}/{len(manifest['pdfs'])} PDFs ({sum(a['bytes'] for a in state['assets'].values()):,} bytes)", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(upload, pdf) for pdf in pending]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as error:
                failed.set()
                with lock:
                    state.update({"stage": "interrupted", "last_error": str(error).replace(token, "[REDACTED]")[:300]})
                    state["fatal_error"] = state["last_error"]
                    save()
                print("Upload interrupted:", state["fatal_error"], flush=True)
                raise SystemExit(state["fatal_error"])
    current = assets()
    for pdf in manifest["pdfs"]:
        if pdf["asset_name"] not in current:
            raise SystemExit("Missing PDF: " + pdf["asset_name"])
        state["assets"][pdf["asset_name"]] = validate(pdf, current[pdf["asset_name"]])
    if release["draft"]:
        release = api("PATCH", prefix + f"/releases/{release_id}", {"draft": False, "make_latest": "false"})
    state.update({"stage": "complete", "release_url": release["html_url"]})
    state.pop("last_error", None)
    save()
    print("All PDFs verified and published:", state["release_url"], flush=True)

if __name__ == "__main__":
    main()
