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
    "TEAM", "WDAY", "INTU", "ADP", "SNPS", "CDNS", "ANET", "FTNT", "OKTA", "ESTC",
    "TTD", "ROKU", "SPOT", "ZM", "DOCU", "TWLO", "HUBS", "GTLB", "S", "CRBG",
]

# High-beta / momentum / retail favorites
_MOMENTUM = [
    "TSLA", "COIN", "HOOD", "SOFI", "MSTR", "MARA", "RIOT", "CLSK", "CVNA",
    "AFRM", "UPST", "DKNG", "RKLB", "ASTS", "ACHR", "JOBY", "LUNR", "IONQ",
    "RGTI", "QBTS", "SMR", "OKLO", "CELH", "ELF", "ANF", "CROX", "NIO", "XPEV",
    "LI", "LCID", "RIVN", "PLUG", "FSLR", "ENPH", "RUN", "SEDG",
    "HIMS", "DUOL", "CAVA", "BIRK", "ONON", "DECK", "LULU", "PTON", "BYND",
    "GME", "AMC", "BB", "NOK", "SNDL", "TLRY", "CGC", "OPEN", "RDFN", "COMP",
]

# Financials / industrials / energy / healthcare large caps (liquid, moves on catalysts)
_BROAD = [
    "JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "BLK", "AXP", "V", "MA",
    "PYPL", "SQ", "BRK-B", "CAT", "DE", "BA", "GE", "HON", "LMT", "RTX", "NOC",
    "XOM", "CVX", "COP", "OXY", "SLB", "HAL", "MPC", "VLO", "UNH", "LLY", "PFE",
    "MRNA", "BNTX", "ABBV", "JNJ", "MRK", "BMY", "GILD", "AMGN", "VRTX", "REGN",
    "ISRG", "DXCM", "COST", "WMT", "TGT", "HD", "LOW", "NKE", "SBUX", "MCD",
    "DIS", "CMCSA", "T", "VZ", "KO", "PEP",
    "IBM", "CSCO", "ACN", "SAP", "SHOP", "SE", "MELI", "JD", "BABA", "PDD",
    "F", "GM", "STLA", "RACE", "TM", "HMC", "SONY", "NU", "XP", "IBKR",
    "COF", "USB", "PNC", "TFC", "BK", "STT", "MET", "PRU", "AIG", "ALL",
    "FCX", "NEM", "GOLD", "AA", "X", "CLF", "NUE", "STLD", "VALE", "RIO",
    "DAL", "UAL", "AAL", "LUV", "ALK", "JBLU", "CCL", "RCL", "NCLH", "MAR",
    "HLT", "BKNG", "EXPE", "ABNB", "WYNN", "LVS", "MGM", "CZR", "PENN", "DKNG",
]

# Consumer / retail / media additions
_CONSUMER = [
    "COST", "WMT", "TGT", "HD", "LOW", "BJ", "DG", "DLTR", "KR", "SYY",
    "PG", "CL", "UL", "EL", "COTY", "ULTA", "BBY", "RH", "WSM", "TPX",
    "NKE", "ADDYY", "UAA", "VFC", "SKX", "CROX", "DECK", "ONON", "BIRK",
    "CMG", "YUM", "DPZ", "WING", "SHAK", "TXRH", "EAT", "CAVA", "WEN",
    "PARA", "WBD", "FOX", "FOXA", "NWSA", "NYT", "MTCH", "BMBL", "IAC",
]

# Semis / hardware / AI infra extras
_SEMIS = [
    "NVDA", "AMD", "AVGO", "MU", "INTC", "QCOM", "ARM", "MRVL", "ON", "SWKS",
    "MPWR", "MCHP", "STM", "GFS", "WOLF", "ALGM", "CRUS", "LSCC", "SLAB",
    "TSM", "ASML", "AMAT", "LRCX", "KLAC", "TER", "ENTG", "ACLS", "AEHR",
    "SMCI", "DELL", "HPQ", "HPE", "NTAP", "PSTG", "WDC", "STX", "SNDK",
]

# Biotech / speculative small-mid cap (higher volatility)
_BIOTECH = [
    "CRSP", "NTLA", "BEAM", "EDIT", "SANA", "DNA", "RXRX", "SRPT", "ARWR",
    "EXAS", "TDOC", "HIMS", "ILMN", "PACB", "TWST", "CDNA", "VCYT", "GH",
    "NVAX", "SAVA", "BIIB", "ALNY", "INCY", "BMRN", "UTHR", "HALO", "NBIX",
]

# Energy / clean tech / materials
_ENERGY = [
    "XOM", "CVX", "COP", "OXY", "EOG", "DVN", "FANG", "APA", "HES", "MRO",
    "SLB", "HAL", "BKR", "FTI", "NOV", "RIG", "VAL", "TDW", "HP",
    "MPC", "VLO", "PSX", "PBF", "DK", "CEG", "VST", "NRG", "TLN",
    "FSLR", "ENPH", "SEDG", "RUN", "ARRY", "SHLS", "STEM", "BE", "PLUG",
    "FCEL", "BLDP", "QS", "CHPT", "EVGO",
]

# Leveraged & sector ETFs (very volatile — core of the speculative strategy)
_ETFS = [
    "TQQQ", "SQQQ", "SOXL", "SOXS", "SPXL", "SPXS", "TNA", "TZA", "FNGU",
    "LABU", "LABD", "WEBL", "NAIL", "DFEN", "NVDL", "TSLL", "BITX", "ETHU",
    "UVXY", "VXX", "BITO", "SMH", "ARKK", "XBI", "GBTC", "IBIT", "MSTX",
    "QQQ", "SPY", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY",
    "XLP", "XLB", "XLU", "XLRE", "KWEB", "EEM", "EFA", "HYG", "TLT", "GLD",
    "SLV", "UNG", "USO", "URA", "LIT", "BOTZ", "HACK", "CIBR", "ARKG", "ARKF",
    "SOXX", "IGV", "SKYY", "CLOU", "TAN", "ICLN", "PBW", "JETS", "XOP", "OIH",
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


SOURCE_UNIVERSE: list[str] = _dedupe(
    _TECH,
    _MOMENTUM,
    _BROAD,
    _CONSUMER,
    _SEMIS,
    _BIOTECH,
    _ENERGY,
    _ETFS,
)
