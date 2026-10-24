"""Offline mock extraction from labels or narrow prose patterns, not general AI.

Document contents are data. No instructions, tools, or executable content are run.
"""
from dataclasses import dataclass, field
from datetime import date
import re


LABELS = {
    'vendor': 'vendor_name', 'vendor name': 'vendor_name',
    'invoice number': 'invoice_number', 'invoice date': 'invoice_date',
    'due date': 'due_date', 'payment due date': 'due_date',
    'currency': 'currency', 'subtotal': 'subtotal', 'tax': 'tax',
    'total': 'total', 'total amount': 'total',
    'description': 'description', 'invoice description': 'description',
}
FIELDS = tuple(dict.fromkeys(LABELS.values()))


@dataclass
class Evidence:
    source: str
    line: int
    value: str


@dataclass
class ExtractionResult:
    mode: str
    status: str
    fields: dict[str, str | None]
    missing_fields: list[str]
    conflicts: dict[str, list[Evidence]]
    evidence: dict[str, list[Evidence]]
    issues: list[str]
    uncertain_fields: dict[str, str] = field(default_factory=dict)


def check_text(document: str, email: str | None) -> None:
    if not isinstance(document, str) or (email is not None and not isinstance(email, str)):
        raise ValueError('Extraction requires text, not binary documents')
    if len(document) + len(email or '') > 1_000_000:
        raise ValueError('Combined text exceeds the one-million-character limit')


def normalize_date(value: str) -> str | None:
    """Only normalize explicit ISO or English named-month dates; never guess locale."""
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return value  # Impossible calendar dates are still the validator's job.
    months = {name.casefold(): number for number, name in enumerate(
        ('January', 'February', 'March', 'April', 'May', 'June', 'July',
         'August', 'September', 'October', 'November', 'December'), 1)}
    match = re.fullmatch(r'([A-Za-z]+) (\d{1,2}),? (\d{4})', value)
    if match and match[1].casefold() in months:
        try:
            return date(int(match[3]), months[match[1].casefold()], int(match[2])).isoformat()
        except ValueError:
            return None
    return None


def mark_uncertain_dates(result: ExtractionResult) -> ExtractionResult:
    for name in ('invoice_date', 'due_date'):
        if result.fields[name] is not None:
            normalized = normalize_date(result.fields[name])
            if normalized is None:
                result.fields[name] = None
                result.uncertain_fields[name] = 'ambiguous_or_unsupported_date_format'
            else:
                result.fields[name] = normalized
    if result.uncertain_fields:
        result.status = 'needs_review'
    return result


# Narrow, documented prose patterns keep the mock predictable. This is not an
# offline language model or a general-purpose natural-language parser.
PROSE_PATTERNS = {
    'invoice_number': r'\binvoice\s+([A-Za-z0-9][\w/-]*)\s+from\s+',
    'vendor_name': r'\binvoice\s+[A-Za-z0-9][\w/-]*\s+from\s+(.+?)(?=\.(?:\s|$)|$)',
    'invoice_date': r'\bissued(?: on)?\s+(.+?)(?=;|\.(?:\s|$)|$)',
    'due_date': r'\bdue(?: on)?\s+(.+?)(?=;|\.(?:\s|$)|$)',
    'currency': r'\bcurrency(?: is)?\s+([A-Z]{3})\b',
    'subtotal': r'\bsubtotal(?: is)?\s+([^\s;]+)',
    'tax': r'\btax(?: is)?\s+([^\s;]+)',
    'total': r'(?<!sub)\btotal(?: is)?\s+([^\s;]+)',
    'description': r'\bcovering\s+(.+?)(?=\.(?:\s|$)|$)',
}


def extract_mock(document: str, email: str | None = None) -> ExtractionResult:
    """Read labels or supported invoice sentences; never choose conflicting values.

    Dates and amounts remain source strings until deterministic validation.
    Only exactly equal trimmed values agree; semantic differences need review.
    """
    check_text(document, email)
    evidence: dict[str, list[Evidence]] = {name: [] for name in FIELDS}
    document_fields = 0
    for source, text in (('document', document), ('email', email or '')):
        for number, line in enumerate(text.splitlines(), start=1):
            label, separator, value = line.partition(':')
            name = LABELS.get(' '.join(label.casefold().split()))
            if separator and name and value.strip():
                evidence[name].append(Evidence(source, number, value.strip()))
                if source == 'document':
                    document_fields += 1
            if separator and name:
                continue  # Do not reinterpret a known label as a prose sentence.
            for field_name, pattern in PROSE_PATTERNS.items():
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    candidate = match[1].strip()
                    if field_name in ('subtotal', 'tax', 'total'):
                        candidate = candidate.removesuffix('.')
                    evidence[field_name].append(Evidence(source, number, candidate))
                    if source == 'document':
                        document_fields += 1
    fields = {}
    conflicts = {}
    for name, items in evidence.items():
        values = {item.value for item in items}
        fields[name] = items[0].value if len(values) == 1 else None
        if len(values) > 1:
            conflicts[name] = items
    missing = [name for name in FIELDS if not evidence[name]]
    issues = []
    if not document_fields:
        issues.append('no_supported_document_fields')
    if conflicts:
        issues.append('conflicting_source_values')
    status = 'needs_review' if missing or conflicts or issues else 'extracted'
    return mark_uncertain_dates(ExtractionResult('mock', status, fields, missing, conflicts, evidence, issues))
