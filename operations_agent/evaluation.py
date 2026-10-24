"""Reproducible mock evaluation; never invokes a live provider or hides failures."""
import argparse
from contextlib import nullcontext
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

from .extraction import FIELDS
from .json_input import load_json
from .observability import JsonlEventLog
from .validation import Validator


DEFAULT_DATASET = Path(__file__).resolve().parents[1] / 'evaluation/dataset.json'


def load_dataset(path):
    raw = Path(path).read_bytes()
    dataset = load_json(raw.decode('utf-8'))
    if (not isinstance(dataset, dict) or dataset.get('schema_version') != 1
            or not isinstance(dataset.get('dataset_id'), str)
            or not isinstance(dataset.get('known_vendors'), list)
            or any(not isinstance(v, str) for v in dataset['known_vendors'])
            or not isinstance(dataset.get('cases'), list) or not dataset['cases']):
        raise ValueError('Dataset must contain nonempty annotated synthetic cases')
    seen = set()
    for case in dataset['cases']:
        if (not isinstance(case, dict) or not isinstance(case.get('id'), str)
                or not case['id'] or case['id'] in seen
                or not isinstance(case.get('sequence'), str) or not case['sequence']
                or not isinstance(case.get('document'), str)
                or case.get('email') is not None and not isinstance(case['email'], str)
                or type(case.get('known_limitation')) is not bool):
            raise ValueError('Malformed or duplicate evaluation case')
        seen.add(case['id'])
        expected = case.get('expected')
        if (not isinstance(expected, dict) or not isinstance(expected.get('fields'), dict)
                or set(expected['fields']) != set(FIELDS)
                or any(v is not None and not isinstance(v, str) for v in expected['fields'].values())
                or not isinstance(expected.get('unresolved_fields'), dict)):
            raise ValueError('Each case needs all nine ground-truth fields')
        unresolved = expected['unresolved_fields']
        if (set(unresolved) != {name for name in FIELDS if expected['fields'][name] is None}
                or any(reason not in ('missing', 'uncertain', 'conflict', 'unreadable') for reason in unresolved.values())
                or expected.get('extraction_status') not in ('extracted', 'needs_review', 'failed')
                or expected.get('validation_status') not in ('valid', 'invalid')
                or type(expected.get('attention_required')) is not bool):
            raise ValueError('Ground-truth uncertainty/outcomes are incomplete')
        for key in ('validation_errors', 'risk_indicators'):
            if not isinstance(expected.get(key), list) or any(not isinstance(v, str) for v in expected[key]):
                raise ValueError('Expected errors/risks must be lists of codes')
    return dataset, hashlib.sha256(raw).hexdigest()


def score_case(case, output):
    """Compare independent annotations to actual output, not to another parser."""
    expected = case['expected']
    extraction = output['extraction']
    actual = extraction['fields']
    if (set(actual) != set(FIELDS)
            or any(value is not None and not isinstance(value, str) for value in actual.values())):
        raise ValueError('Malformed pipeline field schema')
    flagged = set(extraction['missing_fields']) | set(extraction['uncertain_fields']) | set(extraction['conflicts'])
    if not flagged <= set(FIELDS):
        raise ValueError('Unknown unresolved field')
    truth = set(expected['unresolved_fields'])
    known = [name for name in FIELDS if name not in truth]
    mismatches = [{'field': name, 'expected': expected['fields'][name], 'actual': actual[name]}
                  for name in known if actual[name] != expected['fields'][name]]
    confusion = {
        'true_positive': len(truth & flagged), 'false_positive': len(flagged - truth),
        'false_negative': len(truth - flagged), 'true_negative': len(set(FIELDS) - truth - flagged),
    }
    attention = bool(output['risk_indicators'] or output['errors'] or output['workflow']['issues']
                     or output['validation_status'] != 'valid' or extraction['status'] != 'extracted')
    outcomes_match = (
        extraction['status'] == expected['extraction_status']
        and output['validation_status'] == expected['validation_status']
        and sorted(output['errors']) == sorted(expected['validation_errors'])
        and sorted(output['risk_indicators']) == sorted(expected['risk_indicators']
            + (['extraction_needs_review'] if extraction['status'] != 'extracted' else []))
        and attention == expected['attention_required']
    )
    summary = output['review_summary']
    unresolved_markers = (
        [('Missing: ', name) for name in extraction['missing_fields']]
        + [('Uncertain: ', name) for name in extraction['uncertain_fields']]
        + [('Conflicting values: ', name) for name in extraction['conflicts']]
    )
    integrity = {
        'human_decision_pending': output['human_decision'] == 'pending',
        'processing_awaits_review': output['processing_status'] == 'awaiting_review',
        'all_stages_visited': output['workflow']['completed_steps'] == ['extraction', 'validation', 'review'],
        'truth_unresolved_not_invented': all(actual[name] is None for name in truth),
        'flagged_fields_not_filled': all(actual[name] is None for name in flagged),
        'null_fields_explicitly_flagged': all(name in flagged for name in FIELDS if actual[name] is None),
        'unresolved_visible_in_summary': all(prefix + name in summary for prefix, name in unresolved_markers),
        'validation_errors_visible_in_summary': all(error in summary for error in output['errors']),
        'workflow_failures_visible_in_summary': all(issue in summary for issue in output['workflow']['issues']),
        'extraction_mistakes_trigger_attention': not mismatches or attention,
        'problem_outputs_have_review_flags': not (extraction['status'] != 'extracted'
            or output['errors'] or output['workflow']['issues']) or bool(output['risk_indicators']),
    }
    quality_passed = (not mismatches and flagged == truth and outcomes_match
                      and integrity['truth_unresolved_not_invented'])
    return {
        'id': case['id'], 'known_limitation': case['known_limitation'],
        'known_field_count': len(known), 'correct_field_count': len(known) - len(mismatches),
        'field_mismatches': mismatches, 'unresolved_detection': confusion,
        'outcomes_match': outcomes_match, 'quality_passed': quality_passed,
        'integrity': integrity, 'integrity_passed': all(integrity.values()),
        'execution_failed': False,
        'observed': {'extraction_status': extraction['status'],
                     'validation_status': output['validation_status'],
                     'validation_errors': output['errors'],
                     'attention_required': attention, 'human_decision': output['human_decision']},
    }


