"""Small score bonus for preferred market themes (quantum / data center)."""

from __future__ import annotations

THEME_SCORE_BONUS = 1.0

THEME_LABELS_HE: dict[str, str] = {
    "quantum": "קוונטים",
    "datacenter": "Data center",
}

# Pure-play / thematic names — not mega-cap AI (NVDA/AVGO) that already dominate ranks.
_QUANTUM: frozenset[str] = frozenset(
    {
        "IONQ",
        "RGTI",
        "QBTS",
        "QUBT",
        "ARQQ",
    }
)

_DATACENTER: frozenset[str] = frozenset(
    {
        "SMCI",
        "VRT",
        "ANET",
        "EQIX",
        "DLR",
        "AMT",
        "CCI",
        "DELL",
        "HPE",
        "NTAP",
        "PSTG",
        "WDC",
        "STX",
    }
)


def theme_tags(symbol: str) -> list[str]:
    sym = str(symbol or "").strip().upper()
    tags: list[str] = []
    if sym in _QUANTUM:
        tags.append("quantum")
    if sym in _DATACENTER:
        tags.append("datacenter")
    return tags


def theme_score_bonus(symbol: str) -> float:
    """Flat +THEME_SCORE_BONUS once if the symbol matches any preferred theme."""
    return THEME_SCORE_BONUS if theme_tags(symbol) else 0.0


def theme_labels_he(symbol: str) -> list[str]:
    return [THEME_LABELS_HE[t] for t in theme_tags(symbol) if t in THEME_LABELS_HE]


def theme_label_line(symbol: str | None = None, tags: list[str] | None = None) -> str:
    """Short Hebrew suffix for cubes / explanations, or empty."""
    if tags is None:
        tags = theme_tags(symbol or "")
    labels = [THEME_LABELS_HE[t] for t in tags if t in THEME_LABELS_HE]
    if not labels:
        return ""
    return "נושא: " + " · ".join(labels)
