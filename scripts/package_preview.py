"""Build a self-contained offline preview. No credentials or network calls."""
from pathlib import Path
import base64
ROOT = Path(__file__).resolve().parents[1]
def build(target):
    public=ROOT/'public'
    html=(public/'index.html').read_text()
    html=html.replace('<html lang="en">','<html lang="en" data-preview="offline">')
    for stylesheet in ('styles.css','content.css'):
        html=html.replace(f'<link rel="stylesheet" href="{stylesheet}">','<style>'+(public/stylesheet).read_text()+'</style>')
    html=html.replace('<script src="core.js" defer></script>','').replace('<script src="app.js" defer></script>','').replace('<script src="request-examples.js" defer></script>','').replace('<script src="account-tools.js" defer></script>','')
    html=html.replace('href="favicon.svg"','href="data:image/svg+xml;base64,'+base64.b64encode((public/'favicon.svg').read_bytes()).decode()+'"')
    html=html.replace('</body>','<script>'+'\n'.join((public/n).read_text() for n in ['core.js','request-examples.js','app.js','account-tools.js']).replace('</script','<\\/script')+'</script></body>')
    Path(target).write_text(html)
if __name__=='__main__':
    import sys
    build(sys.argv[1] if len(sys.argv)>1 else str(ROOT/'slipvolt-preview.html'))
