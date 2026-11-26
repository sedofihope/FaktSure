import base64
from functools import lru_cache
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.runtime_settings import get_runtime_settings
from app.models.client import Client
from app.models.extracted_field import ExtractedField
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.tax_rule import TaxRule
from app.services.calculation_service import money
from app.utils.number_formatting import format_decimal

PDF_FORMAT_VERSION = 8
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _BACKEND_ROOT / "app" / "templates" / "invoices"
_ASSET_DIR = _BACKEND_ROOT / "app" / "static" / "invoice"
_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(("html", "xml")),
    undefined=StrictUndefined,
)


def _font_data_uri(filename: str) -> str:
    content = (_ASSET_DIR / "fonts" / filename).read_bytes()
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:font/ttf;base64,{encoded}"


@lru_cache(maxsize=1)
def _render_stylesheet() -> str:
    css = (_ASSET_DIR / "facture.css").read_text(encoding="utf-8")
    fonts = {
        "inter_regular": "inter-regular.ttf",
        "inter_semibold": "inter-semibold.ttf",
        "inter_bold": "inter-bold.ttf",
        "space_grotesk_bold": "space-grotesk-bold.ttf",
        "jetbrains_mono_medium": "jetbrains-mono-medium.ttf",
    }
    for placeholder, filename in fonts.items():
        css = css.replace(
            "{{ " + placeholder + " }}",
            _font_data_uri(filename),
        )
    return css


def _format_date(value) -> str | None:
    return value.strftime("%d/%m/%Y") if value is not None else None


def _currency_label(currency: str) -> str:
    return "FCFA (XOF)" if currency == "XOF" else currency


def _format_amount(value: Decimal) -> str:
    formatted = format_decimal(value)
    sign = "-" if formatted.startswith("-") else ""
    unsigned = formatted[1:] if sign else formatted
    integer, separator, fraction = unsigned.partition(".")
    grouped = f"{int(integer):,}".replace(",", " ")
    return f"{sign}{grouped}{separator}{fraction}"


