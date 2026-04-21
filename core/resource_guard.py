"""
Helpers for keeping FFmpeg work within safer RAM limits on low-spec systems.
"""

from __future__ import annotations

import os
import threading
import time

import psutil

_WRITE_LOCK = threading.Lock()


def get_memory_usage_percent() -> float:
    try:
        return float(psutil.virtual_memory().percent or 0.0)
    except Exception:
        return 0.0


def wait_until_memory_below(
    limit_percent: float = 90.0,
    resume_percent: float | None = None,
    check_interval: float = 0.75,
    timeout: float = 300.0,
    log_cb=None,
) -> bool:
    target = float(resume_percent if resume_percent is not None else limit_percent)
    start = time.time()
    warned = False
    while True:
        current = get_memory_usage_percent()
        if current < target:
            return True
        if log_cb and not warned:
            log_cb(
                f"[ResourceGuard] RAM {current:.1f}% masih tinggi. Menunggu turun di bawah {target:.1f}%..."
            )
            warned = True
        if timeout and (time.time() - start) >= timeout:
            return False
        time.sleep(max(0.2, float(check_interval)))


def terminate_ffmpeg_children(log_cb=None) -> int:
    killed = 0
    try:
        parent = psutil.Process(os.getpid())
        children = parent.children(recursive=True)
    except Exception:
        return 0

    ffmpeg_children = []
    for child in children:
        try:
            name = (child.name() or "").lower()
            if "ffmpeg" in name:
                ffmpeg_children.append(child)
        except Exception:
            continue

    for child in ffmpeg_children:
        try:
            child.terminate()
        except Exception:
            pass

    gone, alive = psutil.wait_procs(ffmpeg_children, timeout=2.0)
    killed += len(gone)

    for child in alive:
        try:
            child.kill()
            killed += 1
        except Exception:
            pass

    if killed and log_cb:
        log_cb(f"[ResourceGuard] Menghentikan {killed} proses FFmpeg anak karena tekanan RAM terlalu tinggi.")
    return killed


class FfmpegWriteGuard:
    def __init__(
        self,
        limit_percent: float = 90.0,
        resume_percent: float = 88.0,
        poll_interval: float = 0.75,
        grace_checks: int = 4,
        log_cb=None,
    ):
        self.limit_percent = float(limit_percent)
        self.resume_percent = float(resume_percent)
        self.poll_interval = float(poll_interval)
        self.grace_checks = max(1, int(grace_checks))
        self.log_cb = log_cb
        self._stop_event = threading.Event()
        self._thread = None
        self.stopped_due_to_memory = False
        self._lock_acquired = False

    def __enter__(self):
        _WRITE_LOCK.acquire()
        self._lock_acquired = True
        wait_until_memory_below(
            limit_percent=self.limit_percent,
            resume_percent=self.resume_percent,
            check_interval=self.poll_interval,
            timeout=300.0,
            log_cb=self.log_cb,
        )
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self._lock_acquired:
            _WRITE_LOCK.release()
            self._lock_acquired = False
        return False

    def _monitor(self):
        high_count = 0
        while not self._stop_event.is_set():
            usage = get_memory_usage_percent()
            if usage >= self.limit_percent:
                high_count += 1
                if high_count >= self.grace_checks:
                    killed = terminate_ffmpeg_children(log_cb=self.log_cb)
                    if killed > 0:
                        self.stopped_due_to_memory = True
                        self._stop_event.set()
                        return
            else:
                high_count = 0
            time.sleep(self.poll_interval)
