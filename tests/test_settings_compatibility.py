"""Configuration cleanup must preserve stored credentials and legacy imports."""
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

import gridraft.app as legacy
from gridraft import settings
from test_gridraft import WALLET


def test_legacy_settings_exports_are_the_same_objects():
    assert legacy.Settings is settings.Settings
    assert legacy.validate_settings is settings.validate_settings
    assert legacy.model_limit_overrides_from_env is settings.model_limit_overrides_from_env


@pytest.mark.parametrize('mode', ['prepaid', 'holder_allowance'])
def test_settings_from_env_preserves_keys_sessions_and_schema_on_reopen(tmp_path, monkeypatch, mode):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('APP_ORIGIN', 'http://testserver')
    monkeypatch.setenv('KEY_PEPPER', 'fixture-stable-pepper-for-repository-cleanup')
    monkeypatch.setenv('ACCESS_MODE', mode)
    path = str(tmp_path / 'existing.db')
    requests = []
    transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(503))
    app = legacy.create_app(legacy.Settings.from_env(), path, transport)
    with TestClient(app):
        store = app.state.store
        cookie = store.new_session(WALLET)
        key = store.issue_key(WALLET, 'existing key', 10**9)
        schema = [tuple(row) for row in store.db.execute(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]

    app = legacy.create_app(settings.Settings.from_env(), path, transport)
    with TestClient(app) as client:
        store = app.state.store
        client.cookies.set('gridraft_session', cookie)
        response = client.get('/api/keys')
        assert response.status_code == 200
        assert response.json()['data'][0]['id'] == key['id']
        assert key['key'].startswith('sv_')
        assert store.lookup_key(key['key'])['wallet'] == WALLET
        assert [tuple(row) for row in store.db.execute(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')] == schema
        assert client.post('/api/auth/logout', headers={'Origin': 'http://testserver'}).status_code == 200
        assert store.session_wallet(cookie) is None
        assert store.lookup_key(key['key']) is not None
        assert store.revoke(key['id'], WALLET)
        assert store.lookup_key(key['key']) is None
    assert requests == []


def test_doctor_does_not_import_application_or_create_storage(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items()
           if key in ('PATH', 'SYSTEMROOT', 'WINDIR')}
    env['PYTHONPATH'] = str(root)
    code = '''
import json
import sys
sys.modules['gridraft.app'] = None
sys.modules['gridraft.main'] = None
from gridraft.doctor import report
print(json.dumps(report()))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['network_calls'] == 0
    assert report['inference_requests'] == 0
    assert report['launch_authorized'] is False
    assert list(tmp_path.iterdir()) == []
