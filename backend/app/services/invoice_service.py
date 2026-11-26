from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.anomaly import Anomaly
from app.models.client import Client
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.invoice_sequence import InvoiceSequence
from app.models.tax_rule import TaxRule
from app.schemas.invoice import InvoiceItemCreate
from app.services.calculation_service import calculate_line, money
from app.services.invoice_pdf import PDF_FORMAT_VERSION, render_invoice_pdf


class InvoiceService:
    """Create, calculate, and validate invoices without modifying source documents."""

    def create_draft(self, db: Session, payload, actor_id: int | None = None) -> Invoice:
        document = db.scalar(select(Document).where(Document.public_id == payload.document_id))
        if document is None:
            raise LookupError("Document not found")
        if document.status != "READY":
            raise ValueError("Document must pass human review")
        if db.scalar(select(Invoice).where(Invoice.document_id == document.id)):
            raise ValueError("A main invoice already exists for this document")
        blocker = db.scalar(select(Anomaly).where(Anomaly.document_id == document.id, Anomaly.severity == "BLOCKER", Anomaly.status == "OPEN"))
        if blocker:
            raise ValueError("An unresolved blocker prevents invoice creation")

        fields = db.scalars(
            select(ExtractedField).where(ExtractedField.document_id == document.id)
        ).all()
        extracted = {
            field.field_name: (
                field.corrected_value
                if field.corrected_value is not None
                else field.value
            )
            for field in fields
        }
        client = self._resolve_client(db, payload.client_id, extracted)
        issue_date = payload.issue_date or date.today()
        due_date = payload.due_date
        currency = self._currency(payload.currency or extracted.get("currency"))

        extracted_grand_total = None
        if payload.items is None:
            items, source_totals = self._build_extracted_items(extracted)
            extracted_grand_total = source_totals["grand_total"]
            extracted_tax_total = source_totals["tax_total"]
            applicable_rules = db.scalars(
                select(TaxRule).where(
                    TaxRule.is_active.is_(True),
                    TaxRule.valid_from <= issue_date,
                    (TaxRule.valid_until.is_(None)) | (TaxRule.valid_until >= issue_date),
                ).order_by(TaxRule.id)
            ).all()
            matching_rules = []
            if extracted_tax_total:
                for candidate in applicable_rules:
                    if candidate.calculation_type != "PERCENTAGE":
                        continue
                    calculated_tax = money(sum(
                        (
                            calculate_line(
                                item.quantity,
                                item.unit_price,
                                item.discount,
                                candidate.rate,
                            )[1]
                            for item in items
                        ),
                        Decimal("0"),
                    ))
                    if abs(calculated_tax - extracted_tax_total) <= Decimal("0.01"):
                        matching_rules.append(candidate)
                if len(matching_rules) != 1:
                    raise ValueError(
                        "The extracted tax total does not identify one configured tax rate for all lines; "
                        "provide invoice lines with an explicit tax_rule_id for each applicable rate"
                    )
                selected_rule = matching_rules[0]
                for item in items:
                    item.tax_rule_id = selected_rule.public_id
        else:
            items = payload.items

        invoice = Invoice(
            document_id=document.id,
            client_id=client.id,
            invoice_number=f"DRAFT-{document.id}",
            issue_date=issue_date,
            due_date=due_date,
            payment_terms=payload.payment_terms or extracted.get("payment_terms"),
            currency=currency,
            status="DRAFT",
        )
        try:
            db.add(invoice)
            db.flush()
            subtotal = Decimal("0")
            discount_total = Decimal("0")
            tax_total = Decimal("0")
            for item_payload in items:
                quantity = item_payload.quantity
                unit_price = item_payload.unit_price
                discount = item_payload.discount
                gross = money(quantity * unit_price)
                if discount > gross:
                    raise ValueError("A line discount cannot exceed its gross amount")

                tax_rate = Decimal("0")
                product_id = None
                if item_payload.product_id:
                    from app.models.product import Product

                    product = db.scalar(
                        select(Product).where(Product.public_id == item_payload.product_id)
                    )
                    if product is None or not product.is_active:
                        raise ValueError("An active product is required for the selected item")
                    product_id = product.id
                if item_payload.tax_rule_id:
                    rule = db.scalar(
                        select(TaxRule).where(TaxRule.public_id == item_payload.tax_rule_id)
                    )
                    if rule is None:
                        raise ValueError("Tax rule not found")
                    if not rule.is_active or not (
                        rule.valid_from <= issue_date
                        and (rule.valid_until is None or issue_date <= rule.valid_until)
                    ):
                        raise ValueError("Tax rule is not active on the invoice date")
                    if rule.calculation_type != "PERCENTAGE":
                        raise ValueError(f"Unsupported tax calculation type: {rule.calculation_type}")
                    tax_rate = rule.rate

                net, tax, line_gross = calculate_line(quantity, unit_price, discount, tax_rate)
                db.add(InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=product_id,
                    description=item_payload.description,
                    quantity=quantity,
                    unit=item_payload.unit,
                    unit_price=unit_price,
                    discount=discount,
                    tax_rule_id=rule.id if item_payload.tax_rule_id else None,
                    line_total=net,
                ))
                subtotal += gross
                discount_total += discount
                tax_total += tax
            invoice.subtotal = money(subtotal)
            invoice.discount_total = money(discount_total)
            invoice.tax_total = money(tax_total)
            invoice.grand_total = money(
                invoice.subtotal - invoice.discount_total + invoice.tax_total
            )
            if (
                extracted_grand_total is not None
                and abs(invoice.grand_total - extracted_grand_total) > Decimal("0.01")
            ):
                raise ValueError(
                    "Extracted invoice totals do not reconcile; review the document fields or provide explicit invoice lines"
                )
            if payload.items is None and (
                abs(invoice.subtotal - source_totals["subtotal"]) > Decimal("0.01")
                or abs(invoice.discount_total - source_totals["discount_total"]) > Decimal("0.01")
                or abs(invoice.tax_total - source_totals["tax_total"]) > Decimal("0.01")
            ):
                raise ValueError(
                    "Invoice calculations do not match the reviewed extracted totals; correct the document fields"
                )
            db.add(AuditLog(
                user_id=actor_id,
                action="INVOICE_DRAFT_CREATED",
                entity_type="Invoice",
                entity_id=str(invoice.public_id),
                new_value=f"document_id={document.id}",
            ))
            db.commit()
            db.refresh(invoice)
            return invoice
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _field_value(fields: dict[str, str | None], name: str) -> str | None:
        value = fields.get(name)
        return value.strip() if value and value.strip() else None

    @staticmethod
    def _currency(value: str | None) -> str:
        if not value:
            raise ValueError(
                "Currency is missing from the document; provide currency explicitly"
            )
        normalized = " ".join(value.upper().split())
        if normalized in {"FCFA", "CFA", "F CFA", "FR CFA"}:
            return "XOF"
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError(
                f"Extracted currency '{value}' is not an ISO 4217 code; provide currency explicitly"
            )
        return normalized

    @classmethod
    def _resolve_client(
        cls,
        db: Session,
        client_id,
        fields: dict[str, str | None],
    ) -> Client:
        if client_id is not None:
            client = db.scalar(
                select(Client).where(
                    Client.public_id == client_id,
                    Client.is_active.is_(True),
                )
            )
            if client is None:
                raise LookupError("Active client not found")
            return client

        active_clients = db.scalars(
            select(Client).where(Client.is_active.is_(True))
        ).all()
        identifiers = (
            ("rccm", cls._field_value(fields, "client_rccm")),
            ("tax_identifier", cls._field_value(fields, "client_tax_identifier")),
        )
        matched: dict[int, Client] = {}
        for attribute, value in identifiers:
            if value is None:
                continue
            for client in active_clients:
                candidate = getattr(client, attribute)
                if candidate and candidate.strip().casefold() == value.casefold():
                    matched[client.id] = client
        if len(matched) == 1:
            return next(iter(matched.values()))
        if len(matched) > 1:
            raise ValueError(
                "Extracted client identifiers match multiple clients; provide client_id explicitly"
            )

        name = cls._field_value(fields, "client_name")
        if name:
            normalized_name = " ".join(name.casefold().split())
            name_matches = [
                client for client in active_clients
                if " ".join(client.name.casefold().split()) == normalized_name
            ]
            if len(name_matches) == 1:
                return name_matches[0]
            if len(name_matches) > 1:
                raise ValueError(
                    "Extracted client name matches multiple clients; provide client_id explicitly"
                )
        raise ValueError(
            "No active client uniquely matches the extracted document; create or select the client, then provide client_id"
        )

    @classmethod
    def _build_extracted_items(
        cls,
        fields: dict[str, str | None],
    ) -> tuple[list[InvoiceItemCreate], dict[str, Decimal]]:
        def decimal_value(value, label: str, *, required: bool = True) -> Decimal | None:
            if value is None or (isinstance(value, str) and not value.strip()):
                if required:
                    raise ValueError(
                        f"Extracted {label} is missing; correct the document fields or provide explicit invoice lines"
                    )
                return None
            try:
                return Decimal(str(value).replace(",", "").strip())
            except (InvalidOperation, AttributeError) as exc:
                raise ValueError(
                    f"Extracted {label} is not a valid amount; correct the document fields"
                ) from exc

        line_names = sorted(
            (
                name for name, value in fields.items()
                if name.startswith("item.") and value
            ),
            key=lambda name: (
                (0, int(name.partition(".")[2]))
                if name.partition(".")[2].isdigit()
                else (1, name)
            ),
        )
        if not line_names:
            raise ValueError(
                "No extracted invoice lines were found; provide explicit invoice lines"
            )

        parsed_lines = []
        for name in line_names:
            try:
                line = json.loads(fields[name] or "")
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Extracted line {name} is invalid; correct the document fields"
                ) from exc
            description = line.get("description")
            if not isinstance(description, str) or not description.strip():
                raise ValueError(
                    f"Extracted line {name} has no description; correct the document fields"
                )
            quantity = decimal_value(line.get("quantity"), f"{name} quantity")
            unit_price = decimal_value(line.get("unit_price"), f"{name} unit price")
            line_discount = decimal_value(
                line.get("discount"), f"{name} discount", required=False
            ) or Decimal("0")
            if quantity is None or quantity <= 0 or unit_price is None or unit_price < 0:
                raise ValueError(f"Extracted line {name} contains invalid amounts")
            gross = money(quantity * unit_price)
            if line_discount < 0 or line_discount > gross:
                raise ValueError(f"Extracted line {name} discount exceeds its gross amount")
            parsed_lines.append({
                "description": description.strip(),
                "quantity": quantity,
                "unit": line.get("unit") or "unit",
                "unit_price": unit_price,
                "discount": money(line_discount),
                "gross": gross,
            })

        calculated_subtotal = money(sum(
            (line["gross"] for line in parsed_lines), Decimal("0")
        ))
        source_subtotal = decimal_value(
            fields.get("subtotal"), "subtotal", required=False
        )
        subtotal = money(source_subtotal if source_subtotal is not None else calculated_subtotal)
        if abs(subtotal - calculated_subtotal) > Decimal("0.01"):
            raise ValueError(
                "Extracted subtotal does not match the extracted invoice lines; correct the fields before creating a draft"
            )

        line_discount_total = money(sum(
            (line["discount"] for line in parsed_lines), Decimal("0")
        ))
        source_discount = decimal_value(
            fields.get("discount_total"), "discount total", required=False
        )
        discount_total = money(
            source_discount if source_discount is not None else line_discount_total
        )
        additional_discount = money(discount_total - line_discount_total)
        if additional_discount < 0:
            raise ValueError(
                "Extracted total discount is less than the sum of line discounts; correct the document fields"
            )

        available_base = money(sum(
            (line["gross"] - line["discount"] for line in parsed_lines),
            Decimal("0"),
        ))
        if additional_discount > available_base:
            raise ValueError("Extracted discount exceeds the invoice taxable base")
        if additional_discount:
            remaining = additional_discount
            remaining_base = available_base
            for index, line in enumerate(parsed_lines):
                base = line["gross"] - line["discount"]
                if index == len(parsed_lines) - 1:
                    allocation = remaining
                elif remaining_base:
                    allocation = money(remaining * base / remaining_base)
                    allocation = min(allocation, base, remaining)
                else:
                    allocation = Decimal("0")
                line["discount"] = money(line["discount"] + allocation)
                remaining = money(remaining - allocation)
                remaining_base -= base
            if remaining != 0:
                raise ValueError("Unable to allocate the extracted invoice discount to its lines")

        tax_total = decimal_value(fields.get("tax_total"), "tax total", required=False)
        grand_total = decimal_value(fields.get("grand_total"), "grand total", required=False)
        if tax_total is None and grand_total is not None:
            tax_total = money(grand_total - subtotal + discount_total)
        if tax_total is None:
            raise ValueError(
                "Extracted tax total is missing; correct the document fields or provide explicit invoice lines and tax rules"
            )
        if tax_total < 0:
            raise ValueError("Extracted tax total cannot be negative")
        calculated_grand_total = money(subtotal - discount_total + tax_total)
        if grand_total is not None and abs(
            calculated_grand_total - money(grand_total)
        ) > Decimal("0.01"):
            raise ValueError(
                "Extracted subtotal, discount, tax and grand total do not reconcile; correct the document fields"
            )

        return [
            InvoiceItemCreate(
                description=line["description"],
                quantity=line["quantity"],
                unit=line["unit"],
                unit_price=line["unit_price"],
                discount=line["discount"],
            )
            for line in parsed_lines
        ], {
            "subtotal": subtotal,
            "discount_total": discount_total,
            "tax_total": money(tax_total),
            "grand_total": money(grand_total) if grand_total is not None else calculated_grand_total,
        }

    def validate(self, db: Session, invoice: Invoice, validator_id: int) -> Invoice:
        if invoice.status not in {"DRAFT", "PENDING_VALIDATION"}:
            raise ValueError("Invoice is not pending validation")
        document = db.get(Document, invoice.document_id)
        if document is None or document.status != "READY":
            raise ValueError("Source document has not passed human review")
        blocker = db.scalar(select(Anomaly).where(Anomaly.document_id == document.id, Anomaly.severity == "BLOCKER", Anomaly.status == "OPEN"))
        if blocker:
            raise ValueError("An unresolved blocker prevents validation")
        from sqlalchemy import update
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        year = invoice.issue_date.year
        try:
            claimed = db.execute(
                update(Invoice)
                .where(
                    Invoice.id == invoice.id,
                    Invoice.status.in_(["DRAFT", "PENDING_VALIDATION"]),
                )
                .values(status="VALIDATING")
            )
            if claimed.rowcount != 1:
                raise ValueError("Invoice validation is already in progress or complete")

            dialect = db.get_bind().dialect.name
            insert = sqlite_insert if dialect == "sqlite" else pg_insert if dialect == "postgresql" else None
            if insert is None:
                raise RuntimeError(f"Invoice sequence is unsupported for database dialect {dialect}")
            statement = insert(InvoiceSequence).values(year=year, next_number=1)
            statement = statement.on_conflict_do_update(
                index_elements=[InvoiceSequence.year],
                set_={"next_number": InvoiceSequence.next_number + 1},
            ).returning(InvoiceSequence.next_number)
            number = db.scalar(statement)
            if number is None:
                raise RuntimeError("Unable to allocate invoice number")

            invoice.invoice_number = f"FS-{year}-{number:06d}"
            invoice.status = "ISSUED"
            invoice.validated_by = validator_id
            invoice.validated_at = datetime.now(UTC)
            db.add(AuditLog(
                user_id=validator_id,
                action="INVOICE_ISSUED",
                entity_type="Invoice",
                entity_id=str(invoice.public_id),
                previous_value="VALIDATING",
                new_value=invoice.invoice_number,
            ))
            self.persist_pdf(db, invoice)
            db.commit()
            db.refresh(invoice)
            return invoice
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def persist_pdf(db: Session, invoice: Invoice) -> tuple[str, str, str]:
        """Store the current PDF as a required R2 artifact and persist its digest."""

        from app.storage.manager import R2StorageUnavailable, StorageManager
        from app.utils.hashing import sha256_bytes

        content = render_invoice_pdf(db, invoice)
        key = f"invoices/{invoice.public_id}/invoice.pdf"
        try:
            backend, _local_path = StorageManager().save_essential(key, content)
        except R2StorageUnavailable as exc:
            from app.core.exceptions import ServiceUnavailableError

            raise ServiceUnavailableError(
                "Invoice PDF could not be saved to R2; the invoice was not issued"
            ) from exc
        digest = sha256_bytes(content)
        invoice.pdf_storage_backend = backend
        invoice.pdf_storage_key = key
        invoice.pdf_sha256 = digest
        invoice.pdf_format_version = PDF_FORMAT_VERSION
        return backend, key, digest

    def ensure_pdf(self, db: Session, invoice: Invoice) -> tuple[str, str, str]:
        """Return persisted PDF metadata, generating/updating the artifact if needed."""

        if (
            invoice.status == "ISSUED"
            and invoice.pdf_storage_backend == "r2"
            and invoice.pdf_storage_key
            and invoice.pdf_sha256
            and invoice.pdf_format_version == PDF_FORMAT_VERSION
        ):
            return (
                invoice.pdf_storage_backend,
                invoice.pdf_storage_key,
                invoice.pdf_sha256,
            )
        metadata = self.persist_pdf(db, invoice)
        db.commit()
        db.refresh(invoice)
        return metadata
