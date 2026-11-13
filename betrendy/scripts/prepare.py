#!/usr/bin/env python3
"""Build provenance-preserving catalog JSON, draft WooCommerce CSV and page blocks."""
import csv
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urljoin, unquote
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LANGS = ('uk', 'ru', 'en')
INFO = ('pro-nas','oplata-i-dostavka','obmin-ta-povernennya','publichna-oferta','contacts')
BLOG = ('dohliad-ta-zakhyst-2-v-1-z-losonamy-vid-be-trendy',
        'parfumovani-mus-piny-dlia-dushu-novynka-vid-be-trendy')
CATEGORY_SLUGS = ('dohliad-za-tilom','collections','vanna-spa','spf','podarunkovi-nabory',
    'podarunkovi-aksesuary','sprei-dlia-tila','krem-dlia-tila','mus-pina-dlia-dushu',
    'rich-vibes','care-line','shimmer-line','bombochky-dlia-vann','skraby-dlia-tila',
    'soli-dlia-vann','biser-dlia-vann','losion-z-shymerom')

def urlkey(url):
    return urlsplit(url).path.rstrip('/')

def native_blocks(markup):
    """Convert source prose to supported editable core blocks, not a Custom HTML wrapper."""
    soup = BeautifulSoup(markup, 'html.parser')
    for nested in soup.select('p p'):
        nested.unwrap()
    out = []
    for node in soup.find_all(['h1','h2','h3','h4','p','ul','ol','table','img']):
        if not node.name:
            continue
        if any(p.name in ('p','ul','ol','table') for p in node.parents):
            continue
        if node.name == 'img':
            if node.get('src'):
                src, alt = html.escape(node['src'], quote=True), html.escape(node.get('alt',''), quote=True)
                out.append(f'<!-- wp:image {{"sizeSlug":"full","linkDestination":"none"}} -->\n<figure class="wp-block-image size-full"><img src="{src}" alt="{alt}"/></figure>\n<!-- /wp:image -->')
        elif node.name == 'p' and node.find('img'):
            for img in node.find_all('img'):
                out.append(native_blocks(str(img)))
            if node.get_text(strip=True):
                for img in node.find_all('img'): img.decompose()
                out.append('<!-- wp:paragraph -->\n<p>'+node.decode_contents()+'</p>\n<!-- /wp:paragraph -->')
        elif node.name.startswith('h'):
            level = max(2, int(node.name[1]))
            if node.get_text(strip=True):
                out.append(f'<!-- wp:heading {{"level":{level}}} -->\n<h{level} class="wp-block-heading">{node.decode_contents()}</h{level}>\n<!-- /wp:heading -->')
        elif node.name == 'p' and node.find('a') and 'youtube.com/embed/' in node.find('a').get('href','') and node.get_text(strip=True)==node.find('a').get_text(strip=True):
            source=node.find('a')['href']
            video_id=urlsplit(source).path.rstrip('/').split('/')[-1]
            url='https://www.youtube.com/watch?v='+video_id
            attrs=json.dumps({'url':url,'type':'video','providerNameSlug':'youtube','responsive':True},ensure_ascii=False,separators=(',',':'))
            out.append('<!-- wp:embed '+attrs+' -->\n<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube"><div class="wp-block-embed__wrapper">\n'+html.escape(url)+'\n</div></figure>\n<!-- /wp:embed -->')
        elif node.name == 'p' and node.get_text(strip=True):
            out.append('<!-- wp:paragraph -->\n<p>'+node.decode_contents()+'</p>\n<!-- /wp:paragraph -->')
        elif node.name in ('ul','ol'):
            ordered = ' {"ordered":true}' if node.name == 'ol' else ''
            items = ''.join('<!-- wp:list-item --><li>'+li.decode_contents()+'</li><!-- /wp:list-item -->' for li in node.find_all('li',recursive=False))
            out.append(f'<!-- wp:list{ordered} --><{node.name} class="wp-block-list">{items}</{node.name}><!-- /wp:list -->')
        elif node.name == 'table':
            out.append('<!-- wp:table {"hasFixedLayout":false} --><figure class="wp-block-table">'+str(node)+'</figure><!-- /wp:table -->')
    return '\n\n'.join(out)

def group_block(content, class_name):
    attrs = json.dumps({'className': class_name, 'layout': {'type': 'default'}}, ensure_ascii=False)
    return '<!-- wp:group '+attrs+' -->\n<div class="wp-block-group '+class_name+'">\n'+content+'\n</div>\n<!-- /wp:group -->'

def heading_block(title):
    return '<!-- wp:heading --><h2 class="wp-block-heading">'+html.escape(title)+'</h2><!-- /wp:heading -->'

