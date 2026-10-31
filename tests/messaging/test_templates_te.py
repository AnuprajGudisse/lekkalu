# Copyright (c) 2026 Lekkalu
from app.messaging import templates_te as t


def test_indian_digit_grouping():
    assert t.format_inr(0) == "₹0"
    assert t.format_inr(50) == "₹0.50"
    assert t.format_inr(250000) == "₹2,500"
    assert t.format_inr(10000000) == "₹1,00,000"
    assert t.format_inr(123456700) == "₹12,34,567"
    assert t.format_inr(150050) == "₹1,500.50"
    assert t.format_inr(-50000) == "-₹500"


def test_credit_sale_reply_shows_amount_and_balance():
    reply = t.credit_sale("లక్ష్మి", 250000, 400000)
    assert "₹2,500" in reply
    assert "₹4,000" in reply


def test_repayment_reply_shows_advance_when_overpaid():
    assert "₹500 అడ్వాన్స్" in t.payment_received("లక్ష్మి", 200000, -50000)
