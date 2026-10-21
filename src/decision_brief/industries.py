"""Industry exposure to macro factors, from the team significance matrix."""

from __future__ import annotations

from decision_brief.models import Factor

# Rows are 0..3 exposure for F1..F9. Caps at 3 after company bonuses.
INDUSTRY_EXPOSURE: dict[str, tuple[int, ...]] = {
    "fuel": (2, 2, 2, 1, 1, 3, 2, 1, 0),
    "metals": (2, 3, 1, 1, 1, 1, 2, 1, 2),
    "agri": (2, 2, 3, 2, 1, 1, 1, 1, 0),
    "housing": (3, 1, 2, 2, 2, 1, 2, 2, 0),
    "infrastructure": (3, 1, 2, 0, 2, 1, 3, 2, 1),
    "real_estate": (3, 0, 1, 2, 1, 0, 0, 2, 0),
    "auto": (3, 3, 2, 3, 1, 1, 2, 1, 0),
    "retail": (1, 2, 3, 3, 2, 1, 0, 1, 0),
    "horeca": (1, 1, 2, 3, 3, 0, 0, 0, 0),
    "transport": (2, 1, 2, 1, 2, 3, 1, 1, 0),
    "energy": (2, 1, 2, 0, 1, 1, 2, 3, 0),
    "it": (1, 2, 1, 1, 3, 0, 1, 1, 0),
    "finance": (3, 2, 1, 0, 0, 1, 1, 3, 2),
    "machinery": (2, 2, 1, 1, 2, 0, 3, 1, 1),
    "chemicals": (2, 3, 1, 1, 1, 2, 0, 2, 1),
    "wholesale": (2, 3, 2, 2, 1, 1, 0, 1, 0),
    "services": (1, 1, 1, 1, 2, 0, 1, 0, 0),
}

_FACTOR_ORDER: tuple[Factor, ...] = tuple(Factor)

# First matching OKVED prefix wins.
_OKVED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("19", "fuel"),
    ("06", "fuel"),
    ("24", "metals"),
    ("25", "metals"),
    ("01", "agri"),
    ("10", "agri"),
    ("11", "agri"),
    ("41", "housing"),
    ("42", "infrastructure"),
    ("68", "real_estate"),
    ("45", "auto"),
    ("47", "retail"),
    ("55", "horeca"),
    ("56", "horeca"),
    ("49", "transport"),
    ("35", "energy"),
    ("61", "it"),
    ("62", "it"),
    ("63", "it"),
    ("64", "finance"),
    ("26", "machinery"),
    ("27", "machinery"),
    ("28", "machinery"),
    ("20", "chemicals"),
    ("16", "chemicals"),
    ("46", "wholesale"),
)


def normalize_okved(okved: str) -> str:
    """Collapse equivalent OKVED spellings to one code.

    ``41.2`` and ``41.20`` are the same group: a trailing zero in a
    segment after the class is dropped. The class keeps its digits,
    so ``01`` stays ``01``. A subclass with several groups, such as
    ``49.4``, is left as written and is not turned into ``49.40``.
    """
    cleaned = okved.strip().replace(",", ".").replace(" ", "")
    if not cleaned:
        return ""
    parts = [part for part in cleaned.split(".") if part]
    if not parts:
        return ""
    normalized = [parts[0]]
    for part in parts[1:]:
        if part.isdigit():
            normalized.append(part.rstrip("0") or "0")
        else:
            normalized.append(part)
    return ".".join(normalized)


def industry_for_okved(okved: str) -> str:
    """Map an OKVED code to an industry key. Unknown codes become services.

    The code is normalized first, so ``41.2`` and ``41.20`` take one path.
    """
    normalized = normalize_okved(okved)
    for prefix, industry in _OKVED_PREFIXES:
        if normalized.startswith(prefix):
            return industry
    return "services"


def base_exposure(industry: str) -> dict[Factor, int]:
    """Return the 0..3 industry baseline for every factor."""
    row = INDUSTRY_EXPOSURE.get(industry, INDUSTRY_EXPOSURE["services"])
    return dict(zip(_FACTOR_ORDER, row, strict=True))