def linked_image_block(image, link=''):
    """Use captured media and destinations; the importer resolves local media IDs later."""
    if not image or not image.get('src'):
        return ''
    attrs = {'sizeSlug': 'full', 'linkDestination': 'custom' if link else 'none'}
    body = '<img src="'+html.escape(image['src'], quote=True)+'" alt="'+html.escape(image.get('alt', ''), quote=True)+'"/>'
    if link:
        body = '<a href="'+html.escape(link, quote=True)+'">'+body+'</a>'
    return '<!-- wp:image '+json.dumps(attrs)+' -->\n<figure class="wp-block-image size-full">'+body+'</figure>\n<!-- /wp:image -->'

def products_shortcode(skus):
    # WooCommerce resolves the captured SKUs to the newly imported product IDs.
    skus = list(dict.fromkeys(str(s) for s in skus if re.fullmatch(r'[A-Za-z0-9._-]+', str(s))))
    if not skus:
        return ''
    return '<!-- wp:shortcode -->\n[products skus="'+','.join(skus)+'" columns="5" limit="'+str(len(skus))+'" orderby="post__in"]\n<!-- /wp:shortcode -->'

def homepage_blocks(record, products, warnings):
    """Rebuild each captured storefront section with editable core blocks.

    Product prices and stock stay live in WooCommerce rather than becoming copied text.
    The source's extra product tabs become native expandable sections without custom JS.
    """
    soup = BeautifulSoup(record['main_html'], 'html.parser')
    main = soup.find('main') or soup
    product_lookup = {}
    for product in products.values():
        for key in ('source_url', 'canonical_url'):
            product_lookup[urlkey(product[key])] = product
    promo_sections = list(main.select('section.promo'))
    captured_skus = {}
    for section in promo_sections:
        skus = []
        for card in section.select('.catalogCard'):
            link = card.select_one('.catalogCard-title a[href], a.catalogCard-image[href]')
            if not link:
                continue
            product = product_lookup.get(urlkey(link['href']))
            if product:
                skus.append(product['meta']['sku'])
            else:
                warnings.append({'url': record['source_url'], 'issue': 'Homepage product is missing from captured catalogue', 'product_url': link['href']})
        active = section.select_one('.catalogTabs-nav-i.__active')
        key = active.get('rel') if active else ''
        captured_skus[key] = list(dict.fromkeys(skus))
    result = []
    for section in main.find_all(recursive=False):
        classes = section.get('class', [])
        if 'banners-group' in classes:
            banners = []
            seen = set()
            for banner in section.select('.banner'):
                image = banner.select_one('img[src]')
                link = banner.select_one('a[href]')
                if not image:
                    continue
                destination = link['href'] if link else ''
                identity = (image['src'], destination)
                if identity in seen:
                    continue
                seen.add(identity)
                banners.append(linked_image_block(image, destination))
            if not banners:
                continue
            if section.select_one('.banners--2x'):
                columns = '\n'.join('<!-- wp:column --><div class="wp-block-column">'+b+'</div><!-- /wp:column -->' for b in banners)
                result.append('<!-- wp:columns {"className":"bt-home-promos"} --><div class="wp-block-columns bt-home-promos">'+columns+'</div><!-- /wp:columns -->')
            else:
                result.append(group_block('\n'.join(banners), 'bt-banner-slider'))
        elif 'promo' in classes:
            tabs = section.select('.catalogTabs-nav-i')
            active = next((tab for tab in tabs if '__active' in tab.get('class', [])), tabs[0] if tabs else None)
            if active is None:
                continue
            active_key = active.get('rel', '')
            blocks = [heading_block(active.get_text(' ', strip=True)), products_shortcode(captured_skus.get(active_key, []))]
            for tab in tabs:
                if tab is active:
                    continue
                key, label = tab.get('rel', ''), tab.get_text(' ', strip=True)
                if key == 'global_action':
                    content = '<!-- wp:shortcode -->\n[products on_sale="true" columns="5" limit="10"]\n<!-- /wp:shortcode -->'
                elif key in captured_skus:
                    content = products_shortcode(captured_skus[key])
                else:
                    warnings.append({'url': record['source_url'], 'issue': 'Uncaptured homepage product tab', 'tab': key})
                    continue
                if content:
                    blocks.append('<!-- wp:details --><details class="wp-block-details"><summary>'+html.escape(label)+'</summary>'+content+'</details><!-- /wp:details -->')
            result.append(group_block('\n\n'.join(filter(None, blocks)), 'bt-home-section'))
        elif 'frontInfo' in classes:
            prose = section.select_one('.frontInfo-text .text') or section
            result.append(group_block(native_blocks(str(prose)), 'bt-home-story'))
    if not result:
        warnings.append({'url': record['source_url'], 'issue': 'Homepage layout could not be extracted'})
        return native_blocks(record['content_html'])
    return '\n\n'.join(result)

