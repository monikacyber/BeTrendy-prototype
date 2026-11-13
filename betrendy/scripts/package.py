#!/usr/bin/env python3
"""Create portable WordPress installation packages; never includes credentials/cache."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'packages'
OUT.mkdir(exist_ok=True)
for folder,name in [('wordpress/themes/betrendy','betrendy-theme.zip'),
                    ('wordpress/plugins/betrendy-urls','betrendy-urls-plugin.zip')]:
    source=ROOT/folder
    with ZipFile(OUT/name,'w',ZIP_DEFLATED) as z:
        for p in source.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(source.parent))
    print(name,(OUT/name).stat().st_size)
with ZipFile(OUT/'betrendy-migration-2026-11-13.zip','w',ZIP_DEFLATED) as z:
    for folder in ['assets','data','source/pages','wordpress','scripts']:
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                z.write(p,Path('betrendy')/p.relative_to(ROOT))
    for name in ['README.md','requirements.txt','source/url-inventory.json','source/homepage.json']:
        z.write(ROOT/name,Path('betrendy')/name)
print('Migration package:',(OUT/'betrendy-migration-2026-11-13.zip').stat().st_size)
