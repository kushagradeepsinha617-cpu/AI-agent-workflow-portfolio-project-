from contextlib import redirect_stdout
import io
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from operations_agent.__main__ import main
from operations_agent.observability import JsonlEventLog, stage_event
from operations_agent.orchestration import ReviewPlanStub, process_invoice


ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / 'samples/invoice.txt').read_text()


class CrashingModel(ReviewPlanStub):
    def call(self, messages, **kwargs):
        raise RuntimeError('synthetic-credential-marker')


class ObservabilityTests(unittest.TestCase):
    def test_ordered_stage_events_contain_counts_not_invoice_values(self):
        events = []
        result = process_invoice(TEXT, event_sink=events.append)
        self.assertEqual([(e['stage'], e['event']) for e in events], [
            ('pipeline', 'started'), ('extraction', 'started'), ('extraction', 'finished'),
            ('validation', 'started'), ('validation', 'finished'), ('review', 'started'),
            ('review', 'finished'), ('pipeline', 'finished')])
        self.assertEqual(len({e['run_id'] for e in events}), 1)
        self.assertTrue(all(e['human_decision'] == 'pending' for e in events))
        for forbidden in ('Demo Supplies', 'DEMO-002', '105.00', 'Synthetic office supplies', 'review_summary'):
            self.assertNotIn(forbidden, json.dumps(events))
        self.assertEqual(result['human_decision'], 'pending')

    def test_validation_errors_and_uncertainty_have_structured_counts(self):
        for document, stage, key in ((TEXT.replace('105.00', '110.00'), 'validation', 'error_count'),
                                    (TEXT.replace('2026-10-01', '03/04/2026'), 'extraction', 'uncertain_count')):
            with self.subTest(stage=stage):
                events = []
                process_invoice(document, event_sink=events.append)
                finished = next(e for e in events if e['stage'] == stage and e['event'] == 'finished')
                self.assertGreater(finished[key], 0)
                if stage == 'validation':
                    self.assertIn('inconsistent_total', finished['error_codes'])
                self.assertEqual(events[-1]['status'], 'needs_attention')

    def test_exception_and_environment_secrets_are_absent_from_logs(self):
        events = []
        with patch.dict('os.environ', {'INVOICE_AI_API_KEY': 'synthetic-credential-marker'}):
            result = process_invoice(TEXT, extractor=Mock(side_effect=RuntimeError('synthetic-credential-marker')),
                                     event_sink=events.append)
        self.assertIn('extraction_task_failed', result['workflow']['issues'])
        self.assertNotIn('synthetic-credential-marker', json.dumps(events))
        self.assertEqual(next(e for e in events if e['stage'] == 'extraction' and e['event'] == 'finished')['status'], 'failed')
        untrusted_event = stage_event('synthetic-run', 'validation', 'finished', 'invalid', 'mock',
                                     error_codes=['synthetic-credential-marker', 'missing:invoice_number'])
        self.assertEqual(untrusted_event['error_codes'], ['unrecognized_code', 'missing:invoice_number'])

    def test_framework_error_diagnostics_are_suppressed_and_logging_restored(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        root.addHandler(handler)
        before = root.manager.disable
        try:
            result = process_invoice(TEXT, review_llm=CrashingModel(model='synthetic-crashing-model'))
        finally:
            root.removeHandler(handler)
        self.assertEqual(root.manager.disable, before)
        self.assertIn('review_agent_task_failed', result['workflow']['issues'])
        self.assertNotIn('synthetic-credential-marker', stream.getvalue())

    def test_early_and_late_log_failures_remain_visible_for_review(self):
        for failure_index in (1, 8):
            events = []
            def failing_sink(event):
                events.append(event)
                if len(events) == failure_index:
                    raise OSError('synthetic private path detail')
            with self.subTest(failure_index=failure_index):
                result = process_invoice(TEXT, event_sink=failing_sink)
                self.assertEqual(result['human_decision'], 'pending')
                self.assertEqual(result['validation_status'], 'valid')
                self.assertIn('observability_failed', result['workflow']['issues'])
                self.assertIn('observability_failed', result['review_summary'])
                self.assertIn('workflow_needs_review', result['risk_indicators'])
                self.assertNotIn('private path detail', result['review_summary'])

    def test_jsonl_appends_distinct_runs_and_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'logs/events.jsonl'
            for _ in range(2):
                with JsonlEventLog(path) as sink:
                    process_invoice(TEXT, event_sink=sink)
            events = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(events), 16)
        self.assertEqual(len({event['run_id'] for event in events}), 2)

    def test_cli_separates_json_result_from_jsonl_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            output = io.StringIO()
            with patch('sys.argv', ['operations_agent', str(ROOT / 'samples/invoice.txt'),
                       '--format', 'text', '--orchestrate', '--log-json', str(path)]), redirect_stdout(output):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(output.getvalue())[0]['human_decision'], 'pending')
            self.assertEqual(len(path.read_text().splitlines()), 8)
