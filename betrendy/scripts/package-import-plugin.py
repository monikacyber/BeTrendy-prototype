#!/usr/bin/env python3
"""Package the bounded draft importer and its snapshot data; media packs are separate."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'wordpress/plugins/betrendy-import'
DATA = PLUGIN / 'data'
DATA.mkdir(parents=True, exist_ok=True)
checksums = {}
def guarded_json(content):
    text = content.decode('utf-8')
    delimiter = 'BTR_JSON_' + hashlib.sha256(content).hexdigest()[:24].upper()
    assert delimiter not in text
    return ("<?php\nif (!defined('ABSPATH')) { http_response_code(404); exit; }\n"
            + "return <<<'" + delimiter + "'\n" + text.rstrip('\n')
            + '\n' + delimiter + ';\n').encode('utf-8')

# Remove obsolete generated raw JSON copies: the only deployable payload is guarded PHP.
for old in DATA.glob('*.json'):
    old.unlink()
for name in ('catalog', 'pages', 'categories', 'media-manifest', 'redirects'):
    content = guarded_json((ROOT / 'data' / (name + '.json')).read_bytes())
    (DATA / (name + '.php')).write_bytes(content)
    checksums[name + '.php'] = hashlib.sha256(content).hexdigest()
config = PLUGIN / 'import-config.json'
if not config.exists():
    config.write_text(json.dumps({'github_commit': ''}, indent=2) + '\n')
config_content = guarded_json(config.read_bytes())
(DATA / 'import-config.php').write_bytes(config_content)
checksums['import-config.php'] = hashlib.sha256(config_content).hexdigest()
(DATA / 'checksums.php').write_bytes(guarded_json((json.dumps(checksums, indent=2) + '\n').encode()))
(DATA / '.htaccess').write_text('Require all denied\n')
(DATA / 'index.php').write_text('<?php http_response_code(404); exit;\n')
out = ROOT / 'packages/betrendy-import-plugin.zip'
out.parent.mkdir(exist_ok=True)
with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
    for path in sorted(PLUGIN.rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(PLUGIN.parent))
assert out.stat().st_size < 5 * 1024 * 1024
print(json.dumps({'path': str(out), 'bytes': out.stat().st_size,
                  'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}))
