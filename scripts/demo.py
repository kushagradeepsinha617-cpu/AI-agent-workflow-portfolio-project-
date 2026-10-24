"""Reproduce the documented offline checkpoint, retaining its known quality failure."""
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'local-data/portfolio-demo'


def run(arguments, expected_code):
    completed = subprocess.run([sys.executable, '-m', *arguments], cwd=ROOT,
                               capture_output=True, text=True)
    if completed.returncode != expected_code:
        raise RuntimeError(f'Unexpected exit code {completed.returncode}; expected {expected_code}: {arguments[0]}')
    return completed


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fixtures = 'tests/fixtures/milestone2'
    for name, exit_code, validation in (
        ('valid', 0, 'valid'), ('ambiguous', 1, 'invalid'), ('incorrect_total', 1, 'invalid'),
    ):
        completed = run(['operations_agent', f'{fixtures}/{name}.txt', '--format', 'text',
                         '--mode', 'mock', '--orchestrate', '--known-vendor', 'Demo Supplies',
                         '--log-json', str(OUTPUT / 'workflow-events.jsonl')], exit_code)
        row = json.loads(completed.stdout)[0]
        if (row['human_decision'] != 'pending' or row['processing_status'] != 'awaiting_review'
                or row['validation_status'] != validation or row['workflow']['issues']):
            raise RuntimeError(f'{name}: unexpected processing/review boundary result')
        if name == 'ambiguous' and (row['extraction']['fields']['invoice_date'] is not None
                                   or 'invoice_date' not in row['extraction']['uncertain_fields']):
            raise RuntimeError('Ambiguous date was not preserved as unresolved')
        if name == 'incorrect_total' and (row['extraction']['fields']['total'] != '110.00'
                                         or 'inconsistent_total' not in row['errors']):
            raise RuntimeError('Incorrect total was changed or did not reach deterministic validation')
        (OUTPUT / f'{name}.json').write_text(completed.stdout, encoding='utf-8')
        print(f'{name}: exit {exit_code}, validation {validation}, decision pending')

    report_path = OUTPUT / 'evaluation.json'
    run(['operations_agent.evaluation', '--output', str(report_path),
         '--log-json', str(OUTPUT / 'evaluation-events.jsonl')], 1)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    checkpoint = json.loads((ROOT / 'evaluation/mock_report.json').read_text(encoding='utf-8'))
    if report != checkpoint:
        raise RuntimeError('Measured report differs from the saved checkpoint; inspect evaluation.json')
    failures = [row['id'] for row in report['cases'] if not row['quality_passed']]
    if (report['execution_failures'] or report['integrity_passed_cases'] != report['case_count']
            or failures != ['unsupported_prose'] or report['system_under_test']['live_model_evaluation']):
        raise RuntimeError('Evaluation differs from the documented offline checkpoint; inspect evaluation.json')
    accuracy = report['known_field_accuracy']
    print(f"mock field recovery: {accuracy['correct']}/{accuracy['total']} ({accuracy['accuracy']:.2%})")
    print(f"quality: {report['quality_passed_cases']}/{report['case_count']}; known failure retained: unsupported_prose")
    print(f"integrity: {report['integrity_passed_cases']}/{report['case_count']}; live model evaluation: not performed")
    print(f'Artifacts: {OUTPUT.relative_to(ROOT)}/ (JSON results refreshed; JSONL logs appended)')
    print('Demo matched the checkpoint. The standalone evaluation still exits 1 for the known quality failure.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f'Demo failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
