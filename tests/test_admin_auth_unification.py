"""Main admin authentication must share the treasury's hardened boundary."""
import inspect

import pytest
from fastapi.testclient import TestClient

from gridraft import app as app_module
from gridraft.app import Settings, create_app, validate_settings


ADMIN = 'adm_' + 'a' * 40


def application(tmp_path):
    return create_app(Settings(origin='http://testserver', admin_key=ADMIN,
                               access_mode='prepaid'), str(tmp_path / 'admin-auth.db'))


def test_non_ascii_authorization_fails_401_not_unhandled_typeerror(tmp_path):
    app = application(tmp_path)
    with TestClient(app) as client:
        # Raw latin-1 is a valid ASGI header representation even though
        # compare_digest on a non-ASCII Python string raises TypeError.
        result = client.get('/api/admin/config', headers={'Authorization': b'Bearer \xe9'})
        assert result.status_code == 401, result.text
        assert result.headers['cache-control'] == 'no-store'
        assert result.json()['error']['message'] == 'Invalid admin credential'


@pytest.mark.parametrize('credential', [
    b'Bearer ' + b'x' * 513,
    b'Bearer ' + b'\xe9' * 20,
    b'Basic ' + ADMIN.encode(),
])
def test_malformed_or_oversized_credentials_are_denied_cleanly(tmp_path, credential):
    with TestClient(application(tmp_path)) as client:
        response = client.get('/api/admin/config', headers={'Authorization': credential})
        assert response.status_code == 401
        assert response.headers['cache-control'] == 'no-store'


def test_valid_admin_read_needs_no_origin_but_write_still_requires_origin(tmp_path):
    with TestClient(application(tmp_path)) as client:
        headers = {'Authorization': 'Bearer ' + ADMIN}
        response = client.get('/api/admin/config', headers=headers)
        assert response.status_code == 200, response.text
        denied = client.put('/api/admin/config', headers=headers, json={})
        assert denied.status_code == 403


@pytest.mark.parametrize('bad_key', ['\xe9' * 40, 'A' * 513])
def test_unusable_admin_secrets_fail_configuration_validation(bad_key):
    with pytest.raises(ValueError, match='ADMIN_API_KEY'):
        validate_settings(Settings(admin_key=bad_key))


def test_main_admin_auth_uses_shared_route_authenticator():
    source = inspect.getsource(app_module.create_app)
    assert 'authenticate_admin(request, settings, require_origin=False)' in source
    assert 'secrets.compare_digest(provided,settings.admin_key)' not in source
