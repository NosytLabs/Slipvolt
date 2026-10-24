"""Build a self-contained offline preview. No credentials or network calls."""
from pathlib import Path
import base64
import mimetypes
import re
ROOT = Path(__file__).resolve().parents[1]
def build(target):
    public=ROOT/'public'
    html=(public/'index.html').read_text()
    html=html.replace('<html lang="en">','<html lang="en" data-preview="offline">')
    for name in ('styles.css','tools.css'):
        # Fail before writing if the source package is incomplete.
        css = (public/name).read_text(encoding='utf-8')
        html=html.replace(f'<link rel="stylesheet" href="{name}">','<style>'+css+'</style>')
    html=html.replace('<script src="core.js" defer></script>','').replace('<script src="app.js" defer></script>','').replace('<script src="request-examples.js" defer></script>','').replace('<script src="account-tools.js" defer></script>','')
    for name in ('request-tools.js','launch-tools.js'):
        html=html.replace(f'<script src="{name}" defer></script>','')
    html=html.replace('href="favicon.svg"','href="data:image/svg+xml;base64,'+base64.b64encode((public/'favicon.svg').read_bytes()).decode()+'"')
    # Include the actual brand art so a downloaded preview works without a server.
    for source in set(re.findall(r'<img\b[^>]*\bsrc="(assets/[^"]+)"', html)):
        path=(public/source).resolve()
        if not path.is_relative_to((public/'assets').resolve()):
            raise ValueError('Preview image must be inside public/assets')
        content_type=mimetypes.guess_type(path.name)[0]
        if not content_type or not content_type.startswith('image/'):
            raise ValueError('Preview asset must be an image')
        data=base64.b64encode(path.read_bytes()).decode()
        html=html.replace(f'src="{source}"',f'src="data:{content_type};base64,{data}"')
    html=html.replace('</body>','<script>'+'\n'.join((public/n).read_text() for n in ['core.js','request-examples.js','app.js','account-tools.js','request-tools.js','launch-tools.js']).replace('</script','<\\/script')+'</script></body>')
    Path(target).write_text(html)
if __name__=='__main__':
    import sys
    build(sys.argv[1] if len(sys.argv)>1 else str(ROOT/'slipvolt-preview.html'))