def failed_case(case):
    """Runner exceptions stay in denominators and never become passing null matches."""
    truth_count = len(case['expected']['unresolved_fields'])
    return {
        'id': case['id'], 'known_limitation': case['known_limitation'],
        'known_field_count': len(FIELDS) - truth_count, 'correct_field_count': 0,
        'field_mismatches': [], 'execution_failed': True,
        'execution_error': 'runner_failed_or_malformed_output',
        'unresolved_detection': {'true_positive': 0, 'false_positive': 0,
                                'false_negative': truth_count, 'true_negative': len(FIELDS) - truth_count},
        'outcomes_match': False, 'quality_passed': False,
        'integrity': {'valid_pipeline_output': False}, 'integrity_passed': False,
        'observed': None,
    }


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def evaluate(dataset, dataset_sha256, *, processor=None, event_sink=None):
    if processor is None:
        from .orchestration import process_invoice
        processor = process_invoice
    validators, rows = {}, []
    for case in dataset['cases']:
        validator = validators.setdefault(case['sequence'], Validator(dataset['known_vendors']))
        try:
            output = processor(case['document'], case.get('email'), mode='mock',
                               validator=validator, event_sink=event_sink)
            rows.append(score_case(case, output))
        except Exception:
            rows.append(failed_case(case))
    known = sum(row['known_field_count'] for row in rows)
    correct = sum(row['correct_field_count'] for row in rows)
    per_field = {name: {'correct': 0, 'total': 0} for name in FIELDS}
    for case, row in zip(dataset['cases'], rows):
        incorrect = {item['field'] for item in row['field_mismatches']}
        for name in FIELDS:
            if case['expected']['fields'][name] is not None:
                per_field[name]['total'] += 1
                if not row['execution_failed'] and name not in incorrect:
                    per_field[name]['correct'] += 1
    for counts in per_field.values():
        counts['accuracy'] = ratio(counts['correct'], counts['total'])
    confusion = {key: sum(row['unresolved_detection'][key] for row in rows)
                 for key in ('true_positive', 'false_positive', 'false_negative', 'true_negative')}
    tp, fp, fn, tn = (confusion[key] for key in ('true_positive', 'false_positive', 'false_negative', 'true_negative'))
    return {
        'schema_version': 1, 'dataset_id': dataset['dataset_id'], 'dataset_sha256': dataset_sha256,
        'system_under_test': {'extraction': 'deterministic_mock', 'orchestration': 'real_crewai',
                              'review_model': 'offline_stub', 'live_model_evaluation': False,
                              'crewai_version': version('crewai')},
        'case_count': len(rows), 'execution_failures': sum(row['execution_failed'] for row in rows),
        'known_field_accuracy': {'correct': correct, 'total': known, 'accuracy': ratio(correct, known)},
        'per_field_accuracy': per_field,
        'unresolved_detection': {**confusion, 'precision': ratio(tp, tp + fp),
                                'recall': ratio(tp, tp + fn), 'false_positive_rate': ratio(fp, fp + tn),
                                'false_negative_rate': ratio(fn, fn + tp)},
        'pipeline_outcome_match': {'correct': sum(row['outcomes_match'] for row in rows), 'total': len(rows)},
        'quality_passed_cases': sum(row['quality_passed'] for row in rows),
        'integrity_passed_cases': sum(row['integrity_passed'] for row in rows),
        'cases': rows,
    }


def main():
    parser = argparse.ArgumentParser(description='Evaluate synthetic mock extraction and the real CrewAI pipeline offline.')
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--log-json', type=Path)
    args = parser.parse_args()
    paths = [p.resolve() for p in (args.dataset, args.output, args.log_json) if p is not None]
    if len(set(paths)) != len(paths):
        parser.error('Dataset, output and log must use different files')
    try:
        dataset, fingerprint = load_dataset(args.dataset)
        with JsonlEventLog(args.log_json) if args.log_json else nullcontext() as sink:
            report = evaluate(dataset, fingerprint, event_sink=sink)
        encoded = json.dumps(report, indent=2, allow_nan=False) + '\n'
        if args.output:
            args.output.write_text(encoded, encoding='utf-8')
        else:
            print(encoded, end='')
    except (OSError, ValueError, RecursionError) as exc:
        parser.exit(2, f'Evaluation input/output error: {exc}\n')
    return int(report['quality_passed_cases'] != report['case_count']
               or report['integrity_passed_cases'] != report['case_count'])


if __name__ == '__main__':
    raise SystemExit(main())
