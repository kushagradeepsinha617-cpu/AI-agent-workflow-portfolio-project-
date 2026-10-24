"""Regression cases from the deterministic-baseline audit; all data is synthetic."""
from copy import deepcopy
from decimal import Inexact, localcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from operations_agent.validation import Validator


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('vendor_name', 'invoice_number', 'invoice_date', 'due_date',
            'currency', 'subtotal', 'tax', 'total', 'description')


def invoice(**changes):
    raw = dict(vendor_name='Demo Supplies', invoice_number='AUDIT-001',
               invoice_date='2026-10-01', due_date='2026-10-31', currency='USD',
               subtotal='100.01', tax='0.01', total='100.02',
               description='Synthetic audit supplies')
    raw.update(changes)
    return raw


class ValidatorAuditTests(unittest.TestCase):
    def check_invoice(self, **changes):
        result = Validator({'Demo Supplies'}).validate(invoice(**changes))
        self.assertEqual(result.human_decision, 'pending')
        self.assertEqual(result.processing_status, 'awaiting_review')
        return result

    def test_missing_null_and_empty_for_every_required_field(self):
        for field in REQUIRED:
            for kind in ('omitted', 'null', 'empty'):
                with self.subTest(field=field, kind=kind):
                    raw = invoice()
                    if kind == 'omitted':
                        del raw[field]
                    else:
                        raw[field] = None if kind == 'null' else ''
                    result = Validator().validate(raw)
                    self.assertIn(f'missing:{field}', result.errors)
                    self.assertIsNone(getattr(result.invoice, field))
                    self.assertEqual(result.human_decision, 'pending')

    def test_whitespace_is_invalid_instead_of_inventing_a_value(self):
        for field in REQUIRED:
            with self.subTest(field=field):
                result = self.check_invoice(**{field: ' \t\n '})
                self.assertIn(f'invalid:{field}', result.errors)
                self.assertIsNone(getattr(result.invoice, field))

    def test_unexpected_json_types_for_every_field(self):
        for field in REQUIRED:
            for value in (True, False, [], {}, [1], {'value': '100'}, 1.5):
                with self.subTest(field=field, value=value):
                    result = self.check_invoice(**{field: value})
                    self.assertIn(f'invalid:{field}', result.errors)
                    self.assertIsNone(getattr(result.invoice, field))
        for field in ('vendor_name', 'invoice_number', 'invoice_date', 'due_date',
                      'currency', 'description'):
            with self.subTest(field=field, value=123):
                self.assertIn(f'invalid:{field}', self.check_invoice(**{field: 123}).errors)

    def test_non_object_invoice_is_rejected(self):
        for raw in (None, [], 'invoice', True, 123):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, 'object'):
                    Validator().validate(raw)

    def test_money_boundaries_and_representational_precision(self):
        for subtotal, tax, total in (
            ('0.00', '0.00', '0.00'), (0, 1, 1),
            ('999999999999.99', '0.01', '1000000000000.00'),
            ('1000000000000', '0', '1000000000000'),
        ):
            with self.subTest(total=total, subtotal=subtotal):
                self.assertEqual(self.check_invoice(subtotal=subtotal, tax=tax, total=total).errors, [])
        for field in ('subtotal', 'tax', 'total'):
            for value in ('1000000000000.01', '-0.01', '1.001', '1.000',
                          'sNaN', '-Infinity', '1e99999999999999999999999999'):
                with self.subTest(field=field, value=value):
                    self.assertIn(f'invalid:{field}', self.check_invoice(**{field: value}).errors)

    def test_arithmetic_is_independent_of_ambient_decimal_context(self):
        for trap in (False, True):
            with self.subTest(inexact_trap=trap), localcontext() as context:
                context.prec = 3
                context.traps[Inexact] = trap
                self.assertEqual(self.check_invoice().errors, [])
                self.assertIn('inconsistent_total', self.check_invoice(total='100.03').errors)
                self.assertEqual(context.prec, 3)
                self.assertFalse(context.flags[Inexact])

    def test_date_format_and_calendar_boundaries(self):
        self.assertEqual(self.check_invoice(invoice_date='2024-02-29', due_date='2024-02-29').errors, [])
        for value in ('2025-02-29', '20261001', '2026-W40-4', '2026-10-01T00:00:00', '10/01/2026'):
            with self.subTest(value=value):
                self.assertIn('invalid:invoice_date', self.check_invoice(invoice_date=value).errors)

    def test_duplicates_remember_invalid_invoices_but_not_missing_identifiers(self):
        validator = Validator({'Demo Supplies'})
        first = validator.validate(invoice(total='99.00'))
        self.assertIn('inconsistent_total', first.errors)
        self.assertIn('duplicate_invoice', validator.validate(invoice()).errors)
        for identifier in (None, '', '   ', []):
            with self.subTest(identifier=identifier):
                validator = Validator()
                validator.validate(invoice(invoice_number=identifier))
                self.assertNotIn('duplicate_invoice', validator.validate(invoice()).errors)
        validator = Validator()
        validator.validate(invoice(vendor_name=None))
        self.assertNotIn('duplicate_invoice', validator.validate(invoice()).errors)

    def test_duplicate_identity_and_instance_boundaries(self):
        validator = Validator({'Demo Supplies'})
        validator.validate(invoice())
        result = validator.validate(invoice(vendor_name=' DEMO SUPPLIES ', invoice_number=' audit-001 '))
        self.assertIn('duplicate_invoice', result.errors)
        self.assertEqual(result.human_decision, 'pending')
        self.assertNotIn('duplicate_invoice', validator.validate(invoice(invoice_number='AUDIT-002')).errors)
        self.assertNotIn('duplicate_invoice', validator.validate(invoice(vendor_name='Other Synthetic Vendor')).errors)
        self.assertNotIn('duplicate_invoice', Validator().validate(invoice()).errors)

    def test_input_is_unchanged_and_cannot_supply_approval_state(self):
        raw = invoice(human_decision='approved', processing_status='approved', record_id='supplied')
        original = deepcopy(raw)
        result = Validator({'Demo Supplies'}).validate(raw)
        self.assertEqual(raw, original)
        self.assertEqual(result.human_decision, 'pending')
        self.assertEqual(result.processing_status, 'awaiting_review')
        self.assertNotEqual(result.invoice.record_id, 'supplied')


