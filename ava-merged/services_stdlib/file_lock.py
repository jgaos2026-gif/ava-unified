"""OS-level file locking for the history JSONL store (round 3, Finding C).

Two processes can load the same chain head, both verify, both append
different successors — the store's threading.RLock only excludes
threads inside ONE process, so it cannot prevent that. This module
provides the cross-process lock the store takes around
verify+gate+write (exclusive) and verify+read (shared), so exactly
one writer wins and the loser fails closed instead of forking the
chain.

Two implementations, stdlib only:
  * fcntl.flock where available (Linux/macOS): a real shared /
    exclusive lock on a lockfile beside the store. Blocking with a
    timeout — a lock that cannot be acquired in LOCK_TIMEOUT_SECONDS
    raises FileLockError (fail closed) instead of hanging forever.
  * Lockfile fallback for platforms without fcntl: atomic O_EXCL
    creation of the lockfile holding the holder's PID. A lock whose
    holder PID is dead is stale and is reclaimed; anything else waits
    until the timeout. The fallback has no shared mode — reads take
    the exclusive lock too (correct, coarser). PID reuse is the known
    residual risk: a stale lockfile whose PID was recycled by an
    unrelated live process waits out the timeout instead of being
    reclaimed, and the call fails closed. It can never grant two
    holders at once.

Set AVA_HISTORY_LOCK_FORCE_FALLBACK=1 to exercise the fallback on a
platform that has fcntl (tests do this). Never commit a key or a
token here; the lockfile holds only a PID.
"""
import os
import time

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # noqa: BLE001 - platforms without fcntl (Windows)
    fcntl = None
    _HAVE_FCNTL = False

LOCK_TIMEOUT_SECONDS = 30.0
_POLL_SECONDS = 0.01
# A fallback lockfile whose content is unreadable is reclaimed only
# once it is this old: a fresh garbage lockfile is someone else's
# lock in mid-write, not a stale one.
_GARBAGE_LOCK_MAX_AGE_SECONDS = 60.0

ENV_FORCE_FALLBACK = "AVA_HISTORY_LOCK_FORCE_FALLBACK"


class FileLockError(Exception):
    """The lock could not be acquired (timeout, stale-lock handling
    failed, or the lockfile could not be opened). The caller must fail
    closed — never write or serve on the strength of an unverified
    chain."""


def _force_fallback() -> bool:
    return (os.environ.get(ENV_FORCE_FALLBACK, "").strip().lower()
            in ("1", "true", "yes", "on"))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # a process exists, just not ours
    except OSError:
        return False
    return True


class FileLock:
    """Cross-process lock on `path`. Exclusive (writer) or shared
    (reader) under fcntl; exclusive-only under the fallback.
    Use as a context manager; the lock is always released, and a
    timeout raises FileLockError instead of blocking forever."""

    def __init__(self, path, exclusive=True,
                 timeout=LOCK_TIMEOUT_SECONDS):
        self.path = path
        self.exclusive = exclusive
        self.timeout = timeout
        self._fd = None
        self._use_fcntl = _HAVE_FCNTL and not _force_fallback()
        self._held_fallback = False

    # -- fcntl path ---------------------------------------------------
    def _acquire_fcntl(self):
        op = fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH
        try:
            self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as e:
            raise FileLockError("cannot open lockfile %s: %s"
                                % (self.path, e))
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self._fd, op | fcntl.LOCK_NB)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(self._fd)
                    self._fd = None
                    raise FileLockError(
                        "timed out after %.0fs waiting for %s lock on %s"
                        % (self.timeout,
                           "exclusive" if self.exclusive else "shared",
                           self.path))
                time.sleep(_POLL_SECONDS)

    def _release_fcntl(self):
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    # -- O_EXCL fallback path -----------------------------------------
    def _acquire_fallback(self):
        # The fallback has no shared mode: every holder takes the
        # exclusive lock. Reads serialize; correctness over speed.
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.path,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(fd, str(os.getpid()).encode("ascii"))
                finally:
                    os.close(fd)
                self._held_fallback = True
                return
            except FileExistsError:
                if self._try_reclaim_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise FileLockError(
                        "timed out after %.0fs waiting for lock on %s"
                        % (self.timeout, self.path))
                time.sleep(_POLL_SECONDS)
            except OSError as e:
                raise FileLockError("cannot create lockfile %s: %s"
                                    % (self.path, e))

    def _try_reclaim_stale(self) -> bool:
        """Remove the lockfile if its holder is dead. Returns True
        when a stale lock was reclaimed (caller retries acquisition).
        A lockfile whose holder is alive, or whose content cannot be
        read and is still fresh, is left alone."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError:
            return False  # vanished or unreadable; retry acquisition
        try:
            pid = int(content)
        except ValueError:
            try:
                age = time.time() - os.path.getmtime(self.path)
            except OSError:
                return False
            if age < _GARBAGE_LOCK_MAX_AGE_SECONDS:
                return False
            pid = None  # garbage this old is stale, reclaim below
        if pid is not None and _pid_alive(pid):
            return False
        try:
            os.unlink(self.path)
        except OSError:
            return False  # someone else reclaimed it first; retry
        return True

    def _release_fallback(self):
        if not self._held_fallback:
            return
        self._held_fallback = False
        try:
            os.unlink(self.path)
        except OSError:
            pass  # already reclaimed as stale; nothing to release

    # -- context manager ----------------------------------------------
    def __enter__(self):
        if self._use_fcntl:
            self._acquire_fcntl()
        else:
            self._acquire_fallback()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._use_fcntl:
            if self._fd is not None:
                self._release_fcntl()
        else:
            self._release_fallback()
        return False
