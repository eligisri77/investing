import argparse
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd
import requests
import schedule
import yfinance as yf
from trading_pulse.agent.signal_sources import (
    DEFAULT_SIGNAL_SOURCES,
    DEFAULT_SOURCE_WEIGHTS,
    SOURCE_LABELS,
    build_signal_universe,
)
from trading_pulse.telegram.app_notify import clear_pending_plan, uses_app_notifications, uses_telegram_notifications
from trading_pulse.agent.strategy_backtest import backtest_symbol
from trading_pulse.telegram.telegram_store import append_message as log_telegram_message


from trading_pulse.core.app_paths import (
    CONFIG_FILE,
    DATA_DIR,
    PLANS_DIR,
    REPORTS_DIR,
    STATE_FILE,
)

DEFAULT_TICKERS = [
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "TSLA",
    "AMD",
    "GOOGL",
    "JPM",
    "XLF",
    "XLE",
    "XLK",
]

DEFAULT_SPECULATIVE_TICKERS = [
    "TQQQ",
    "SOXL",
    "LABU",
    "MSTR",
    "COIN",
    "SMCI",
    "RKLB",
    "PLTR",
    "AMD",
    "NVDA",
    "TSLA",
    "MARA",
    "RIOT",
    "GME",
    "IONQ",
    "SOUN",
    "HOOD",
    "RIVN",
    "SOFI",
    "UPST",
]


RISK_PROFILES: dict[str, dict[str, Any]] = {
    "conservative": {
        "max_trades_per_day": 3,
        "max_position_pct": 0.10,
        "max_daily_loss_pct": 0.02,
        "label": "שמרני",
        "max_deploy_pct": 0.30,
        "strategy": "momentum",
    },
    "balanced": {
        "max_trades_per_day": 3,
        "max_position_pct": 0.167,
        "max_daily_loss_pct": 0.03,
        "label": "מאוזן",
        "max_deploy_pct": 0.50,
        "strategy": "momentum",
    },
    "aggressive": {
        "max_trades_per_day": 3,
        "max_position_pct": 0.34,
        "max_daily_loss_pct": 0.05,
        "label": "אגרסיבי",
        "max_deploy_pct": 1.00,
        "strategy": "momentum",
    },
    "speculative": {
        "max_trades_per_day": 4,
        "max_position_pct": 0.25,
        "max_daily_loss_pct": 0.50,
        "label": "ספקולטיבי",
        "max_deploy_pct": 1.00,
        "strategy": "speculative",
        "stop_loss_pct": 0.12,
        "take_profit_pct": 0.25,
        "min_volume_ratio": 1.0,
        "min_avg_volume_20d": 500_000,
        "hold_mode": "swing",
        "max_hold_days": 5,
        "max_open_positions": 4,
    },
}


@dataclass
class AgentConfig:
    initial_capital: float = 1000.0
    monthly_target_usd: float = 2000.0
    risk_profile: str = "conservative"
    max_trades_per_day: int = 3
    max_position_pct: float = 0.10
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    max_daily_loss_pct: float = 0.02
    planning_time: str = "21:00"
    market_open_sim_time: str = "16:40"  # UTC ~ 09:40 ET (summer)
    market_close_sim_time: str = "23:10"  # UTC ~ 16:10 ET (summer)
    heartbeat_time: str = "09:00"
    send_heartbeat_on_startup: bool = True
    plan_reminder_time: str = "22:00"
    intraday_check_enabled: bool = True
    intraday_check_interval_minutes: int = 60
    intraday_alert_cooldown_minutes: int = 120
    telegram_poll_interval_sec: int = 60
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    min_volume_ratio: float = 1.2
    min_price_usd: float = 5.0
    min_avg_volume_20d: float = 1_000_000
    news_headlines_count: int = 3
    news_sources: list[str] = None
    signal_sources: list[str] = None
    min_signal_sources: int = 3
    source_weights: dict[str, float] = None
    max_source_score_std: float = 4.5
    max_source_score_spread: float = 9.0
    disagreement_score_penalty: float = 0.75
    exclude_on_source_disagreement: bool = False
    sentiment_score_factor: float = 1.0
    backtest_days: int = 90
    min_entry_score: float = 0.0
    symbol_cooldown_days_after_loss: int = 5
    max_leveraged_etf_positions: int = 1
    notification_mode: str = "app"
    hold_mode: str = "swing"
    max_hold_days: int = 5
    max_open_positions: int = 4
    commission_per_side_usd: float = 1.0
    tickers: list[str] = None

    def __post_init__(self) -> None:
        if self.news_sources is None:
            self.news_sources = ["yahoo", "google", "finviz"]
        if self.signal_sources is None:
            self.signal_sources = list(DEFAULT_SIGNAL_SOURCES)
        if self.source_weights is None:
            self.source_weights = dict(DEFAULT_SOURCE_WEIGHTS)
        if self.tickers is None:
            self.tickers = (
                DEFAULT_SPECULATIVE_TICKERS
                if self.risk_profile == "speculative"
                else DEFAULT_TICKERS
            )


def profile_strategy(cfg: AgentConfig) -> str:
    profile = RISK_PROFILES.get(cfg.risk_profile, RISK_PROFILES["conservative"])
    return str(profile.get("strategy", "momentum"))


def is_speculative(cfg: AgentConfig) -> bool:
    return profile_strategy(cfg) == "speculative"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PLANS_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "logs").mkdir(exist_ok=True)


def scheduler_log_file() -> Path:
    from trading_pulse.core.app_paths import SCHEDULER_LOG_FILE

    return SCHEDULER_LOG_FILE


def load_config() -> AgentConfig:
    if not CONFIG_FILE.exists():
        cfg = AgentConfig()
        apply_risk_profile(cfg)
        save_json(CONFIG_FILE, cfg.__dict__)
        return cfg
    raw = read_json(CONFIG_FILE)
    from trading_pulse.core.env_config import apply_secrets_to_config

    raw = apply_secrets_to_config(raw)
    cfg = AgentConfig(**raw)
    apply_risk_profile(cfg, raw)
    return cfg


def apply_risk_profile(cfg: AgentConfig, raw: dict[str, Any] | None = None) -> None:
    raw = raw or {}
    profile = RISK_PROFILES.get(cfg.risk_profile)
    if profile is None:
        logging.warning("Unknown risk_profile '%s', using conservative", cfg.risk_profile)
        profile = RISK_PROFILES["conservative"]
        cfg.risk_profile = "conservative"
    if "max_trades_per_day" not in raw:
        cfg.max_trades_per_day = int(profile["max_trades_per_day"])
    if "max_position_pct" not in raw:
        cfg.max_position_pct = float(profile["max_position_pct"])
    if "max_daily_loss_pct" not in raw:
        cfg.max_daily_loss_pct = float(profile["max_daily_loss_pct"])
    for key in ("stop_loss_pct", "take_profit_pct", "min_volume_ratio", "min_avg_volume_20d"):
        if key not in raw and key in profile:
            setattr(cfg, key, float(profile[key]))
    for key in ("hold_mode", "max_hold_days", "max_open_positions"):
        if key not in raw and key in profile:
            if key == "hold_mode":
                setattr(cfg, key, str(profile[key]))
            else:
                setattr(cfg, key, int(profile[key]))


def risk_profile_summary(cfg: AgentConfig, equity: float | None = None) -> str:
    profile = RISK_PROFILES.get(cfg.risk_profile, RISK_PROFILES["conservative"])
    capital = float(equity if equity is not None else cfg.initial_capital)
    max_deploy = capital * float(profile["max_deploy_pct"])
    per_trade = capital * cfg.max_position_pct
    return (
        f"{profile['label']} ({cfg.risk_profile}) | "
        f"up to {int(profile['max_deploy_pct']*100)}% deployed (${max_deploy:.0f}) | "
        f"{cfg.max_trades_per_day} trades x ${per_trade:.0f}"
    )


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_state(cfg: AgentConfig) -> dict[str, Any]:
    if not STATE_FILE.exists():
        state = {
            "equity": cfg.initial_capital,
            "last_report_date": None,
            "history": [],
            "open_positions": [],
        }
        ensure_month_tracking(cfg, state)
        save_json(STATE_FILE, state)
        return state
    state = read_json(STATE_FILE)
    from trading_pulse.agent.positions import ensure_open_positions, backfill_position_floors

    ensure_open_positions(state)
    backfill_position_floors(state, cfg)
    ensure_month_tracking(cfg, state)
    return state


def count_us_trading_days_remaining(from_day: date) -> int:
    if from_day.month == 12:
        month_end = date(from_day.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(from_day.year, from_day.month + 1, 1) - timedelta(days=1)
    count = 0
    day = from_day
    while day <= month_end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def ensure_month_tracking(cfg: AgentConfig, state: dict[str, Any]) -> None:
    experiment = state.get("experiment") or {}
    forced_month = experiment.get("month_key")
    today = date.today()
    month_key = str(forced_month) if forced_month else today.strftime("%Y-%m")
    if state.get("month_key") != month_key:
        state["month_key"] = month_key
        state["month_start_equity"] = round(float(state.get("equity", cfg.initial_capital)), 2)
        state["month_start_date"] = date.fromisoformat(f"{month_key}-01").isoformat()


def monthly_target_summary(cfg: AgentConfig, state: dict[str, Any]) -> str:
    equity = float(state.get("equity", cfg.initial_capital))
    target = float(cfg.monthly_target_usd)
    start = float(state.get("month_start_equity", cfg.initial_capital))
    month_pnl = equity - start
    month_pnl_pct = (month_pnl / start * 100) if start > 0 else 0.0
    gap = target - equity
    trading_days_left = count_us_trading_days_remaining(date.today())
    return (
        f"יעד חודשי: ${target:.0f} | נוכחי: ${equity:.2f} | "
        f"חודש: {month_pnl:+.2f}$ ({month_pnl_pct:+.1f}%) | "
        f"נותר: ${gap:+.0f} | {trading_days_left} ימי מסחר"
    )


def setup_logger(log_file: Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )


def get_next_us_trading_day(from_day: date) -> date:
    nxt = from_day + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def is_us_trading_day(day: date) -> bool:
    return day.weekday() < 5


def should_send_plan_today(run_day: date) -> bool:
    """Plan only on the evening before a US trading day (not on Shabbat)."""
    if run_day.weekday() == 5:
        return False
    next_td = get_next_us_trading_day(run_day)
    gap = (next_td - run_day).days
    if gap == 1:
        return True
    if run_day.weekday() == 6 and next_td.weekday() == 0:
        return True
    return False


def should_run_simulation_today(run_day: date) -> bool:
    """Simulate only on US trading days when a plan exists."""
    if not is_us_trading_day(run_day):
        return False
    return plan_path(run_day).exists()


def plan_path(trading_day: date) -> Path:
    return PLANS_DIR / f"plan_{trading_day.isoformat()}.json"


def plan_is_protected(plan: dict[str, Any]) -> bool:
    """Approved or allocated plans must not be overwritten by scheduled jobs."""
    alloc = plan.get("allocation") or {}
    if alloc.get("status") == "applied":
        return True
    if plan.get("status") == "approved":
        return True
    return any(r.get("approved") for r in plan.get("recommendations") or [])


def pending_plan_entry_symbols(*, as_of: date | None = None) -> set[str]:
    """Symbols approved/allocated in active plans awaiting simulation."""
    symbols: set[str] = set()
    as_of = as_of or date.today()
    for path in PLANS_DIR.glob("plan_*.json"):
        try:
            plan = read_json(path)
        except OSError:
            continue
        td = plan.get("for_trading_day")
        if not td:
            continue
        try:
            trading_day = date.fromisoformat(td)
        except ValueError:
            continue
        if trading_day < as_of:
            continue
        alloc = plan.get("allocation") or {}
        if alloc.get("status") == "applied":
            symbols.update(str(sym) for sym in (alloc.get("amounts") or {}))
        for rec in plan.get("recommendations") or []:
            if rec.get("approved"):
                symbols.add(str(rec["symbol"]))
    return symbols


def report_path(trading_day: date) -> Path:
    return REPORTS_DIR / f"report_{trading_day.isoformat()}.json"


NEWS_POSITIVE_HINTS = (
    "surge",
    "rally",
    "beat",
    "upgrade",
    "record",
    "soar",
    "jump",
    "approval",
    "partnership",
    "bull",
    "gain",
    "rise",
    "high",
    "growth",
    "strong",
)
NEWS_NEGATIVE_HINTS = (
    "drop",
    "fall",
    "miss",
    "downgrade",
    "lawsuit",
    "probe",
    "cut",
    "layoff",
    "bear",
    "crash",
    "decline",
    "warning",
    "selloff",
    "loss",
    "weak",
    "recall",
)

NEWS_SOURCE_LABELS = {
    "yahoo": "Yahoo Finance",
    "google": "Google News",
    "finviz": "Finviz",
}

NEWS_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def normalize_headline_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title.lower().strip())
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return cleaned[:100]


