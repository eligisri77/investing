"""Large source universe for the weekly watchlist funnel.

The weekly scan ranks these liquid, tradeable US symbols and selects the best
~60 for the coming week. The daily plan then only scans that shortlist.

Focus: liquid large/mid-cap equities with enough volatility to produce
speculative momentum setups, plus popular leveraged/sector ETFs.
"""

from __future__ import annotations

# Mega/large-cap tech + growth
_TECH = [
    "AAPL", "MSFT", "NVDA", "AMD", "AVGO", "MU", "ARM", "MRVL", "INTC", "QCOM",
    "TXN", "ON", "SMCI", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "ADI", "NXPI",
    "GOOGL", "META", "AMZN", "NFLX", "CRM", "ORCL", "ADBE", "NOW", "SNOW", "CRWD",
    "PANW", "ZS", "NET", "DDOG", "MDB", "PLTR", "SNAP", "PINS", "SHOP", "UBER",
    "ABNB", "DASH", "RBLX", "U", "DUOL", "APP", "PATH", "AI", "SOUN", "BBAI",
]

# High-beta / momentum / retail favorites
_MOMENTUM = [
    "TSLA", "COIN", "HOOD", "SOFI", "MSTR", "MARA", "RIOT", "CLSK", "CVNA",
    "AFRM", "UPST", "DKNG", "RKLB", "ASTS", "ACHR", "JOBY", "LUNR", "IONQ",
    "RGTI", "QBTS", "SMR", "OKLO", "CELH", "ELF", "ANF", "CROX", "NIO", "XPEV",
    "LI", "LCID", "RIVN", "PLUG", "FSLR", "ENPH", "RUN", "SEDG",
]

# Financials / industrials / energy / healthcare large caps (liquid, moves on catalysts)
_BROAD = [
    "JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "BLK", "AXP", "V", "MA",
    "PYPL", "SQ", "BRK-B", "CAT", "DE", "BA", "GE", "HON", "LMT", "RTX", "NOC",
    "XOM", "CVX", "COP", "OXY", "SLB", "HAL", "MPC", "VLO", "UNH", "LLY", "PFE",
    "MRNA", "BNTX", "ABBV", "JNJ", "MRK", "BMY", "GILD", "AMGN", "VRTX", "REGN",
    "ISRG", "DXCM", "COST", "WMT", "TGT", "HD", "LOW", "NKE", "SBUX", "MCD",
    "DIS", "CMCSA", "T", "VZ", "KO", "PEP",
]

# Biotech / speculative small-mid cap (higher volatility)
_BIOTECH = [
    "CRSP", "NTLA", "BEAM", "EDIT", "SANA", "DNA", "RXRX", "SRPT", "ARWR",
    "EXAS", "TDOC", "HIMS",
]

# Leveraged & sector ETFs (very volatile — core of the speculative strategy)
_ETFS = [
    "TQQQ", "SQQQ", "SOXL", "SOXS", "SPXL", "SPXS", "TNA", "TZA", "FNGU",
    "LABU", "LABD", "WEBL", "NAIL", "DFEN", "NVDL", "TSLL", "BITX", "ETHU",
    "UVXY", "VXX", "BITO", "SMH", "ARKK", "XBI", "GBTC", "IBIT", "MSTX",
]


def _dedupe(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for sym in group:
            s = sym.strip().upper()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


SOURCE_UNIVERSE: list[str] = _dedupe(_TECH, _MOMENTUM, _BROAD, _BIOTECH, _ETFS)
