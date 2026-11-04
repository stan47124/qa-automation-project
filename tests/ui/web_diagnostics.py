"""Allowlisted browser state: no HTML, cookies, form contents or URL tokens."""

import json
import re
from urllib.parse import urlsplit

import allure

KNOWN_TITLES = {
    'Automation Exercise', 'Automation Exercise - All Products',
    'Automation Exercise - Contact Us', 'Automation Exercise - Product Details',
    'Automation Exercise - Checkout', 'Automation Exercise - Cart',
    'One moment, please...', 'Just a moment...', 'Секундочку…',
}
PAGE_FLAGS = """
return {
  document_ready: document.readyState === 'complete',
  home_marker: !!document.querySelector('.features_items .title'),
  contact_marker: !!document.querySelector('.contact-form h2'),
  challenge_title: /one moment|just a moment|секундочку/i.test(document.title),
  challenge_message: /please wait while your request is being verified|Пожалуйста, подождите|запрос будет проверен/i.test(document.body?.innerText || '')
};
"""


def safe_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or parsed.hostname not in {
            'automationexercise.com', 'www.automationexercise.com',
        }:
            return '[unexpected URL omitted]'
        path = parsed.path
        if not re.fullmatch(r'/(?:contact_us|products|view_cart|product_details/[0-9]+)?', path):
            path = '/[other path omitted]'
        return f'{parsed.scheme}://{parsed.hostname}{path}'
    except (TypeError, ValueError):
        return '[invalid URL omitted]'


def browser_state(driver):
    title = driver.title
    flags = driver.execute_script(PAGE_FLAGS)
    # Copy known booleans only; never serialize an arbitrary browser response.
    result = {key: flags.get(key) is True for key in (
        'document_ready', 'home_marker', 'contact_marker', 'challenge_title', 'challenge_message',
    )}
    result.update(url=safe_url(driver.current_url),
                  title=title if title in KNOWN_TITLES else '[unrecognized title omitted]')
    result['request_check_page'] = result['challenge_title'] or result['challenge_message']
    return result


def attach_browser_state(driver, phase):
    try:
        state = browser_state(driver)
    except Exception as error:
        state = {'diagnostic_error_type': type(error).__name__}
    allure.attach(json.dumps(state, ensure_ascii=False),
                  name=f'Web UI: {phase} page state (allowlisted)',
                  attachment_type=allure.attachment_type.JSON)
