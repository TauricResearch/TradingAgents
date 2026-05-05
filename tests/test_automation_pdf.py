from automation.pdf import write_investment_pdf, write_text_pdf


def test_write_text_pdf_creates_pdf(tmp_path):
    path = write_text_pdf("# Title\n\n**Rating**: Buy\n\nBody", tmp_path / "report.pdf")
    data = path.read_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert b"/Type /Catalog" in data


def test_write_investment_pdf_includes_dashboard(tmp_path):
    signal = {
        "ticker": "CFISP500.SN",
        "action": "SELL",
        "rating": "Underweight",
        "confidence": "medium",
        "risk_reward": 1.67,
        "entry_price": 1663.6,
        "stop_loss": 1690.05,
        "take_profit": 1619.51,
        "position_bias": "avoid",
        "reasons": ["Portfolio Manager rating: Underweight."],
    }
    price_history = [
        {"date": "2026-04-29", "close": 100.0},
        {"date": "2026-04-30", "close": 102.0},
        {"date": "2026-05-01", "close": 101.0},
    ]
    path = write_investment_pdf(
        "# Trading Analysis Report: CFISP500.SN\n\nGenerated: 2026-05-04\n\n## Conclusion\n\nBody",
        tmp_path / "memo.pdf",
        signal=signal,
        price_history=price_history,
    )
    data = path.read_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert b"Investment Memo" in data
    assert b"Executive Dashboard" in data
    assert b"Price & Risk Map" in data
    assert b"Technical Snapshot" in data
    assert b"[GREEN]" not in data
    assert b"[RED]" not in data
    assert b"[!]" not in data
