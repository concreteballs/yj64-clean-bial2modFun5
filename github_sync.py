"""
YJ-64 GitHub Sync Utility
Version: 1.0.0
Language: Python 3.10+
Description: Pushes or updates a local file in the GitHub repository via REST API using a Personal Access Token.
"""

from __future__ import annotations
import os
import sys
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path

def push_file_to_github(
    file_path: str | Path,
    repo_full_name: str,
    branch: str = "main",
    commit_message: str = "Update via YJ-64 sync utility"
) -> bool:
    path_obj = Path(file_path)
    if not path_obj.exists():
        print(f"Error: Local file {path_obj} does not exist.")
        return False

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is not set.")
        return False

    with open(path_obj, "rb") as f:
        content_bytes = f.read()
    content_encoded = base64.b64encode(content_bytes).decode("utf-8")

    repo_path = path_obj.name
    url = f"https://api.github.com/repos/{repo_full_name}/contents/{repo_path}"

    sha = None
    req_get = urllib.request.Request(
        url + f"?ref={branch}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "YJ-64-Sync-Agent"
        }
    )
    try:
        with urllib.request.urlopen(req_get) as response:
            data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, dict) and "sha" in data:
                sha = data["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"API Warning/Error during file check: {e.code} {e.reason}")
    except Exception as ex:
        print(f"Connection check failed: {ex}")

    payload = {
        "message": commit_message,
        "content": content_encoded,
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    req_put = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "YJ-64-Sync-Agent"
        },
        method="PUT"
    )

    try:
        with urllib.request.urlopen(req_put) as response:
            if response.status in (200, 201):
                print(f"Success: File {path_obj.name} successfully pushed to {repo_full_name} ({branch}).")
                return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if e.fp else ""
        print(f"HTTP Error {e.code}: {e.reason} - {err_body}")
    except Exception as e:
        print(f"Failed to push file: {e}")

    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python github_sync.py <path_to_file>")
        sys.exit(1)
    
    target_file = sys.argv[1]
    repo_name = "concreteballs/yj64-clean-bial2modFun5"
    success = push_file_to_github(target_file, repo_name)
    sys.exit(0 if success else 1)
