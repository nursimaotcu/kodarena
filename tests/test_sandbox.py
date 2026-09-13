import threading

import pytest

from arena.sandbox import Execution, InfrastructureError, LostLease, container_command, judge, normalize

LIMITS = {"memory_mb": 128, "wall_seconds": 2, "output_bytes": 16384, "pids": 32}


def test_container_has_no_host_mount_or_network():
    source = "print('$(do-not-execute)')"
    command = container_command("kodarena-test", "python:3.12-slim", "python", source, LIMITS)
    for flag in [
        "--read-only",
        "--cap-drop",
        "--security-opt",
        "--pids-limit",
        "--memory",
        "--memory-swap",
        "--cpus",
    ]:
        assert flag in command
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--user") + 1] == "65534:65534"
    assert not {"--privileged", "--volume", "-v", "--mount"} & set(command)
    assert command[-1] == source
    assert "no-new-privileges=true" in command


def test_unsupported_language_fails_closed():
    with pytest.raises(InfrastructureError):
        container_command("test", "image", "shell", "whoami", LIMITS)


@pytest.mark.parametrize(("actual", "expected"), [(" a  \r\nb\n\n", " a\nb"), ("1  2\n", "1  2"), ("", "")])
def test_normalization(actual, expected):
    assert normalize(actual) == expected


def test_judge_uses_full_output_before_truncation():
    class Sandbox:
        def run(self, *args):
            return Execution("ok", "x" * 5000, "", 2)

    job = {
        "language": "python",
        "source": "",
        "spec": {"limits": LIMITS, "cases": [{"input": "", "expected": "x" * 5000}]},
    }
    result = judge(job, Sandbox())[0]
    assert result["verdict"] == "accepted"
    assert len(result["stdout"]) == 4096


def test_judge_does_not_pass_expected_output_to_runner():
    calls = []

    class Sandbox:
        def run(self, *args):
            calls.append(args)
            return Execution("ok", "wrong", "", 2)

    job = {
        "language": "python",
        "source": "code",
        "spec": {"limits": LIMITS, "cases": [{"input": "input", "expected": "secret-expected"}]},
    }
    assert judge(job, Sandbox())[0]["verdict"] == "wrong_answer"
    assert "secret-expected" not in str(calls)


@pytest.mark.parametrize("verdict", ["time_limit", "memory_limit", "output_limit", "runtime_error"])
def test_resource_verdict_preserved(verdict):
    class Sandbox:
        def run(self, *args):
            return Execution(verdict, "", "", 3)

    job = {
        "language": "python",
        "source": "",
        "spec": {"limits": LIMITS, "cases": [{"input": "", "expected": ""}]},
    }
    assert judge(job, Sandbox())[0]["verdict"] == verdict


def test_lost_lease_prevents_execution():
    abort = threading.Event()
    abort.set()
    job = {"spec": {"cases": [{}]}}
    with pytest.raises(LostLease):
        judge(job, None, abort)


def test_hidden_output_not_transmitted_to_api():
    class Sandbox:
        def run(self, *args):
            return Execution("ok", "secret-input", "private", 2)

    job = {
        "language": "python",
        "source": "",
        "spec": {
            "limits": LIMITS,
            "cases": [{"input": "secret-input", "expected": "secret-input", "public": False}],
        },
    }
    result = judge(job, Sandbox())[0]
    assert result["verdict"] == "accepted"
    assert result["stdout"] == result["stderr"] == ""
