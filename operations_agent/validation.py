"""Validate structured synthetic invoices without an LLM."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Context, Decimal, InvalidOperation, localcontext
from uuid import uuid4


@dataclass
class Invoice:
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    description: str | None = None
    record_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class Result:
    invoice: Invoice
    errors: list[str]
    risk_indicators: list[str]
    human_decision: str = 'pending'
    processing_status: str = 'awaiting_review'

    @property
    def validation_status(self):
        return 'invalid' if self.errors else 'valid'


class Validator:
    def __init__(self, known_vendors=(), currencies=('USD', 'EUR', 'GBP', 'INR')):
        self.known_vendors = {v.strip().casefold() for v in known_vendors}
        self.currencies = set(currencies)
        self.seen = set()

    def validate(self, raw):
        if not isinstance(raw, dict):
            raise ValueError('Each invoice must be an object')
        invoice, errors, risks = Invoice(), [], []
        for name in ('vendor_name', 'invoice_number', 'currency', 'description',
                     'invoice_date', 'due_date', 'subtotal', 'tax', 'total'):
            value = raw.get(name)
            if value is None or value == '':
                errors.append(f'missing:{name}')
                continue
            try:
                if name in ('subtotal', 'tax', 'total'):
                    if isinstance(value, bool) or not isinstance(value, (str, int)):
                        raise ValueError
                    value = Decimal(value)
                    if not value.is_finite() or value < 0 or value > Decimal('1000000000000'):
                        raise ValueError
                    if value.as_tuple().exponent < -2:
                        raise ValueError
                else:
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError
                    value = value.strip()
                    if name in ('invoice_date', 'due_date'):
                        parsed = date.fromisoformat(value)
                        if parsed.isoformat() != value:
                            raise ValueError
                        value = parsed
                    elif name == 'currency':
                        value = value.upper()
                setattr(invoice, name, value)
            except (ValueError, InvalidOperation):
                errors.append(f'invalid:{name}')
        if invoice.currency and invoice.currency not in self.currencies:
            errors.append('unsupported:currency')
        if invoice.invoice_date and invoice.due_date and invoice.due_date < invoice.invoice_date:
            errors.append('due_date_before_invoice_date')
        if all(getattr(invoice, n) is not None for n in ('subtotal', 'tax', 'total')):
            # Valid amounts have at most 13 integer and two fractional digits.
            # A private context keeps arithmetic exact even if a caller changes
            # decimal precision or enables rounding exceptions elsewhere.
            with localcontext(Context(prec=32)):
                expected_total = invoice.subtotal + invoice.tax
            if expected_total != invoice.total:
                errors.append('inconsistent_total')
        if invoice.vendor_name:
            vendor = invoice.vendor_name.casefold()
            if vendor not in self.known_vendors:
                risks.append('unknown_vendor')
            if invoice.invoice_number:
                key = (vendor, invoice.invoice_number.casefold())
                if key in self.seen:
                    errors.append('duplicate_invoice')
                    risks.append('duplicate_invoice')
                self.seen.add(key)
        if errors:
            risks.append('validation_failed')
        return Result(invoice, errors, risks)
