from decimal import Decimal

from app.services.calculation_service import calculate_line, money


def test_calculation_uses_decimal_and_rounding():
    net, tax, gross = calculate_line(Decimal("3"), Decimal("100.125"), Decimal("10"), Decimal("18"))

    assert net == Decimal("290.38")
    assert tax == Decimal("52.27")
    assert gross == Decimal("342.65")


def test_money_rounds_half_up():
    assert money(Decimal("1.005")) == Decimal("1.01")
