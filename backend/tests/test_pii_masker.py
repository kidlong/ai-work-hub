from app.ai.pii_masker import PiiMasker


def test_masks_phone_account_email_and_restores():
    m = PiiMasker()
    src = "KH chủ TK 0123456789012, SĐT 0912345678, email kh.a@gmail.com báo lỗi E-504 ngày 2026-10-08 lúc 08:30."
    masked = m.mask(src)
    assert "0912345678" not in masked
    assert "0123456789012" not in masked
    assert "kh.a@gmail.com" not in masked
    assert "[SĐT_1]" in masked and "[EMAIL_1]" in masked
    # Không che nhầm ngày, giờ, mã lỗi
    assert "2026-10-08" in masked and "08:30" in masked and "E-504" in masked
    assert m.unmask(masked) == src


def test_card_number_luhn_and_cccd():
    m = PiiMasker()
    masked = m.mask("Thẻ 4111 1111 1111 1111, CCCD 001203004567, CMND 012345678")
    assert "[THẺ_1]" in masked
    assert "[CCCD_1]" in masked
    assert "[CMND_1]" in masked


def test_same_value_same_token_and_international_phone():
    m = PiiMasker()
    masked = m.mask("Gọi +84912345678 hoặc +84912345678")
    assert masked.count("[SĐT_1]") == 2


def test_does_not_mask_jira_keys_or_small_numbers():
    m = PiiMasker()
    text = "CORE-2481 xử lý 2 triệu giao dịch, hạn mức 50 tỷ"
    assert m.mask(text) == text
