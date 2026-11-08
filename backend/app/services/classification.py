"""Transaction-code classification and role normalisation (SIG-01, SIG-03, SIG-04)."""

from __future__ import annotations

from dataclasses import dataclass

CEO = "CEO"
CFO = "CFO"
COO = "COO"
CTO = "CTO"
PRESIDENT = "President"
DIRECTOR = "Director"
TEN_PERCENT_OWNER = "10% Owner"
OTHER = "Other"

STARRED_ROLES = frozenset({CEO, CFO})


@dataclass(frozen=True, slots=True)
class CodeInfo:
    type_label: str
    action: str
    counts: bool


CODE_MAP: dict[str, CodeInfo] = {
    "P": CodeInfo("Open-market buy", "buy", True),
    "S": CodeInfo("Open-market sell", "sell", True),
    "A": CodeInfo("Award / grant", "other", False),
    "M": CodeInfo("Option exercise / conversion", "other", False),
    "X": CodeInfo("Option exercise / conversion", "other", False),
    "C": CodeInfo("Option exercise / conversion", "other", False),
    "F": CodeInfo("Tax withholding", "other", False),
    "G": CodeInfo("Gift", "other", False),
    "D": CodeInfo("Disposed to issuer", "other", False),
}

OTHER_CODE = CodeInfo("Other", "other", False)


def classify(code: str) -> CodeInfo:
    """Map a Form 4 code; anything unmapped is treated as Other (SRS 6.2)."""

    return CODE_MAP.get(code.strip().upper(), OTHER_CODE)


def normalise_role(
    *,
    officer_title: str | None,
    is_director: bool = False,
    is_officer: bool = False,
    is_ten_percent_owner: bool = False,
) -> str:
    """Normalise the free-text title to the eight roles in SIG-03."""

    title = (officer_title or "").strip()
    lowered = title.lower()

    if "chief executive" in lowered or _has_token(lowered, "ceo"):
        return CEO
    if "chief financial" in lowered or _has_token(lowered, "cfo"):
        return CFO
    if "chief operating" in lowered or _has_token(lowered, "coo"):
        return COO
    if "chief technology" in lowered or _has_token(lowered, "cto"):
        return CTO
    if "president" in lowered and "vice" not in lowered:
        return PRESIDENT
    if is_director:
        return DIRECTOR
    if is_ten_percent_owner:
        return TEN_PERCENT_OWNER
    if is_officer and title:
        return OTHER
    return OTHER


def _has_token(text: str, token: str) -> bool:
    return token in text.replace(".", "").replace(",", "").split()


def is_starred(action: str, role: str) -> bool:
    """A row is starred only for an open-market buy by a CEO or CFO (SIG-04)."""

    return action == "buy" and role in STARRED_ROLES
