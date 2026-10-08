"""Che dữ liệu cá nhân/khách hàng trước khi gửi sang LLM.

Thay giá trị nhạy cảm bằng token như [SĐT_1], [STK_2]... và giữ bảng ánh xạ
trong bộ nhớ để khôi phục ở câu trả lời (người dùng vốn có quyền xem dữ liệu
của chính họ). Bảng ánh xạ không bao giờ rời khỏi backend.

Thứ tự áp dụng quan trọng: email -> số thẻ (Luhn) -> SĐT -> CCCD/CMND -> số tài khoản.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Chuỗi số dài, có thể nhóm bằng khoảng trắng (số thẻ, số tài khoản).
# Không coi '-' là phân cách để tránh nhận nhầm ngày dạng 2026-10-08.
DIGIT_RUN_RE = re.compile(r"(?<![\w-])\d(?: ?\d){7,18}(?![\w-])")
PHONE_RE = re.compile(r"(?<!\d)(?:\+84|0084|0)(?:3|5|7|8|9)\d{8}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


@dataclass
class MaskResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)


class PiiMasker:
    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}
        self._reverse: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def _token(self, label: str, value: str) -> str:
        if value in self._reverse:
            return self._reverse[value]
        self._counters[label] = self._counters.get(label, 0) + 1
        tok = f"[{label}_{self._counters[label]}]"
        self.mapping[tok] = value
        self._reverse[value] = tok
        return tok

    def _classify_digits(self, raw: str) -> str | None:
        digits = re.sub(r"\D", "", raw)
        n = len(digits)
        if 13 <= n <= 19 and _luhn_ok(digits):
            return "THẺ"
        if n == 12:
            return "CCCD"
        if n == 9:
            return "CMND"
        if 8 <= n <= 19:
            return "STK"
        return None

    def mask(self, text: str) -> str:
        if not text:
            return text
        text = EMAIL_RE.sub(lambda m: self._token("EMAIL", m.group(0)), text)
        text = PHONE_RE.sub(lambda m: self._token("SĐT", m.group(0)), text)

        def repl(m: re.Match) -> str:
            label = self._classify_digits(m.group(0))
            return self._token(label, m.group(0)) if label else m.group(0)

        return DIGIT_RUN_RE.sub(repl, text)

    def unmask(self, text: str) -> str:
        if not text:
            return text
        for tok, val in self.mapping.items():
            text = text.replace(tok, val)
        return text


def mask_text(text: str) -> MaskResult:
    m = PiiMasker()
    return MaskResult(m.mask(text), dict(m.mapping))
