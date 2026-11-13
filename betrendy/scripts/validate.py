#!/usr/bin/env python3
"""Validate real migration invariants: source coverage, SKU parity, prices and media hashes."""
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from capture import normalize

ROOT=Path(__file__).resolve().parents[1]
read=lambda name:json.loads((ROOT/'data'/name).read_text())
catalog=read('catalog.json')
report=read('capture-report.json')
assert not report['media_errors'], report['media_errors']
inventory=json.loads((ROOT/'source/url-inventory.json').read_text())
required=set(filter(None,(normalize(row['url']) for row in inventory['links'])))
captured={json.loads(p.read_text())['source_url'] for p in (ROOT/'source/pages').rglob('*.json')}
assert not required-captured, sorted(required-captured)
assert report['captured_pages']+len(report['page_errors'])==report['requested_pages']
assert all('/filter/page=all/' in row['url'] for row in report['page_errors']),report['page_errors']
sku_sets={lang:{p['sku'] for p in catalog if p['language']==lang} for lang in ('uk','ru','en')}
assert sku_sets['uk']==sku_sets['ru']==sku_sets['en']
assert all(n==1 for n in Counter((p['language'],p['sku']) for p in catalog).values())
manifest={m['url']:m for m in read('media-manifest.json')}
for product in catalog:
    assert product['name'] and product['description'] and product['gallery'], product['sku']
    assert product['currency']==('USD' if product['language']=='en' else 'UAH')
    assert Decimal(product['regular_price'])>=0
    if product['sale_price']:
        assert Decimal(product['sale_price'])<=Decimal(product['regular_price'])
    for url in product['gallery']:assert url in manifest,url
for item in manifest.values():
    path=ROOT/item['path']
    assert path.exists(),str(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],str(path)
with (ROOT/'data/woocommerce-products-uk.csv').open(encoding='utf-8-sig') as f:
    rows=list(csv.DictReader(f))
assert len(rows)==len(sku_sets['uk'])
assert all(row['Published']=='-1' for row in rows)
assert {r['SKU'] for r in rows}==sku_sets['uk']
pages=read('pages.json')
assert len(pages)==24
assert all(p['content_blocks'].strip() or (p['type']=='post' and p.get('source_content_empty')) for p in pages)
result={'passed':True,'captured_public_pages':report['captured_pages'],
        'required_inventory_pages':len(required),'required_inventory_pages_missing':0,
        'supplementary_full_listing_pages_unavailable':report['page_errors'],
        'unique_skus_per_language':{l:len(v) for l,v in sku_sets.items()},
        'verified_original_images':len(manifest),'csv_drafts':len(rows),
        'editable_pages_posts':sum(bool(p['content_blocks'].strip()) for p in pages),
        'empty_article_translations_in_source':sum(not bool(p['content_blocks'].strip()) for p in pages),
        'runtime_wordpress_tested':False,'hostinger_deployed':False}
(ROOT/'data/validation-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
