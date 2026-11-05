"""Isolated SauceDemo PoC; no pytest collection, Jenkins or Allure publication.

Public training credentials below belong to the demo site, never to a user.
No raw exceptions, browser logs, cookies, HTML or input values are persisted.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from uuid import uuid4

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / 'artifacts'
sys.path.insert(0, str(ROOT / 'ci'))
from windows_resources import OwnedProcesses

URL = 'https://www.saucedemo.com/'
WAIT_SECONDS = 15
RUN_SECONDS = 120


class BlockedAccessError(RuntimeError):
    pass


def safe_state(driver):
    parsed = urlsplit(driver.current_url)
    path = parsed.path if parsed.path in {'/', '/inventory.html', '/cart.html'} else '/[omitted]'
    url = 'https://www.saucedemo.com' + path if parsed.scheme == 'https' and parsed.hostname == 'www.saucedemo.com' else '[unexpected URL omitted]'
    title = driver.title
    flags = driver.execute_script('''return {
        challenge: /just a moment|one moment|секундочку|access denied|403 forbidden/i.test(document.title) ||
          /verify you are human|checking your browser|запрос будет проверен/i.test(document.body?.innerText || ''),
        captcha: [...document.querySelectorAll('iframe[src*="captcha"],iframe[title*="challenge"]')].some(e => e.getBoundingClientRect().height > 0),
        login: !!document.querySelector('#login-button'),
        catalog: !!document.querySelector('#inventory_container'),
        cart: !!document.querySelector('.cart_list')
    };''')
    return {'url': url, 'title': title if title in {'Swag Labs','Just a moment...','One moment, please...','403 Forbidden','Access Denied','Секундочку…'} else '[unrecognized title omitted]',
            **{key: flags.get(key) is True for key in ['challenge','captcha','login','catalog','cart']}}


def guard(driver):
    state = safe_state(driver)
    if state['challenge'] or state['captcha']:
        raise BlockedAccessError()
    for entry in driver.get_log('performance'):
        message = json.loads(entry['message'])['message']
        data = message.get('params', {})
        if message['method'] == 'Network.responseReceived' and data.get('type') == 'Document':
            response = data.get('response', {})
            if urlsplit(response.get('url','')).hostname == 'www.saucedemo.com' and response.get('status') in {403,429}:
                raise BlockedAccessError()


def execute(mode, folder):
    result = {'mode': mode, 'status': 'failed', 'phase': 'browser_start',
              'selenium': importlib.metadata.version('selenium'), 'login_page_seconds': None,
              'catalog_seconds': None, 'cart_verified': False, 'driver_closed': False}
    driver = None
    started = time.monotonic()
    try:
        options = webdriver.ChromeOptions()
        if mode == 'headless': options.add_argument('--headless=new')
        options.add_argument('--window-size=1440,1000')
        options.add_argument('--disable-notifications')
        options.set_capability('goog:loggingPrefs', {'performance':'ALL'})
        driver = webdriver.Chrome(options=options, service=webdriver.ChromeService(log_output=os.devnull))
        driver.set_page_load_timeout(45)
        driver.set_script_timeout(10)
        cap = driver.capabilities
        profile = Path(cap['chrome']['userDataDir']).resolve()
        result.update(chrome=cap['browserVersion'], chromedriver=cap['chrome']['chromedriverVersion'].split(' ')[0],
                      temporary_profile=profile.is_relative_to(Path(tempfile.gettempdir()).resolve()),
                      profile_instance=profile.name)
        assert result['temporary_profile'], 'A fresh temporary ChromeDriver profile is required'
        wait = WebDriverWait(driver, WAIT_SECONDS, ignored_exceptions=(StaleElementReferenceException,))
        def until(condition):
            def check(d):
                guard(d)
                return condition(d)
            return wait.until(check)
        result['phase'] = 'login_page'
        phase = time.monotonic()
        driver.get(URL)  # exactly one explicit site navigation per independent run
        for identifier in ['user-name','password','login-button']:
            until(EC.visibility_of_element_located((By.ID, identifier)))
        result['login_page_seconds'] = round(time.monotonic()-phase,3)
        result['phase'] = 'demo_login'
        driver.find_element(By.ID,'user-name').send_keys('standard_user')
        driver.find_element(By.ID,'password').send_keys('secret_sauce')
        phase = time.monotonic()
        until(EC.element_to_be_clickable((By.ID,'login-button'))).click()
        until(EC.visibility_of_element_located((By.ID,'inventory_container')))
        until(lambda d: d.find_elements(By.CSS_SELECTOR,'.inventory_item'))
        result['catalog_seconds'] = round(time.monotonic()-phase,3)
        result['phase'] = 'add_backpack'
        cards = driver.find_elements(By.CSS_SELECTOR,'.inventory_item')
        backpack = next(card for card in cards if card.find_element(By.CSS_SELECTOR,'.inventory_item_name').text == 'Sauce Labs Backpack')
        backpack.find_element(By.ID,'add-to-cart-sauce-labs-backpack').click()
        until(EC.text_to_be_present_in_element((By.CSS_SELECTOR,'.shopping_cart_badge'),'1'))
        until(EC.visibility_of_element_located((By.ID,'remove-sauce-labs-backpack')))
        until(EC.element_to_be_clickable((By.CSS_SELECTOR,'.shopping_cart_link'))).click()
        until(EC.visibility_of_element_located((By.CSS_SELECTOR,'.cart_item')))
        def correct_cart(d):
            items = d.find_elements(By.CSS_SELECTOR,'.cart_item')
            return len(items) == 1 and items[0].find_element(By.CSS_SELECTOR,'.inventory_item_name').text == 'Sauce Labs Backpack' and items[0].find_element(By.CSS_SELECTOR,'.cart_quantity').text == '1'
        assert until(correct_cart)
        result['cart_verified'] = True
        result['state'] = safe_state(driver)
        result['status'], result['phase'] = 'passed', 'finished'
    except Exception as error:
        result['error_type'] = type(error).__name__
        if isinstance(error, BlockedAccessError): result['status'] = 'blocked'
        if driver:
            try:
                result['state'] = safe_state(driver)
                # Login contains the public demo password in its footer. Never
                # screenshot it, unknown pages, challenges or entered form data.
                safe = result['state']['url'] in {URL+'inventory.html',URL+'cart.html'} and result['state']['title']=='Swag Labs'
                no_inputs = driver.execute_script('return document.querySelectorAll("input,textarea").length === 0;')
                if safe and no_inputs and not result['state']['challenge'] and not result['state']['captcha']:
                    driver.save_screenshot(str(folder/'failure.png'))
                    result['screenshot'] = 'failure.png'
                else: result['screenshot'] = 'omitted_for_data_protection'
            except Exception:
                result['screenshot'] = 'unavailable'
    finally:
        if driver:
            try:
                driver.quit()
                result['driver_closed'] = True
            except Exception:
                result['status'],result['error_type'] = 'failed','DriverCleanupError'
        result['total_seconds'] = round(time.monotonic()-started,3)
        (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def report_text(summary):
    lines = ['# SauceDemo isolated PoC', '',
             'Manual Chrome check: NOT CONFIRMED (record separately).',
             'Execution: local Windows process, project .venv; not a Jenkins agent identity run.',
             'Recommendation: CONDITIONALLY SUITABLE pending manual/agent checks.' if all(r['status']=='passed' for r in summary['runs']) else 'Recommendation: NOT SUITABLE on current evidence.',
             '', '| Trial | Mode | Status | Login seconds | Catalog seconds | Cart | Error |',
             '|---|---|---|---|---|---|---|']
    for r in summary['runs']:
        lines.append(f"| {r['trial']} | {r['mode']} | {r['status']} | {r.get('login_page_seconds')} | {r.get('catalog_seconds')} | {r.get('cart_verified')} | {r.get('error_type','')} |")
    lines.extend(['', 'Three repeated runs per mode are a small reproducibility check, not a long-term stability guarantee.',
                  'No cookies, tokens, password values, personal profiles, raw browser logs or HTML were saved.',
                  'No real checkout/order was submitted. Existing tests, Jenkins and Allure were not used or modified.'])
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['headed','headless','both'],
                        default='headless' if os.getenv('HEADLESS','').lower() in {'true','1','yes'} else 'both')
    parser.add_argument('--repeatability', action='store_true', help='After both primary probes pass, run three fresh sessions per selected mode.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--_worker', choices=['headed','headless'], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._worker:
        folder = args.output.resolve()
        if not folder.is_relative_to(ARTIFACTS.resolve()): parser.error('Output must be under project artifacts')
        return 0 if execute(args._worker,folder)['status']=='passed' else 1
    if os.name != 'nt': parser.error('This PoC uses existing Windows OwnedProcesses infrastructure')
    folder = (args.output or ARTIFACTS/('saucedemo-poc-'+uuid4().hex)).resolve()
    if not folder.is_relative_to(ARTIFACTS.resolve()): parser.error('Output must be under project artifacts')
    folder.mkdir(parents=True,exist_ok=False)
    modes = ['headed','headless'] if args.mode=='both' else [args.mode]
    summary = {'environment':{'python':sys.version.split()[0],**{p:importlib.metadata.version(p) for p in ['pytest','selenium','selene']}},
               'manual_chrome':'not_confirmed','jenkins_agent_identity':'not_tested', 'runs':[]}
    def run(mode,trial):
        target=folder/f'{trial}-{mode}';target.mkdir()
        with open(os.devnull,'wb') as sink, OwnedProcesses() as owned:
            process=owned.start([sys.executable,str(Path(__file__).resolve()),'--_worker',mode,'--output',str(target)],sink,os.environ.copy())
            try: process.wait(timeout=RUN_SECONDS)
            except subprocess.TimeoutExpired: pass  # job closes only this run's process tree
        if (target/'result.json').exists(): result=json.loads((target/'result.json').read_text(encoding='utf-8'))
        else: result={'mode':mode,'status':'failed','error_type':'WorkerTimeoutOrExit','cart_verified':False}
        result['trial']=trial;summary['runs'].append(result)
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        (folder/'report.md').write_text(report_text(summary),encoding='utf-8')
        print(json.dumps({'trial':trial,'mode':mode,'status':result['status'],'error_type':result.get('error_type')}) ,flush=True)
        return result['status']=='passed'
    primary_ok=True
    for mode in modes:
        if not run(mode,'primary'):
            primary_ok=False
            break
    if primary_ok and args.repeatability:
        for mode in modes:
            for index in range(1,4):
                if not run(mode,f'repeat-{index}'):
                    print('Stopped after failed independent run; no retries.',flush=True)
                    print('ARTIFACTS:',folder,flush=True)
                    return 1
    print('ARTIFACTS:',folder,flush=True)
    return 0 if primary_ok else 1


if __name__=='__main__': sys.exit(main())
