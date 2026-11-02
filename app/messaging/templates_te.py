# Copyright (c) 2026 Lekkalu
"""Telugu replies. Amounts come from ledger rows and names from customer records, never from model text."""


def format_inr(paise: int) -> str:
    """Indian digit grouping: ₹1,00,000. Paise shown only when not zero."""
    sign = "-" if paise < 0 else ""
    rupees, rest = divmod(abs(paise), 100)
    digits = str(rupees)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    text = ",".join([*groups, tail])
    return f"{sign}₹{text}" + (f".{rest:02d}" if rest else "")


def _owed(balance: int) -> str:
    if balance > 0:
        return f"మొత్తం బాకీ {format_inr(balance)}."
    if balance < 0:
        return f"{format_inr(-balance)} అడ్వాన్స్ ఉంది."
    return "బాకీ ఏమీ లేదు."


def sale(amount: int) -> str:
    return f"✅ అమ్మకం రాశాను: {format_inr(amount)}."


def credit_sale(name: str, amount: int, balance: int) -> str:
    return f"✅ {name} కి {format_inr(amount)} అప్పు రాశాను. {_owed(balance)}"


def payment_received(name: str, amount: int, balance: int) -> str:
    return f"✅ {name} నుండి {format_inr(amount)} వచ్చింది. {_owed(balance)}"


def purchase(amount: int) -> str:
    return f"✅ కొనుగోలు రాశాను: {format_inr(amount)}."


def expense(amount: int) -> str:
    return f"✅ ఖర్చు రాశాను: {format_inr(amount)}."


ASK_AMOUNT = "ఎంత డబ్బు? మొత్తం కూడా చెప్పి మళ్ళీ పంపండి."
ASK_AMOUNT_UNCLEAR = "మొత్తం సరిగ్గా అర్థం కాలేదు. మొత్తం మళ్ళీ చెప్పండి."
UNKNOWN_CUSTOMER = "ఈ కస్టమర్ పేరు నా దగ్గర లేదు లేదా స్పష్టంగా లేదు. పూర్తి పేరుతో మళ్ళీ పంపండి."
SEND_SEPARATELY = "ఒక్కో లావాదేవీని విడిగా పంపండి."
NOT_YET = "ఈ సదుపాయం త్వరలో వస్తుంది."
NOT_UNDERSTOOD = "అర్థం కాలేదు. మళ్ళీ చెప్పండి."
SEND_AGAIN = "ఏదో పొరపాటు జరిగింది. దయచేసి మళ్ళీ పంపండి."
