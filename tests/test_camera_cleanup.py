import subprocess

from lib import camera


class TimeoutThenKillProcess:
    def __init__(self):
        self.terminate_called = False
        self.kill_called = False
        self.wait_calls = 0

    def poll(self):
        return None if not self.kill_called else -9

    def terminate(self):
        self.terminate_called = True

    def wait(self, timeout=None):
        self.wait_calls += 1
        if not self.kill_called:
            raise subprocess.TimeoutExpired("gst-launch-1.0", timeout)
        return -9

    def kill(self):
        self.kill_called = True


class EmptyStream:
    def __init__(self, receiver):
        self.receiver = receiver

    def read(self, _size):
        self.receiver._gst_proc = None  # pylint: disable=protected-access
        return b""


class ExitedProcess:
    def __init__(self, receiver):
        self.stdout = EmptyStream(receiver)
        self.stderr = []
        self.returncode = 0
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        raise AssertionError("already-exited process should not be terminated")

    def wait(self, timeout=None):
        self.wait_calls += 1
        return self.returncode

    def kill(self):
        raise AssertionError("already-exited process should not be killed")


def test_gst_cleanup_reaps_process_after_kill():
    receiver = camera.RPiCameraReceiver()
    proc = TimeoutThenKillProcess()
    receiver._gst_proc = proc  # pylint: disable=protected-access

    receiver._cleanup_gst()  # pylint: disable=protected-access

    assert proc.terminate_called is True
    assert proc.kill_called is True
    assert proc.wait_calls == 2
    assert receiver._gst_proc is None  # pylint: disable=protected-access


def test_gst_reader_uses_local_process_when_cleanup_clears_instance_ref(monkeypatch):
    receiver = camera.RPiCameraReceiver()
    proc = ExitedProcess(receiver)

    monkeypatch.setattr(camera.shutil, "which", lambda _name: "/usr/bin/gst-launch-1.0")
    monkeypatch.setattr(camera.subprocess, "Popen", lambda *args, **kwargs: proc)

    receiver._run_gst_subprocess()  # pylint: disable=protected-access

    assert proc.wait_calls == 1
    assert receiver._gst_proc is None  # pylint: disable=protected-access
