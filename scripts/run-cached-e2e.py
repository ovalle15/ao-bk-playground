"""Restore Linux Python wheels, run the containerized E2E suite, and save the cache."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


# Resolve everything relative to this file: Buildkite may start the job from a
# different directory, but the cache target and requirements must stay fixed.
ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-e2e.txt"
WHEEL_DIR = ROOT / ".buildkite-cache" / "e2e-wheels"
# Use one Compose project name so startup and cleanup address the same stack.
COMPOSE = ("docker", "compose", "-p", "nasa-app-pytest", "-f", "docker-compose.test.yml")


def run(*command: str, env: dict[str, str]) -> None:
    """Show each external command and stop the job if it fails."""
    # check=True turns a failed cache, download, or test command into a failed job.
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def docker_environment() -> dict[str, str]:
    """Use the selected Docker context when the agent has no DOCKER_HOST."""
    env = os.environ.copy()
    if not env.get("DOCKER_HOST"):
        # Some agent hosts select Docker through a context rather than an
        # exported DOCKER_HOST; pass that endpoint to every Docker subprocess.
        env["DOCKER_HOST"] = subprocess.check_output(
            ("docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"),
            cwd=ROOT,
            env=env,
            text=True,
        ).strip()
    return env


def main() -> int:
    env = docker_environment()
    # Buildkite's cache key hashes this same file. The local marker is a second
    # check that the restored wheel directory belongs to these requirements.
    checksum = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()

    # The cache definition names e2e_wheels and maps it to WHEEL_DIR. A first
    # build or changed requirements can miss; restore does not populate wheels.
    print("Restoring the Linux Python wheel cache", flush=True)
    run("buildkite-agent", "cache", "restore", "--name", "e2e_wheels", env=env)

    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    marker = WHEEL_DIR / ".requirements-sha256"
    cached_checksum = marker.read_text().strip() if marker.exists() else ""
    if cached_checksum != checksum:
        # Download inside Linux with Python 3.11, matching the test image.
        # Wheels with native code can be specific to the OS, CPU, and Python ABI.
        print("Downloading Python wheels for the E2E test image", flush=True)
        run(
            "docker",
            "run",
            "--rm",
            # Mount the inputs instead of copying them into the download image.
            "--mount",
            f"type=bind,source={REQUIREMENTS},target=/requirements-e2e.txt,readonly",
            "--mount",
            f"type=bind,source={WHEEL_DIR},target=/wheels",
            "python:3.11-slim-bookworm",
            "python",
            "-m",
            "pip",
            "download",
            # Require installable wheels, including for transitive dependencies.
            "--only-binary=:all:",
            "-r",
            "/requirements-e2e.txt",
            "--dest",
            "/wheels",
            env=env,
        )
        # An incomplete download must not look like a reusable cache hit.
        marker.write_text(checksum + "\n")
    else:
        # The Dockerfile will use these wheels only if its own checksum matches.
        print("Using restored Python wheels", flush=True)

    # Upload new wheels to the S3-backed Buildkite cache. An already existing
    # key is skipped by Buildkite unless a force save is requested.
    print("Saving the wheel cache for later builds", flush=True)
    run("buildkite-agent", "cache", "save", "--name", "e2e_wheels", env=env)

    # Start fresh because the NASA stub has one-time failure state. Compose
    # rebuilds the E2E image, whose Dockerfile installs from the mounted wheels.
    print("Running the containerized browser E2E suite", flush=True)
    run(*COMPOSE, "down", env=env)
    try:
        run(
            *COMPOSE,
            "up",
            "--build",
            "--attach",
            "e2e",
            # End the stack when a service exits and report pytest's exit code.
            "--abort-on-container-exit",
            "--exit-code-from",
            "e2e",
            env=env,
        )
    finally:
        # Leave no test containers behind, including after a failed test. Do
        # not let a cleanup error replace the original pytest/Compose failure.
        subprocess.run((*COMPOSE, "down"), cwd=ROOT, env=env, check=False)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
