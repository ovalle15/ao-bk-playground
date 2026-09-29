"""Temporary registry auth should use Docker's config file, not Keychain."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path


def test_writes_private_docker_config_without_credential_helper(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "write-docker-auth.py"
    environment = {**os.environ, "DOCKER_CONFIG": str(tmp_path)}

    subprocess.run(
        [sys.executable, str(script), "packages.buildkite.com"],
        input="short-lived-token\n",
        text=True,
        env=environment,
        check=True,
        capture_output=True,
    )

    config_path = tmp_path / "config.json"
    config = json.loads(config_path.read_text())
    assert "credsStore" not in config
    assert "credHelpers" not in config
    encoded = config["auths"]["packages.buildkite.com"]["auth"]
    assert base64.b64decode(encoded).decode() == "buildkite:short-lived-token"
    assert config_path.stat().st_mode & 0o777 == 0o600