def contacts_html(record):
    """Keep contact values as usable links; exclude the removed callback dialog."""
    soup = BeautifulSoup(record['main_html'], 'html.parser')
    result, seen = [], set()
    for item in soup.select('.contacts-info__item'):
        if item.find_parent(class_='popup'):
            continue
        label = item.get_text(' ', strip=True)
        if not label or label in seen:
            continue
        anchor = item.find('a')
        href = (anchor.get('href') or unquote(anchor.get('data-fake-href', ''))) if anchor else ''
        if item.get('itemprop') == 'telephone' or href.startswith('tel:'):
            number = re.sub(r'[^0-9+]', '', item.get('content') or label)
            if re.fullmatch(r'0\d{9}', number):
                number = '+38'+number
            href = 'tel:'+number
        elif (anchor and anchor.get('itemprop') == 'email') or href.startswith('mailto:'):
            href = 'mailto:'+label.strip()
        if href.startswith(('tel:', 'mailto:', 'https://', 'http://')):
            result.append('<p><a href="'+html.escape(href, quote=True)+'">'+html.escape(label)+'</a></p>')
        else:
            result.append('<p>'+html.escape(label)+'</p>')
        seen.add(label)
    for address in soup.select('.contacts-address'):
        title = address.select_one('.h3, h2, h3')
        value = address.find('address')
        if title:
            result.append('<h2>'+html.escape(title.get_text(' ', strip=True))+'</h2>')
        if value:
            result.append('<p>'+html.escape(value.get_text(' ', strip=True))+'</p>')
    return ''.join(result) or record['content_html']

def select_products(group, warnings, redirects):
    by_sku = {}
    for record in group:
        if record['type'] != 'product':
            continue
        sku = record['meta'].get('sku')
        if not sku:
            warnings.append({'url': record['source_url'], 'issue': 'Missing SKU'})
            continue
        by_sku.setdefault(sku, []).append(record)
    chosen = {}
    for sku, candidates in by_sku.items():
        canonical = [r for r in candidates if urlkey(r['source_url']) == urlkey(r['canonical_url'])]
        selected = canonical[0] if canonical else candidates[0]
        chosen[sku] = selected
        for record in candidates:
            if record is selected:
                continue
            if urlkey(record['canonical_url']) == urlkey(selected['canonical_url']):
                redirects.append({'from': record['source_url'], 'to': selected['source_url']})
            else:
                warnings.append({'url': record['source_url'], 'issue': 'Duplicate SKU has a different canonical URL', 'sku': sku})
    return chosen

def category_chain(slug, categories_by_slug):
    """Return root-to-leaf category ancestry without following a malformed cycle."""
    chain = []
    while slug and slug not in chain:
        chain.append(slug)
        slug = categories_by_slug.get(slug, {}).get('parent_slug', '')
    return list(reversed(chain))

