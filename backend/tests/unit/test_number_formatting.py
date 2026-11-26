from decimal import Decimal

from app.utils.number_formatting import format_decimal


def test_format_decimal_removes_only_insignificant_fractional_zeroes():
    assert format_decimal(Decimal("8.000000")) == "8"
    assert format_decimal(Decimal("381000.000000")) == "381000"
    assert format_decimal(Decimal("1.250000")) == "1.25"
    assert format_decimal(Decimal("1000000")) == "1000000"
    assert format_decimal(Decimal("-0.000000")) == "0"
