"""Serial, loopback-only synthetic invoice viewer. No approval or paid-model route."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path

from .__main__ import encode
from .extraction import FIELDS
from .json_input import load_json


ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / 'web'
MAX_BODY_BYTES = 256_000
ROUTES = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}
EXAMPLE_NAMES = {'valid_labelled': 'Valid invoice', 'ambiguous_date': 'Ambiguous date',
                 'conflicting_total': 'Conflicting email', 'incorrect_total': 'Incorrect total',
                 'unreadable': 'Unreadable text'}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def example_documents():
    dataset = load_json((ROOT / 'evaluation/dataset.json').read_text(encoding='utf-8'))
    return [{'id': case['id'], 'title': EXAMPLE_NAMES[case['id']],
             'document': case['document'], 'email': case['email'] or ''}
            for case in dataset['cases'] if case['id'] in EXAMPLE_NAMES]


def checked_request(payload):
    """Check the transport contract only; invoice business rules stay elsewhere."""
    if not isinstance(payload, dict) or set(payload) - {'document', 'email', 'known_vendors'}:
        raise ValueError('Expected document, optional email and known_vendors only.')
    document, email = payload.get('document'), payload.get('email', '')
    vendors = payload.get('known_vendors', [])
    if not isinstance(document, str) or not document.strip():
        raise ValueError('Enter nonempty synthetic invoice text.')
    if not isinstance(email, str):
        raise ValueError('Email context must be text.')
    if (not isinstance(vendors, list) or len(vendors) > 100
            or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in vendors)):
        raise ValueError('Known vendors must be a list of up to 100 nonempty names, each at most 200 characters.')
    return document, email, [v.strip() for v in vendors]


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = 'InvoiceWorkbench'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        pass  # Do not log request paths, invoice content, or arbitrary exceptions.

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        if isinstance(body, dict):
            body = json.dumps(body, default=encode, allow_nan=False).encode('utf-8')
        self.send_response(status)
        for name, value in {'Content-Type': content_type, 'Content-Length': str(len(body)),
                            'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff',
                            'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store',
                            'Connection': 'close'}.items():
            self.send_header(name, value)
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def error(self, status, code, message):
        self.reply(status, {'error': code, 'message': message, 'human_decision': 'pending'})

    def allowed_request(self, require_origin=False):
        port = self.server.server_address[1]
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host_headers = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        if len(host_headers) != 1 or host_headers[0].lower() not in hosts:
            self.error(403, 'host_not_allowed', 'Use the local workbench host and port.')
            return False
        if (require_origin and not origins or len(origins) > 1
                or origins and origins[0] not in {'http://' + host for host in hosts}):
            self.error(403, 'origin_not_allowed', 'Requests must come from the local workbench.')
            return False
        return True

    def do_GET(self):
        if not self.allowed_request():
            return
        if self.path == '/api/examples':
            self.reply(200, {'examples': self.server.examples, 'human_decision': 'pending'})
        elif self.path in ROUTES:
            name, content_type = ROUTES[self.path]
            self.reply(200, (ASSETS / name).read_bytes(), content_type)
        else:
            self.error(404, 'route_not_found', 'This workbench route does not exist.')

    def do_POST(self):
        if not self.allowed_request(require_origin=True):
            return
        if self.path != '/api/process':
            self.error(404, 'route_not_found', 'This workbench route does not exist.')
            return
        if self.headers.get('Transfer-Encoding'):
            self.error(400, 'unsupported_transfer_encoding', 'Chunked requests are not supported.')
            return
        lengths = self.headers.get_all('Content-Length', [])
        if not lengths:
            self.error(411, 'length_required', 'Content-Length is required.')
            return
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            self.error(400, 'invalid_length', 'Content-Length must be a nonnegative integer.')
            return
        if len(lengths[0]) > 9:
            self.error(413, 'request_too_large', 'The request exceeds the 256,000-byte limit.')
            return
        size = int(lengths[0])
        if size > MAX_BODY_BYTES:
            self.error(413, 'request_too_large', 'The request exceeds the 256,000-byte limit.')
            return
        if self.headers.get_content_type() != 'application/json':
            self.error(415, 'json_required', 'Send UTF-8 JSON.')
            return
        try:
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError('Incomplete request body.')
            document, email, vendors = checked_request(load_json(body.decode('utf-8')))
        except (ValueError, RecursionError):
            self.error(400, 'invalid_request', 'Check the JSON fields and use nonempty synthetic text.')
            return
        except OSError:
            self.error(408, 'request_timeout', 'The request body could not be read in time.')
            return
        try:
            output = self.server.processor(document, email, mode='mock', known_vendors=vendors)
            if (not isinstance(output, dict) or output.get('human_decision') != 'pending'
                    or output.get('processing_status') != 'awaiting_review'
                    or output.get('validation_status') not in ('valid', 'invalid', 'unavailable')
                    or not isinstance(output.get('extraction'), dict)
                    or set(output['extraction'].get('fields', {})) != set(FIELDS)):
                raise ValueError('Malformed pipeline output')
            self.reply(200, output)
        except Exception:
            self.error(500, 'processing_failed', 'Processing failed. No approval or financial action occurred.')

    def do_OPTIONS(self):
        self.error(405, 'method_not_allowed', 'Only local GET and POST requests are supported.')


def make_server(port=8765, processor=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('Port must be between 0 and 65535.')
    if processor is None:
        from .orchestration import process_invoice
        processor = process_invoice
    examples = example_documents()
    server = HTTPServer(('127.0.0.1', port), WorkbenchHandler)
    server.processor = processor
    server.examples = examples
    return server


def main():
    parser = argparse.ArgumentParser(description='Mock-only pending-review workbench for synthetic invoices.')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        with make_server(args.port) as server:
            print(f'Pending-review workbench listening on local port {server.server_address[1]}.', flush=True)
            print('Mock mode only. Records are not saved. Stop with Ctrl+C.', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except ImportError:
        parser.exit(2, 'Workbench dependencies are missing; install requirements.lock in .venv.\n')
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Workbench startup failed: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
