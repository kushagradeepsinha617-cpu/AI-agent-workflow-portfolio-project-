import argparse
from contextlib import nullcontext
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from .validation import Validator
from .extraction import extract_mock
from .ai_extraction import extract_ai
from .json_input import load_json
from .observability import JsonlEventLog


def encode(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description='Validate synthetic invoices; never approves records.')
    parser.add_argument('input', type=Path)
    parser.add_argument('--known-vendor', action='append', default=[])
    parser.add_argument('--format', choices=('json', 'text'), default='json')
    parser.add_argument('--mode', choices=('mock', 'ai'), default='mock',
                        help='Text extraction mode; ai makes a paid provider request')
    parser.add_argument('--orchestrate', action='store_true',
                        help='Run text processing through CrewAI Flow and bounded review agent')
    parser.add_argument('--email', type=Path, help='Optional labelled email text; requires --format text')
    parser.add_argument('--log-json', type=Path, help='Append sanitized JSONL stage events; requires --orchestrate')
    args = parser.parse_args()
    if args.email and args.format != 'text':
        parser.error('--email requires --format text')
    if args.mode == 'ai' and args.format != 'text':
        parser.error('--mode ai requires --format text')
    if args.orchestrate and args.format != 'text':
        parser.error('--orchestrate requires --format text')
    if args.log_json and not args.orchestrate:
        parser.error('--log-json requires --orchestrate')
    try:
        if args.orchestrate:
            try:
                from .orchestration import process_invoice
            except ImportError:
                parser.exit(2, 'CrewAI dependencies are missing; install requirements.lock in .venv\n')
            with JsonlEventLog(args.log_json) if args.log_json else nullcontext() as event_sink:
                output = process_invoice(args.input.read_text(encoding='utf-8'),
                                         args.email.read_text(encoding='utf-8') if args.email else None,
                                         mode=args.mode, known_vendors=args.known_vendor,
                                         event_sink=event_sink)
            print(json.dumps([output], default=encode, indent=2))
            return int(output['validation_status'] != 'valid'
                       or output['extraction']['status'] != 'extracted'
                       or bool(output['workflow']['issues']))
        extraction = None
        if args.format == 'text':
            extractor = extract_ai if args.mode == 'ai' else extract_mock
            extraction = extractor(args.input.read_text(encoding='utf-8'),
                                   args.email.read_text(encoding='utf-8') if args.email else None)
            records = [extraction.fields]
        else:
            records = load_json(args.input.read_text(encoding='utf-8'))
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            raise ValueError('Input must be a JSON array of invoice objects')
        validator = Validator(args.known_vendor)
        results = []
        for raw in records:
            result = validator.validate(raw)
            output = {**asdict(result), 'validation_status': result.validation_status}
            if extraction:
                output['extraction'] = asdict(extraction)
                if extraction.status != 'extracted':
                    output['risk_indicators'].append('extraction_needs_review')
            results.append(output)
        print(json.dumps(results, default=encode, indent=2))
    except RecursionError:
        parser.exit(2, 'Input error: JSON input is nested too deeply\n')
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Input error: {exc}\n')
    return int(any(r['validation_status'] == 'invalid' or
                   r.get('extraction', {}).get('status', 'extracted') != 'extracted' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
