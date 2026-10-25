from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class Elements(HTMLParser):
    def __init__(self): super().__init__();self.links=[];self.ids=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a':self.links.append(attrs.get('href',''))
        if 'id' in attrs:self.ids.append(attrs['id'])

def test_homepage_connects_models_and_token_evidence_and_preserves_key_compatibility():
    text=(ROOT/'public/index.html').read_text();p=Elements();p.feed(text)
    assert 'models/' in p.links, 'Live model directory is not reachable'
    assert 'token/' in p.links, 'Token evidence is not reachable'
    assert 'HOLDBYTE_API_KEY' in text and 'SLIPVOLT_API_KEY' in text
    assert 'unsigned burn instructions' in text and 'not enabled' in text

def test_new_views_have_unique_ids_and_keyboard_entry_points():
    for path in ('public/models/index.html','public/admin/burns/index.html'):
        text=(ROOT/path).read_text();p=Elements();p.feed(text)
        assert len(p.ids)==len(set(p.ids))
        assert '#main' in p.links
        assert '<h1' in text and 'aria-label' in text
        assert 'cdn.' not in text and 'http://' not in text
