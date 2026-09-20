"""Public guides must be served, truthful about scope, and fully navigable."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import ChatInput, Settings, create_app

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'
PAGES = ('help/index.html', 'privacy/index.html', 'terms/index.html')


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def read_page(path):
    file = PUBLIC / path
    assert file.is_file(), f'Missing customer guide: {path}'
    return file.read_text()


@pytest.mark.parametrize('path', PAGES)
def test_content_is_semantic_and_accessible_without_javascript(path):
    tags = Markup(read_page(path)).tags
    assert sum(t == 'h1' for t, _ in tags) == 1
    assert sum(t == 'main' for t, _ in tags) == 1
    assert any(t == 'meta' and a.get('name') == 'description' for t, a in tags)
    assert any(t == 'a' and a.get('href') == '#main' for t, a in tags)
    assert any(t == 'nav' and a.get('aria-label') for t, a in tags)
    assert not any(t in ('iframe', 'form', 'script') for t, _ in tags)
    ids = [a['id'] for _, a in tags if 'id' in a]
    assert len(ids) == len(set(ids)), 'Duplicate anchor IDs'


@pytest.mark.parametrize('path', ('index.html',) + PAGES)
def test_all_public_content_links_and_styles_resolve(path):
    for tag, attrs in Markup(read_page(path)).tags:
        href = attrs.get('href') if tag in ('a', 'link') else None
        if not href:
            continue
        u = urlsplit(href)
        if u.scheme or u.netloc:
            assert u.scheme == 'https'
            if attrs.get('target') == '_blank':
                assert {'noopener', 'noreferrer'} <= set(attrs.get('rel', '').split())
            continue
        if u.path in ('/api/usage/export', '/api/status', '/api/models', '/v1/models', '/openapi.json'):
            continue  # Backend routes, not files.
        target = (PUBLIC / unquote(u.path).lstrip('/')) if u.path.startswith('/') else (PUBLIC / path).parent / unquote(u.path)
        if not u.path:
            target = PUBLIC / path
        if target.is_dir():
            target /= 'index.html'
        assert target.resolve().is_relative_to(PUBLIC.resolve())
        assert target.is_file(), f'{path}: broken link {href}'
        if u.fragment:
            assert u.fragment in {a.get('id') for _, a in Markup(target.read_text()).tags}, f'{path}: missing anchor {href}'


@pytest.mark.parametrize('route', ('/help/', '/privacy/', '/terms/', '/content.css'))
def test_guides_are_served_through_the_application(tmp_path, route):
    app = create_app(Settings(pepper='test-public-content-pepper-32-characters'), str(tmp_path/'content.db'),
                     httpx.MockTransport(lambda _: httpx.Response(503)))
    with TestClient(app) as c:
        r = c.get(route)
        assert r.status_code == 200, r.text
        assert r.headers['x-content-type-options'] == 'nosniff'
        assert "script-src 'self'" in r.headers['content-security-policy']


def test_help_has_scope_pricing_reset_and_retry_explanations():
    text = read_page('help/index.html')
    for term in ('00:00 UTC', 'latest 100', 'Idempotency-Key', '409', 'Retry-After',
                 'X-Request-Id', 'not a replay', 'No checkout', 'not the same model revision',
                 '1 billion', '$120', '$0.12', 'no rollover', 'Text-only'):
        assert term.lower() in text.lower(), term


def test_help_request_examples_match_the_real_schema():
    import re
    text = read_page('help/index.html')
    examples = re.findall(r'<code class="json-example">(.*?)</code>', text, re.S)
    assert examples
    for example in examples:
        from html import unescape
        body = ChatInput.model_validate(json.loads(unescape(example)))
        assert body.n == 1
        assert body.max_tokens <= 4096


def test_privacy_does_not_claim_anonymous_or_zero_retention_service():
    text = read_page('privacy/index.html')
    for term in ('gridraft_session', 'OpenBroker', 'RPC', 'retention', 'not anonymous',
                 'not an end-to-end zero-retention guarantee', 'no self-service account deletion', 'prelaunch'):
        assert term.lower() in text.lower(), term


def test_service_rules_separate_current_access_from_unbuilt_token_features():
    text = read_page('terms/index.html')
    for term in ('draft', 'not a treasury share', 'no guaranteed return', 'staking',
                 'checkout', 'refund', 'No token purchase', 'operator'):
        assert term.lower() in text.lower(), term


def test_homepage_exposes_help_and_protected_usage_export():
    text = read_page('index.html')
    for href in ('help/', 'privacy/', 'terms/', '/api/usage/export'):
        assert f'href="{href}"' in text
    assert 'latest 100' in text
    assert text.count('data-site-name') >= 2


def test_llms_content_no_longer_contradicts_function_tools():
    text = (PUBLIC/'llms.txt').read_text()
    assert 'Tools, multimodal input and non-schema fields are not supported.' not in text
    assert 'never executes' in text
    assert '/help/' in text and '/privacy/' in text and '/terms/' in text


def test_usage_export_still_requires_wallet_session(tmp_path):
    app = create_app(Settings(pepper='test-public-content-pepper-32-characters'), str(tmp_path/'content.db'),
                     httpx.MockTransport(lambda _: httpx.Response(503)))
    with TestClient(app) as c:
        assert c.get('/api/usage/export').status_code == 401


def test_packaged_preview_inlines_every_stylesheet(tmp_path):
    from scripts.package_preview import build
    target = tmp_path/'preview.html'
    build(target)
    assert not any(t == 'link' and a.get('rel') == 'stylesheet' for t, a in Markup(target.read_text()).tags)
