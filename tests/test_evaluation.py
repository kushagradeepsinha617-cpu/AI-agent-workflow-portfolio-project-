from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from operations_agent.evaluation import DEFAULT_DATASET, evaluate, load_dataset, main, ratio, score_case
from operations_agent.orchestration import process_invoice


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset, cls.fingerprint = load_dataset(DEFAULT_DATASET)
        cls.cases = {case['id']: case for case in cls.dataset['cases']}
        cls.outputs = {name: process_invoice(cls.cases[name]['document'],
                      cls.cases[name]['email'], known_vendors={'Demo Supplies'})
                       for name in ('valid_labelled', 'missing_invoice_number', 'unsupported_prose')}

    def test_measured_dataset_and_saved_report_match(self):
        with patch('socket.socket.connect', side_effect=AssertionError('network')) as net:
            measured = evaluate(self.dataset, self.fingerprint)
            net.assert_not_called()
        saved = json.loads((DEFAULT_DATASET.parent / 'mock_report.json').read_text())
        self.assertEqual(measured, saved)
        self.assertEqual(measured['case_count'], 17)
        self.assertEqual(measured['execution_failures'], 0)
        self.assertEqual(measured['known_field_accuracy']['correct'], 131)
        self.assertEqual(measured['known_field_accuracy']['total'], 140)
        self.assertEqual(measured['per_field_accuracy']['invoice_number']['correct'], 14)
        self.assertEqual(measured['per_field_accuracy']['invoice_number']['total'], 15)
        self.assertEqual(sum(counts['total'] for counts in measured['per_field_accuracy'].values()), 140)
        self.assertEqual(measured['quality_passed_cases'], 16)
        self.assertEqual(measured['integrity_passed_cases'], 17)
        self.assertFalse(measured['system_under_test']['live_model_evaluation'])
        rows = {row['id']: row for row in measured['cases']}
        self.assertEqual(rows['duplicate_first']['observed']['validation_errors'], [])
        self.assertIn('duplicate_invoice', rows['duplicate_repeat']['observed']['validation_errors'])

    def test_unresolved_nulls_do_not_inflate_known_field_accuracy(self):
        row = score_case(self.cases['missing_invoice_number'], self.outputs['missing_invoice_number'])
        self.assertEqual(row['known_field_count'], 8)
        self.assertEqual(row['correct_field_count'], 8)
        self.assertEqual(row['unresolved_detection']['true_positive'], 1)
        self.assertTrue(row['quality_passed'])

    def test_known_limitation_is_counted_as_failure_not_skipped(self):
        row = score_case(self.cases['unsupported_prose'], self.outputs['unsupported_prose'])
        self.assertTrue(row['known_limitation'])
        self.assertFalse(row['quality_passed'])
        self.assertTrue(row['integrity_passed'])
        self.assertEqual(row['known_field_count'], 9)
        self.assertEqual(row['correct_field_count'], 0)
        self.assertEqual(row['unresolved_detection']['false_positive'], 9)

    def test_silent_field_error_fails_integrity(self):
        output = deepcopy(self.outputs['valid_labelled'])
        output['extraction']['fields']['invoice_number'] = 'WRONG-BUT-WELL-FORMED'
        row = score_case(self.cases['valid_labelled'], output)
        self.assertFalse(row['quality_passed'])
        self.assertFalse(row['integrity']['extraction_mistakes_trigger_attention'])

    def test_filled_uncertainty_and_missing_flags_are_detected(self):
        for change in ('guess', 'drop_flag'):
            with self.subTest(change=change):
                output = deepcopy(self.outputs['missing_invoice_number'])
                if change == 'guess':
                    output['extraction']['fields']['invoice_number'] = 'GUESSED'
                else:
                    output['extraction']['missing_fields'] = []
                row = score_case(self.cases['missing_invoice_number'], output)
                self.assertFalse(row['quality_passed'])
                self.assertFalse(row['integrity_passed'])
                if change == 'drop_flag':
                    self.assertEqual(row['unresolved_detection']['false_negative'], 1)

    def test_hidden_errors_and_changed_decision_fail_integrity(self):
        output = deepcopy(self.outputs['missing_invoice_number'])
        output['review_summary'] = 'Everything looks fine.'
        output['human_decision'] = 'approved'
        row = score_case(self.cases['missing_invoice_number'], output)
        self.assertFalse(row['integrity']['human_decision_pending'])
        self.assertFalse(row['integrity']['validation_errors_visible_in_summary'])
        self.assertFalse(row['integrity']['unresolved_visible_in_summary'])

    def test_runner_exceptions_remain_in_denominators_and_are_sanitized(self):
        processor = Mock(side_effect=RuntimeError('synthetic-secret-marker'))
        report = evaluate(self.dataset, self.fingerprint, processor=processor)
        self.assertEqual(report['execution_failures'], 17)
        self.assertEqual(report['known_field_accuracy']['total'], 140)
        self.assertEqual(report['known_field_accuracy']['correct'], 0)
        self.assertTrue(all(counts['correct'] == 0 for counts in report['per_field_accuracy'].values()))
        self.assertEqual(report['integrity_passed_cases'], 0)
        self.assertEqual(report['unresolved_detection']['false_negative'], 13)
        self.assertNotIn('synthetic-secret-marker', json.dumps(report))

    def test_malformed_pipeline_outputs_cannot_pass(self):
        for output in (None, {}, {'extraction': {}}):
            with self.subTest(output=output):
                report = evaluate(self.dataset, self.fingerprint, processor=Mock(return_value=output))
                self.assertEqual(report['execution_failures'], 17)
                self.assertEqual(report['quality_passed_cases'], 0)

    def test_undefined_rates_are_null(self):
        self.assertIsNone(ratio(0, 0))
        self.assertEqual(ratio(0, 3), 0)

    def test_dataset_fingerprint_changes_with_source_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dataset.json'
            path.write_text(DEFAULT_DATASET.read_text() + '\n')
            _, fingerprint = load_dataset(path)
            self.assertNotEqual(fingerprint, self.fingerprint)

    def test_incomplete_duplicate_or_empty_annotations_are_rejected(self):
        mutations = [lambda d: d.update(cases=[]),
                     lambda d: d['cases'].append(deepcopy(d['cases'][0])),
                     lambda d: d['cases'][0]['expected']['fields'].pop('total'),
                     lambda d: d['cases'][0]['expected']['fields'].update(total=None)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dataset.json'
            for index, mutate in enumerate(mutations):
                with self.subTest(index=index):
                    data = deepcopy(self.dataset)
                    mutate(data)
                    path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        load_dataset(path)

    def test_cli_nonzero_for_quality_failures_and_no_dataset_overwrite(self):
        report = {'case_count': 17, 'quality_passed_cases': 16, 'integrity_passed_cases': 17}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            with patch('sys.argv', ['evaluation', '--output', str(path)]), \
                    patch('operations_agent.evaluation.evaluate', return_value=report):
                self.assertEqual(main(), 1)
            self.assertEqual(json.loads(path.read_text()), report)
        before = DEFAULT_DATASET.read_bytes()
        with patch('sys.argv', ['evaluation', '--output', str(DEFAULT_DATASET)]), \
                patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit) as raised:
            main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(DEFAULT_DATASET.read_bytes(), before)