def make_headline(
    title: str,
    source: str,
    summary: str = "",
    publisher: str = "",
    pub_date: str = "",
) -> dict[str, str]:
    return {
        "title": title.strip(),
        "summary": summary[:400].strip(),
        "publisher": publisher.strip(),
        "pub_date": pub_date.strip(),
        "source": NEWS_SOURCE_LABELS.get(source, source),
    }


def parse_news_article(article: dict[str, Any]) -> dict[str, str] | None:
    content = article.get("content", article)
    if not isinstance(content, dict):
        return None
    title = str(content.get("title", "")).strip()
    if not title:
        return None
    summary = str(content.get("summary") or "").strip()
    if not summary:
        summary = str(content.get("description") or "").strip()
    provider = content.get("provider", {})
    publisher = ""
    if isinstance(provider, dict):
        publisher = str(provider.get("displayName", "")).strip()
    pub_date = str(content.get("pubDate", "")).strip()
    return make_headline(title, "yahoo", summary=summary, publisher=publisher, pub_date=pub_date)


def fetch_yahoo_headlines(symbol: str, count: int) -> list[dict[str, str]]:
    try:
        articles = yf.Ticker(symbol).news or []
    except Exception as ex:
        logging.warning("Yahoo news failed for %s: %s", symbol, ex)
        return []
    headlines: list[dict[str, str]] = []
    for article in articles:
        parsed = parse_news_article(article)
        if parsed is None:
            continue
        headlines.append(parsed)
        if len(headlines) >= count:
            break
    return headlines


def fetch_google_news_headlines(symbol: str, count: int) -> list[dict[str, str]]:
    query = f'"{symbol}" (stock OR ETF OR shares) when:7d'
    url = (
        "https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        res = requests.get(url, timeout=15, headers=NEWS_HTTP_HEADERS)
        res.raise_for_status()
        root = ET.fromstring(res.text)
    except Exception as ex:
        logging.warning("Google News failed for %s: %s", symbol, ex)
        return []

    headlines: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title_raw = (item.findtext("title") or "").strip()
        if not title_raw:
            continue
        summary = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        publisher = ""
        if " - " in title_raw:
            title, publisher = title_raw.rsplit(" - ", 1)
        else:
            title = title_raw
        headlines.append(
            make_headline(title, "google", summary=summary, publisher=publisher, pub_date=pub_date)
        )
        if len(headlines) >= count:
            break
    return headlines


def fetch_finviz_headlines(symbol: str, count: int) -> list[dict[str, str]]:
    url = f"https://finviz.com/quote.ashx?t={symbol}"
    try:
        res = requests.get(url, timeout=15, headers=NEWS_HTTP_HEADERS)
        res.raise_for_status()
        html = res.text
    except Exception as ex:
        logging.warning("Finviz news failed for %s: %s", symbol, ex)
        return []

    headlines: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'class="tab-link-news"[^>]*href="([^"]*)"[^>]*>([^<]+)<', html):
        title = re.sub(r"\s+", " ", match.group(2)).strip()
        if not title:
            continue
        key = normalize_headline_title(title)
        if key in seen:
            continue
        seen.add(key)
        headlines.append(make_headline(title, "finviz", publisher="Finviz"))
        if len(headlines) >= count:
            break
    return headlines


NEWS_FETCHERS = {
    "yahoo": fetch_yahoo_headlines,
    "google": fetch_google_news_headlines,
    "finviz": fetch_finviz_headlines,
}


