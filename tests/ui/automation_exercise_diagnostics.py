"""Allowlisted Automation Exercise evidence without form values or full HTML."""
import json
from urllib.parse import urlsplit

import allure
from selenium.webdriver.common.by import By

CONTAINERS = {
    '/': '.features_items', '/products': '.features_items',
    '/product_details/1': '.product-information', '/view_cart': '#cart_info',
}
TITLES = {'Automation Exercise', 'Automation Exercise - All Products',
          'Automation Exercise - Product Details', 'Automation Exercise - Checkout',
          'Automation Exercise - Contact Us', 'One moment, please...', 'Just a moment...',
          'Секундочку…', '403 Forbidden', 'Access Denied'}
FLAGS = """return {
  catalog: !!document.querySelector('.features_items .title'),
  cart: !!document.querySelector('#cart_info_table'),
  contact: !!document.querySelector('#contact-us-form'),
  password: !!document.querySelector('input[type="password"]'),
  challenge: /one moment|just a moment|секундоч|access denied|403 forbidden/i.test(document.title) ||
    /verify you are human|checking your browser/.test(document.body?.innerText || ''),
  captcha: [...document.querySelectorAll('iframe[src*="captcha"],iframe[title*="challenge"]')]
    .some(e => e.getBoundingClientRect().height > 0)
};"""


def safe_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or parsed.hostname != 'automationexercise.com':
            return '[unexpected URL omitted]'
        path = parsed.path if parsed.path in {*CONTAINERS, '/contact_us'} else '/[other path omitted]'
        return 'https://automationexercise.com' + path
    except (TypeError, ValueError):
        return '[invalid URL omitted]'


def attach_failure(driver, phase):
    state = None
    try:
        flags = driver.execute_script(FLAGS)
        state = {key: flags.get(key) is True for key in
                 ['catalog', 'cart', 'contact', 'password', 'challenge', 'captcha']}
        title = driver.title
        state.update(url=safe_url(driver.current_url),
                     title=title if title in TITLES else '[unrecognized title omitted]')
    except Exception as error:
        state = {'diagnostic_error_type': type(error).__name__}
    try:
        allure.attach(json.dumps(state, ensure_ascii=False),
                      name=f'Web UI: {phase} page state (allowlisted)',
                      attachment_type=allure.attachment_type.JSON)
    except Exception:
        pass
    try:
        path = urlsplit(state.get('url', '')).path
        if (path not in CONTAINERS or not state.get('title', '').startswith('Automation Exercise')
                or any(state.get(key) for key in ['contact', 'password', 'challenge', 'captcha'])):
            return
        png = driver.find_element(By.CSS_SELECTOR, CONTAINERS[path]).screenshot_as_png
        if not png.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Expected PNG evidence')
        allure.attach(png, name=f'Web UI: {phase} page container',
                      attachment_type=allure.attachment_type.PNG)
    except Exception:
        pass  # Evidence must never replace the original test exception.
