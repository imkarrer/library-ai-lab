import fcntl
import logging
import os
from typing import IO

logger = logging.getLogger(__name__)


def acquire_oversight_lock(db_path: str) -> IO | None:
    """Acquire an exclusive lock for Oversight operations.

    Args:
        db_path: Path to the database file

    Returns:
        File handle if lock acquired, None if another process holds the lock
    """
    # Create the lock file path in the same directory as the database
    lock_file_path = os.path.join(os.path.dirname(db_path), "oversight.lock")

    try:
        # Open the lock file (create if it doesn't exist) without context manager
        lock_file = open(lock_file_path, "w")
        # Try to acquire an exclusive non-blocking lock
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file
        except BlockingIOError:
            # Another process holds the lock
            # Close the file before returning None
            lock_file.close()
            logger.warning(f"Oversight off: another process holds {lock_file_path}")
            return None
    except OSError:
        # Handle file system errors (permissions, non-existent directory, etc.)
        return None
