"""The offline preview must follow the homepage's local dependency declarations."""
import pytest

from scripts import package_preview


@pytest.fixture
def source(tmp_path, monkeypatch):
    public = tmp_path / 'public'
    public.mkdir()
    monkeypatch.setattr(package_preview, 'ROOT', tmp_path)
    return public


def build(source, markup):
    (source / 'index.html').write_text(markup, encoding='utf-8')
    target = source.parent / 'preview.html'
    package_preview.build(target)
    return target.read_text(encoding='utf-8')


def test_preview_follows_declared_styles_and_script_order(source):
    (source / 'first.js').write_text('window.order = ["first"];')
    (source / 'second.js').write_text('window.order.push("second");')
    (source / 'extra.css').write_text('body { color: purple; }')
    output = build(source, """<html lang="en"><head>
        <link href='extra.css' rel='stylesheet'>
        <script defer src='second.js'></script>
        <script src="first.js" defer></script>
        </head><body><p>Holdbyte</p></body></html>""")
    assert 'body { color: purple; }' in output
    assert output.index('window.order.push') < output.index('window.order =')
    assert output.index('<p>Holdbyte</p>') < output.index('window.order.push')
    assert output.count('<script>') == output.count('</script>') == 2
    assert 'data-preview="offline"' in output
    assert '<script src=' not in output and '<link ' not in output


@pytest.mark.parametrize('asset, error', [
    ('missing.js', FileNotFoundError),
    ('../private.js', ValueError),
    ('%2e%2e/private.js', ValueError),
    ('https://example.test/remote.js', ValueError),
])
def test_preview_rejects_missing_or_nonlocal_scripts_without_overwriting(source, asset, error):
    (source.parent / 'private.js').write_text('private fixture')
    target = source.parent / 'preview.html'
    target.write_text('previous-good-preview')
    (source / 'index.html').write_text(
        f'<html lang="en"><body><script src="{asset}" defer></script></body></html>')
    with pytest.raises(error):
        package_preview.build(target)
    assert target.read_text() == 'previous-good-preview'


def test_preview_rejects_symlinks_outside_public(source):
    outside = source.parent / 'private.js'
    outside.write_text('private fixture')
    (source / 'linked.js').symlink_to(outside)
    with pytest.raises(ValueError):
        build(source, '<html><body><script src="linked.js" defer></script></body></html>')


@pytest.mark.parametrize('attributes', ['async', 'type="module"', ''])
def test_preview_rejects_scripts_whose_execution_semantics_cannot_be_preserved(source, attributes):
    (source / 'extra.js').write_text('window.extra = true;')
    with pytest.raises(ValueError):
        build(source, f'<html><body><script src="extra.js" {attributes}></script></body></html>')


def test_preview_escapes_script_end_tags_and_embeds_declared_images(source):
    (source / 'extra.js').write_text('window.example = "</ScRiPt>";')
    (source / 'mark.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    output = build(source, """<html lang="en"><head><link rel='icon' href='mark.svg'></head>
        <body><img alt='Holdbyte &amp; friends' src='mark.svg'>
        <script src="extra.js" defer></script></body></html>""")
    assert output.count('data:image/svg+xml;base64,') == 2
    assert 'Holdbyte &amp; friends' in output
    assert '</ScRiPt>' not in output
    assert output.count('</script>') == 1
