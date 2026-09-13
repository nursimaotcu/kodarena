"""Opt-in real Docker boundary tests. No fallback to executing source on the host."""

import os
import threading

import pytest

from arena.sandbox import DockerSandbox, LostLease

pytestmark = pytest.mark.skipif(
    os.environ.get("ARENA_DOCKER_TESTS") != "1",
    reason="Set ARENA_DOCKER_TESTS=1 with Linux Docker and both runtime images",
)
LIMITS = {"memory_mb": 128, "wall_seconds": 2, "output_bytes": 16384, "pids": 32}


@pytest.fixture(scope="module")
def sandbox():
    runner = DockerSandbox()
    runner.preflight()
    return runner


@pytest.mark.parametrize(
    ("language", "source"),
    [
        ("python", "print(sum(map(int,input().split())))"),
        (
            "javascript",
            "console.log(require('fs').readFileSync(0,'utf8').trim().split(/\\s+/).map(Number).reduce((a,b)=>a+b,0))",
        ),
    ],
)
def test_real_correct_program(sandbox, language, source):
    result = sandbox.run(language, source, "4 7\n", LIMITS)
    assert result.verdict == "ok" and result.stdout.strip() == "11"


def test_real_timeout(sandbox):
    assert sandbox.run("python", "while True: pass", "", LIMITS).verdict == "time_limit"


def test_real_output_limit(sandbox):
    assert sandbox.run("python", "print('x'*100000)", "", LIMITS).verdict == "output_limit"


def test_real_runtime_error(sandbox):
    assert sandbox.run("python", "raise ValueError('example')", "", LIMITS).verdict == "runtime_error"


def test_real_memory_limit(sandbox):
    result = sandbox.run("python", "x=bytearray(512*1024*1024);print(len(x))", "", LIMITS)
    assert result.verdict == "memory_limit"


def test_real_filesystem_network_and_uid(sandbox):
    source = """import os,socket
assert os.getuid()==65534
try:
 open('/forbidden','w').write('x')
 raise AssertionError('root filesystem writable')
except OSError: pass
s=socket.socket();s.settimeout(.2)
try:
 s.connect(('1.1.1.1',80))
 raise AssertionError('network reachable')
except OSError: pass
print('restricted')
"""
    result = sandbox.run("python", source, "", LIMITS)
    assert result.verdict == "ok" and result.stdout.strip() == "restricted"


def test_real_cancel_and_cleanup(sandbox):
    abort = threading.Event()
    timer = threading.Timer(0.5, abort.set)
    timer.start()
    try:
        with pytest.raises(LostLease):
            sandbox.run("python", "while True: pass", "", LIMITS, abort)
    finally:
        timer.cancel()
