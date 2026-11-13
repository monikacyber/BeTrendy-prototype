#!/usr/bin/env python3
"""Read-only audit of the public BeTrendy storefront, links and image responses."""
import concurrent.futures, hashlib, json, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
BASE='https://betrendy.online'
CACHE=ROOT/'.cache/live-audit';CACHE.mkdir(parents=True,exist_ok=True)
HEADERS={'User-Agent':'Mozilla/5.0 BeTrendyMigrationAudit/1.0','Cache-Control':'no-cache'}
def fetch(url,head=False):
 p=urlsplit(url);url=urlunsplit((p.scheme,p.netloc,quote(p.path,safe='/%:@'),p.query,''))
 try:
  with urlopen(Request(url,headers=HEADERS,method='HEAD' if head else 'GET'),timeout=45) as r:return r.status,r.headers.get('Content-Type',''),b'' if head else r.read(),r.geturl()
 except HTTPError as e:return e.code,e.headers.get('Content-Type',''),b'',url
 except Exception as e:return 0,str(e),b'',url
m=json.loads((ROOT/'data/wordpress-content-map.json').read_text())
urls={BASE+'/',BASE+'/shop/',BASE+'/blog/',BASE+'/cart/',BASE+'/checkout/',BASE+'/my-account/'}
for kind in ('pages','posts','products'):
 for x in m[kind]:
  if x.get('slug')!='home':urls.add(x['link'].split('?')[0])
for x in m['categories']:urls.add(BASE+'/'+x['slug']+'/')
images=set();internal=set();results=[]
def page(url):
 status,ctype,body,final=fetch(url)
 soup=BeautifulSoup(body,'html.parser')
 text=soup.get_text(' ',strip=True)
 blocked=any(x in text.lower() for x in ['checking your browser','магазин скоро відкриється','great things are on the horizon','welcome to wordpress. this is your first post'])
 if url==BASE+'/' and not ('Новинки' in text and 'Хіти продажу' in text):blocked=True
 (CACHE/(hashlib.sha256(url.encode()).hexdigest()[:16]+'.html')).write_bytes(body)
 imgs={urljoin(final,x.get('src','')) for x in soup.find_all('img') if x.get('src') and not x['src'].startswith('data:')}
 links={urljoin(final,a['href']).split('#')[0] for a in soup.find_all('a',href=True)}
 return {'url':url,'status':status,'content_type':ctype,'title':soup.title.get_text(strip=True) if soup.title else '', 'image_count':len(imgs),'blocked':blocked,'bytes':len(body)},imgs,links
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for n,(r,imgs,links) in enumerate(pool.map(page,sorted(urls)),1):
  results.append(r);images.update(imgs);internal.update(x for x in links if urlsplit(x).netloc=='betrendy.online')
  if n%10==0:print(json.dumps({'pages_checked':n,'total':len(urls)}),flush=True)
def image(url):
 s,t,_,u=fetch(url,True)
 return {'url':url,'status':s,'content_type':t,'valid':s==200 and t.lower().startswith('image/')}
image_results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 for n,r in enumerate(pool.map(image,sorted(images)),1):
  image_results.append(r)
  if n%40==0:print(json.dumps({'images_checked':n,'total':len(images)}),flush=True)
failed_pages=[x for x in results if x['status']!=200 or x['blocked'] or not x['bytes']]
failed_images=[x for x in image_results if not x['valid']]
report={'checked_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'pages_checked':len(results),'images_checked':len(image_results),'failed_pages':failed_pages,'failed_images':failed_images,'pages':results,'images':image_results,'internal_links_discovered':len(internal),'passed':not failed_pages and not failed_images}
(ROOT/'data/live-site-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(CACHE/'internal-links.json').write_text(json.dumps(sorted(internal),ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('pages','images')},ensure_ascii=False),flush=True)
