"""Keep the documentation map usable without moving published file paths."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_documentation_has_one_entry_point():
    index = ROOT/'docs/README.md'
    assert index.is_file(), 'Missing documentation index'
    assert '(docs/README.md)' in (ROOT/'README.md').read_text()
    text = index.read_text()
    for filename in ('FUNCTIONAL-SETUP.md', 'ADMIN.md', 'TOKEN-AUDIT.md',
                     'TREASURY-BURNS.md', 'API-POLICY.md', 'SECURITY.md', 'VERIFICATION.md'):
        assert '('+filename+')' in text


def test_documentation_index_has_no_orphan_guides():
    text = (ROOT/'docs/README.md').read_text()
    for path in (ROOT/'docs').glob('*.md'):
        if path.name != 'README.md':
            assert '('+path.name+')' in text, f'Unlisted guide: {path.name}'


def test_readme_and_documentation_index_links_exist():
    for source in (ROOT/'README.md', ROOT/'docs/README.md'):
        for target in re.findall(r'\[[^\]]+\]\(([^\s)]+)\)', source.read_text()):
            if '://' in target or target.startswith(('#', 'mailto:')):
                continue
            relative = target.split('#', 1)[0]
            assert (source.parent/relative).exists(), f'{source.name}: broken link {target}'


def test_root_readme_names_current_tools_and_preserves_compatibility():
    text = (ROOT/'README.md').read_text()
    for item in ('/models/', '/token/', '/admin/burns/', 'HOLDBYTE_API_KEY',
                 'SLIPVOLT_API_KEY', 'gridraft_session', 'sv_', 'sh scripts/verify.sh'):
        assert item in text
