from pathlib import Path
from html.parser import HTMLParser
import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import create_app,Settings

@pytest.mark.parametrize('path',['/status/','/status/app.js','/tools.css','/request-tools.js','/launch-tools.js'])
def test_new_routes_are_served_by_real_app(tmp_path,path):
    with TestClient(create_app(Settings(),str(tmp_path/'a.db'),httpx.MockTransport(lambda _:httpx.Response(503)))) as c:
        r=c.get(path)
        assert r.status_code==200,r.text
        assert r.headers['x-content-type-options']=='nosniff'
        assert "script-src 'self'" in r.headers['content-security-policy']

def test_packaged_preview_contains_functional_controls(tmp_path):
    from scripts.package_preview import build
    target=tmp_path/'preview.html';build(target);s=target.read_text()
    assert 'id="check-request"' in s and 'id="connection-kit"' in s
    assert 'function connectionKit' in s and "'/api/preflight'" in s
    assert '<script src=' not in s and '<link rel="stylesheet"' not in s

def test_new_pages_do_not_advertise_completed_launch_or_guaranteed_returns():
    s=Path('public/status/index.html').read_text()
    assert 'not a completed inference test' in s
    assert 'not a verified token launch' in s
    assert 'not Slipvolt customer activity' in s
