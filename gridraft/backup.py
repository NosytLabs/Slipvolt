"""Private, read-only SQLite backup and integrity verification.

Use SQLite's online backup API for consistent live/WAL snapshots. Neither
function connects to a provider, reads KEY_PEPPER or changes source data.
The caller must transfer/encrypt backup copies off-host and test restoration.
"""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

PUBLIC_ROOT = Path(__file__).resolve().parents[1] / 'public'
REQUIRED_TABLES = frozenset(('accounts', 'api_keys'))


def _source_file(path):
    # Resolve existing files before SQLite can touch them. mode=ro ensures a
    # typo never silently creates an empty source database.
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
        raise ValueError('Expected a regular SQLite database file')
    return source


def _connect_read_only(path, *, immutable=False):
    options = '?mode=ro&immutable=1' if immutable else '?mode=ro'
    return sqlite3.connect(path.as_uri() + options, uri=True, timeout=30)


def _require_standalone(path):
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(path) + suffix)
        if sidecar.is_symlink() or (sidecar.exists() and sidecar.stat().st_size):
            raise ValueError('Verify a standalone snapshot without SQLite journal files')


def _integrity_check(connection):
    if connection.execute('PRAGMA integrity_check').fetchone() != ('ok',):
        raise ValueError('Database integrity check failed')
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('accounts','api_keys')"
    )
    if not REQUIRED_TABLES.issubset({row[0] for row in rows}):
        raise ValueError('File is not an initialized Holdbyte database')


def _report(path, status):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {
        'ok': True,
        'status': status,
        'bytes': path.stat().st_size,
        'sha256': digest.hexdigest(),
        'contains_private_data': True,
        'restoration_tested': False,
        'transactions_sent': 0,
    }


def verify_database(path):
    """Verify a stable standalone backup without reading SQLite sidecars."""
    source = _source_file(path)
    _require_standalone(source)
    before = source.stat()
    with closing(_connect_read_only(source, immutable=True)) as connection:
        _integrity_check(connection)
    report = _report(source, 'verified')
    _require_standalone(source)
    after = source.stat()
    if any(getattr(before, field) != getattr(after, field) for field in
           ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
        raise ValueError('Database changed during verification')
    return report


def create_backup(source_path, destination_path):
    """Create a consistent, owner-only snapshot without replacing any file.

    An exclusive hard link publishes the verified staged file atomically,
    so concurrent backup attempts cannot replace each other. The staging
    file is always removed on either success or failure.
    """
    source = _source_file(source_path)
    destination = Path(destination_path).expanduser().absolute()
    candidate = destination.resolve(strict=False)
    if candidate == source or destination.is_symlink() or destination.exists():
        raise FileExistsError('Destination already exists or points to the source')
    if candidate.is_relative_to(PUBLIC_ROOT.resolve(strict=False)):
        raise ValueError('Cannot put a sensitive database backup inside the public directory')
    if not destination.parent.is_dir():
        raise FileNotFoundError('Backup directory does not exist')

    fd, stage = tempfile.mkstemp(prefix='.holdbyte-backup-', suffix='.tmp',
                                dir=destination.parent)
    os.close(fd)
    temporary = Path(stage)
    try:
        with closing(_connect_read_only(source)) as origin, closing(
                sqlite3.connect(temporary, timeout=30)) as snapshot:
            _integrity_check(origin)
            origin.backup(snapshot, pages=256, sleep=0.01)
            snapshot.commit()
        verified = verify_database(temporary)
        # The destination must never exist before this atomic create.
        # A same-directory stage also keeps the operation on one filesystem.
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        return {**verified, 'status': 'created'}
    finally:
        temporary.unlink(missing_ok=True)
        # SQLite should not create these in a fresh backup destination, but
        # clean them if a partial copy failed while journal files existed.
        for suffix in ('-wal', '-shm', '-journal'):
            Path(stage + suffix).unlink(missing_ok=True)
