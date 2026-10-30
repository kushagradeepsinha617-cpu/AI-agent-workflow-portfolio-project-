"""HTTP contracts using loopback sockets and the real mock pipeline, no paid calls."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import Mock, patch

from operations_agent.workbench import MAX_BODY_BYTES, checked_request, make_server


ROOT = Path(__file__).resolve().parents[1]


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_address[1]
        cls.thread = Thread(target=cls.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def request(self, method, path, body=None, headers=None):
        request_headers = {'Origin': f'http://127.0.0.1:{self.port}', 'Content-Type': 'application/json'}
        if headers:
            request_headers.update(headers)
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def process(self, document, email='', **changes):
        payload = {'document': document, 'email': email, 'known_vendors': ['Demo Supplies']}
        payload.update(changes)
        status, headers, body = self.request('POST', '/api/process', json.dumps(payload))
        result = json.loads(body)
        self.assertEqual(result['human_decision'], 'pending')
        return status, headers, result

    def test_static_assets_and_security_headers(self):
        for path, content_type in (('/', 'text/html'), ('/app.js', 'text/javascript'), ('/style.css', 'text/css')):
            with self.subTest(path=path):
                status, headers, body = self.request('GET', path)
                self.assertEqual(status, 200)
                self.assertTrue(headers['Content-Type'].startswith(content_type))
                self.assertGreater(len(body), 0)
                self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
                self.assertNotIn('unsafe-inline', headers['Content-Security-Policy'])
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_examples_are_sources_not_ground_truth(self):
        status, _, body = self.request('GET', '/api/examples')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['human_decision'], 'pending')
        self.assertEqual(len(data['examples']), 5)
        for example in data['examples']:
            self.assertEqual(set(example), {'id', 'title', 'document', 'email'})
            self.assertIsInstance(example['document'], str)
            self.assertIsInstance(example['email'], str)

    def test_valid_real_pipeline_cannot_make_an_ai_call(self):
        with patch.dict('os.environ', {'INVOICE_AI_API_KEY': 'synthetic-key', 'INVOICE_AI_MODEL': 'synthetic-model'}):
            with patch('operations_agent.ai_extraction.request_openai') as provider:
                status, _, result = self.process((ROOT / 'samples/invoice.txt').read_text())
                provider.assert_not_called()
        self.assertEqual(status, 200)
        self.assertEqual(result['validation_status'], 'valid')
        self.assertEqual(result['processing_status'], 'awaiting_review')
        self.assertEqual(result['extraction']['mode'], 'mock')
        self.assertEqual(result['workflow']['issues'], [])
        self.assertEqual(result['workflow']['completed_steps'], ['extraction', 'validation', 'review'])
        self.assertIn('Source for total', result['review_summary'])

    def test_ambiguous_and_incorrect_totals_survive_http_handoff(self):
        for name, missing, error in (('ambiguous', 'invoice_date', 'missing:invoice_date'),
                                      ('incorrect_total', None, 'inconsistent_total')):
            with self.subTest(name=name):
                text = (ROOT / f'tests/fixtures/milestone2/{name}.txt').read_text()
                status, _, result = self.process(text)
                self.assertEqual(status, 200)  # Business issues are successful processing, not HTTP errors.
                self.assertEqual(result['validation_status'], 'invalid')
                self.assertIn(error, result['errors'])
                self.assertIn(error, result['review_summary'])
                if missing:
                    self.assertIsNone(result['extraction']['fields'][missing])
                    self.assertIn(missing, result['extraction']['uncertain_fields'])
                else:
                    self.assertEqual(result['extraction']['fields']['total'], '110.00')

    def test_conflict_keeps_both_source_tokens(self):
        status, _, result = self.process((ROOT / 'samples/invoice.txt').read_text(), 'Total: 115.00')
        self.assertEqual(status, 200)
        self.assertIsNone(result['extraction']['fields']['total'])
        self.assertEqual([item['value'] for item in result['extraction']['conflicts']['total']], ['105.00', '115.00'])
        self.assertIn('extraction_needs_review', result['risk_indicators'])

    def test_unknown_vendor_is_a_review_flag(self):
        status, _, result = self.process((ROOT / 'samples/invoice.txt').read_text(), known_vendors=[])
        self.assertEqual(status, 200)
        self.assertEqual(result['validation_status'], 'valid')
        self.assertIn('unknown_vendor', result['risk_indicators'])

    def test_untrusted_markup_is_only_returned_as_record_data(self):
        token = '<script>window.syntheticInjection = true</script>'
        text = (ROOT / 'samples/invoice.txt').read_text().replace('Synthetic office supplies', token)
        status, headers, result = self.process(text)
        self.assertEqual(status, 200)
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        self.assertEqual(result['extraction']['fields']['description'], token)
        _, _, page = self.request('GET', '/')
        self.assertNotIn(token.encode(), page)
        # This verifies transport separation, not actual browser script execution.

    def test_malformed_json_types_and_schema_are_rejected_without_processing(self):
        with patch.object(self.server, 'processor') as processor:
            for raw in (b'{bad', b'null', b'[]', b'\xff', b'{"document":"A","document":"B"}',
                        b'{"document":NaN}', b'[' * 20000 + b'0' + b']' * 20000):
                with self.subTest(raw_prefix=raw[:20]):
                    status, _, body = self.request('POST', '/api/process', raw)
                    self.assertEqual(status, 400)
                    self.assertEqual(json.loads(body)['human_decision'], 'pending')
            for payload in ({}, {'document': '  '}, {'document': []}, {'document': 'A', 'email': None},
                            {'document': 'A', 'known_vendors': 'vendor'}, {'document': 'A', 'known_vendors': ['']},
                            {'document': 'A', 'known_vendors': ['x'] * 101},
                            {'document': 'A', 'known_vendors': ['x' * 201]}):
                with self.subTest(payload=payload):
                    status, _, _ = self.request('POST', '/api/process', json.dumps(payload))
                    self.assertEqual(status, 400)
            processor.assert_not_called()

    def test_mode_and_decision_cannot_be_supplied(self):
        with patch.object(self.server, 'processor') as processor:
            for field, value in (('mode', 'ai'), ('human_decision', 'approved'),
                                  ('processing_status', 'approved'), ('file_path', '/etc/passwd')):
                with self.subTest(field=field):
                    status, _, _ = self.process('Synthetic text', **{field: value})
                    self.assertEqual(status, 400)
            processor.assert_not_called()

    def test_foreign_hosts_and_origins_are_rejected(self):
        with patch.object(self.server, 'processor') as processor:
            for headers in ({'Host': 'foreign.example'}, {'Origin': 'https://foreign.example'},
                            {'Origin': 'null'}, {'Host': f'foreign.example:{self.port}'}):
                with self.subTest(headers=headers):
                    status, _, _ = self.request('POST', '/api/process', '{"document":"Synthetic"}', headers)
                    self.assertEqual(status, 403)
            processor.assert_not_called()

    def test_missing_duplicate_host_or_origin_headers_are_rejected(self):
        for host_count, origins in ((0, []), (2, []), (1, []), (1, ['http://localhost:1', 'http://localhost:2'])):
            with self.subTest(host_count=host_count, origins=origins):
                connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
                connection.putrequest('POST', '/api/process', skip_host=True)
                for _ in range(host_count):
                    connection.putheader('Host', f'127.0.0.1:{self.port}')
                for origin in origins:
                    connection.putheader('Origin', origin)
                connection.putheader('Content-Length', '0')
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
                connection.close()

    def test_request_size_media_type_and_transfer_limits(self):
        for body, headers, expected in (
            (b'x' * (MAX_BODY_BYTES + 1), {}, 413),
            (b'', {'Content-Length': '9' * 5000}, 413),
            (b'', {'Content-Length': '-1'}, 400),
            (b'', {'Content-Length': 'not-a-number'}, 400),
            (b'{}', {'Content-Type': 'text/plain'}, 415),
            (b'', {'Transfer-Encoding': 'chunked'}, 400),
        ):
            with self.subTest(expected=expected, headers=list(headers)):
                status, _, _ = self.request('POST', '/api/process', body, headers)
                self.assertEqual(status, expected)

    def test_missing_content_length_has_controlled_response(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        connection.putrequest('POST', '/api/process')
        connection.putheader('Origin', f'http://127.0.0.1:{self.port}')
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 411)
        response.read()
        connection.close()

    def test_route_allowlist_has_no_filesystem_or_approval_routes(self):
        for path in ('/../README.md', '/.env', '/operations_agent/validation.py', '/api/process'):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 404)
        for path in ('/api/approve', '/api/reject', '/api/pay'):
            with self.subTest(path=path):
                status, _, body = self.request('POST', path, '{}')
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(body)['human_decision'], 'pending')
        self.assertEqual(self.request('OPTIONS', '/api/process')[0], 405)

    def test_pipeline_errors_and_nonpending_output_fail_closed(self):
        secret = 'synthetic-private-diagnostic'
        with patch.object(self.server, 'processor', side_effect=RuntimeError(secret)):
            status, _, result = self.process('Synthetic invoice')
            self.assertEqual(status, 500)
            self.assertNotIn(secret, json.dumps(result))
        for reply in (None, {}, {'human_decision': 'approved'}, {'human_decision': 'pending'}):
            with self.subTest(reply=reply), patch.object(self.server, 'processor', return_value=reply):
                status, _, result = self.process('Synthetic invoice')
                self.assertEqual(status, 500)
                self.assertEqual(result['human_decision'], 'pending')

    def test_server_is_serial_and_bound_only_to_loopback(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        self.assertNotIn('ThreadingMixIn', [base.__name__ for base in type(self.server).__mro__])
        for bad_port in (-1, 65536, True, '8765'):
            with self.subTest(bad_port=bad_port), self.assertRaises(ValueError):
                make_server(bad_port)

    def test_incomplete_pipeline_metadata_is_not_a_success_response(self):
        _, _, valid = self.process((ROOT / 'samples/invoice.txt').read_text())
        for section, key, value in (('extraction', 'evidence', None),
                                    ('extraction', 'uncertain_fields', []),
                                    ('workflow', 'issues', None),
                                    (None, 'review_summary', {}),
                                    (None, 'errors', 'not a list')):
            reply = deepcopy(valid)
            target = reply[section] if section else reply
            target[key] = value
            with self.subTest(section=section, key=key), patch.object(self.server, 'processor', return_value=reply):
                status, _, result = self.process('Synthetic invoice')
                self.assertEqual(status, 500)
                self.assertEqual(result['human_decision'], 'pending')

    def test_request_validation_preserves_input_and_zero_source_values(self):
        raw = {'document': 'Total: 0.00', 'email': '', 'known_vendors': [' Demo Supplies ']}
        before = deepcopy(raw)
        document, email, vendors = checked_request(raw)
        self.assertEqual(raw, before)
        self.assertEqual(document, 'Total: 0.00')
        self.assertEqual(vendors, ['Demo Supplies'])
        self.assertEqual(email, '')
