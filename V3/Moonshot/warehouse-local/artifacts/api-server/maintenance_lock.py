"""Cross-process exclusion between the API and offline database maintenance."""

from contextlib import contextmanager
import portable_lock as fcntl
from pathlib import Path


@contextmanager
def _lock(data_dir: Path, exclusive: bool):
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    # Never unlink this file: changing its inode would defeat a held flock.
    with (directory / "operational-maintenance.lock").open("a") as handle:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Operational database is in use. Stop all API processes before "
                "maintenance, or finish maintenance before starting the API."
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def runtime_lock(data_dir: Path):
    """Hold for the complete API lifetime, including worker shutdown."""
    return _lock(data_dir, exclusive=False)


def exclusive_maintenance(data_dir: Path):
    """Fail closed when an API or another maintenance command is running."""
    return _lock(data_dir, exclusive=True)