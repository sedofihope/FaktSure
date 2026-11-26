from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Round a financial amount to two decimal places, half up."""

    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def calculate_line(quantity: Decimal, unit_price: Decimal, discount: Decimal = Decimal("0"), tax_rate: Decimal = Decimal("0")) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate net line, tax, and gross line using Decimal arithmetic."""

    gross = money(quantity * unit_price)
    net = money(gross - discount)
    tax = money(net * tax_rate / Decimal("100"))
    return net, tax, money(net + tax)
