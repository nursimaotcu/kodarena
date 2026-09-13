"""Exercise Docker orchestration with a fake CLI transport, never execute source on host."""

import io
import json
import subprocess
import threading

import pytest

from arena.sandbox import DockerSandbox, InfrastructureError, LostLease

LIMITS = {"memory_mb": 128, "wall_seconds": 0.01, "output_bytes": 16384, "pids": 32}


class Process:
    def __init__(self, output=b"", stderr=b"", running=False):
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(output), io.BytesIO(stderr)
        self.running = running

    def poll(self):
        return None if self.running else 0

    def wait(self, timeout=None):
        self.running = False
        return 0

    def kill(self):
        self.running = False


def transport(monkeypatch, output=b"", stderr=b"", running=False, oom=False, exit_code=0):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, b"id", b""))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: Process(output, stderr, running))
    runner = DockerSandbox()

    def cli(args, timeout=15):
        calls.append(args)
        return (
            json.dumps({"Status": "exited", "ExitCode": exit_code, "OOMKilled": oom, "Error": ""})
            if args[0] == "inspect"
            else ""
        )

    monkeypatch.setattr(runner, "cli", cli)
    return runner, calls


def test_normal_exit_and_cleanup(monkeypatch):
    runner, calls = transport(monkeypatch, output=b"11\n")
    result = runner.run("python", "not-executed", "", LIMITS)
    assert result.verdict == "ok" and result.stdout == "11\n"
    assert calls[-1][0:2] == ["rm", "--force"]


def test_combined_output_cap(monkeypatch):
    runner, _ = transport(monkeypatch, output=b"a" * 12000, stderr=b"b" * 12000)
    result = runner.run("python", "not-executed", "", LIMITS)
    assert result.verdict == "output_limit"
    assert len(result.stdout) + len(result.stderr) <= 16384


def test_timeout_kills_container(monkeypatch):
    runner, calls = transport(monkeypatch, running=True)
    assert runner.run("python", "not-executed", "", LIMITS).verdict == "time_limit"
    assert any(call[0] == "kill" for call in calls)


def test_oom_is_reported(monkeypatch):
    runner, _ = transport(monkeypatch, oom=True, exit_code=137)
    assert runner.run("python", "not-executed", "", LIMITS).verdict == "memory_limit"


def test_cancel_still_removes_created_container(monkeypatch):
    runner, calls = transport(monkeypatch)
    abort = threading.Event()
    abort.set()
    with pytest.raises(LostLease):
        runner.run("python", "not-executed", "", LIMITS, abort)
    assert calls[-1][0:2] == ["rm", "--force"]


def test_daemon_error_does_not_become_wrong_answer(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, b"", b"daemon unavailable")
    )
    with pytest.raises(InfrastructureError):
        DockerSandbox().run("python", "not-executed", "", LIMITS)


def test_exit_racing_timeout_keeps_limit_verdict(monkeypatch):
    runner, _ = transport(monkeypatch, running=True)
    normal_cli = runner.cli

    def cli(args, timeout=15):
        if args[0] == "kill":
            raise InfrastructureError("container already stopped")
        return normal_cli(args, timeout)

    monkeypatch.setattr(runner, "cli", cli)
    assert runner.run("python", "not-executed", "", LIMITS).verdict == "time_limit"
