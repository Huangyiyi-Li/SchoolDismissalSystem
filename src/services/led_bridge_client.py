from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import threading


WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


@dataclass(frozen=True)
class BridgeResult:
    ok: bool
    message: str


class JavaLedBridge:
    MAIN_CLASS = "cn.xxt.dismissal.led.OnbonLedBridge"

    def __init__(
        self,
        bridge_dir,
        java_command=None,
        runner=None,
        timeout_seconds=20,
        display_timeout_seconds=60,
    ):
        self.bridge_dir = Path(bridge_dir)
        self.java_command = java_command or self._default_java_command()
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.display_timeout_seconds = display_timeout_seconds
        self._process_lock = threading.Lock()
        self._active_process = None
        self._shutdown_event = threading.Event()

    def _default_java_command(self):
        bundled = self.bridge_dir / "runtime" / "bin" / ("java.exe" if os.name == "nt" else "java")
        return str(bundled) if bundled.exists() else "java"

    def _base_command(self):
        separator = ";" if os.name == "nt" else ":"
        classpath = separator.join(
            [str(self.bridge_dir / "led-bridge.jar"), str(self.bridge_dir / "lib" / "*")]
        )
        return [self.java_command, "-Djava.awt.headless=true", "-cp", classpath, self.MAIN_CLASS]

    def _run_default(self, command, timeout):
        with self._process_lock:
            if self._shutdown_event.is_set():
                raise OSError("LED Bridge 已停止")
            window_options = {}
            if os.name == "nt":
                window_options["creationflags"] = WINDOWS_CREATE_NO_WINDOW
            process = subprocess.Popen(
                command,
                cwd=str(self.bridge_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **window_options,
            )
            self._active_process = process
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        finally:
            with self._process_lock:
                if self._active_process is process:
                    self._active_process = None

    def _run(self, arguments, timeout=None):
        command = self._base_command() + [str(value) for value in arguments]
        effective_timeout = timeout or self.timeout_seconds
        try:
            if self.runner is None:
                completed = self._run_default(command, effective_timeout)
            else:
                completed = self.runner(
                    command,
                    cwd=str(self.bridge_dir),
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                )
        except (OSError, subprocess.SubprocessError) as exc:
            return BridgeResult(False, str(exc))

        output = (completed.stdout or completed.stderr or "").strip()
        if completed.returncode == 0:
            return BridgeResult(True, output or "操作成功")
        return BridgeResult(False, output or f"Java Bridge 退出码 {completed.returncode}")

    def ping(self, ip, port):
        return self._run(["ping", "--ip", ip, "--port", int(port)])

    def display(self, ip, port, image_paths, stay_seconds=5, width=1024, height=96):
        paths = [str(Path(path).resolve()) for path in image_paths]
        if not paths:
            return BridgeResult(False, "没有可发送的 LED 页面")
        stay_units = max(1, int(float(stay_seconds) * 100))
        return self._run(
            [
                "display", "--ip", ip, "--port", int(port),
                "--width", int(width), "--height", int(height),
                "--stay", stay_units, "--images",
            ] + paths,
            timeout=self.display_timeout_seconds,
        )

    def clear(self, ip, port):
        return self._run(["clear", "--ip", ip, "--port", int(port)])

    def shutdown(self):
        with self._process_lock:
            self._shutdown_event.set()
            process = self._active_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass
