import json
from pathlib import Path
import subprocess
import sys
import unittest
from decimal import Decimal
from operations_agent.validation import Validator

ROOT = Path(__file__).resolve().parents[1]


def sample(**changes):
    raw = dict(vendor_name='Demo Supplies', invoice_number='INV-1', invoice_date='2026-10-01',
               due_date='2026-10-31', currency='USD', subtotal='0.10', tax='0.20',
               total='0.30', description='Synthetic supplies')
    raw.update(changes)
    return raw


class ValidationTests(unittest.TestCase):
    def check(self, **changes):
        return Validator({'Demo Supplies'}).validate(sample(**changes))

    def test_valid_and_pending(self):
        result = self.check()
        self.assertEqual(result.errors, [])
        self.assertEqual(result.invoice.total, Decimal('0.30'))
        self.assertEqual(result.human_decision, 'pending')
        self.assertEqual(result.processing_status, 'awaiting_review')

    def test_missing(self):
        result = self.check(invoice_number=None, due_date=None)
        self.assertIn('missing:invoice_number', result.errors)
        self.assertIn('missing:due_date', result.errors)
        self.assertIsNone(result.invoice.due_date)

    def test_dates(self):
        self.assertIn('invalid:invoice_date', self.check(invoice_date='2026-02-30').errors)
        self.assertIn('due_date_before_invoice_date', self.check(due_date='2026-09-01').errors)

    def test_total(self):
        self.assertIn('inconsistent_total', self.check(total='0.31').errors)

    def test_invalid_money(self):
        for value in ('NaN', 'Infinity', '-1', 'garbage', True, 0.1, '0.001', '1e100'):
            with self.subTest(value=value):
                result = self.check(total=value)
                self.assertIn('invalid:total', result.errors)
                self.assertIsNone(result.invoice.total)

    def test_duplicate_scope(self):
        validator = Validator({'Demo Supplies'})
        validator.validate(sample())
        self.assertIn('duplicate_invoice', validator.validate(sample(vendor_name=' demo supplies ', invoice_number='inv-1')).errors)
        self.assertNotIn('duplicate_invoice', validator.validate(sample(vendor_name='Other')).errors)

    def test_vendor_and_currency(self):
        self.assertIn('unknown_vendor', self.check(vendor_name='Other').risk_indicators)
        self.assertIn('unsupported:currency', self.check(currency='XYZ').errors)
        self.assertEqual(self.check(currency='usd').invoice.currency, 'USD')

    def test_bad_types(self):
        for name in ('vendor_name', 'invoice_number', 'description', 'currency', 'due_date'):
            with self.subTest(name=name):
                self.assertIn(f'invalid:{name}', self.check(**{name: []}).errors)

    def test_cli_sample(self):
        result = subprocess.run([sys.executable, '-m', 'operations_agent', 'samples/invoices.json', '--known-vendor', 'Demo Supplies'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual([r['validation_status'] for r in rows], ['valid', 'invalid', 'invalid'])
        self.assertTrue(all(r['human_decision'] == 'pending' for r in rows))

    def test_cli_missing_file(self):
        result = subprocess.run([sys.executable, '-m', 'operations_agent', 'does-not-exist.json'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Input error:', result.stderr)
