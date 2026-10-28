"""Online SQLite backup and offline verification must never overwrite source/data."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

import pytest

from gridraft.membership import Membership
from gridraft.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def live_store(tmp_path):
    source = tmp_path / 'live.db'
    store = Store(str(source), 'test-only-pepper-0123456789abcdefghijklmnop')
    Membership(store)
    store.db.execute("INSERT INTO accounts(wallet,balance_nusd) VALUES(?,?)", ('wallet', 123456789))
    store.db.execute("INSERT INTO sessions(hash,wallet,expires) VALUES(?,?,?)",
                     ('PRIVATE-SESSION-HASH', 'wallet', 9_999_999_999))
    try:
        yield source, store
    finally:
        store.close()


def test_online_backup_includes_wal_records_and_can_be_verified(live_store, tmp_path):
    from gridraft.backup import create_backup, verify_database
    source, store = live_store
    target = tmp_path / 'safe' / 'snapshot.db'
    target.parent.mkdir(mode=0o700)
    created = create_backup(source, target)
    assert created['status'] == 'created' and created['ok'] is True
    assert created['sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert created['bytes'] == target.stat().st_size > 0
    assert not any(t in json.dumps(created) for t in
                   ('PRIVATE-SESSION-HASH', str(source), str(target)))
    if os.name == 'posix':
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    # Source remains writable and is not checkpointed or replaced.
    store.db.execute("INSERT INTO accounts(wallet,balance_nusd) VALUES(?,?)", ('after', 7))
    with sqlite3.connect(target) as restored:
        assert restored.execute("SELECT balance_nusd FROM accounts WHERE wallet='wallet'").fetchone() == (123456789,)
        assert restored.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert restored.execute("SELECT COUNT(*) FROM accounts WHERE wallet='after'").fetchone()[0] == 0
        assert restored.execute("PRAGMA integrity_check").fetchone() == ('ok',)
    checked = verify_database(target)
    assert checked['status'] == 'verified'
    assert checked['sha256'] == created['sha256']
    assert checked['ok'] is True


def test_existing_backup_is_not_overwritten_or_modified(live_store, tmp_path):
    from gridraft.backup import create_backup
    source, _ = live_store
    target = tmp_path / 'existing.db'
    target.write_bytes(b'PRIVATE-OLD-BACKUP')
    with pytest.raises(FileExistsError):
        create_backup(source, target)
    assert target.read_bytes() == b'PRIVATE-OLD-BACKUP'
    assert not list(tmp_path.glob('.holdbyte-backup-*'))


def test_verify_rejects_active_wal_instead_of_hashing_only_the_main_file(live_store, tmp_path):
    from gridraft.backup import create_backup, verify_database
    source, store = live_store
    wal = Path(str(source) + '-wal')
    assert wal.is_file() and wal.stat().st_size > 0
    with pytest.raises(ValueError, match='standalone'):
        verify_database(source)
    assert store.db.execute("SELECT balance_nusd FROM accounts WHERE wallet='wallet'").fetchone()[0] == 123456789
    snapshot = tmp_path / 'snapshot.db'
    create_backup(source, snapshot)
    assert verify_database(snapshot)['sha256'] == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_verify_rejects_rollback_journal(tmp_path, live_store):
    from gridraft.backup import create_backup, verify_database
    source, _ = live_store
    snapshot = tmp_path / 'snapshot.db'
    create_backup(source, snapshot)
    journal = Path(str(snapshot) + '-journal')
    journal.write_bytes(b'nonempty journal')
    with pytest.raises(ValueError, match='standalone'):
        verify_database(snapshot)
    assert journal.read_bytes() == b'nonempty journal'


def test_verify_rejects_a_snapshot_modified_during_verification(tmp_path, live_store, monkeypatch):
    import gridraft.backup as backup
    source, _ = live_store
    snapshot = tmp_path / 'snapshot.db'
    backup.create_backup(source, snapshot)
    original_report = backup._report

    def changing_report(path, status):
        result = original_report(path, status)
        with path.open('ab') as stream:
            stream.write(b'changed')
        return result

    monkeypatch.setattr(backup, '_report', changing_report)
    with pytest.raises(ValueError, match='changed during verification'):
        backup.verify_database(snapshot)


def test_missing_source_is_not_created(live_store, tmp_path):
    from gridraft.backup import create_backup, verify_database
    target = tmp_path / 'backup.db'
    missing = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        create_backup(missing, target)
    assert not missing.exists() and not target.exists()
    with pytest.raises(FileNotFoundError):
        verify_database(missing)
    assert not missing.exists()


def test_reject_invalid_source_and_clean_up_staged_copy(tmp_path):
    from gridraft.backup import create_backup, verify_database
    source = tmp_path / 'bad.db'
    source.write_bytes(b'not a sqlite database PRIVATE')
    target = tmp_path / 'backup.db'
    with pytest.raises((sqlite3.Error, ValueError)):
        create_backup(source, target)
    assert not target.exists()
    assert not list(tmp_path.glob('.holdbyte-backup-*'))
    with pytest.raises((sqlite3.Error, ValueError)):
        verify_database(source)


def test_reject_destination_symlink_and_same_database(live_store, tmp_path):
    from gridraft.backup import create_backup
    source, _ = live_store
    linked = tmp_path / 'linked.db'
    linked.symlink_to(source)
    with pytest.raises((FileExistsError, ValueError)):
        create_backup(source, linked)
    with pytest.raises((FileExistsError, ValueError)):
        create_backup(source, source)
    assert source.exists()
    assert not list(tmp_path.glob('.holdbyte-backup-*'))


def test_cli_backs_up_without_requiring_pepper_and_verifies_after_transfer(live_store, tmp_path):
    source, _ = live_store
    config = tmp_path / 'private.env'
    config.write_text('DATABASE_PATH=' + str(source) + '\n')
    target = tmp_path / 'cli.db'
    env = {k: v for k, v in os.environ.items() if k not in ('KEY_PEPPER', 'DATABASE_PATH')}
    env['PYTHONPATH'] = str(ROOT)
    command = [sys.executable, '-m', 'gridraft.cli', '--env-file', str(config)]
    backed = subprocess.run(command + ['backup-db', '--output', str(target)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert backed.returncode == 0, backed.stderr
    info = json.loads(backed.stdout)
    assert info['status'] == 'created'
    assert not any(s in backed.stdout for s in (str(source), str(target), 'PRIVATE-SESSION-HASH'))
    moved = tmp_path / 'moved.db'
    target.rename(moved)
    checked = subprocess.run(command + ['verify-db', '--file', str(moved)],
                             cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)['sha256'] == info['sha256']


def test_cli_backup_failure_redacts_paths_and_does_not_create_empty_file(tmp_path):
    config = tmp_path / 'private.env'
    secret = 'PRIVATE-PATH-SECRET'
    config.write_text('DATABASE_PATH=' + str(tmp_path / (secret + '.db')) + '\n')
    target = tmp_path / 'backup.db'
    env = {k: v for k, v in os.environ.items() if k not in ('KEY_PEPPER', 'DATABASE_PATH')}
    env['PYTHONPATH'] = str(ROOT)
    command = [sys.executable, '-m', 'gridraft.cli', '--env-file', str(config),
               'backup-db', '--output', str(target)]
    result = subprocess.run(command, cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert secret not in result.stdout + result.stderr
    assert not target.exists()


def test_public_static_directory_cannot_receive_sensitive_backup(live_store, tmp_path, monkeypatch):
    import gridraft.backup as backup
    source, _ = live_store
    public = tmp_path / 'public'
    public.mkdir()
    monkeypatch.setattr(backup, 'PUBLIC_ROOT', public)
    with pytest.raises(ValueError, match='public'):
        backup.create_backup(source, public / 'leak.db')
    assert not (public / 'leak.db').exists()
