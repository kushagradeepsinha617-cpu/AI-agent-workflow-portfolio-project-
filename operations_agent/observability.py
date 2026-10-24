"""Opt-in JSONL events: counts and fixed status codes, never invoice contents."""
from datetime import datetime, timezone
import json
from pathlib import Path

from .extraction import FIELDS


SAFE_CODES = {
    'due_date_before_invoice_date', 'inconsistent_total', 'duplicate_invoice',
    'unknown_vendor', 'validation_failed', 'no_supported_document_fields',
    'conflicting_source_values', 'missing_api_key', 'missing_model_configuration',
    'provider_connection_failed', 'invalid_or_incomplete_model_response',
    'extraction_task_failed', 'validation_task_failed', 'review_agent_task_failed',
    'observability_failed', 'extraction_needs_review', 'workflow_needs_review',
} | {f'{prefix}:{name}' for prefix in ('missing', 'invalid', 'unsupported') for name in FIELDS}


def safe_codes(codes):
    # Codes can come from injected components. Never log an arbitrary string.
    return [code if isinstance(code, str) and code in SAFE_CODES else 'unrecognized_code'
            for code in codes]


class JsonlEventLog:
    """Append one JSON event per line; intended for the synchronous CLI runner."""
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a', encoding='utf-8')
        return self

    def __exit__(self, *args):
        self.stream.close()

    def __call__(self, event):
        self.stream.write(json.dumps(event, sort_keys=True) + '\n')
        self.stream.flush()


def stage_event(run_id, stage, event, status, mode, *, missing_count=0,
                uncertain_count=0, conflict_count=0, error_count=0,
                risk_count=0, workflow_issue_count=0, error_codes=(), review_flags=()):
    """Only explicitly named metadata can enter the application log."""
    return {
        'schema_version': 1,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'run_id': run_id, 'stage': stage, 'event': event, 'status': status,
        'mode': mode, 'human_decision': 'pending',
        'missing_count': missing_count, 'uncertain_count': uncertain_count,
        'conflict_count': conflict_count, 'error_count': error_count,
        'risk_count': risk_count, 'workflow_issue_count': workflow_issue_count,
        'error_codes': safe_codes(error_codes), 'review_flags': safe_codes(review_flags),
    }