def _format_percentage(value: Decimal) -> str:
    return format_decimal(
        value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def render_invoice_pdf(db: Session, invoice: Invoice) -> bytes:
    """Render the branded invoice HTML/CSS and print it to PDF with Chromium."""

    items = db.scalars(
        select(InvoiceItem)
        .where(InvoiceItem.invoice_id == invoice.id)
        .order_by(InvoiceItem.id)
    ).all()
    client = db.get(Client, invoice.client_id) if invoice.client_id else None
    settings = get_runtime_settings()
    extracted_fields = db.scalars(
        select(ExtractedField).where(
            ExtractedField.document_id == invoice.document_id
        )
    ).all()
    extracted = {
        field.field_name: (
            field.corrected_value
            if field.corrected_value is not None
            else field.value
        )
        for field in extracted_fields
    }

    tax_rule_ids = {item.tax_rule_id for item in items if item.tax_rule_id is not None}
    if invoice.tax_rule_id is not None:
        tax_rule_ids.add(invoice.tax_rule_id)
    tax_rules = {
        rule.id: rule
        for rule in db.scalars(
            select(TaxRule).where(TaxRule.id.in_(tax_rule_ids))
        ).all()
    } if tax_rule_ids else {}

    rendered_items: list[dict[str, str | None]] = []
    tax_totals: dict[tuple[str, Decimal], dict[str, Decimal]] = {}
    if invoice.tax_rule_id is not None:
        invoice_tax_rule = tax_rules.get(invoice.tax_rule_id)
        if invoice_tax_rule is not None:
            tax_totals[(invoice_tax_rule.name, invoice_tax_rule.rate)] = {
                "base": money(invoice.subtotal - invoice.discount_total),
                "amount": invoice.tax_total,
            }
    for item in items:
        rule = tax_rules.get(item.tax_rule_id)
        gross = money(item.quantity * item.unit_price)
        tax_amount = (
            money(item.line_total * rule.rate / Decimal("100"))
            if rule is not None and invoice.tax_rule_id is None
            else Decimal("0.00")
        )
        if rule is not None and invoice.tax_rule_id is None:
            tax_key = (rule.name, rule.rate)
            totals = tax_totals.setdefault(
                tax_key,
                {"base": Decimal("0"), "amount": Decimal("0")},
            )
            totals["base"] += item.line_total
            totals["amount"] += tax_amount
        discount_rate = (
            _format_percentage(item.discount * Decimal("100") / gross)
            if item.discount and gross
            else None
        )
        rendered_items.append({
            "description": item.description,
            "quantity": format_decimal(item.quantity),
            "unit": item.unit,
            "unit_price": _format_amount(item.unit_price),
            "discount": _format_amount(item.discount),
            "discount_rate": discount_rate,
            "tax_name": rule.name if rule else None,
            "tax_rate": format_decimal(rule.rate) if rule else None,
            "tax_amount": _format_amount(tax_amount),
            "line_total": _format_amount(item.line_total),
        })

    taxes = [
        {
            "name": name,
            "rate": format_decimal(rate),
            "rate_label": format_decimal(rate) + " %",
            "base": _format_amount(money(values["base"])),
            "amount": _format_amount(money(values["amount"])),
        }
        for (name, rate), values in sorted(tax_totals.items())
    ]
    detailed_tax_total = sum(
        (values["amount"] for values in tax_totals.values()),
        Decimal("0"),
    )
    other_tax = money(invoice.tax_total - detailed_tax_total)
    if other_tax:
        net_after_discount = money(invoice.subtotal - invoice.discount_total)
        effective_rate = (
            _format_percentage(other_tax * Decimal("100") / net_after_discount)
            if net_after_discount > 0
            else None
        )
        if effective_rate and abs(
            money(net_after_discount * Decimal(effective_rate) / Decimal("100"))
            - other_tax
        ) > Decimal("0.01"):
            effective_rate = None
        taxes.append({
            "name": "Taxe non catégorisée",
            "rate": None,
            "rate_label": (
                f"taux effectif calculé : {effective_rate} %"
                if effective_rate
                else "taux non déterminé"
            ),
            "base": None,
            "amount": _format_amount(other_tax),
        })

    source_reference = extracted.get("document_number")

    def available(*values: str | None) -> str | None:
        return next((value.strip() for value in values if value and value.strip()), None)

    client_source_text = "\n".join(
        field.source_text or ""
        for field in extracted_fields
        if field.field_name.startswith("client_")
    )
    extracted_rccm = extracted.get("client_rccm")
    if not extracted_rccm:
        rccm_match = re.search(
            r"(?im)^\s*RCCM\s*[:：]\s*(.+?)\s*$",
            client_source_text,
        )
        extracted_rccm = rccm_match.group(1).strip() if rccm_match else None

    client_values = {
        "name": client.name if client else None,
        "address": available(client.address if client else None, extracted.get("client_address")),
        "tax_identifier": available(client.tax_identifier if client else None, extracted.get("client_tax_identifier")),
        "rccm": available(client.rccm if client else None, extracted_rccm),
        "email": available(client.email if client else None, extracted.get("client_email")),
        "phone": available(client.phone if client else None, extracted.get("client_phone")),
    }
    issuer_values = {
        "name": settings.issuer_name,
        "address": settings.issuer_address,
        "tax_identifier": settings.issuer_tax_identifier,
        "rccm": settings.issuer_rccm,
        "email": settings.issuer_email,
        "phone": settings.issuer_phone,
    }
    payment_terms = invoice.payment_terms or settings.issuer_payment_terms
    is_issued = invoice.status == "ISSUED"
    template = _TEMPLATE_ENV.get_template("facture.html")
    html = template.render(
        css=_render_stylesheet(),
        title=f"{'Facture' if is_issued else 'Brouillon'} {invoice.invoice_number}",
        is_issued=is_issued,
        invoice_number=invoice.invoice_number,
        issue_date=_format_date(invoice.issue_date),
        due_date=_format_date(invoice.due_date),
        currency=_currency_label(invoice.currency),
        client=client_values,
        issuer=issuer_values,
        source_reference=source_reference,
        payment_terms=payment_terms,
        items=rendered_items,
        taxes=taxes,
        subtotal=_format_amount(invoice.subtotal),
        discount_total=_format_amount(invoice.discount_total),
        tax_total=_format_amount(invoice.tax_total),
        taxable_base_total=_format_amount(money(invoice.subtotal - invoice.discount_total)),
        grand_total=_format_amount(invoice.grand_total),
    )

    executable_path = (
        settings.chromium_executable_path
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
    )
    if executable_path is None:
        raise RuntimeError(
            "Chromium is required to render invoice PDFs; install Chromium or set CHROMIUM_EXECUTABLE_PATH"
        )

    with tempfile.TemporaryDirectory(prefix="faktsure-invoice-") as temp_dir:
        temp_path = Path(temp_dir)
        html_path = temp_path / "invoice.html"
        pdf_path = temp_path / "invoice.pdf"
        profile_path = temp_path / "chromium-profile"
        html_path.write_text(html, encoding="utf-8")
        command = [
            executable_path,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile_path}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Chromium timed out while rendering the invoice PDF") from exc
        if result.returncode != 0 or not pdf_path.is_file():
            raise RuntimeError(
                "Chromium failed to render the invoice PDF"
                + (f": {result.stderr[-1000:]}" if result.stderr else "")
            )
        content = pdf_path.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise RuntimeError("Chromium returned invalid PDF content")
        return content
