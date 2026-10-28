"""Build a self-contained offline preview from the homepage's local assets."""
import base64
from html import escape
from html.parser import HTMLParser
import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class _Dependencies(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ('html', 'img') or (tag == 'script' and 'src' in attributes) or (
            tag == 'link' and attributes.get('rel') in ('stylesheet', 'icon')
        ):
            self.tags.append((tag, attributes, self.get_starttag_text()))


def _asset_path(public, source):
    url = urlsplit(source or '')
    if not url.path or url.scheme or url.netloc or url.query or url.fragment:
        raise ValueError('Preview assets must be local files inside public')
    path = (public / unquote(url.path)).resolve()
    if not path.is_relative_to(public.resolve()):
        raise ValueError('Preview assets must be local files inside public')
    return path


def _tag(name, attrs):
    attributes = ''.join(' ' + key + (
        '' if value is None else '="' + escape(value, quote=True) + '"'
    ) for key, value in attrs.items())
    return '<' + name + attributes + '>'


def _image_url(path):
    content_type = mimetypes.guess_type(path.name)[0]
    if not content_type or not content_type.startswith('image/'):
        raise ValueError('Preview asset must be an image')
    data = base64.b64encode(path.read_bytes()).decode('ascii')
    return 'data:' + content_type + ';base64,' + data


def build(target):
    public = ROOT / 'public'
    html = (public / 'index.html').read_text(encoding='utf-8')
    dependencies = _Dependencies()
    dependencies.feed(html)
    scripts = []
    for tag, attrs, markup in dependencies.tags:
        if tag == 'html':
            html = html.replace(markup, _tag(tag, {**attrs, 'data-preview': 'offline'}), 1)
            continue
        attribute = 'href' if tag == 'link' else 'src'
        path = _asset_path(public, attrs.get(attribute))
        if tag == 'script':
            if set(attrs) != {'src', 'defer'} or path.suffix != '.js':
                raise ValueError('Preview supports only local deferred classic scripts')
            scripts.append(path.read_text(encoding='utf-8'))
            html, count = re.subn(re.escape(markup) + r'\s*</script\s*>', '', html, count=1, flags=re.I)
            if count != 1:
                raise ValueError('External preview scripts must have empty bodies')
        elif attrs.get('rel') == 'stylesheet':
            if path.suffix != '.css':
                raise ValueError('Preview stylesheet must be a CSS file')
            css = path.read_text(encoding='utf-8')
            style_attrs = {key: value for key, value in attrs.items() if key not in ('rel', 'href')}
            html = html.replace(markup, _tag('style', style_attrs) + css + '</style>', 1)
        else:
            html = html.replace(markup, _tag(tag, {**attrs, attribute: _image_url(path)}), 1)
    # Keep compilation boundaries: concatenation can change ASI and strict mode.
    inline_scripts = []
    for script in scripts:
        escaped = re.sub(r'</script', lambda match: '<\\/' + match.group()[2:], script, flags=re.I)
        inline_scripts.append('<script>' + escaped + '</script>')
    html, count = re.subn(r'</body\s*>', lambda _: '\n'.join(inline_scripts) + '</body>', html, count=1, flags=re.I)
    if count != 1:
        raise ValueError('Preview requires a closing body tag')
    Path(target).write_text(html, encoding='utf-8')


if __name__ == '__main__':
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'slipvolt-preview.html')
