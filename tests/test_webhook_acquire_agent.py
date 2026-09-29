"""Check that scheduled jobs start a host Buildkite agent."""

import importlib.util
import json
import sys
from pathlib import Path


def test_scheduled_job_starts_host_agent(monkeypatch, capsys):
    script = Path(__file__).resolve().parents[1] / "scripts" / "webhook-acquire-agent.py"
    spec = importlib.util.spec_from_file_location("webhook_acquire_agent", script)
    watcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watcher)

    event = {
        "event": "job.scheduled",
        "job": {"id": "1234-5678", "type": "script", "agent_query_rules": ["queue=webhook-acquire"]},
    }
    monkeypatch.setattr(watcher, "fetch_requests", lambda token, api_key: [
        {"uuid": "event-1", "headers": {}, "content": json.dumps(event)}
    ])
    monkeypatch.setattr(watcher.shutil, "which", lambda name: "/usr/local/bin/buildkite-agent")
    monkeypatch.setenv("WEBHOOK_SITE_TOKEN", "test-inbox")
    monkeypatch.setenv("BUILDKITE_AGENT_TOKEN", "test-agent-token")
    monkeypatch.setenv("BUILDKITE_TARGET_QUEUE", "webhook-acquire")
    monkeypatch.delenv("BUILDKITE_PIPELINE_SLUG", raising=False)
    monkeypatch.delenv("BUILDKITE_WEBHOOK_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", [str(script), "--once", "--replay-existing"])

    commands = []

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(command, env):
        commands.append(command)
        assert env["BUILDKITE_AGENT_TOKEN"] == "test-agent-token"
        assert "WEBHOOK_SITE_TOKEN" not in env
        return FakeProcess()

    monkeypatch.setattr(watcher.subprocess, "Popen", fake_popen)

    assert watcher.main() == 0
    assert len(commands) == 1
    assert commands[0][:2] == ["/usr/local/bin/buildkite-agent", "start"]
    assert commands[0][commands[0].index("--acquire-job") + 1] == "1234-5678"
    assert commands[0][commands[0].index("--queue") + 1] == "webhook-acquire"
    assert "docker" not in commands[0]
    assert "launching one-shot agent for job 1234-5678" in capsys.readouterr().out
