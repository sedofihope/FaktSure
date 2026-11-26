from decimal import Decimal


def format_decimal(value: Decimal) -> str:
    """Format decimals without insignificant fractional zeroes."""

    if value == 0:
        return "0"
    formatted = format(value.normalize(), "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