def main():
    records = [json.loads(p.read_text()) for p in sorted((ROOT/'source/pages').rglob('*.json'))]
    catalog, pages, categories, redirects = [], [], [], []
    media = {a['url']:a for a in json.loads((ROOT/'data/media-manifest.json').read_text()) if 'path' in a}
    warnings = []
    for lang in LANGS:
        group = [r for r in records if r['language']==lang]
        products_by_sku = select_products(group, warnings, redirects)
        memberships = {}
        for cat in (r for r in group if r['slug'] in CATEGORY_SLUGS):
            hierarchy = [b for b in cat['breadcrumbs'] if b['url'].rstrip('/').split('/')[-1] in CATEGORY_SLUGS]
            parent = hierarchy[-1]['url'].rstrip('/').split('/')[-1] if hierarchy else ''
            if parent == cat['slug']: parent = ''
            categories.append({'language':lang,'slug':cat['slug'],'name':cat['title'],'parent_slug':parent,
                'description':cat['content_html'],'source_url':cat['source_url']})
        for cat in group:
            # Horoshop pagination is a path, e.g. /vanna-spa/filter/page=all/.
            # Use any captured continuation pages without creating duplicate categories.
            category_slug = cat['slug'].split('/filter/', 1)[0]
            if category_slug not in CATEGORY_SLUGS:
                continue
            doc = BeautifulSoup(cat['main_html'],'html.parser')
            for a in doc.select('.catalogCard a[href], .catalog-grid a[href], .catalog-list a[href]'):
                memberships.setdefault(urlkey(a['href']),set()).add(category_slug)
        category_lookup = {c['slug']: c for c in categories if c['language'] == lang}
        for sku, r in products_by_sku.items():
            meta=r['meta']
            price=meta.get('product:price:amount','')
            regular=meta.get('product:original_price:amount') or price
            sale=price if price != regular else ''
            cats=set(memberships.get(urlkey(r['source_url']),[]))
            cats.update(b['url'].rstrip('/').split('/')[-1] for b in r['breadcrumbs']
                        if b['url'].rstrip('/').split('/')[-1] in CATEGORY_SLUGS)
            cats = {ancestor for slug in cats for ancestor in category_chain(slug, category_lookup)}
            feature_table='<table><tbody>'+''.join('<tr><th>'+html.escape(k)+'</th><td>'+html.escape(v)+'</td></tr>' for k,v in r['features'].items())+'</tbody></table>'
            catalog.append({'sku':sku,'language':lang,'slug':r['slug'],'name':r['title'],
                'gtin':meta.get('gtin',''),'description':r['content_html'],
                'description_blocks':native_blocks(r['content_html'])+'\n\n'+native_blocks(feature_table),
                'short_description':meta.get('og:description',''),'features':r['features'],
                'regular_price':regular,'sale_price':sale,'currency':meta.get('product:price:currency',''),
                'stock_status':'instock' if meta.get('product:availability')=='instock' else 'outofstock',
                'source_availability':meta.get('product:availability',''), 'manage_stock':False,
                'category_slugs':sorted(cats),'gallery':r['gallery'],
                'source_url':r['source_url'],'canonical_url':r['canonical_url'],
                'seo_title':meta.get('title',r['title']),'seo_description':meta.get('description',''),
                'captured_date':'2026-11-13'})
        for r in group:
            if r['slug'] not in INFO+BLOG+('home',): continue
            content=r['content_html']
            if r['slug']=='contacts':
                content=contacts_html(r)
            blocks = homepage_blocks(r, products_by_sku, warnings) if r['slug'] == 'home' else native_blocks(content)
            source_empty = not bool(BeautifulSoup(content, 'html.parser').get_text(strip=True)) and not BeautifulSoup(content, 'html.parser').find('img')
            if not blocks.strip():
                warnings.append({'url':r['source_url'],'issue':'Source article has no translated body; kept empty, no text invented'})
            cover=BeautifulSoup(r['main_html'],'html.parser').select_one('.article__cover img[src]')
            pages.append({'language':lang,'slug':r['slug'],'title':r['title'] or 'Be Trendy',
                'type':'post' if r['slug'] in BLOG else 'page','content_blocks':blocks,
                'source_content_empty':bool(source_empty),
                'featured_image':cover['src'] if cover else '',
                'source_url':r['source_url'],'seo_title':r['meta'].get('title',''),
                'seo_description':r['meta'].get('description','')})
    for filename, value in [('catalog.json',catalog),('pages.json',pages),('categories.json',categories),('redirects.json',redirects)]:
        (ROOT/'data'/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2))
    # Only UAH/Ukrainian catalog is directly importable. Other languages remain translation data,
    # never duplicate products/SKUs and never overwrite UAH with the source's English USD prices.
    uk=[p for p in catalog if p['language']=='uk']
    uk_categories={c['slug']:c for c in categories if c['language']=='uk'}
    def csv_category_path(slug):
        return ' > '.join(uk_categories.get(c, {}).get('name', c).replace(',',r'\,')
                          for c in category_chain(slug, uk_categories))
    headers=['Type','SKU','Name','Published','Visibility in catalog','Short description','Description',
             'In stock?','Regular price','Sale price','Categories','Images','GTIN, UPC, EAN, or ISBN',
             'meta:betrendy_source_url','meta:betrendy_captured_date','meta:betrendy_source_currency']
    with (ROOT/'data/woocommerce-products-uk.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader()
        for p in uk:
            writer.writerow({'Type':'simple','SKU':p['sku'],'Name':p['name'],'Published':-1,
                'Visibility in catalog':'visible','Short description':p['short_description'],
                'Description':p['description_blocks'],'In stock?':int(p['stock_status']=='instock'),
                'Regular price':p['regular_price'],'Sale price':p['sale_price'],
                'Categories':', '.join(csv_category_path(c) for c in p['category_slugs']),
                'Images':', '.join(p['gallery']),'GTIN, UPC, EAN, or ISBN':p['gtin'],
                'meta:betrendy_source_url':p['source_url'],'meta:betrendy_captured_date':'2026-11-13',
                'meta:betrendy_source_currency':p['currency']})
    summary={'products_by_language':{l:sum(p['language']==l for p in catalog) for l in LANGS},
        'pages_and_posts':len(pages),'categories':len(categories),'warnings':warnings,
        'missing_gallery_assets':sorted(set(u for p in catalog for u in p['gallery'] if u not in media)),
        'currencies':{l:sorted(set(p['currency'] for p in catalog if p['language']==l)) for l in LANGS}}
    (ROOT/'data/prepare-report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