def merge_headlines_from_sources(
    symbol: str,
    sources: list[str],
    total: int,
) -> list[dict[str, str]]:
    per_source = max(total, 3)
    buckets: dict[str, list[dict[str, str]]] = {}
    for source in sources:
        fetcher = NEWS_FETCHERS.get(source)
        if fetcher is None:
            logging.warning("Unknown news source '%s', skipping", source)
            continue
        buckets[source] = fetcher(symbol, per_source)
        logging.info(
            "News source %s for %s: %d headline(s)",
            source,
            symbol,
            len(buckets[source]),
        )

    if not buckets:
        return []

    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    idx = 0
    while len(merged) < total:
        added = False
        for source in sources:
            items = buckets.get(source, [])
            if idx >= len(items):
                continue
            item = items[idx]
            key = normalize_headline_title(item.get("title", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
            added = True
            if len(merged) >= total:
                break
        if not added:
            break
        idx += 1
    return merged


def fetch_ticker_headlines(
    symbol: str,
    count: int = 3,
    sources: list[str] | None = None,
) -> list[dict[str, str]]:
    active_sources = sources or list(NEWS_FETCHERS.keys())
    return merge_headlines_from_sources(symbol, active_sources, count)


def summarize_headlines(symbol: str, headlines: list[dict[str, str]]) -> str:
    if not headlines:
        return f"אין חדשות זמינות עבור {symbol}."

    combined = " ".join(
        f"{h.get('title', '')} {h.get('summary', '')}" for h in headlines
    ).lower()
    pos = sum(1 for hint in NEWS_POSITIVE_HINTS if hint in combined)
    neg = sum(1 for hint in NEWS_NEGATIVE_HINTS if hint in combined)
    if pos > neg and pos > 0:
        tone = "טון חיובי-מעורב"
    elif neg > pos and neg > 0:
        tone = "טון שלילי-מעורב"
    else:
        tone = "טון ניטרלי"

    themes: list[str] = []
    if any(x in combined for x in ("earnings", "revenue", "profit", "guidance")):
        themes.append("דוחות/רווחיות")
    if any(x in combined for x in ("ai", "chip", "semiconductor", "data center")):
        themes.append("AI/צ'יפים")
    if any(x in combined for x in ("fed", "inflation", "rate", "tariff")):
        themes.append("מאקרו/ריבית")
    if any(x in combined for x in ("upgrade", "downgrade", "price target")):
        themes.append("המלצות אנליסטים")

    theme_text = f" נושאים: {', '.join(themes)}." if themes else ""
    latest = headlines[0].get("title", "").strip()
    return f"{tone}.{theme_text} כותרת אחרונה: {latest}"


def analyze_news_sentiment(headlines: list[dict[str, str]]) -> dict[str, Any]:
    if not headlines:
        return {
            "sentiment_tone": "neutral",
            "sentiment_score": 0,
            "sentiment_adjustment": 0.0,
        }

    combined = " ".join(
        f"{h.get('title', '')} {h.get('summary', '')}" for h in headlines
    ).lower()
    pos = sum(1 for hint in NEWS_POSITIVE_HINTS if hint in combined)
    neg = sum(1 for hint in NEWS_NEGATIVE_HINTS if hint in combined)
    sentiment_score = pos - neg

    if sentiment_score > 0:
        tone = "positive"
    elif sentiment_score < 0:
        tone = "negative"
    else:
        tone = "neutral"

    adjustment = max(min(sentiment_score * 0.4, 1.5), -1.5)
    return {
        "sentiment_tone": tone,
        "sentiment_score": sentiment_score,
        "sentiment_adjustment": round(adjustment, 2),
    }


def apply_sentiment_to_score(rec: dict[str, Any], factor: float) -> None:
    sentiment = analyze_news_sentiment(rec.get("news_headlines", []))
    rec.update(sentiment)
    base_score = float(rec.get("score", 0))
    adjustment = float(sentiment["sentiment_adjustment"]) * factor
    rec["score_before_sentiment"] = round(base_score, 4)
    rec["score"] = round(base_score + adjustment, 4)


def attach_backtest_to_recommendation(
    rec: dict[str, Any],
    cfg: AgentConfig,
    speculative: bool,
) -> None:
    backtest = backtest_symbol(
        rec["symbol"],
        stop_loss_pct=float(rec.get("stop_loss_pct", cfg.stop_loss_pct)),
        take_profit_pct=float(rec.get("take_profit_pct", cfg.take_profit_pct)),
        lookback_days=cfg.backtest_days,
        speculative=speculative,
        min_volume_ratio=cfg.min_volume_ratio,
        min_price_usd=cfg.min_price_usd,
        min_avg_volume_20d=cfg.min_avg_volume_20d,
        max_trades_per_day=cfg.max_trades_per_day,
    )
    rec["backtest"] = backtest


def attach_news_to_recommendations(
    recommendations: list[dict[str, Any]],
    headlines_count: int,
    sources: list[str] | None = None,
) -> None:
    for rec in recommendations:
        symbol = str(rec["symbol"])
        headlines = fetch_ticker_headlines(symbol, headlines_count, sources=sources)
        rec["news_headlines"] = headlines
        rec["news_summary"] = summarize_headlines(symbol, headlines)
        source_names = sorted({h.get("source", "") for h in headlines if h.get("source")})
        logging.info(
            "News for %s: %d headline(s) from %s | summary=%s",
            symbol,
            len(headlines),
            ", ".join(source_names) or "none",
            rec["news_summary"][:80],
        )


def enrich_recommendations(
    recommendations: list[dict[str, Any]],
    cfg: AgentConfig,
    speculative: bool,
) -> None:
    attach_news_to_recommendations(
        recommendations,
        cfg.news_headlines_count,
        sources=cfg.news_sources,
    )
    for rec in recommendations:
        apply_sentiment_to_score(rec, cfg.sentiment_score_factor)
        attach_backtest_to_recommendation(rec, cfg, speculative)

    recommendations.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
    for rank, rec in enumerate(recommendations, start=1):
        rec["explanation"] = build_recommendation_explanation(rec, rank, speculative=speculative)


def build_recommendation_explanation(rec: dict[str, Any], rank: int, speculative: bool = False) -> str:
    symbol = rec["symbol"]
    score = float(rec.get("score", 0))
    ret5 = float(rec.get("ret_5d_pct", 0))
    vol_ratio = float(rec.get("vol_ratio", 0))
    volume_ok = bool(rec.get("volume_ok", False))

    if speculative:
        atr_pct = float(rec.get("atr_pct", 0))
        breakout_ok = bool(rec.get("breakout_ok", False))
        near_high_pct = float(rec.get("near_high_pct", 0))
        parts = [f"דירוג #{rank} (ציון {score:.2f})"]
        parts.append(f"תנודתיות יומית (ATR): {atr_pct:.1f}%")
        if breakout_ok:
            parts.append(f"פריצה — במרחק {near_high_pct:.1f}% מהשיא 20 יום")
        else:
            parts.append(f"לא בפריצה — {near_high_pct:.1f}% מתחת לשיא 20 יום")
        if ret5 > 0:
            parts.append(f"עלייה של {ret5:.1f}% ב-5 ימים")
        elif ret5 < 0:
            parts.append(f"ירידה של {abs(ret5):.1f}% ב-5 ימים — סיכון גבוה")
        if volume_ok:
            parts.append(f"volume spike ({vol_ratio:.2f}x מהממוצע)")
        else:
            parts.append(f"נפח רגיל ({vol_ratio:.2f}x)")
        asset_hint = {
            "TQQQ": "ETF ממונף x3 על נאסד\"ק",
            "SOXL": "ETF ממונף x3 על סמיקונדקטורים",
            "LABU": "ETF ממונף x3 על ביוטק",
            "MSTR": "חשיפה גבוהה לביטקוין",
            "COIN": "בורסת קריפטו — תנודתיות קיצונית",
        }.get(symbol)
        if asset_hint:
            parts.append(asset_hint)
        source_scores = rec.get("source_scores") or {}
        if source_scores:
            breakdown = ", ".join(
                f"{SOURCE_LABELS.get(k, k)} {v:.1f}"
                for k, v in sorted(source_scores.items(), key=lambda x: -x[1])
            )
            parts.append(f"ציון משוקלל מ-{rec.get('sources_used', len(source_scores))} אתרים ({breakdown})")
        if rec.get("source_disagreement"):
            parts.append(
                f"⚠️ מקורות לא מסכימים (std {float(rec.get('source_score_std', 0)):.1f}, "
                f"פער {float(rec.get('source_score_spread', 0)):.1f})"
            )
        sentiment_adj = float(rec.get("sentiment_adjustment", 0))
        if sentiment_adj != 0:
            tone = rec.get("sentiment_tone", "neutral")
            parts.append(f"חדשות ({tone}): {sentiment_adj:+.1f} לציון")
        backtest = rec.get("backtest") or {}
        if backtest.get("trades"):
            parts.append(f"Backtest: {backtest.get('summary', '')}")
        return f"{symbol}: " + ". ".join(parts) + "."

    above_ma = float(rec.get("above_ma20_pct", 0))
    vol_ratio = float(rec.get("vol_ratio", 0))
    momentum_ok = bool(rec.get("momentum_ok", False))
    volume_ok = bool(rec.get("volume_ok", False))

    parts = [f"דירוג #{rank} (ציון {score:.2f})"]
    if momentum_ok:
        parts.append(f"מחיר מעל MA20 ב-{above_ma:+.1f}%")
    else:
        parts.append("מחיר מתחת ל-MA20")

    if ret5 > 0:
        parts.append(f"עלייה של {ret5:.1f}% ב-5 ימים")
    elif ret5 < 0:
        parts.append(f"ירידה של {abs(ret5):.1f}% ב-5 ימים")
    else:
        parts.append("ללא שינוי משמעותי ב-5 ימים")

    if volume_ok:
        parts.append(f"נפח גבוה מהממוצע ({vol_ratio:.2f}x)")
    else:
        parts.append(f"נפח נמוך ({vol_ratio:.2f}x) — נבחר בעיקר בגלל מומנטום")

    asset_hint = {
        "QQQ": "ETF על מדד הנאסד\"ק",
        "SPY": "ETF על מדד S&P 500",
        "IWM": "ETF על מניות קטנות",
        "XLF": "ETF על מגזר הפיננסים",
        "XLE": "ETF על מגזר האנרגיה",
        "XLK": "ETF על מגזר הטכנולוגיה",
    }.get(symbol)
    if asset_hint:
        parts.append(asset_hint)

    source_scores = rec.get("source_scores") or {}
    if source_scores:
        breakdown = ", ".join(
            f"{SOURCE_LABELS.get(k, k)} {v:.1f}"
            for k, v in sorted(source_scores.items(), key=lambda x: -x[1])
        )
        parts.append(f"ציון משוקלל מ-{rec.get('sources_used', len(source_scores))} אתרים ({breakdown})")
    if rec.get("source_disagreement"):
        parts.append("⚠️ מקורות לא מסכימים")
    sentiment_adj = float(rec.get("sentiment_adjustment", 0))
    if sentiment_adj != 0:
        parts.append(f"חדשות: {sentiment_adj:+.1f}")
    backtest = rec.get("backtest") or {}
    if backtest.get("trades"):
        parts.append(f"Backtest: {backtest.get('summary', '')}")

    return f"{symbol}: " + ". ".join(parts) + "."


def escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def truncate_text(text: str, max_len: int = 72) -> str:
    cleaned = re.sub(r"\s+", " ", str(text).strip())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def format_source_scores_line(rec: dict[str, Any]) -> str:
    source_scores = rec.get("source_scores") or {}
    if not source_scores:
        return ""
    parts = [
        f"{SOURCE_LABELS.get(k, k)[:6]} {v:.1f}"
        for k, v in sorted(source_scores.items(), key=lambda x: -x[1])
    ]
    used = int(rec.get("sources_used", len(source_scores)))
    label = "משוקלל" if rec.get("score_technical") is not None else "ממוצע"
    line = f"{label} {used} אתרים: " + " | ".join(parts)
    if rec.get("source_disagreement"):
        line += f"\n⚠️ פער מקורות std={float(rec.get('source_score_std', 0)):.1f}"
    return line


def format_enrichment_lines(rec: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    adj = float(rec.get("sentiment_adjustment", 0))
    if adj != 0:
        tone = rec.get("sentiment_tone", "neutral")
        lines.append(f"חדשות ({tone}): {adj:+.1f} → ציון {float(rec.get('score', 0)):.1f}")
    backtest = rec.get("backtest") or {}
    if backtest.get("summary"):
        lines.append(f"📊 {backtest['summary']}")
    return lines


def format_rec_signal_compact(rec: dict[str, Any], speculative: bool) -> str:
    score = float(rec.get("score", 0))
    parts = [f"ציון {score:.1f}"]
    if speculative:
        parts.append(f"ATR {float(rec.get('atr_pct', 0)):.1f}%")
        parts.append("פריצה" if rec.get("breakout_ok") else "מתחת לשיא")
    else:
        parts.append("מעל MA20" if rec.get("momentum_ok") else "מתחת MA20")
    parts.append(f"5d {float(rec.get('ret_5d_pct', 0)):+.1f}%")
    line = " · ".join(parts)
    if rec.get("source_disagreement"):
        line += " · ⚠️ פער מקורות"
    return line


def format_rec_signal_block(rec: dict[str, Any], speculative: bool) -> str:
    sources_line = format_source_scores_line(rec)
    enrich_lines = format_enrichment_lines(rec)
    if speculative:
        breakout = (
            "פריצה לשיא 20 יום"
            if rec.get("breakout_ok")
            else f"מתחת לשיא ({float(rec.get('near_high_pct', 0)):+.1f}%)"
        )
        lines = [
            f"ציון {float(rec.get('score', 0)):.1f} | ATR {float(rec.get('atr_pct', 0)):.1f}%",
            f"5 ימים {float(rec.get('ret_5d_pct', 0)):+.1f}% | נפח {float(rec.get('vol_ratio', 0)):.2f}x",
            breakout,
        ]
        if sources_line:
            lines.append(sources_line)
        lines.extend(enrich_lines)
        return "\n".join(lines)
    momentum = "מעל MA20" if rec.get("momentum_ok") else "מתחת MA20"
    lines = [
        f"ציון {float(rec.get('score', 0)):.1f} | {momentum}",
        f"5 ימים {float(rec.get('ret_5d_pct', 0)):+.1f}% | נפח {float(rec.get('vol_ratio', 0)):.2f}x",
    ]
    if sources_line:
        lines.append(sources_line)
    lines.extend(enrich_lines)
    return "\n".join(lines)


def format_plan_message(plan: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import format_plan

    speculative = plan.get("risk_profile") == "speculative"
    return format_plan(
        plan,
        rec_formatter=lambda rec, compact=False: (
            format_rec_signal_compact(rec, speculative) if compact else format_rec_signal_block(rec, speculative)
        ),
    )


def format_plan_message_for_app(plan: dict[str, Any]) -> str:
    recs = plan.get("recommendations", [])
    day = plan.get("for_trading_day", "")
    speculative = plan.get("risk_profile") == "speculative"
    lines = [
        f"📋 תוכנית Dry Run — {day}",
        "",
        "סיכום חשבון",
        f"הון: ${float(plan.get('equity_snapshot', 0)):.0f}",
        f"הפסד יומי מקס: ${float(plan.get('daily_loss_limit_usd', 0)):.0f}",
        f"סיכון: {plan.get('risk_profile_summary', 'n/a')}",
    ]
    if plan.get("monthly_target_summary"):
        lines.append(plan["monthly_target_summary"])
    holdings = plan.get("holdings") or []
    if holdings:
        lines.append("")
        lines.append(f"📂 מחזיקים ({len(holdings)}) — נשארים פתוחים:")
        for h in holdings:
            lines.append(
                f"  {h['symbol']} · ${float(h['capital_usd']):.0f} · מ-{h['entry_day']} · {h['days_held']} ימים"
            )
        lines.append(f"פנוי לחדשות: ${float(plan.get('available_capital_usd', 0)):.0f}")
    if not recs:
        if holdings:
            lines.extend(["", "אין כניסות חדשות — רק החזקה."])
            return "\n".join(lines)
        lines.extend(["", "🔍 אין המלצות היום"])
        from trading_pulse.telegram.telegram_format import format_scan_summary

        summary = format_scan_summary(plan, html=False)
        if summary:
            lines.extend(["", "📊 סיכום סריקה", summary])
        elif plan.get("no_picks_reason"):
            lines.append(str(plan["no_picks_reason"]))
        return "\n".join(lines)
    lines.append("")
    lines.append(f"כניסות חדשות ({len(recs)}):")
    for idx, rec in enumerate(recs, start=1):
        lines.extend(
            [
                "",
                f"#{idx} {rec['symbol']} · LONG",
                format_rec_signal_block(rec, speculative),
            ]
        )
        if rec.get("news_summary"):
            lines.append(f"📰 {rec['news_summary']}")
    lines.extend(["", "פתח באפליקציה → תוכנית פעילה → אשר או דחה"])
    return "\n".join(lines)


def format_heartbeat_message(cfg: AgentConfig, state: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import format_heartbeat

    return format_heartbeat(
        cfg,
        state,
        summary_fn=risk_profile_summary,
        monthly_fn=monthly_target_summary,
        speculative_fn=is_speculative,
    )


def send_heartbeat(cfg: AgentConfig, reason: str) -> None:
    state = load_state(cfg)
    today = date.today().isoformat()
    if state.get("last_heartbeat_date") == today:
        logging.info("Heartbeat skipped (%s): already sent today", reason)
        return
    logging.info("Sending heartbeat (%s)", reason)
    message = format_heartbeat_message(cfg, state)
    if send_user_notification(cfg, message, context="heartbeat", parse_mode="HTML"):
        state["last_heartbeat_date"] = today
        state["last_heartbeat_at"] = datetime.now(timezone.utc).isoformat()
        save_json(STATE_FILE, state)
        logging.info("Heartbeat delivered (%s)", reason)
    else:
        logging.warning("Heartbeat not delivered (%s)", reason)


def format_report_message(report: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import format_report

    return format_report(report)


def telegram_api_call(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    clean_token = str(token).strip()
    url = f"https://api.telegram.org/bot{clean_token}/{method}"
    # Use form-encoded payload for maximum compatibility with Telegram API.
    res = requests.post(url, data=payload, timeout=20)
    res.raise_for_status()
    data = res.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data


def telegram_raw_post(token: str, method: str, payload: dict[str, Any]) -> requests.Response:
    clean_token = str(token).strip()
    url = f"https://api.telegram.org/bot{clean_token}/{method}"
    return requests.post(url, data=payload, timeout=20)


def _send_telegram_api(
    cfg: AgentConfig,
    text: str,
    context: str = "message",
    parse_mode: str | None = None,
) -> bool:
    token = str(cfg.telegram_bot_token).strip()
    chat_id = str(cfg.telegram_chat_id).strip()
    if not token or not chat_id:
        logging.warning("Telegram skip (%s): missing token or chat_id", context)
        return False
    preview = text.replace("\n", " | ")[:120]
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    sent_text = text
    try:
        telegram_api_call(token, "sendMessage", payload)
        logging.info("Telegram sent (%s): %s", context, preview)
        if not uses_app_notifications(cfg):
            log_telegram_message("out", context, sent_text, parse_mode=parse_mode)
        return True
    except Exception as ex:
        if parse_mode:
            logging.warning("Telegram HTML send failed (%s), retrying plain text: %s", context, ex)
            try:
                plain = re.sub(r"<[^>]+>", "", text)
                telegram_api_call(token, "sendMessage", {"chat_id": chat_id, "text": plain})
                logging.info("Telegram sent (%s) as plain text", context)
                if not uses_app_notifications(cfg):
                    log_telegram_message("out", context, plain, parse_mode=None)
                return True
            except Exception as retry_ex:
                logging.warning("Telegram send failed (%s): %s", context, retry_ex)
                return False
        logging.warning("Telegram send failed (%s): %s", context, ex)
        return False


def send_telegram_photo(
    cfg: AgentConfig,
    image_bytes: bytes,
    caption: str,
    context: str = "photo",
    parse_mode: str | None = "HTML",
) -> bool:
    token = str(cfg.telegram_bot_token).strip()
    chat_id = str(cfg.telegram_chat_id).strip()
    if not token or not chat_id:
        logging.warning("Telegram photo skip (%s): missing token or chat_id", context)
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    cap = caption[:1024]

    def _post(data: dict[str, Any]) -> requests.Response:
        files = {"photo": ("chart.png", image_bytes, "image/png")}
        return requests.post(url, data=data, files=files, timeout=30)

    data: dict[str, Any] = {"chat_id": chat_id, "caption": cap}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        res = _post(data)
        if parse_mode and res.status_code >= 400:
            logging.warning("Telegram photo HTML caption failed (%s), retrying plain", context)
            plain = re.sub(r"<[^>]+>", "", cap)
            res = _post({"chat_id": chat_id, "caption": plain})
        res.raise_for_status()
        body = res.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body}")
        logging.info("Telegram photo sent (%s)", context)
        log_telegram_message(
            "out",
            context,
            f"[image] {re.sub(r'<[^>]+>', '', cap)[:200]}",
            parse_mode=None,
            metadata={"image": True},
        )
        return True
    except Exception as ex:
        logging.warning("Telegram photo send failed (%s): %s", context, ex)
        return False


def send_telegram_table_image(
    cfg: AgentConfig,
    image_bytes: bytes,
    caption: str,
    context: str,
) -> None:
    if not uses_telegram_notifications(cfg):
        return
    send_telegram_photo(cfg, image_bytes, caption, context=f"{context}:image", parse_mode="HTML")


def send_plan_table_image(
    cfg: AgentConfig,
    plan: dict[str, Any],
    *,
    caption: str | None = None,
) -> None:
    try:
        from trading_pulse.telegram.telegram_format import format_plan_table_caption
        from trading_pulse.telegram.telegram_images import render_plan_image

        img = render_plan_image(plan)
        cap = caption or format_plan_table_caption(plan)
        send_telegram_table_image(cfg, img, cap, "plan")
    except Exception as ex:
        logging.warning("Plan table image failed: %s", ex)


def send_plan_stock_charts(cfg: AgentConfig, plan: dict[str, Any]) -> None:
    """One Telegram photo per recommendation with price chart."""
    from trading_pulse.telegram.app_notify import uses_telegram_notifications
    from trading_pulse.telegram.telegram_format import format_recommendation
    from trading_pulse.telegram.telegram_images import render_recommendation_chart

    if not uses_telegram_notifications(cfg):
        return
    recs = plan.get("recommendations") or []
    if not recs:
        return
    day = str(plan.get("for_trading_day", ""))
    speculative = plan.get("risk_profile") == "speculative"
    for idx, rec in enumerate(recs, start=1):
        try:
            img = render_recommendation_chart(rec, idx, day)
            if not img:
                continue
            signal_lines = format_rec_signal_block(rec, speculative).splitlines()
            caption = format_recommendation(rec, idx, plan, signal_lines=signal_lines)
            send_telegram_photo(
                cfg,
                img,
                caption,
                context=f"plan:stock:{rec['symbol']}",
                parse_mode="HTML",
            )
        except Exception as ex:
            logging.warning("Plan chart for %s failed: %s", rec.get("symbol"), ex)


def send_plan_notifications(cfg: AgentConfig, plan: dict[str, Any]) -> None:
    """Summary text, summary table, then per-stock chart messages."""
    from trading_pulse.telegram.app_notify import notify_user, uses_app_notifications, uses_telegram_notifications

    if uses_app_notifications(cfg):
        notify_user(
            cfg,
            format_plan_message_for_app(plan),
            context="plan",
            plan=plan,
            telegram_sender=False,
        )
    if uses_telegram_notifications(cfg):
        _send_telegram_api(cfg, format_plan_message(plan), context="plan", parse_mode="HTML")
    send_plan_table_image(cfg, plan)
    send_plan_stock_charts(cfg, plan)


def send_report_table_image(cfg: AgentConfig, report: dict[str, Any]) -> None:
    try:
        from trading_pulse.telegram.telegram_images import render_report_image

        img = render_report_image(report)
        day = report.get("trading_day", "")
        pnl = float(report.get("pnl_usd", 0))
        sign = "+" if pnl >= 0 else ""
        send_telegram_table_image(cfg, img, f"<b>📊 דוח {day}</b> · P/L <b>{sign}${pnl:.2f}</b>", "report")
    except Exception as ex:
        logging.warning("Report table image failed: %s", ex)


def send_user_notification(
    cfg: AgentConfig,
    text: str,
    context: str = "message",
    parse_mode: str | None = None,
    plan: dict[str, Any] | None = None,
) -> bool:
    from trading_pulse.telegram.app_notify import notify_user

    return notify_user(
        cfg,
        text,
        context,
        parse_mode=parse_mode,
        plan=plan,
        telegram_sender=_send_telegram_api,
    )


def send_telegram_message(
    cfg: AgentConfig,
    text: str,
    context: str = "message",
    parse_mode: str | None = None,
) -> bool:
    return send_user_notification(cfg, text, context, parse_mode=parse_mode)


def parse_indices(raw: str, total: int) -> list[int]:
    if raw.upper() == "ALL":
        return list(range(total))
    picked: list[int] = []
    for chunk in raw.split(","):
        val = chunk.strip()
        if not val.isdigit():
            continue
        idx = int(val) - 1
        if 0 <= idx < total:
            picked.append(idx)
    return sorted(set(picked))


def set_plan_status(
    trading_day: str,
    action: str,
    indices: list[int],
    *,
    cfg: AgentConfig | None = None,
    notify_allocation: bool = True,
) -> str:
    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        return f"❌ <b>אין תוכנית ל-{trading_day}</b>\nחכה לתוכנית ב-21:00."
    plan = read_json(path)
    recs = plan.get("recommendations", [])
    if not recs:
        return f"📭 <b>אין המלצות</b> בתוכנית של {trading_day}."

    approved_value = action.upper() == "APPROVE"
    symbols: list[str] = []
    for idx in indices:
        recs[idx]["approved"] = approved_value
        symbols.append(str(recs[idx]["symbol"]))
    plan["status"] = "approved" if any(x.get("approved") for x in recs) else "pending_approval"
    plan["approved_at"] = datetime.now(timezone.utc).isoformat()
    if not any(x.get("approved") for x in recs):
        plan.pop("allocation", None)
    elif action.upper() == "APPROVE":
        plan["allocation"] = {"status": "pending"}
    save_json(path, plan)
    clear_pending_plan(trading_day)
    log_telegram_message(
        "in",
        f"app:{action.lower()}",
        f"{'אישור' if approved_value else 'דחייה'}: {', '.join(symbols)} ({trading_day})",
        metadata={"trading_day": trading_day, "indices": indices, "action": action.lower()},
    )

    verb = "אושרו" if approved_value else "נדחו"
    all_approved = [str(r["symbol"]) for r in recs if r.get("approved")]
    allocation_sent = False
    if approved_value and notify_allocation and all_approved:
        send_allocation_prompt(trading_day, cfg=cfg)
        allocation_sent = True

    from trading_pulse.telegram.telegram_format import format_approval_reply

    return format_approval_reply(
        trading_day=trading_day,
        picked_symbols=symbols,
        all_approved_symbols=all_approved,
        rejected=not approved_value,
        allocation_sent=allocation_sent,
    )


def send_allocation_prompt(trading_day: str, *, cfg: AgentConfig | None = None) -> bool:
    from trading_pulse.telegram.app_notify import notify_user
    from trading_pulse.agent.capital_allocation import ensure_allocation_options, format_allocation_prompt

    if cfg is None:
        cfg = load_config()
    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        return False
    plan = read_json(path)
    state = load_state(cfg)
    options = ensure_allocation_options(cfg, plan, state)
    plan.setdefault("allocation", {})["options"] = options
    plan["allocation"]["status"] = "pending"
    save_json(path, plan)
    text = format_allocation_prompt(plan, options, trading_day=trading_day, state=state)
    return notify_user(
        cfg,
        text,
        "allocation:prompt",
        parse_mode="HTML",
        telegram_sender=send_telegram_message,
    )


def apply_allocation_choice(trading_day: str, option_id: int, *, cfg: AgentConfig | None = None) -> str:
    from trading_pulse.agent.capital_allocation import (
        apply_allocation_option,
        ensure_allocation_options,
        format_allocation_applied,
    )

    if cfg is None:
        cfg = load_config()
    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        return f"❌ <b>אין תוכנית ל-{trading_day}</b>."
    plan = read_json(path)
    state = load_state(cfg)
    options = ensure_allocation_options(cfg, plan, state)
    chosen = apply_allocation_option(plan, option_id, options)
    if chosen is None:
        from trading_pulse.telegram.telegram_format import user_guide_invalid_allocation

        return user_guide_invalid_allocation()
    save_json(path, plan)
    return format_allocation_applied(chosen, trading_day)


def ensure_plan_allocation(cfg: AgentConfig, plan: dict[str, Any], state: dict[str, Any], trading_day: date) -> None:
    """Apply default allocation (original plan amounts) if user did not choose."""
    from trading_pulse.agent.capital_allocation import allocation_pending, apply_allocation_option, ensure_allocation_options

    if not allocation_pending(plan):
        return
    options = ensure_allocation_options(cfg, plan, state)
    apply_allocation_option(plan, 4, options)
    save_json(plan_path(trading_day), plan)
    logging.info(
        "Allocation auto-applied for %s: original plan amounts (no user choice)",
        trading_day.isoformat(),
    )


def plan_status_text(trading_day: str) -> str:
    from trading_pulse.telegram.telegram_format import SEP, user_guide_done, user_guide_step1, user_guide_step2

    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        return f"❌ <b>אין תוכנית ל-{trading_day}</b>."
    plan = read_json(path)
    recs = plan.get("recommendations", [])
    lines = [
        f"<b>📋 סטטוס תוכנית</b>",
        f"<b>יום מסחר:</b> {trading_day}",
        "",
        "<b>שלב 1 — אישור</b>",
    ]
    if not recs:
        lines.append("אין המלצות.")
        return "\n".join(lines)
    for idx, rec in enumerate(recs, start=1):
        if rec.get("approved"):
            status = "✅ מאושר"
        else:
            status = "⏳ ממתין"
        cap = float(rec.get("capital_usd", 0))
        lines.append(f"{idx}. <b>{rec['symbol']}</b> — {status} (${cap:.0f})")
    approved_n = sum(1 for r in recs if r.get("approved"))
    all_approved = [r["symbol"] for r in recs if r.get("approved")]
    lines.extend(["", f"<b>מאושרות:</b> {', '.join(all_approved) or 'אין'} ({approved_n}/{len(recs)})"])
    alloc = plan.get("allocation") or {}
    lines.append("")
    lines.append("<b>שלב 2 — חלוקה</b>")
    if alloc.get("status") == "applied":
        lines.append(f"✅ {alloc.get('title', '')} · ח{alloc.get('selected_option', '?')}")
        amounts = alloc.get("amounts") or {}
        if amounts:
            parts = [f"{s} ${a:.0f}" for s, a in amounts.items()]
            lines.append(" · ".join(parts))
    elif approved_n and alloc.get("status") == "pending":
        lines.append("⏳ ממתין לבחירת חלוקה")
    elif approved_n:
        lines.append("⏳ חלוקה לא נבחרה")
    else:
        lines.append("— טרם אושרו המלצות")
    lines.extend(["", SEP, "<b>מה לשלוח:</b>"])
    if alloc.get("status") == "applied":
        lines.append(user_guide_done())
    elif approved_n and alloc.get("status") == "pending":
        lines.append(user_guide_step2())
    else:
        lines.append(user_guide_step1())
    return "\n".join(lines)


def get_active_trading_day() -> str | None:
    """Most recently generated plan (the one the user just received)."""
    latest_day: str | None = None
    latest_gen = ""
    for path in PLANS_DIR.glob("plan_*.json"):
        plan = read_json(path)
        gen = str(plan.get("generated_at", ""))
        td = plan.get("for_trading_day")
        if td and gen >= latest_gen:
            latest_gen = gen
            latest_day = str(td)
    if latest_day:
        return latest_day
    today_path = plan_path(date.today())
    if today_path.exists():
        return date.today().isoformat()
    return None


def resolve_trading_day(explicit: str | None) -> str:
    if explicit:
        return explicit
    active = get_active_trading_day()
    if active is None:
        raise ValueError("no_active_plan")
    return active


def allocation_choice_pending_for_active_plan() -> bool:
    """True when user should pick ח1…ח5 (not approve recommendations)."""
    from trading_pulse.agent.capital_allocation import allocation_pending

    try:
        day = get_active_trading_day()
        if not day:
            return False
        plan = read_json(plan_path(date.fromisoformat(day)))
        return allocation_pending(plan)
    except (ValueError, OSError):
        return False


def parse_telegram_user_command(text: str) -> dict[str, Any]:
    raw = text.strip()
    lower = raw.lower()

    if lower in {"help", "עזרה", "?", "פקודות", "help"}:
        return {"kind": "help"}

    if lower in {"מדריך", "מדריך טלגרם", "guide", "telegram guide"}:
        return {"kind": "guide_telegram"}

    if lower in {
        "איך בוחרים מניות",
        "איך בוחרים מניה",
        "איך בוחרים",
        "בחירת מניות",
        "בחירת מניה",
        "selection",
        "selection guide",
        "how to pick",
    }:
        return {"kind": "guide_selection"}

    if lower in {
        "חיבור בוט",
        "יצירת בוט",
        "איך יוצרים בוט",
        "איך ליצור בוט",
        "הגדרת בוט",
        "bot setup",
        "connect bot",
    }:
        return {"kind": "guide_bot_setup"}

    if lower in {"status", "סטטוס", "מצב"}:
        return {"kind": "status", "day": None}

    if lower in {"portfolio", "תיק", "השקעות", "תיק השקעות", "holdings", "positions"}:
        return {"kind": "portfolio"}

    if lower in {"חלוקה", "allocation", "alloc"}:
        return {"kind": "allocation_show", "day": None}

    if lower in {"רשימה", "מניות", "רשימת מניות", "tickers", "watchlist", "list tickers"}:
        return {"kind": "tickers_list"}

    if lower in {
        "חפש מניות",
        "סרוק מניות",
        "גלה מניות",
        "discover",
        "scan tickers",
        "find tickers",
    }:
        return {"kind": "tickers_discover"}

    add_match = re.fullmatch(
        r"(?:הוסף|add|\+)\s+([A-Za-z][A-Za-z0-9.\-^]{0,9})",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if add_match:
        return {"kind": "ticker_add", "symbol": add_match.group(1).upper()}

    remove_match = re.fullmatch(
        r"(?:הסר|הורד|remove|del|delete|-)\s+([A-Za-z][A-Za-z0-9.\-^]{0,9})",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if remove_match:
        return {"kind": "ticker_remove", "symbol": remove_match.group(1).upper()}

    plan_now_phrases = {
        "תוכנית עכשיו",
        "תוכנית חדשה",
        "צור תוכנית",
        "plan now",
        "new plan",
    }
    plan_show_phrases = {
        "תוכנית",
        "תוכנית נוכחית",
        "תוכנית פעילה",
        "הצג תוכנית",
        "שלח תוכנית",
        "plan",
        "show plan",
    }
    if lower in plan_now_phrases:
        return {"kind": "plan_now", "day": None}
    if lower in plan_show_phrases or lower.startswith("תוכנית "):
        # "תוכנית 2026-06-25" optional date
        m = re.fullmatch(r"תוכנית\s+(\d{4}-\d{2}-\d{2})", raw.strip())
        if m:
            return {"kind": "plan_show", "day": m.group(1)}
        if lower not in plan_now_phrases:
            return {"kind": "plan_show", "day": None}

    alloc_pick = re.fullmatch(r"ח([1-5])", raw.strip())
    if alloc_pick:
        return {"kind": "allocation_pick", "day": None, "option_id": int(alloc_pick.group(1))}

    alloc_named = re.fullmatch(r"חלוקה\s*([1-5])", raw.strip())
    if alloc_named:
        return {"kind": "allocation_pick", "day": None, "option_id": int(alloc_named.group(1))}

    action = "approve"
    rest = raw

    approve_prefixes = ("approve ", "אישור ", "אשר ")
    reject_prefixes = ("reject ", "דחה ", "דחייה ", "לא ")
    for prefix in approve_prefixes:
        if lower.startswith(prefix):
            action = "approve"
            rest = raw[len(prefix) :].strip()
            break
    else:
        for prefix in reject_prefixes:
            if lower.startswith(prefix):
                action = "reject"
                rest = raw[len(prefix) :].strip()
                break

    if lower in {"all", "הכל", "הכול", "כן", "yes", "ok", "אוקי", "יאללה"}:
        return {"kind": action, "day": None, "indices_raw": "ALL"}

    if lower in {"לא", "no", "reject", "דחה"}:
        return {"kind": "reject", "day": None, "indices_raw": "ALL"}

    if re.fullmatch(r"[\d,\s]+", raw) and any(ch.isdigit() for ch in raw):
        return {"kind": "approve", "day": None, "indices_raw": raw.replace(" ", "")}

    parts = rest.split() if rest else []
    day: str | None = None
    indices_raw = "ALL"

    if parts and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
        day = parts[0]
        parts = parts[1:]

    if parts:
        indices_raw = parts[0].upper()
        if len(parts) > 1 and parts[0].upper() in {"APPROVE", "REJECT"}:
            action = parts[0].lower()
            if len(parts) >= 3 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[1]):
                day = parts[1]
                indices_raw = parts[2].upper()
            elif len(parts) >= 2:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[1]):
                    day = parts[1]
                else:
                    indices_raw = parts[1].upper()

    upper = raw.upper()
    if upper.startswith("APPROVE ") or upper.startswith("REJECT "):
        legacy = raw.split()
        action = legacy[0].lower()
        if len(legacy) >= 3:
            day = legacy[1]
            indices_raw = legacy[2].upper()
        elif len(legacy) == 2:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", legacy[1]):
                day = legacy[1]
            else:
                indices_raw = legacy[1].upper()

    if indices_raw != "ALL" and not _looks_like_indices(indices_raw):
        return {"kind": "unknown"}

    return {"kind": action, "day": day, "indices_raw": indices_raw}


def _looks_like_indices(raw: str) -> bool:
    text = str(raw).strip().upper()
    if text == "ALL":
        return True
    return bool(re.fullmatch(r"[\d,\s]+", text) and any(ch.isdigit() for ch in text))


def telegram_help_text() -> str:
    from trading_pulse.telegram.telegram_format import user_guide_full

    return user_guide_full()


def telegram_unknown_reply() -> str:
    from trading_pulse.telegram.telegram_format import user_guide_full, user_guide_step1, user_guide_step2

    if allocation_choice_pending_for_active_plan():
        return "\n".join(["❓ <b>לא הבנתי.</b> אולי התכוונת לחלוקה?", "", user_guide_step2()])
    return "\n".join(["❓ <b>לא הבנתי.</b>", "", user_guide_full()])


def resend_plan_telegram(cfg: AgentConfig, plan: dict[str, Any]) -> None:
    """Resend existing plan to Telegram (no regeneration)."""
    from trading_pulse.telegram.app_notify import uses_telegram_notifications

    if not uses_telegram_notifications(cfg):
        return
    text = format_plan_message(plan)
    send_telegram_message(cfg, text, context="plan:resend", parse_mode="HTML")
    send_plan_table_image(cfg, plan)
    send_plan_stock_charts(cfg, plan)


def run_plan_now_telegram(cfg: AgentConfig) -> str:
    """Generate a fresh plan and deliver notifications."""
    state = load_state(cfg)
    plan = generate_plan(cfg, state, date.today(), force=True)
    send_plan_notifications(cfg, plan)
    day = plan.get("for_trading_day", "")
    n = len(plan.get("recommendations", []))
    if n == 0:
        reason = plan.get("no_picks_reason", "")
        extra = f"\n{reason}" if reason else ""
        return (
            f"<b>✅ תוכנית נוצרה</b>\n"
            f"<b>יום מסחר:</b> {day}\n"
            f"<b>המלצות:</b> 0 — אין כניסות חדשות.{extra}\n"
            "נשלח סיכום וטבלה."
        )
    return (
        f"<b>✅ תוכנית נוצרה</b>\n"
        f"<b>יום מסחר:</b> {day}\n"
        f"<b>המלצות:</b> {n}\n"
        f"נשלחו הודעות עם סיכום וגרפים."
    )


def process_telegram_commands(cfg: AgentConfig) -> int:
    if not uses_telegram_notifications(cfg):
        return 0
    token = str(cfg.telegram_bot_token).strip()
    chat_id = str(cfg.telegram_chat_id).strip()
    if not token or not chat_id:
        logging.debug("Telegram poll skipped: missing credentials")
        return 0
    state = load_state(cfg)
    offset = int(state.get("telegram_last_update_id", 0)) + 1
    data = telegram_api_call(
        token,
        "getUpdates",
        {"offset": offset, "timeout": 1},
    )
    updates = data.get("result", [])
    if not updates:
        logging.debug("Telegram poll: no new updates")
        return 0

    logging.info("Telegram poll: processing %d update(s)", len(updates))
    last_id = offset - 1
    handled = 0
    for upd in updates:
        last_id = max(last_id, int(upd.get("update_id", 0)))
        msg = upd.get("message", {})
        msg_chat_id = str(msg.get("chat", {}).get("id", ""))
        if msg_chat_id != chat_id:
            logging.debug("Ignoring update from chat %s", msg_chat_id)
            continue
        text = str(msg.get("text", "")).strip()
        if not text:
            continue
        log_telegram_message("in", "user", text)
        reply = telegram_unknown_reply()
        reply_context = "reply"
        logging.info("Telegram command received: %s", text)
        try:
            bare_digit_allocation = False
            if re.fullmatch(r"[1-5]", text.strip()) and allocation_choice_pending_for_active_plan():
                bare_digit_allocation = True
                parsed = {
                    "kind": "allocation_pick",
                    "day": None,
                    "option_id": int(text.strip()),
                }
            else:
                parsed = parse_telegram_user_command(text)
            kind = parsed.get("kind", "")

            if kind == "help":
                reply = telegram_help_text()
                reply_context = "reply:help"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "guide_telegram":
                from trading_pulse.telegram.telegram_guide import format_telegram_guide_messages

                for i, msg in enumerate(format_telegram_guide_messages()):
                    send_telegram_message(
                        cfg, msg, context=f"reply:guide_telegram:{i}", parse_mode="HTML"
                    )
                handled += 1
                continue
            elif kind == "guide_selection":
                from trading_pulse.guides.selection_guide import format_selection_guide_messages

                fresh_cfg = load_config()
                for i, msg in enumerate(format_selection_guide_messages(fresh_cfg.__dict__)):
                    send_telegram_message(
                        cfg, msg, context=f"reply:guide_selection:{i}", parse_mode="HTML"
                    )
                handled += 1
                continue
            elif kind == "guide_bot_setup":
                from trading_pulse.telegram.telegram_bot_guide import format_telegram_bot_guide_messages

                for i, msg in enumerate(format_telegram_bot_guide_messages()):
                    send_telegram_message(
                        cfg, msg, context=f"reply:guide_bot:{i}", parse_mode="HTML"
                    )
                handled += 1
                continue
            elif kind == "status":
                trading_day = resolve_trading_day(parsed.get("day"))
                reply = plan_status_text(trading_day)
                reply_context = "reply:status"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "portfolio":
                from trading_pulse.agent.portfolio import build_portfolio
                from trading_pulse.telegram.telegram_images import render_portfolio_image

                pdata = build_portfolio()
                img = render_portfolio_image(pdata)
                sign = "+" if pdata["total_realized_pnl"] >= 0 else ""
                caption = (
                    f"💼 <b>תיק</b> · הון <b>${pdata['equity']:.2f}</b> · "
                    f"P/L <b>{sign}${pdata['total_realized_pnl']:.2f}</b>"
                )
                send_telegram_photo(cfg, img, caption, context="reply:portfolio", parse_mode="HTML")
                handled += 1
                continue
            elif kind == "allocation_show":
                trading_day = resolve_trading_day(parsed.get("day"))
                plan = read_json(plan_path(date.fromisoformat(trading_day)))
                from trading_pulse.agent.capital_allocation import ensure_allocation_options, format_allocation_prompt

                state = load_state(cfg)
                options = ensure_allocation_options(cfg, plan, state)
                plan.setdefault("allocation", {})["options"] = options
                save_json(plan_path(date.fromisoformat(trading_day)), plan)
                reply = format_allocation_prompt(plan, options, trading_day=trading_day, state=state)
                reply_context = "reply:allocation"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "plan_show":
                trading_day = resolve_trading_day(parsed.get("day"))
                path = plan_path(date.fromisoformat(trading_day))
                if not path.exists():
                    reply = f"❌ <b>אין תוכנית ל-{trading_day}</b>\nחכה ל-21:00 או שלח <code>תוכנית עכשיו</code>"
                    reply_context = "reply:plan"
                    send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                else:
                    plan = read_json(path)
                    resend_plan_telegram(cfg, plan)
                    if plan.get("recommendations"):
                        reply = (
                            f"<b>📋 שלחתי שוב את התוכנית</b> · {trading_day}\n"
                            f"לאישור: <code>הכל</code> או <code>1,2</code>"
                        )
                    else:
                        reply = (
                            f"<b>📋 שלחתי שוב את התוכנית</b> · {trading_day}\n"
                            "אין המלצות היום — אין צורך באישור."
                        )
                    reply_context = "reply:plan"
                    send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "plan_now":
                reply = run_plan_now_telegram(cfg)
                reply_context = "reply:plan"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "tickers_list":
                from trading_pulse.agent.ticker_manager import format_tickers_list_html

                reply = format_tickers_list_html()
                reply_context = "reply:tickers"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "ticker_add":
                from trading_pulse.agent.ticker_manager import add_ticker, format_add_ticker_reply

                try:
                    result = add_ticker(str(parsed.get("symbol", "")))
                    reply = format_add_ticker_reply(result)
                except ValueError as ex:
                    reply = f"⚠️ <b>{ex}</b>"
                reply_context = "reply:ticker_add"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "ticker_remove":
                from trading_pulse.agent.ticker_manager import format_remove_ticker_reply, remove_ticker

                try:
                    result = remove_ticker(str(parsed.get("symbol", "")))
                    reply = format_remove_ticker_reply(result)
                except ValueError as ex:
                    reply = f"⚠️ <b>{ex}</b>"
                reply_context = "reply:ticker_remove"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "tickers_discover":
                from trading_pulse.agent.ticker_manager import discover_and_add_tickers, format_discover_reply

                fresh_cfg = load_config()
                result = discover_and_add_tickers(fresh_cfg, max_add=3)
                reply = format_discover_reply(result)
                reply_context = "reply:tickers_discover"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "allocation_pick":
                trading_day = resolve_trading_day(parsed.get("day"))
                option_id = int(parsed.get("option_id", 0))
                reply = apply_allocation_choice(trading_day, option_id, cfg=cfg)
                if bare_digit_allocation:
                    from trading_pulse.telegram.telegram_format import user_guide_bare_digit_allocation

                    reply = user_guide_bare_digit_allocation(option_id) + "\n\n" + reply
                reply_context = "reply:allocation"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind in {"approve", "reject"}:
                trading_day = resolve_trading_day(parsed.get("day"))
                plan = read_json(plan_path(date.fromisoformat(trading_day)))
                total = len(plan.get("recommendations", []))
                indices = parse_indices(str(parsed.get("indices_raw", "ALL")), total=total)
                if not indices:
                    from trading_pulse.telegram.telegram_format import user_guide_invalid_approve

                    reply = user_guide_invalid_approve()
                    reply_context = f"reply:{kind}"
                    send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                    handled += 1
                    continue
                else:
                    reply = set_plan_status(trading_day, kind.upper(), indices, cfg=cfg)
                    reply_context = f"reply:{kind}"
                    send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                    handled += 1
                    continue
            else:
                reply = telegram_unknown_reply()
        except ValueError as ex:
            if str(ex) == "no_active_plan":
                reply = "📭 <b>אין תוכנית פעילה.</b>\nחכה להודעה ב-21:00 או שלח <code>סטטוס</code>."
            else:
                reply = "⚠️ <b>תאריך לא תקין.</b>"
            reply_context = "reply:error"
        except Exception as ex:
            from trading_pulse.telegram.telegram_format import escape_html

            reply = f"❌ <b>שגיאה:</b> {escape_html(str(ex))}\n\nנסה שוב או שלח <code>עזרה</code>"
            reply_context = "reply:error"
            logging.exception("Telegram command failed: %s", ex)
        send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
        handled += 1

    state["telegram_last_update_id"] = last_id
    save_json(STATE_FILE, state)
    logging.info("Telegram poll done: handled %d command(s)", handled)
    return handled


def _extract_series(df: pd.DataFrame, col: str) -> pd.Series:
    series = df[col]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series


def fetch_signal_universe(tickers: list[str], cfg: AgentConfig) -> pd.DataFrame:
    speculative = is_speculative(cfg)
    logging.info(
        "Fetching signals from %d sources: %s",
        len(cfg.signal_sources),
        ", ".join(cfg.signal_sources),
    )
    return build_signal_universe(
        tickers,
        cfg.signal_sources,
        speculative,
        cfg.min_signal_sources,
        min_volume_ratio=cfg.min_volume_ratio,
        min_price_usd=cfg.min_price_usd,
        min_avg_volume_20d=cfg.min_avg_volume_20d,
        source_weights=cfg.source_weights,
        max_source_score_std=cfg.max_source_score_std,
        max_source_score_spread=cfg.max_source_score_spread,
        disagreement_score_penalty=cfg.disagreement_score_penalty,
        exclude_on_source_disagreement=cfg.exclude_on_source_disagreement,
    )


def generate_plan(
    cfg: AgentConfig,
    state: dict[str, Any],
    run_day: date,
    *,
    force: bool = False,
) -> dict[str, Any]:
    from trading_pulse.agent.ticker_manager import list_tickers

    # Reload watchlist so Telegram add/remove applies without restart.
    try:
        cfg.tickers = list_tickers()
    except OSError:
        pass

    from trading_pulse.agent.positions import available_capital, deployed_capital, held_symbols, holdings_snapshot

    target_day = get_next_us_trading_day(run_day)
    existing_path = plan_path(target_day)
    if not force and existing_path.exists():
        existing = read_json(existing_path)
        if plan_is_protected(existing):
            logging.info(
                "Plan for %s is approved/allocated — skipping regeneration",
                target_day.isoformat(),
            )
            existing["_regeneration_skipped"] = True
            return existing
    strategy = profile_strategy(cfg)
    capital = float(state["equity"])
    held = held_symbols(state)
    holdings = holdings_snapshot(state)
    logging.info("Scanning %d tickers (%s strategy)", len(cfg.tickers), strategy)
    candidates = fetch_signal_universe(cfg.tickers, cfg)
    candidates_before_quality = len(candidates)
    logging.info("Found %d candidate(s) before quality filters", candidates_before_quality)
    from trading_pulse.agent.symbol_cooldown import filter_candidates_dataframe

    filter_stats: dict[str, Any] = {}
    candidates = filter_candidates_dataframe(
        candidates,
        state,
        cfg,
        held_symbols=held,
        as_of=run_day,
        stats_out=filter_stats,
    )
    logging.info("Found %d candidate(s) after quality filters", len(candidates))
    open_slots = max(0, int(cfg.max_open_positions) - len(holdings))
    new_trade_slots = min(open_slots, int(cfg.max_trades_per_day))
    deployable = available_capital(cfg, state)
    per_trade_cap = min(capital * cfg.max_position_pct, deployable / max(new_trade_slots, 1))

    if not candidates.empty and held:
        candidates = candidates[~candidates["symbol"].isin(held)]
    logging.info(
        "Plan slots: %d new | holding %d symbol(s) | deployed $%s",
        new_trade_slots,
        len(holdings),
        deployed_capital(state),
    )
    picks = candidates.head(new_trade_slots) if new_trade_slots > 0 and not candidates.empty else pd.DataFrame()
    recommendations: list[dict[str, Any]] = []
    speculative = is_speculative(cfg)

    for rank, (_, row) in enumerate(picks.iterrows(), start=1):
        entry = float(row["close"])
        vol_ratio = float(row.get("vol_ratio", 0.0))
        volume_flag = "yes" if bool(row.get("volume_ok", False)) else "no"
        rec: dict[str, Any] = {
            "symbol": row["symbol"],
            "side": "LONG",
            "capital_usd": round(per_trade_cap, 2),
            "entry_ref_price": round(entry, 4),
            "stop_loss_price": round(entry * (1 - cfg.stop_loss_pct), 4),
            "take_profit_price": round(entry * (1 + cfg.take_profit_pct), 4),
            "floor_price": round(entry * (1 - cfg.stop_loss_pct), 4),
            "stop_loss_pct": cfg.stop_loss_pct,
            "take_profit_pct": cfg.take_profit_pct,
            "score": round(float(row["score"]), 4),
            "score_technical": round(float(row.get("score_technical", row["score"])), 4),
            "score_simple_avg": round(float(row.get("score_simple_avg", row["score"])), 4),
            "source_score_std": round(float(row.get("source_score_std", 0)), 4),
            "source_score_spread": round(float(row.get("source_score_spread", 0)), 4),
            "source_disagreement": bool(row.get("source_disagreement", False)),
            "ret_5d_pct": round(float(row.get("ret_5d_pct", 0)), 2),
            "vol_ratio": round(vol_ratio, 2),
            "volume_ok": bool(row.get("volume_ok", False)),
            "source_scores": dict(row.get("source_scores", {})),
            "sources_used": int(row.get("sources_used", 0)),
            "sources_list": list(row.get("sources_list", [])),
            "approved": False,
        }
        if speculative:
            breakout_flag = "yes" if bool(row.get("breakout_ok", False)) else "no"
            atr_pct = round(float(row.get("atr_pct", 0)), 2)
            rec.update(
                {
                    "atr_pct": atr_pct,
                    "near_high_pct": round(float(row.get("near_high_pct", 0)), 2),
                    "breakout_ok": bool(row.get("breakout_ok", False)),
                    "reason": (
                        f"Speculative: ATR {atr_pct:.1f}%, "
                        f"breakout={breakout_flag}, vol {vol_ratio:.2f}x"
                    ),
                }
            )
        else:
            momentum_flag = "yes" if bool(row.get("momentum_ok", False)) else "no"
            rec.update(
                {
                    "above_ma20_pct": round(float(row.get("above_ma20_pct", 0)), 2),
                    "momentum_ok": bool(row.get("momentum_ok", False)),
                    "reason": f"Momentum(MA20): {momentum_flag}, Volume ratio: {vol_ratio:.2f}x (signal={volume_flag})",
                }
            )
        recommendations.append(rec)

    enrich_recommendations(recommendations, cfg, speculative=speculative)

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "for_trading_day": target_day.isoformat(),
        "risk_profile": cfg.risk_profile,
        "strategy": strategy,
        "hold_mode": cfg.hold_mode,
        "risk_profile_summary": risk_profile_summary(cfg, capital),
        "equity_snapshot": round(capital, 2),
        "deployed_capital_usd": deployed_capital(state),
        "available_capital_usd": round(deployable, 2),
        "holdings": holdings,
        "max_trades": new_trade_slots,
        "planned_per_trade_cap": round(per_trade_cap, 2),
        "daily_loss_limit_usd": round(capital * cfg.max_daily_loss_pct, 2),
        "monthly_target_usd": cfg.monthly_target_usd,
        "recommendations": recommendations,
        "scan_stats": {
            "tickers_scanned": len(cfg.tickers),
            "before_quality": candidates_before_quality,
            "after_quality": len(candidates),
            "min_entry_score": float(cfg.min_entry_score or 0),
            "min_volume_ratio": float(cfg.min_volume_ratio or 0),
            **filter_stats,
        },
    }
    if recommendations:
        plan["status"] = "pending_approval"
    elif holdings:
        plan["status"] = "hold_only"
    else:
        plan["status"] = "no_picks"
        if candidates_before_quality > 0 and candidates.empty:
            top = filter_stats.get("top_skipped_scores") or []
            if top:
                names = ", ".join(f"{r['symbol']} ({r['score']:.1f})" for r in top[:3])
                plan["no_picks_reason"] = (
                    f"סף ציון {cfg.min_entry_score:.0f} — הציונים הגבוהים: {names}"
                )
            else:
                plan["no_picks_reason"] = "הסינון האיכותי לא מצא מניה שעומדת בכל התנאים."
        else:
            plan["no_picks_reason"] = "לא נמצאו מועמדים בסריקת האותות להיום."
    if speculative:
        plan["monthly_target_summary"] = monthly_target_summary(cfg, state)
    save_json(plan_path(target_day), plan)
    logging.info("Saved plan: %s", plan_path(target_day))
    return plan


def approve_plan(trading_day: str) -> None:
    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        raise FileNotFoundError(f"No plan found for {trading_day}: {path}")
    plan = read_json(path)
    recs = plan.get("recommendations", [])
    if not recs:
        print("No recommendations to approve.")
        return
    for rec in recs:
        q = f"Approve {rec['symbol']} LONG ${rec['capital_usd']}? [y/N]: "
        ans = input(q).strip().lower()
        rec["approved"] = ans in {"y", "yes"}
    plan["status"] = "approved"
    plan["approved_at"] = datetime.now(timezone.utc).isoformat()
    save_json(path, plan)
    print(f"Saved approvals for {trading_day}: {path}")


def simulation_already_done(state: dict[str, Any], trading_day: date) -> bool:
    day_str = trading_day.isoformat()
    if state.get("last_report_date") == day_str:
        return True
    return any(h.get("trading_day") == day_str for h in state.get("history", []))


def revert_prior_simulation(state: dict[str, Any], trading_day: date) -> None:
    day_str = trading_day.isoformat()
    history = state.get("history", [])
    prior = [h for h in history if h.get("trading_day") == day_str]
    if not prior:
        return
    pnl_total = sum(float(h.get("pnl_usd", 0)) for h in prior)
    state["equity"] = round(float(state["equity"]) - pnl_total, 2)
    state["history"] = [h for h in history if h.get("trading_day") != day_str]
    remaining = state["history"]
    state["last_report_date"] = remaining[-1]["trading_day"] if remaining else None


def _merge_intraday_floor_exits(
    state: dict[str, Any],
    trading_day: date,
    executed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    day_str = trading_day.isoformat()
    merged = list(executed)
    seen = {str(t.get("symbol")) for t in merged}
    for row in state.get("intraday_floor_exits") or []:
        if row.get("trading_day") != day_str:
            continue
        symbol = str(row.get("symbol", ""))
        if not symbol or symbol in seen:
            continue
        merged.insert(
            0,
            {
                "symbol": symbol,
                "entry_price": row.get("entry_price"),
                "exit_price": row.get("exit_price"),
                "exit_reason": row.get("exit_reason", "floor_price"),
                "capital_usd": row.get("capital_usd"),
                "pnl_pct": row.get("pnl_pct"),
                "pnl_usd": row.get("pnl_usd"),
                "days_held": row.get("days_held"),
                "entry_day": row.get("entry_day"),
                "fees_usd": row.get("fees_usd", 0),
                "intraday_exit": True,
            },
        )
        seen.add(symbol)
    return merged


def simulate_day(
    cfg: AgentConfig,
    state: dict[str, Any],
    trading_day: date,
    *,
    force: bool = False,
) -> dict[str, Any]:
    rpath = report_path(trading_day)
    if force and rpath.exists():
        revert_prior_simulation(state, trading_day)
        try:
            rpath.unlink(missing_ok=True)
        except OSError:
            pass

    if not force and rpath.exists():
        existing = read_json(rpath)
        if simulation_already_done(state, trading_day):
            logging.info(
                "Simulation skipped for %s: already completed (report exists)",
                trading_day.isoformat(),
            )
            existing["_skipped"] = True
            return existing
        logging.info(
            "Simulation skipped for %s: report file exists (use --force to re-run)",
            trading_day.isoformat(),
        )
        existing["_skipped"] = True
        return existing

    path = plan_path(trading_day)
    if not path.exists():
        raise FileNotFoundError(f"No plan file for {trading_day}.")
    plan = read_json(path)
    approved = [x for x in plan.get("recommendations", []) if x.get("approved")]
    logging.info("Simulation for %s: %d approved trade(s)", trading_day.isoformat(), len(approved))
    ensure_plan_allocation(cfg, plan, state, trading_day)
    plan = read_json(path)
    approved = [x for x in plan.get("recommendations", []) if x.get("approved")]

    if getattr(cfg, "hold_mode", "swing") == "swing":
        from trading_pulse.agent.positions import simulate_swing_day

        equity_before = float(state["equity"])
        daily_loss_limit = equity_before * cfg.max_daily_loss_pct
        executed, held_eod, pnl_total, fees_total = simulate_swing_day(
            cfg, state, trading_day, approved
        )
        executed = _merge_intraday_floor_exits(state, trading_day, executed)
        if not executed and not approved and not held_eod:
            report = {
                "trading_day": trading_day.isoformat(),
                "executed": [],
                "held_eod": [],
                "pnl_usd": 0.0,
                "fees_usd": 0.0,
                "equity_before": round(equity_before, 2),
                "equity_after": round(equity_before, 2),
                "note": "No trades.",
            }
            save_json(report_path(trading_day), report)
            return report

        equity_after = equity_before + pnl_total
        report = {
            "trading_day": trading_day.isoformat(),
            "executed": executed,
            "held_eod": held_eod,
            "pnl_usd": round(pnl_total, 2),
            "fees_usd": fees_total,
            "equity_before": round(equity_before, 2),
            "equity_after": round(equity_after, 2),
            "max_daily_loss_usd": round(daily_loss_limit, 2),
            "hold_mode": "swing",
        }
        save_json(report_path(trading_day), report)
        state["equity"] = round(equity_after, 2)
        state["last_report_date"] = trading_day.isoformat()
        state["history"].append(report)
        ensure_month_tracking(cfg, state)
        if is_speculative(cfg):
            report["monthly_target_summary"] = monthly_target_summary(cfg, state)
            save_json(report_path(trading_day), report)
        save_json(STATE_FILE, state)
        return report

    if not approved:
        report = {
            "trading_day": trading_day.isoformat(),
            "executed": [],
            "pnl_usd": 0.0,
            "equity_before": round(float(state["equity"]), 2),
            "equity_after": round(float(state["equity"]), 2),
            "note": "No approved trades.",
        }
        save_json(report_path(trading_day), report)
        return report

    equity_before = float(state["equity"])
    daily_loss_limit = equity_before * cfg.max_daily_loss_pct
    pnl_total = 0.0
    executed: list[dict[str, Any]] = []

    for rec in approved[: cfg.max_trades_per_day]:
        if pnl_total <= -daily_loss_limit:
            break
        symbol = rec["symbol"]
        day_df = yf.download(
            symbol,
            start=trading_day.isoformat(),
            end=(trading_day + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        ).dropna()
        if day_df.empty:
            continue

        open_col = day_df["Open"]
        high_col = day_df["High"]
        low_col = day_df["Low"]
        close_col = day_df["Close"]
        if isinstance(open_col, pd.DataFrame):
            open_col = open_col.iloc[:, 0]
        if isinstance(high_col, pd.DataFrame):
            high_col = high_col.iloc[:, 0]
        if isinstance(low_col, pd.DataFrame):
            low_col = low_col.iloc[:, 0]
        if isinstance(close_col, pd.DataFrame):
            close_col = close_col.iloc[:, 0]

        o = float(open_col.iloc[0])
        h = float(high_col.iloc[0])
        l = float(low_col.iloc[0])
        c = float(close_col.iloc[0])

        stop_price = o * (1 - cfg.stop_loss_pct)
        take_price = o * (1 + cfg.take_profit_pct)
        capital = min(float(rec["capital_usd"]), equity_before * cfg.max_position_pct)

        if l <= stop_price:
            exit_price = stop_price
            exit_reason = "stop_loss"
        elif h >= take_price:
            exit_price = take_price
            exit_reason = "take_profit"
        else:
            exit_price = c
            exit_reason = "close"

        pnl_pct = (exit_price / o) - 1
        pnl_usd = capital * pnl_pct
        pnl_total += pnl_usd

        executed.append(
            {
                "symbol": symbol,
                "entry_price": round(o, 4),
                "exit_price": round(exit_price, 4),
                "exit_reason": exit_reason,
                "capital_usd": round(capital, 2),
                "pnl_pct": round(pnl_pct * 100, 3),
                "pnl_usd": round(pnl_usd, 2),
            }
        )

    equity_after = equity_before + pnl_total
    report = {
        "trading_day": trading_day.isoformat(),
        "executed": executed,
        "pnl_usd": round(pnl_total, 2),
        "equity_before": round(equity_before, 2),
        "equity_after": round(equity_after, 2),
        "max_daily_loss_usd": round(daily_loss_limit, 2),
    }
    save_json(report_path(trading_day), report)

    state["equity"] = round(equity_after, 2)
    state["last_report_date"] = trading_day.isoformat()
    state["history"].append(report)
    ensure_month_tracking(cfg, state)
    if is_speculative(cfg):
        report["monthly_target_summary"] = monthly_target_summary(cfg, state)
        save_json(report_path(trading_day), report)
    save_json(STATE_FILE, state)
    return report


def plan_notification_payload(cfg: AgentConfig, plan: dict[str, Any]) -> tuple[str, str | None]:
    if uses_app_notifications(cfg):
        return format_plan_message_for_app(plan), None
    return format_plan_message(plan), "HTML"


def cmd_plan(args: argparse.Namespace) -> None:
    ensure_dirs()
    setup_logger()
    cfg = load_config()
    state = load_state(cfg)
    run_day = date.fromisoformat(args.day) if args.day else date.today()
    plan = generate_plan(cfg, state, run_day)
    logging.info("Plan generated for %s", plan["for_trading_day"])
    logging.info("Recommendations: %d", len(plan["recommendations"]))
    send_plan_notifications(cfg, plan)


def cmd_approve(args: argparse.Namespace) -> None:
    ensure_dirs()
    approve_plan(args.day)


def cmd_simulate(args: argparse.Namespace) -> None:
    ensure_dirs()
    setup_logger()
    cfg = load_config()
    state = load_state(cfg)
    trading_day = date.fromisoformat(args.day) if args.day else date.today()
    report = simulate_day(cfg, state, trading_day, force=getattr(args, "force", False))
    if report.get("_skipped"):
        logging.info("Simulation skipped for %s (already done)", trading_day.isoformat())
        return
    logging.info("Simulated %s", trading_day.isoformat())
    logging.info("PnL USD: %s", report["pnl_usd"])
    send_user_notification(cfg, format_report_message(report), context="report", parse_mode="HTML")
    send_report_table_image(cfg, report)


def cmd_telegram_poll(_: argparse.Namespace) -> None:
    ensure_dirs()
    setup_logger(scheduler_log_file())
    cfg = load_config()
    handled = process_telegram_commands(cfg)
    logging.info("Telegram poll completed (%d command(s))", handled)


def cmd_reset_experiment(args: argparse.Namespace) -> None:
    from trading_pulse.agent.experiment_reset import reset_experiment

    ensure_dirs()
    setup_logger(scheduler_log_file())
    label = str(getattr(args, "label", None) or "july_2026")
    month = getattr(args, "month", None)
    result = reset_experiment(label=label, month_key=month)
    logging.info(
        "Experiment reset: %s | equity $%s | archive %s",
        result["label"],
        result["starting_equity"],
        result["archive_dir"],
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_heartbeat(_: argparse.Namespace) -> None:
    ensure_dirs()
    setup_logger(scheduler_log_file())
    cfg = load_config()
    # Force send even if already sent today (for manual test).
    state = load_state(cfg)
    state.pop("last_heartbeat_date", None)
    save_json(STATE_FILE, state)
    send_heartbeat(cfg, reason="manual")


def cmd_intraday_check(args: argparse.Namespace) -> None:
    from trading_pulse.agent.intraday_monitor import build_intraday_report, is_within_market_hours, run_intraday_check
    from trading_pulse.telegram.telegram_format import format_intraday_monitor

    ensure_dirs()
    setup_logger(scheduler_log_file())
    cfg = load_config()
    state = load_state(cfg)
    if getattr(args, "dry_run", False):
        report = build_intraday_report(cfg, state)
        print(format_intraday_monitor(report))
        return
    if not getattr(args, "force", False) and not is_within_market_hours(cfg):
        logging.warning("Outside market hours — use --force to run anyway")
        return
    sent = run_intraday_check(cfg, state)
    logging.info("Intraday check %s", "sent" if sent else "no alert")


def cmd_telegram_test(_: argparse.Namespace) -> None:
    ensure_dirs()
    setup_logger()
    cfg = load_config()
    token = str(cfg.telegram_bot_token).strip()
    chat_id = str(cfg.telegram_chat_id).strip()
    if not token or not chat_id:
        logging.error("Missing telegram_bot_token or telegram_chat_id in config.json")
        return

    logging.info("Token length: %d", len(token))
    logging.info("Chat ID repr: %r", chat_id)
    try:
        me = telegram_api_call(token, "getMe", {})
        logging.info("getMe ok, bot username: %s", me["result"].get("username"))
    except Exception as ex:
        logging.exception("getMe failed: %s", ex)
        return

    # getChat is useful to validate the chat id target.
    chat_resp = telegram_raw_post(token, "getChat", {"chat_id": chat_id})
    logging.info("getChat status=%s body=%s", chat_resp.status_code, chat_resp.text[:500])

    send_resp = telegram_raw_post(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": "telegram-test from dryrun_agent"},
    )
    logging.info("sendMessage status=%s body=%s", send_resp.status_code, send_resp.text[:500])


def run_scheduler_loop(service: bool = True) -> None:
    """Run the daily schedule loop (blocks until interrupted)."""
    from trading_pulse.agent.health_tracker import record_job
    from trading_pulse.core.instance_lock import acquire_instance_lock

    if not acquire_instance_lock("scheduler" if not service else "app-scheduler"):
        return

    ensure_dirs()
    log_file = scheduler_log_file() if service else None
    setup_logger(log_file)
    cfg = load_config()

    def run_plan_job() -> None:
        today = date.today()
        if not should_send_plan_today(today):
            record_job("plan", "skipped", f"no trading day; today={today.isoformat()}")
            logging.info(
                "JOB SKIP: daily plan (no US trading tomorrow; today=%s)",
                today.isoformat(),
            )
            return
        logging.info("JOB START: daily plan")
        try:
            state = load_state(cfg)
            plan = generate_plan(cfg, state, today)
            if plan.pop("_regeneration_skipped", False):
                record_job(
                    "plan",
                    "skipped",
                    f"protected plan kept for {plan['for_trading_day']}",
                )
                logging.info(
                    "JOB SKIP: daily plan (protected plan kept for %s)",
                    plan["for_trading_day"],
                )
                return
            logging.info(
                "Plan ready for %s with %d recommendation(s)",
                plan["for_trading_day"],
                len(plan.get("recommendations", [])),
            )
            send_plan_notifications(cfg, plan)
            record_job("plan", "ok", trading_day=plan["for_trading_day"])
            logging.info("JOB END: daily plan")
        except Exception as ex:
            record_job("plan", "failed", str(ex))
            logging.exception("JOB FAILED: daily plan: %s", ex)

    def run_sim_job() -> None:
        today = date.today()
        if not should_run_simulation_today(today):
            record_job("simulation", "skipped", f"today={today.isoformat()}")
            logging.info(
                "JOB SKIP: daily simulation (market closed or no plan; today=%s)",
                today.isoformat(),
            )
            return
        logging.info("JOB START: daily simulation")
        try:
            state = load_state(cfg)
            report = simulate_day(cfg, state, today)
            if report.get("_skipped"):
                record_job("simulation", "skipped", f"already done; day={today.isoformat()}")
                logging.info("JOB SKIP: daily simulation (already completed for %s)", today)
                return
            logging.info(
                "Simulation done for %s | PnL $%s | equity $%s -> $%s",
                report["trading_day"],
                report["pnl_usd"],
                report["equity_before"],
                report["equity_after"],
            )
            send_user_notification(cfg, format_report_message(report), context="report", parse_mode="HTML")
            send_report_table_image(cfg, report)
            record_job("simulation", "ok", trading_day=report["trading_day"], pnl=report["pnl_usd"])
            logging.info("JOB END: daily simulation")
        except Exception as ex:
            record_job("simulation", "failed", str(ex))
            logging.exception("JOB FAILED: daily simulation: %s", ex)

    def run_heartbeat_job() -> None:
        logging.info("JOB START: heartbeat")
        try:
            send_heartbeat(cfg, reason="daily")
            record_job("heartbeat", "ok")
            logging.info("JOB END: heartbeat")
        except Exception as ex:
            record_job("heartbeat", "failed", str(ex))
            logging.exception("JOB FAILED: heartbeat: %s", ex)

    def run_plan_reminder_job() -> None:
        from trading_pulse.agent.plan_reminders import send_pre_simulation_reminder

        today = date.today()
        active_cfg = load_config()
        try:
            if send_pre_simulation_reminder(active_cfg, today):
                record_job("plan_reminder", "ok", f"day={today.isoformat()}")
                logging.info("JOB DONE: plan reminder for %s", today.isoformat())
            else:
                record_job("plan_reminder", "skipped", f"not needed; day={today.isoformat()}")
        except Exception as ex:
            record_job("plan_reminder", "failed", str(ex))
            logging.exception("JOB FAILED: plan reminder: %s", ex)

    def run_intraday_check_job() -> None:
        from trading_pulse.agent.intraday_monitor import run_intraday_check

        active_cfg = load_config()
        if not active_cfg.intraday_check_enabled:
            return
        today = date.today()
        if not is_us_trading_day(today):
            return
        logging.info("JOB START: intraday check")
        try:
            state = load_state(active_cfg)
            sent = run_intraday_check(active_cfg, state)
            if sent:
                record_job("intraday_check", "ok", f"day={today.isoformat()}")
                logging.info("JOB END: intraday check (alert sent)")
            else:
                record_job("intraday_check", "skipped", "nothing noteworthy")
                logging.info("JOB END: intraday check (quiet)")
        except Exception as ex:
            record_job("intraday_check", "failed", str(ex))
            logging.exception("JOB FAILED: intraday check: %s", ex)

    schedule.every().day.at(cfg.planning_time).do(run_plan_job)
    schedule.every().day.at(cfg.market_close_sim_time).do(run_sim_job)
    schedule.every().day.at(cfg.heartbeat_time).do(run_heartbeat_job)
    schedule.every().day.at(cfg.plan_reminder_time).do(run_plan_reminder_job)
    cfg_holder: dict[str, AgentConfig] = {"cfg": cfg}

    def run_telegram_poll_job() -> None:
        try:
            handled = process_telegram_commands(cfg_holder["cfg"])
            if handled:
                record_job("telegram_poll", "ok", f"{handled} command(s)")
                logging.info("JOB DONE: telegram poll (%d command(s))", handled)
        except requests.exceptions.Timeout as ex:
            logging.warning("Telegram poll timeout (will retry): %s", ex)
            record_job("telegram_poll", "skipped", "timeout — will retry")
        except requests.exceptions.RequestException as ex:
            logging.warning("Telegram poll network error (will retry): %s", ex)
            record_job("telegram_poll", "skipped", f"network: {ex}")
        except Exception as ex:
            record_job("telegram_poll", "failed", str(ex))
            logging.exception("JOB FAILED: telegram poll: %s", ex)

    def schedule_telegram_poll(interval_sec: int) -> None:
        schedule.clear("telegram-poll")
        schedule.every(interval_sec).seconds.do(run_telegram_poll_job).tag("telegram-poll")

    def schedule_intraday_check(interval_min: int) -> None:
        schedule.clear("intraday-check")
        schedule.every(max(15, interval_min)).minutes.do(run_intraday_check_job).tag("intraday-check")

    if cfg.intraday_check_enabled:
        schedule_intraday_check(cfg.intraday_check_interval_minutes)

    if uses_telegram_notifications(cfg):
        schedule_telegram_poll(cfg.telegram_poll_interval_sec)
        logging.info("Telegram poll: running once at startup")
        try:
            handled = process_telegram_commands(cfg)
            if handled:
                record_job("telegram_poll", "ok", f"{handled} command(s) at startup")
                logging.info("Telegram startup poll: handled %d command(s)", handled)
        except Exception as ex:
            logging.warning("Telegram startup poll failed (scheduler will retry): %s", ex)

    logging.info("Scheduler started")
    logging.info("  notification_mode: %s", cfg.notification_mode)
    logging.info("  risk profile: %s", risk_profile_summary(cfg))
    logging.info("  heartbeat: %s", cfg.heartbeat_time)
    logging.info("  plan: %s", cfg.planning_time)
    logging.info("  plan reminder: %s", cfg.plan_reminder_time)
    logging.info("  simulation report: %s", cfg.market_close_sim_time)
    if cfg.intraday_check_enabled:
        logging.info(
            "  intraday check: every %s min (%s–%s)",
            cfg.intraday_check_interval_minutes,
            cfg.market_open_sim_time,
            cfg.market_close_sim_time,
        )
    if uses_telegram_notifications(cfg):
        logging.info("  telegram poll: every %s sec", cfg.telegram_poll_interval_sec)
    if log_file:
        logging.info("Logging to %s", log_file)

    if service and cfg.send_heartbeat_on_startup:
        send_heartbeat(cfg, reason="startup")

    record_job("scheduler", "running", f"mode={cfg.notification_mode}")
    logging.info("Waiting for scheduled jobs... (Ctrl+C to stop)")
    poll_interval = cfg.telegram_poll_interval_sec
    intraday_interval = cfg.intraday_check_interval_minutes
    intraday_scheduled = bool(cfg.intraday_check_enabled)
    while True:
        fresh = load_config()
        cfg_holder["cfg"] = fresh
        if uses_telegram_notifications(fresh) and fresh.telegram_poll_interval_sec != poll_interval:
            poll_interval = fresh.telegram_poll_interval_sec
            schedule_telegram_poll(poll_interval)
            logging.info("Telegram poll interval reloaded: every %s sec", poll_interval)
        if fresh.intraday_check_enabled:
            if not intraday_scheduled or intraday_interval != fresh.intraday_check_interval_minutes:
                intraday_interval = fresh.intraday_check_interval_minutes
                schedule_intraday_check(intraday_interval)
                intraday_scheduled = True
                logging.info("Intraday check interval: every %s min", intraday_interval)
        elif intraday_scheduled:
            schedule.clear("intraday-check")
            intraday_scheduled = False
            logging.info("Intraday check disabled")
        schedule.run_pending()
        time.sleep(max(1, schedule.idle_seconds()))


def cmd_run_scheduler(args: argparse.Namespace) -> None:
    run_scheduler_loop(service=args.service)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="US stocks/ETFs dry-run trading agent")
    sub = p.add_subparsers(required=True)

    plan_cmd = sub.add_parser("plan", help="Generate tomorrow plan")
    plan_cmd.add_argument("--day", help="Run day YYYY-MM-DD")
    plan_cmd.set_defaults(func=cmd_plan)

    approve_cmd = sub.add_parser("approve", help="Approve plan for a trading day")
    approve_cmd.add_argument("--day", required=True, help="Trading day YYYY-MM-DD")
    approve_cmd.set_defaults(func=cmd_approve)

    sim_cmd = sub.add_parser("simulate", help="Simulate approved trades for day")
    sim_cmd.add_argument("--day", help="Trading day YYYY-MM-DD")
    sim_cmd.add_argument("--force", action="store_true", help="Re-run even if report exists")
    sim_cmd.set_defaults(func=cmd_simulate)

    scheduler_cmd = sub.add_parser("run-scheduler", help="Run daily scheduler")
    scheduler_cmd.add_argument(
        "--service",
        action="store_true",
        help="Also write logs to data/logs/scheduler.log (for background service)",
    )
    scheduler_cmd.set_defaults(func=cmd_run_scheduler)

    telegram_poll_cmd = sub.add_parser("telegram-poll", help="Poll Telegram and apply commands")
    telegram_poll_cmd.set_defaults(func=cmd_telegram_poll)

    telegram_test_cmd = sub.add_parser("telegram-test", help="Debug Telegram configuration")
    telegram_test_cmd.set_defaults(func=cmd_telegram_test)

    heartbeat_cmd = sub.add_parser("heartbeat", help="Send heartbeat message to Telegram now")
    heartbeat_cmd.set_defaults(func=cmd_heartbeat)

    intraday_cmd = sub.add_parser("intraday-check", help="Run hourly intraday monitor once")
    intraday_cmd.add_argument("--force", action="store_true", help="Run even outside market hours")
    intraday_cmd.add_argument("--dry-run", action="store_true", help="Print report without sending")
    intraday_cmd.set_defaults(func=cmd_intraday_check)

    reset_cmd = sub.add_parser("reset-experiment", help="Archive state and start a clean experiment")
    reset_cmd.add_argument("--label", default="july_2026", help="Experiment label for archive folder")
    reset_cmd.add_argument("--month", default="2026-07", help="Month key YYYY-MM for target tracking")
    reset_cmd.set_defaults(func=cmd_reset_experiment)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
