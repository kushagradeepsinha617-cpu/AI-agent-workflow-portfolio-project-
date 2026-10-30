"""Optional local screenshot runner. Requires a running mock workbench and Playwright.

Run on the same machine as the workbench; uses an isolated browser context.
No API calls, user browser profiles, or application decisions are involved.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description='Capture ten real mock-workbench screenshots locally.')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        parser.error('Use the root URL of your local loopback workbench.')

    from playwright.sync_api import expect, sync_playwright

    output = (Path(__file__).resolve().parents[1] / 'local-data/screenshots'
              / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    cases = [('valid_labelled', 'valid'), ('ambiguous_date', 'invalid'),
             ('conflicting_total', 'invalid'), ('incorrect_total', 'invalid'),
             ('unreadable', 'invalid')]
    captures = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                          device_scale_factor=1, reduced_motion='reduce')
            page = context.new_page()
            page.set_default_timeout(30000)
            page.goto(args.url, wait_until='networkidle')
            expect(page.locator('#example option')).to_have_count(6)
            output.mkdir(parents=True, exist_ok=False)
            for index, (case, validation) in enumerate(cases):
                page.locator('#example').select_option(case)
                expect(page.locator('#placeholder')).to_be_visible()
                name = f'{index * 2 + 1:02d}-{case}-source.png'
                page.screenshot(path=str(output / name), full_page=True)
                captures.append(name)

                with page.expect_response(lambda response: response.url.endswith('/api/process')
                                          and response.request.method == 'POST') as pending:
                    page.locator('#process').click()
                response = pending.value
                if response.status != 200:
                    raise RuntimeError(f'{case}: processing returned HTTP {response.status}')
                result = response.json()
                if (result.get('human_decision') != 'pending'
                        or result.get('processing_status') != 'awaiting_review'
                        or result.get('validation_status') != validation
                        or result.get('workflow', {}).get('issues') != []):
                    raise RuntimeError(f'{case}: unexpected workflow result; screenshot run stopped')
                expect(page.locator('#result')).to_be_visible()
                expect(page.locator('#fields tr')).to_have_count(9)
                expect(page.locator('#validation-status')).to_have_text(validation)
                for summary in page.locator('#result details > summary').all():
                    if summary.locator('..').get_attribute('open') is None:
                        summary.click()
                name = f'{index * 2 + 2:02d}-{case}-result.png'
                page.screenshot(path=str(output / name), full_page=True)
                captures.append(name)
                print(f'{case}: source and result captured; decision pending')
        finally:
            browser.close()
    (output / 'README.txt').write_text(
        'Actual browser captures of the synthetic mock workbench. No live model used.\n'
        + '\n'.join(captures) + '\n', encoding='utf-8')
    print(f'Saved {len(captures)} screenshots to {output}')


if __name__ == '__main__':
    main()
