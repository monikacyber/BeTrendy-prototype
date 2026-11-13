#!/usr/bin/env python3
"""Restore archived public images from a SHA-256 manifest, without credentials."""
import concurrent.futures
import hashlib
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]

def restore(item):
    if 'path' not in item: raise RuntimeError('Manifest contains failed image: '+item['url'])
    p=urlsplit(item['url'])
    if p.scheme!='https' or p.hostname!='betrendy.space' or not p.path.startswith('/content/'):
        raise RuntimeError('Unexpected source URL')
    dest=(ROOT/item['path']).resolve()
    if not dest.is_relative_to((ROOT/'assets').resolve()): raise RuntimeError('Invalid asset path')
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()==item['sha256']:
        return
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(dest.suffix+'.partial')
    subprocess.run(['curl','-fLsS','--retry','5','--retry-delay','4','--max-time','120',
        '-A','Mozilla/5.0 (compatible; BeTrendyMigration/1.0)',item['url'],'-o',str(temp)],check=True)
    data=temp.read_bytes()
    if hashlib.sha256(data).hexdigest()!=item['sha256']:
        temp.unlink(missing_ok=True)
        raise RuntimeError('Source image changed since capture: '+item['url'])
    temp.replace(dest)
    time.sleep(0.4)

def main():
    rows=json.loads((ROOT/'data/media-manifest.json').read_text())
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(restore,row):row for row in rows}
        for i,job in enumerate(concurrent.futures.as_completed(jobs),1):
            try: job.result()
            except Exception as exc:
                failures.append({'path':jobs[job]['path'],'url':jobs[job]['url'],'error':str(exc)})
            if i%50==0: print(f'Verified {i}/{len(rows)} images',flush=True)
    if failures:
        print('FILES_REQUIRING_ORIGINAL_LOCAL_COPY='+json.dumps(failures,ensure_ascii=False),flush=True)
        raise SystemExit(1)
    print(f'Complete: {len(rows)} original images verified')

if __name__=='__main__':main()
