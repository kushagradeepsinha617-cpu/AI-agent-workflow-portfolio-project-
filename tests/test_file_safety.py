"""Output paths must never modify their own synthetic input documents."""
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from operations_agent.__main__ import main as invoice_main
from operations_agent.evaluation import main as evaluation_main


class FileSafetyTests(unittest.TestCase):
    def test_invoice_log_cannot_alias_document_or_email(self):
        for target in ('document', 'email'):
            for hardlink in (False, True):
                with self.subTest(target=target, hardlink=hardlink), tempfile.TemporaryDirectory() as directory:
                    document, email, log = [Path(directory) / name for name in ('document.txt', 'email.txt', 'log.jsonl')]
                    document.write_text('Total: 105.00', encoding='utf-8')
                    email.write_text('Total: 110.00', encoding='utf-8')
                    victim = document if target == 'document' else email
                    if hardlink:
                        os.link(victim, log)
                    else:
                        log = victim
                    before = (document.read_bytes(), email.read_bytes())
                    arguments = ['invoice', str(document), '--format', 'text', '--orchestrate',
                                 '--email', str(email), '--log-json', str(log)]
                    with patch('sys.argv', arguments), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                        invoice_main()
                    self.assertEqual(raised.exception.code, 2)
                    self.assertEqual((document.read_bytes(), email.read_bytes()), before)

    def test_evaluation_output_hardlink_cannot_overwrite_dataset(self):
        root = Path(__file__).resolve().parents[1]
        for option in ('--output', '--log-json'):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                dataset, output = Path(directory) / 'dataset.json', Path(directory) / 'output.json'
                dataset.write_bytes((root / 'evaluation/dataset.json').read_bytes())
                before = dataset.read_bytes()
                os.link(dataset, output)
                with patch('sys.argv', ['evaluation', '--dataset', str(dataset), option, str(output)]), \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    evaluation_main()
                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(dataset.read_bytes(), before)
