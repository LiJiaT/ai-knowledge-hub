"""Publish this repository to GitHub Pages using a locally stored token."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "LiJiaT/ai-knowledge-hub"
SITE_URL = "https://lijiat.github.io/ai-knowledge-hub/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Read deployment status without publishing")
    args = parser.parse_args()
    token_file = Path.home() / ".config/github-pages/token"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or token_file.read_text().strip()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({"https": "http://127.0.0.1:7897"}))
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ai-knowledge-hub-publisher"}

    def api(method, path, payload=None, missing=False, empty=False):
        request = urllib.request.Request("https://api.github.com" + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers, method=method)
        try:
            with client.open(request, timeout=40) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            if (missing and error.code == 404) or (empty and error.code == 409):
                return None
            try:
                message = json.loads(error.read()).get("message", "")
            except Exception:
                message = ""
            raise SystemExit(f"GitHub API {method} {path}: HTTP {error.code} {message[:250]}")
        except urllib.error.URLError:
            raise SystemExit(f"GitHub connection failed: {method} {path}; retry this command after connectivity recovers")

    prefix = "/repos/" + REPOSITORY
    if args.status:
        pages = api("GET", prefix + "/pages", missing=True)
        if pages is None:
            print("GitHub Pages has not been enabled.", flush=True)
            return
        build = api("GET", prefix + "/pages/builds/latest", missing=True)
        print(json.dumps({"site_url": pages.get("html_url"), "status": pages.get("status"), "source": pages.get("source"), "https_enforced": pages.get("https_enforced"), "build": None if build is None else {key: build.get(key) for key in ("status", "commit", "error", "updated_at")}}, ensure_ascii=False, indent=2), flush=True)
        return

    user = api("GET", "/user")
    if user["login"] != REPOSITORY.split("/")[0]:
        raise SystemExit("Token account does not match the configured repository owner.")
    info = api("GET", prefix)
    if info["private"]:
        raise SystemExit("Expected the authorized public repository; leaving visibility unchanged.")
    state_file = ROOT / "DEPLOYMENT_LOCAL.json"
    if not state_file.exists():
        branch = api("GET", prefix + "/git/ref/heads/main", missing=True, empty=True)
        if info["size"] != 0 or branch is not None:
            raise SystemExit("No local deployment record and remote repository is not empty; leaving it untouched.")
        state = {"repository": REPOSITORY, "repository_url": info["html_url"], "stage": "repository_created_in_browser"}
    else:
        state = json.loads(state_file.read_text())
        if state.get("repository") != REPOSITORY:
            raise SystemExit("Local deployment record differs.")
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print("Confirmed public repository:", info["html_url"], flush=True)

    readme = ROOT / "README.md"
    content = readme.read_text().replace("| 统一导航首页 | 已准备 |", "| 统一导航首页 | 已接入 |").replace("| 公众号 AI 库 | 首批发布 |", "| 公众号 AI 库 | 已接入 |")
    if "## 访问地址" not in content:
        content += "\n## 访问地址\n\n- 统一入口：" + SITE_URL + "\n- 公众号 AI 库：" + SITE_URL + "gzh/\n"
    readme.write_text(content)

    def git(*command, allowed=(0,), environment=None):
        result = subprocess.run(["git", "-C", str(ROOT), *command], env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode not in allowed:
            diagnostic = (result.stdout + "\n" + result.stderr).replace(token, "[REDACTED]")
            raise SystemExit(f"Git {command[0]} failed: {diagnostic[-2000:]}")
        return result

    if not (ROOT / ".git").exists():
        git("init", "-b", "main")
    git("config", "user.name", user["login"])
    git("config", "user.email", str(user["id"]) + "+" + user["login"] + "@users.noreply.github.com")
    remote = git("remote", "get-url", "origin", allowed=(0, 2, 128))
    if remote.returncode == 0:
        if remote.stdout.strip() != info["clone_url"]:
            raise SystemExit("Local origin differs; leaving it unchanged.")
    else:
        git("remote", "add", "origin", info["clone_url"])
    git("add", "--", ".gitignore", "README.md", "docs", "scripts/sync_gzh.py", "scripts/publish_github.py")
    if git("diff", "--cached", "--quiet", allowed=(0, 1)).returncode == 1:
        git("commit", "-m", "Publish AI knowledge hub static sites")
    commit = git("rev-parse", "HEAD").stdout.strip()
    print("Prepared commit:", commit, flush=True)

    with tempfile.TemporaryDirectory(prefix="ai-hub-git-") as directory:
        askpass = Path(directory) / "askpass.py"
        askpass.write_text('#!/usr/bin/env python3\nimport os,sys\nprint(os.environ["GH_TOKEN"] if "password" in sys.argv[1].lower() else os.environ["GITHUB_LOGIN"])\n')
        askpass.chmod(0o700)
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith("GIT_TRACE") or key == "GIT_CURL_VERBOSE":
                environment.pop(key)
        environment.update({"GH_TOKEN": token, "GITHUB_LOGIN": user["login"], "GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0"})
        git("-c", "credential.helper=", "-c", "http.proxy=http://127.0.0.1:7897", "push", "--set-upstream", "origin", "main", environment=environment)
    print("Pushed main to GitHub.", flush=True)
    state.update({"stage": "pushed", "commit": commit})
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    pages = api("GET", prefix + "/pages", missing=True)
    source = {"branch": "main", "path": "/docs"}
    if pages is None:
        pages = api("POST", prefix + "/pages", {"build_type": "legacy", "source": source})
    elif pages.get("source") != source or pages.get("build_type") == "workflow":
        api("PUT", prefix + "/pages", {"build_type": "legacy", "source": source})
    state.update({"stage": "pages_enabled", "site_url": pages.get("html_url", SITE_URL), "source": source})
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print("GitHub Pages configured:", state["site_url"], flush=True)


if __name__ == "__main__":
    main()
