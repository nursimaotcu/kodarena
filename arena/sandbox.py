"""Docker CLI boundary. No shell, host bind mount, host execution fallback or socket in jobs."""

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass


class InfrastructureError(Exception):
    pass


class LostLease(Exception):
    pass


@dataclass
class Execution:
    verdict: str
    stdout: str
    stderr: str
    elapsed_ms: float


def normalize(output):
    # Ignore only trailing whitespace on lines and empty lines at end.
    return "\n".join(line.rstrip() for line in output.splitlines()).rstrip()


def container_command(name, image, language, source, limits):
    command = [
        "docker",
        "create",
        "--name",
        name,
        "--label",
        "kodarena.managed=true",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--user",
        "65534:65534",
        "--memory",
        f"{limits['memory_mb']}m",
        "--memory-swap",
        f"{limits['memory_mb']}m",
        "--cpus",
        "0.5",
        "--pids-limit",
        str(limits["pids"]),
        "--ulimit",
        "nofile=64:64",
        "--ulimit",
        "core=0:0",
        "--ulimit",
        "cpu=3:3",
        "--stop-timeout",
        "1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
        "--log-driver",
        "none",
        "--init",
        "-i",
        image,
        "timeout",
        "--signal=KILL",
        "5s",
    ]
    if language == "python":
        command += ["python", "-I", "-B", "-c", source]
    elif language == "javascript":
        command += ["node", "--max-old-space-size=64", "--input-type=commonjs", "-e", source]
    else:
        raise InfrastructureError("Unsupported language")
    return command


class DockerSandbox:
    def __init__(self):
        self.images = {
            "python": os.environ.get("ARENA_PYTHON_IMAGE", "python:3.12-slim"),
            "javascript": os.environ.get("ARENA_JS_IMAGE", "node:22-slim"),
        }

    @staticmethod
    def cli(args, timeout=15):
        try:
            result = subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InfrastructureError("Docker CLI unavailable or timed out") from exc
        if result.returncode:
            raise InfrastructureError(
                "Docker command failed: " + result.stderr.decode(errors="replace")[:300]
            )
        return result.stdout.decode(errors="replace")

    def preflight(self):
        if self.cli(["info", "--format", "{{.OSType}}"], timeout=10).strip() != "linux":
            raise InfrastructureError("Linux container engine required")
        for image in self.images.values():
            self.cli(["image", "inspect", image, "--format", "{{.Id}}"])

    def run(self, language, source, stdin, limits, abort=None):
        abort = abort or threading.Event()
        name = "kodarena-" + uuid.uuid4().hex
        proc = None
        created = False
        try:
            args = container_command(name, self.images[language], language, source, limits)
            try:
                result = subprocess.run(args, capture_output=True, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                # Creation may have completed even when the CLI timed out.
                self.cli(["rm", "-f", name])
                raise InfrastructureError("Container creation failed") from exc
            if result.returncode:
                raise InfrastructureError(
                    "Container creation failed: " + result.stderr.decode(errors="replace")[:300]
                )
            created = True
            if abort.is_set():
                raise LostLease()
            start = time.monotonic()
            proc = subprocess.Popen(
                ["docker", "start", "--attach", "--interactive", name],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            buffers = [bytearray(), bytearray()]
            exceeded = threading.Event()
            lock = threading.Lock()
            total = 0

            def drain(stream, target):
                nonlocal total
                while chunk := stream.read(1024):
                    with lock:
                        remaining = max(0, limits["output_bytes"] - total)
                        target.extend(chunk[:remaining])
                        total += len(chunk)
                        if total > limits["output_bytes"]:
                            exceeded.set()

            readers = [
                threading.Thread(target=drain, args=(proc.stdout, buffers[0]), daemon=True),
                threading.Thread(target=drain, args=(proc.stderr, buffers[1]), daemon=True),
            ]
            for thread in readers:
                thread.start()

            def feed():
                try:
                    proc.stdin.write(stdin.encode())
                    proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

            writer = threading.Thread(target=feed, daemon=True)
            writer.start()
            verdict = None
            while proc.poll() is None:
                if abort.is_set():
                    raise LostLease()
                if exceeded.is_set():
                    verdict = "output_limit"
                    break
                if time.monotonic() - start > limits["wall_seconds"]:
                    verdict = "time_limit"
                    break
                time.sleep(0.02)
            if verdict:
                try:
                    self.cli(["kill", name])
                except InfrastructureError:
                    # The process may exit between observing a limit and sending kill.
                    state = json.loads(self.cli(["inspect", "--format", "{{json .State}}", name]))
                    if state.get("Status") != "exited":
                        raise
            proc.wait(timeout=10)
            for thread in readers:
                thread.join(timeout=2)
            elapsed = (time.monotonic() - start) * 1000
            state = json.loads(self.cli(["inspect", "--format", "{{json .State}}", name]))
            if state.get("Error") or state.get("Status") != "exited":
                raise InfrastructureError("Container did not exit normally")
            if exceeded.is_set():
                verdict = "output_limit"
            if verdict is None:
                verdict = (
                    "memory_limit"
                    if state.get("OOMKilled")
                    else ("ok" if state["ExitCode"] == 0 else "runtime_error")
                )
            return Execution(
                verdict, buffers[0].decode(errors="replace"), buffers[1].decode(errors="replace"), elapsed
            )
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise InfrastructureError("Sandbox process failed") from exc
        finally:
            cleanup_error = None
            if created:
                try:
                    self.cli(["rm", "--force", name])
                except InfrastructureError as exc:
                    cleanup_error = exc
            if proc:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    if stream:
                        stream.close()
            if cleanup_error:
                # Stop/retry rather than silently leave unmanaged execution behind.
                raise InfrastructureError(
                    "Container cleanup failed; inspect managed containers"
                ) from cleanup_error


def judge(job, sandbox, abort=None):
    results = []
    for index, case in enumerate(job["spec"]["cases"]):
        if abort and abort.is_set():
            raise LostLease()
        result = sandbox.run(job["language"], job["source"], case["input"], job["spec"]["limits"], abort)
        verdict = result.verdict
        if verdict == "ok":
            verdict = (
                "accepted" if normalize(result.stdout) == normalize(case["expected"]) else "wrong_answer"
            )
        results.append(
            {
                "index": index,
                "verdict": verdict,
                "stdout": result.stdout[:4096] if case.get("public", True) else "",
                "stderr": result.stderr[:4096] if case.get("public", True) else "",
                "elapsed_ms": result.elapsed_ms,
            }
        )
    return results
