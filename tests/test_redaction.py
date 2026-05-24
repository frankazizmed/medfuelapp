from medfuel.extract.redaction import redact


def test_redact_replaces_pii_patterns_and_counts():
    text = (
        "Patient John Doe, MRN: 12345678, DOB: 03/15/1962. "
        "Contact: john.doe@example.com, phone (415) 555-1234. "
        "SSN 123-45-6789. Card 4111-1111-1111-1111."
    )
    result = redact(text)
    assert "[REDACTED:email]" in result.text
    assert "[REDACTED:phone]" in result.text
    assert "[REDACTED:ssn]" in result.text
    assert "[REDACTED:mrn]" in result.text
    assert "[REDACTED:dob]" in result.text
    assert "[REDACTED:credit_card]" in result.text
    # original PII tokens should be gone
    assert "john.doe@example.com" not in result.text
    assert "123-45-6789" not in result.text
    assert result.counts["email"] == 1
    assert result.counts["ssn"] == 1
    assert result.total >= 6


def test_redact_passes_clean_text_unchanged():
    text = "FDA approved Acmenil on January 15, 2025 for adult patients."
    result = redact(text)
    assert result.text == text
    assert result.counts == {}
    assert result.total == 0
