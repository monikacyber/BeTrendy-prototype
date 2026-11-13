#!/usr/bin/env python3
"""Exercise a new guest cart; never submit checkout, place an order or send mail.

API contract: https://developer.woocommerce.com/docs/apis/store-api/resources-endpoints/cart/
Cart tokens are kept in memory and are excluded from the report.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://betrendy.online/wp-json/wc/store/v1/'
opener = build_opener(HTTPCookieProcessor(CookieJar()))
token = ''


def api(path, payload=None):
    global token
    headers = {'User-Agent': 'BeTrendyCartAudit/1.0', 'Cache-Control': 'no-cache'}
    if token:
        headers['Cart-Token'] = token
    data = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(payload).encode()
    with opener.open(Request(BASE + path, data=data, headers=headers), timeout=60) as response:
        token = response.headers.get('Cart-Token', token)
        return json.load(response)


def snapshot(cart):
    return {
        'items_count': cart['items_count'], 'total_items': cart['totals']['total_items'],
        'currency': cart['totals']['currency_code'],
        'payment_methods': cart.get('payment_methods'), 'errors': cart.get('errors'),
        'shipping_rates': [{'id': r['rate_id'], 'name': r['name'], 'price': r['price']}
                           for package in cart.get('shipping_rates', []) for r in package['shipping_rates']],
    }


products = api('products?per_page=100')
assert len(products) == 61, f'Expected 61 public products, got {len(products)}'
assert all(p['images'] for p in products), 'A product has no image'
product = next(p for p in products if p['sku'] == '100001')
assert product['is_purchasable'] and product['is_in_stock']
price = int(product['prices']['price']) / 10 ** product['prices']['currency_minor_unit']
cart = api('cart')
assert not cart['items'], 'The isolated guest cart must start empty'
report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'site_url': 'https://betrendy.online',
          'public_products': len(products), 'products_with_images': sum(bool(p['images']) for p in products),
          'tested_product_id': product['id'], 'tested_sku': product['sku'], 'orders_created': 0,
          'emails_sent': 0, 'tests': {}}
key = None
try:
    cart = api('cart/add-item', {'id': product['id'], 'quantity': 1})
    key = cart['items'][0]['key']
    assert cart['items_count'] == 1
    cart = api('cart/update-customer', {'shipping_address': {'country': 'UA', 'city': 'Київ', 'postcode': '01001'},
                                        'billing_address': {'country': 'UA', 'city': 'Київ', 'postcode': '01001'}})
    report['tests']['below_free_delivery_threshold'] = snapshot(cart)
    rates = report['tests']['below_free_delivery_threshold']['shipping_rates']
    assert len(rates) == 3 and all('підтвердить менеджер' in r['name'] for r in rates)
    assert 'bacs' in cart['payment_methods']
    cart = api('cart/select-shipping-rate', {'package_id': cart['shipping_rates'][0]['package_id'], 'rate_id': rates[1]['id']})
    assert any(r['selected'] and r['rate_id'] == rates[1]['id'] for r in cart['shipping_rates'][0]['shipping_rates'])
    report['tests']['select_locker_delivery'] = True
    quantity = math.ceil(1500 / price)
    cart = api('cart/update-item', {'key': key, 'quantity': quantity})
    report['tests']['above_free_delivery_threshold'] = snapshot(cart)
    rates = report['tests']['above_free_delivery_threshold']['shipping_rates']
    assert len(rates) == 3 and all('безкоштовно' in r['name'] and int(r['price']) == 0 for r in rates)
    assert not cart.get('errors')
    report['passed'] = True
finally:
    if key:
        cart = api('cart/remove-item', {'key': key})
        report['guest_cart_cleared'] = cart['items_count'] == 0
    (ROOT / 'data/cart-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