class JsonInputAuditTests(unittest.TestCase):
    def run_input(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            path.write_text(text, encoding='utf-8')
            return subprocess.run([sys.executable, '-m', 'operations_agent', str(path),
                                   '--known-vendor', 'Demo Supplies'], cwd=ROOT,
                                  capture_output=True, text=True)

    def assert_input_error(self, text):
        result = self.run_input(text)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertIn('Input error:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_malformed_json_and_wrong_batch_shapes(self):
        for text in ('', '[{', '{"total":}', '{}', 'null', '"invoice"', '[null]', '[1]', '[[], {}]'):
            with self.subTest(text=text):
                self.assert_input_error(text)

    def test_duplicate_json_fields_are_not_silently_overwritten(self):
        for first, second in (('105.00', '0.00'), ('105.00', '105.00')):
            with self.subTest(first=first, second=second):
                self.assert_input_error('[{"total":"' + first + '","total":"' + second + '"}]')
        self.assert_input_error('[{"vendor_name":"A","vendor_\\u006eame":"B"}]')

    def test_nonstandard_json_constants_are_rejected(self):
        for constant in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(constant=constant):
                self.assert_input_error('[{"total":' + constant + '}]')

    def test_excessive_json_nesting_has_controlled_error(self):
        self.assert_input_error('[' * 20000 + '0' + ']' * 20000)

    def test_valid_batch_empty_batch_and_float_policy(self):
        result = self.run_input(json.dumps([invoice()]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]['human_decision'], 'pending')
        empty = self.run_input('[]')
        self.assertEqual(empty.returncode, 0, empty.stderr)
        self.assertEqual(json.loads(empty.stdout), [])
        floating = self.run_input(json.dumps([invoice(total=100.02)]))
        self.assertEqual(floating.returncode, 1, floating.stderr)
        self.assertIn('invalid:total', json.loads(floating.stdout)[0]['errors'])
