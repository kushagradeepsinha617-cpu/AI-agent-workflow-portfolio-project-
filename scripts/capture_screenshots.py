"""Optional local screenshot runner. Requires a running mock workbench and Playwright.

Run on the same machine as the workbench; uses an isolated browser context.
No API calls, user browser profiles, or application decisions are involved.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def workbench(url, start_server):
    """Reuse the user's server, or start and stop only our own child process."""
    child = None
    try:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status != 200:
                    raise RuntimeError('The local server did not return the workbench.')
        except URLError:
            if not start_server:
                raise RuntimeError('Workbench is not running. Retry with --start-server.') from None
            python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            if not python.exists():
                raise RuntimeError('Install the project dependencies in .venv first.')
            port = urlsplit(url).port or 80
            child = subprocess.Popen([str(python), '-m', 'operations_agent.workbench', '--port', str(port)],
                                     cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 60
            while True:
                if child.poll() is not None:
                    raise RuntimeError('Workbench startup failed. Run its command directly to see the error.')
                try:
                    with urlopen(url, timeout=2):
                        break
                except URLError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Workbench did not become ready within 60 seconds.') from None
                    time.sleep(.25)
        yield
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description='Capture ten real mock-workbench screenshots locally.')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--record', action='store_true', help='Also record a paced, silent WebM walkthrough')
    parser.add_argument('--start-server', action='store_true', help='Start the workbench if it is not running')
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        parser.error('Use the root URL of your local loopback workbench.')

    from playwright.sync_api import expect, sync_playwright

    output = (ROOT / 'local-data/screenshots'
              / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    cases = [('valid_labelled', 'valid'), ('incorrect_total', 'invalid'),
             ('ambiguous_date', 'invalid'), ('conflicting_total', 'invalid'),
             ('unreadable', 'invalid')]
    captures = []
    with workbench(args.url, args.start_server), sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        context = None
        try:
            output.mkdir(parents=True, exist_ok=False)
            recording = {'record_video_dir': str(output),
                         'record_video_size': {'width': 1440, 'height': 1000}} if args.record else {}
            context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                          device_scale_factor=1, reduced_motion='reduce', **recording)
            page = context.new_page()
            page.set_default_timeout(30000)
            page.goto(args.url, wait_until='networkidle')
            expect(page.locator('#example option')).to_have_count(6)
            for index, (case, validation) in enumerate(cases):
                page.locator('.review-title').scroll_into_view_if_needed()
                page.locator('#example').select_option(case)
                expect(page.locator('#placeholder')).to_be_visible()
                name = f'{index * 2 + 1:02d}-{case}-source.png'
                page.screenshot(path=str(output / name), full_page=True)
                captures.append(name)
                if args.record:
                    page.wait_for_timeout(2000)  # Reading time in the video, not a readiness check.

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
                if case == 'incorrect_total' and 'inconsistent_total' not in result['errors']:
                    raise RuntimeError('Incorrect-total example did not expose the expected error.')
                if case == 'ambiguous_date' and result['extraction']['fields']['invoice_date'] is not None:
                    raise RuntimeError('Ambiguous date was unexpectedly resolved.')
                if args.record:
                    page.locator('.review-title').scroll_into_view_if_needed()
                    page.wait_for_timeout(2500)
                    page.locator('#issues-heading').scroll_into_view_if_needed()
                    page.wait_for_timeout(3000)
                for summary in page.locator('#result details > summary').all():
                    if summary.locator('..').get_attribute('open') is None:
                        summary.click()
                if args.record:
                    page.locator('#evidence').scroll_into_view_if_needed()
                    page.wait_for_timeout(2000)
                    page.locator('.review-title').scroll_into_view_if_needed()
                    page.wait_for_timeout(1500)
                name = f'{index * 2 + 2:02d}-{case}-result.png'
                page.screenshot(path=str(output / name), full_page=True)
                captures.append(name)
                print(f'{case}: source and result captured; decision pending')
        finally:
            if context is not None:
                context.close()  # Flush the video even if a later assertion fails.
            browser.close()
        if args.record:
            # Only label a video as complete after every assertion and screenshot succeeds.
            page.video.save_as(str(output / 'workflow.webm'))
            original = Path(page.video.path())
            if original != output / 'workflow.webm':
                original.unlink()
    (output / 'README.txt').write_text(
        'Actual browser captures of the synthetic mock workbench. No live model used.\n'
        + '\n'.join(captures) + '\n', encoding='utf-8')
    print(f'Saved {len(captures)} screenshots to {output}')
    if args.record:
        print(f'Video: {output / "workflow.webm"} (silent; synthetic mock mode, not live AI)')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
