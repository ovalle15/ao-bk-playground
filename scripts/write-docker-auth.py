#!/usr/bin/env python3
"""Write a short-lived registry token to an isolated Docker config."""

import base64
import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2 or not os.environ.get("DOCKER_CONFIG"):
        print("usage: DOCKER_CONFIG=<temp-dir> write-docker-auth.py <registry-host>", file=sys.stderr)
        return 2

    token = sys.stdin.read().strip()
    if not token:
        print("OIDC token was empty", file=sys.stderr)
        return 1

    registry = sys.argv[1]
    encoded = base64.b64encode(f"buildkite:{token}".encode()).decode()
    config_path = Path(os.environ["DOCKER_CONFIG"]) / "config.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    with os.fdopen(os.open(config_path, flags, 0o600), "w") as config_file:
        os.fchmod(config_file.fileno(), 0o600)
        json.dump({"auths": {registry: {"auth": encoded}}}, config_file)
        config_file.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
