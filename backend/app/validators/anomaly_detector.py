import json
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.audit_log import AuditLog
from app.models.client import Client
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.models.invoice import Invoice
from app.models.product import Product
from app.models.product_price import ProductPrice


class AnomalyDetector:
    """Run deterministic, backend-owned document checks."""

    REQUIRED_FIELDS = {
        "client_name",
        "document_date",
        "document_number",
        "currency",
        "subtotal",
        "grand_total",
    }

    @staticmethod
    def _value(field: ExtractedField | None) -> str | None:
        if field is None:
            return None
        return field.corrected_value if field.corrected_value is not None else field.value

    @staticmethod
    def _normalized(value: str | None) -> str:
        return " ".join((value or "").casefold().split())

    @staticmethod
    def _decimal(value: str | None) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(value.replace(",", "").strip())
        except Exception:
            return None

    @staticmethod
    def _anomaly(
        document_id: int,
        anomaly_type: str,
        severity: str,
        description: str,
        field_name: str | None = None,
        expected_value: str | None = None,
        actual_value: str | None = None,
    ) -> Anomaly:
        return Anomaly(
            document_id=document_id,
            field_name=field_name,
            anomaly_type=anomaly_type,
            severity=severity,
            description=description,
            expected_value=expected_value,
            actual_value=actual_value,
        )

    def detect(
        self,
        db: Session,
        document: Document,
        *,
        commit: bool = True,
        actor_id: int | None = None,
    ) -> list[Anomaly]:
        """Replace current open anomalies with deterministic validation results."""

        db.query(Anomaly).filter(
            Anomaly.document_id == document.id,
            Anomaly.status == "OPEN",
        ).delete()
        fields = db.scalars(
            select(ExtractedField).where(ExtractedField.document_id == document.id)
        ).all()
        by_name = {field.field_name: field for field in fields}
        anomalies: list[Anomaly] = []

        for field in fields:
            if (
                field.field_name in self.REQUIRED_FIELDS
                and (field.status == "MISSING" or not self._value(field))
            ):
                anomalies.append(self._anomaly(
                    document.id,
                    "MISSING_REQUIRED_FIELD",
                    "BLOCKER",
                    "Required extracted field is missing",
                    field_name=field.field_name,
                ))
            elif field.confidence < 0.5:
                anomalies.append(self._anomaly(
                    document.id,
                    "LOW_CONFIDENCE",
                    "WARNING",
                    "Field has low confidence or no reliably matched source evidence",
                    field_name=field.field_name,
                    actual_value=field.value,
                ))

        if not any(field.field_name.startswith("item.") for field in fields):
            anomalies.append(self._anomaly(
                document.id,
                "MISSING_REQUIRED_FIELD",
                "BLOCKER",
                "At least one invoice line is required",
                field_name="items",
            ))

        duplicate = db.scalar(
            select(Document.id).where(
                Document.sha256 == document.sha256,
                Document.id != document.id,
            ).limit(1)
        )
        if duplicate is not None:
            anomalies.append(self._anomaly(
                document.id,
                "DUPLICATE_DOCUMENT",
                "BLOCKER",
                "An identical document already exists",
                expected_value=str(duplicate),
                actual_value=document.sha256,
            ))

        document_number = self._value(by_name.get("document_number"))
        if document_number:
            duplicate_order = db.scalar(
                select(ExtractedField.document_id)
                .join(Document, Document.id == ExtractedField.document_id)
                .outerjoin(Invoice, Invoice.document_id == Document.id)
                .where(
                    ExtractedField.document_id != document.id,
                    ExtractedField.field_name == "document_number",
                    func.coalesce(
                        ExtractedField.corrected_value,
                        ExtractedField.value,
                    ) == document_number,
                    or_(Invoice.id.is_(None), Invoice.status != "CANCELLED"),
                )
                .limit(1)
            )
            if duplicate_order is not None:
                anomalies.append(self._anomaly(
                    document.id,
                    "DUPLICATE_ORDER",
                    "BLOCKER",
                    "This order number has already been processed",
                    field_name="document_number",
                    expected_value=str(duplicate_order),
                    actual_value=document_number,
                ))

        client_name = self._value(by_name.get("client_name"))
        tax_identifier = self._value(by_name.get("client_tax_identifier"))
        rccm = self._value(by_name.get("client_rccm"))
        active_clients = db.scalars(
            select(Client).where(Client.is_active.is_(True))
        ).all()
        matching_client = next(
            (
                client for client in active_clients
                if self._normalized(client.name) == self._normalized(client_name)
                or (
                    tax_identifier
                    and client.tax_identifier
                    and client.tax_identifier.casefold() == tax_identifier.casefold()
                )
                or (
                    rccm
                    and client.rccm
                    and client.rccm.casefold() == rccm.casefold()
                )
            ),
            None,
        )
        if (client_name or tax_identifier or rccm) and matching_client is None:
            candidates = sorted(
                (
                    (
                        SequenceMatcher(
                            None,
                            self._normalized(client_name),
                            self._normalized(client.name),
                        ).ratio(),
                        client.name,
                    )
                    for client in active_clients
                ),
                reverse=True,
            ) if client_name else []
            anomalies.append(self._anomaly(
                document.id,
                "CLIENT_UNKNOWN",
                "WARNING",
                "Client does not match an active reference client",
                field_name="client_name" if client_name else "client_rccm" if rccm else "client_tax_identifier",
                expected_value=candidates[0][1] if candidates and candidates[0][0] >= 0.6 else None,
                actual_value=client_name,
            ))

        document_date_value = self._value(by_name.get("document_date"))
        try:
            effective_date = date.fromisoformat(document_date_value) if document_date_value else None
        except ValueError:
            effective_date = None
            anomalies.append(self._anomaly(
                document.id,
                "CONTRADICTORY_FIELD",
                "BLOCKER",
                "Document date is not a valid ISO date",
                field_name="document_date",
                actual_value=document_date_value,
            ))
        currency = (self._value(by_name.get("currency")) or "").upper()
        line_sum = Decimal("0")
        has_line_total = False

        active_products = db.scalars(
            select(Product).where(Product.is_active.is_(True))
        ).all()
        for field in fields:
            if not field.field_name.startswith("item."):
                continue
            try:
                item = json.loads(self._value(field) or "{}")
            except json.JSONDecodeError:
                anomalies.append(self._anomaly(
                    document.id,
                    "CONTRADICTORY_FIELD",
                    "BLOCKER",
                    "Extracted line item is not valid structured data",
                    field_name=field.field_name,
                ))
                continue

            description = item.get("description")
            sku = item.get("sku")
            quantity = self._decimal(str(item["quantity"])) if item.get("quantity") is not None else None
            unit_price = self._decimal(str(item["unit_price"])) if item.get("unit_price") is not None else None
            discount = self._decimal(str(item.get("discount") or "0"))
            line_total = self._decimal(str(item["line_total"])) if item.get("line_total") is not None else None
            product = next(
                (
                    candidate for candidate in active_products
                    if (sku and candidate.sku and sku.casefold() == candidate.sku.casefold())
                    or (
                        description
                        and self._normalized(description) == self._normalized(candidate.name)
                    )
                ),
                None,
            )

            if product is None:
                product_candidates = sorted(
                    (
                        (
                            SequenceMatcher(
                                None,
                                self._normalized(description),
                                self._normalized(candidate.name),
                            ).ratio(),
                            candidate.name,
                        )
                        for candidate in active_products
                    ),
                    reverse=True,
                )
                anomalies.append(self._anomaly(
                    document.id,
                    "PRODUCT_UNKNOWN",
                    "WARNING",
                    "Line item does not match an active reference product",
                    field_name=field.field_name,
                    expected_value=(
                        product_candidates[0][1]
                        if product_candidates and product_candidates[0][0] >= 0.6
                        else None
                    ),
                    actual_value=description or sku,
                ))
            elif effective_date and unit_price is not None:
                reference = db.scalar(
                    select(ProductPrice).where(
                        ProductPrice.product_id == product.id,
                        ProductPrice.valid_from <= effective_date,
                        or_(
                            ProductPrice.valid_until.is_(None),
                            ProductPrice.valid_until >= effective_date,
                        ),
                    ).order_by(ProductPrice.valid_from.desc()).limit(1)
                )
                if reference and reference.currency.upper() == currency:
                    if unit_price != reference.unit_price:
                        anomalies.append(self._anomaly(
                            document.id,
                            "PRICE_MISMATCH",
                            "WARNING",
                            "Extracted unit price differs from the reference price",
                            field_name=field.field_name,
                            expected_value=str(reference.unit_price),
                            actual_value=str(unit_price),
                        ))
                elif reference and reference.currency.upper() != currency:
                    anomalies.append(self._anomaly(
                        document.id,
                        "CURRENCY_MISMATCH",
                        "WARNING",
                        "Document currency differs from the reference price currency",
                        field_name="currency",
                        expected_value=reference.currency,
                        actual_value=currency,
                    ))

            if quantity is not None and (quantity <= 0 or quantity > 1000):
                anomalies.append(self._anomaly(
                    document.id,
                    "QUANTITY_UNUSUAL",
                    "WARNING",
                    "Quantity is non-positive or unusually large",
                    field_name=field.field_name,
                    expected_value="1..1000",
                    actual_value=str(quantity),
                ))
            if quantity is not None and unit_price is not None and discount is not None and line_total is not None:
                expected_line = (quantity * unit_price - discount).quantize(Decimal("0.01"))
                if expected_line != line_total.quantize(Decimal("0.01")):
                    anomalies.append(self._anomaly(
                        document.id,
                        "CONTRADICTORY_FIELD",
                        "BLOCKER",
                        "Line total differs from quantity times unit price less discount",
                        field_name=field.field_name,
                        expected_value=str(expected_line),
                        actual_value=str(line_total),
                    ))
            if line_total is not None:
                line_sum += line_total + (discount or Decimal("0"))
                has_line_total = True

        subtotal = self._decimal(self._value(by_name.get("subtotal")))
        discount_total = self._decimal(self._value(by_name.get("discount_total"))) or Decimal("0")
        tax = self._decimal(self._value(by_name.get("tax_total")))
        grand_total = self._decimal(self._value(by_name.get("grand_total")))
        if subtotal is not None and has_line_total:
            if abs(subtotal - line_sum) > Decimal("0.01"):
                anomalies.append(self._anomaly(
                    document.id,
                    "TOTAL_MISMATCH",
                    "BLOCKER",
                    "Subtotal differs from the sum of extracted line totals",
                    field_name="subtotal",
                    expected_value=str(line_sum),
                    actual_value=str(subtotal),
                ))
        if subtotal is not None and tax is not None and grand_total is not None:
            expected_grand_total = subtotal - discount_total + tax
            if abs(expected_grand_total - grand_total) > Decimal("0.01"):
                anomalies.append(self._anomaly(
                    document.id,
                    "TOTAL_MISMATCH",
                    "BLOCKER",
                    "Subtotal less discount plus tax does not equal grand total",
                    field_name="grand_total",
                    expected_value=str(expected_grand_total),
                    actual_value=str(grand_total),
                ))

        due_date_value = self._value(by_name.get("due_date"))
        if due_date_value and effective_date:
            try:
                due_date = date.fromisoformat(due_date_value)
                if due_date < effective_date:
                    anomalies.append(self._anomaly(
                        document.id,
                        "CONTRADICTORY_FIELD",
                        "BLOCKER",
                        "Due date precedes document date",
                        field_name="due_date",
                        expected_value=f">={effective_date.isoformat()}",
                        actual_value=due_date_value,
                    ))
            except ValueError:
                anomalies.append(self._anomaly(
                    document.id,
                    "CONTRADICTORY_FIELD",
                    "BLOCKER",
                    "Due date is not a valid ISO date",
                    field_name="due_date",
                    actual_value=due_date_value,
                ))

        db.add_all(anomalies)
        db.add(AuditLog(
            user_id=actor_id,
            action="DOCUMENT_ANOMALIES_DETECTED",
            entity_type="Document",
            entity_id=str(document.public_id),
            new_value=f"count={len(anomalies)}",
        ))
        if commit:
            db.commit()
        else:
            db.flush()
        return anomalies
