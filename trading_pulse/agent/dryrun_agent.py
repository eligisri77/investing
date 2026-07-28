import argparse
import json
import logging
import re
import sys
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
        "max_open_positions": 5,
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
    planning_time: str = "20:15"  # UTC ≈ 16:15 ET — תוכנית אחרי סגירת וול סטריט
    entry_sim_time: str = "13:35"  # UTC ≈ 09:35 ET — כניסה במחיר פתיחה
    market_open_sim_time: str = "13:30"  # UTC ≈ 09:30 ET — תחילת מעקב intraday
    market_close_sim_time: str = "20:20"  # UTC ≈ 16:20 ET — דוח סוף יום
    heartbeat_time: str = "13:00"  # UTC ≈ 09:00 ET
    send_heartbeat_on_startup: bool = True
    plan_reminder_time: str = "20:00"  # UTC ≈ 16:00 ET — תזכורת לפני תוכנית
    initial_deploy_stocks: int = 4  # יום ראשון — חלוקה על כמה מניות (כולל מניית נרות)
    strategy_mode: str = "balanced_mix"
    candle_fourth_enabled: bool = True  # מניה רביעית לפי Rising Three Methods
    trend_pullback_enabled: bool = False
    vcp_breakout_enabled: bool = False
    relative_strength_enabled: bool = False
    market_regime_filter_enabled: bool = False
    method2_allow_short: bool = True
    method2_enabled: bool = True  # מניה חמישית — שיטה 2 (שרוול סיכון)
    method2_risk_pct: float = 0.02
    method2_max_position_pct: float = 0.15
    method2_intraday_enabled: bool = True  # פריצה תוך־יומית (5m/1m) אחרי הבוקר
    method2_intraday_intervals: list[str] | None = None  # default ["5m","1m"]
    intraday_check_enabled: bool = True
    intraday_check_interval_minutes: int = 60
    intraday_alert_cooldown_minutes: int = 120
    telegram_poll_interval_sec: int = 10
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
    max_open_positions: int = 5
    commission_per_side_usd: float = 1.0
    weekly_scan_enabled: bool = True
    weekly_scan_day: str = "sunday"
    weekly_scan_time: str = "06:00"
    weekly_watchlist_size: int = 60
    weekly_scan_chunk: int = 20
    weekly_scan_throttle_sec: float = 1.5
    weekly_strategy_rank_enabled: bool = True
    weekly_strategy_enrich_cap: int = 150
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
    parts = risk_profile_parts(cfg, equity)
    return (
        f"{parts['label']} · "
        f"עד {parts['max_deploy_pct']}% מההון מושקע (${parts['max_deploy_usd']:.0f}) · "
        f"עד {parts['max_trades']} עסקאות · כ־${parts['per_trade_usd']:.0f} לעסקה"
    )


def risk_profile_parts(cfg: AgentConfig, equity: float | None = None) -> dict[str, Any]:
    profile = RISK_PROFILES.get(cfg.risk_profile, RISK_PROFILES["conservative"])
    capital = float(equity if equity is not None else cfg.initial_capital)
    return {
        "label": str(profile["label"]),
        "max_deploy_pct": int(float(profile["max_deploy_pct"]) * 100),
        "max_deploy_usd": capital * float(profile["max_deploy_pct"]),
        "max_trades": int(cfg.max_trades_per_day),
        "per_trade_usd": capital * float(cfg.max_position_pct),
    }


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


_SELL_CONFIRM_WORDS = frozenset(
    {"כן", "yes", "ok", "אוקי", "אישור", "יאללה", "מאשר", "אשר"}
)


def set_pending_sell_confirm(state: dict[str, Any], symbol: str) -> None:
    state["pending_sell_confirm"] = {
        "symbol": str(symbol).upper(),
        "at": datetime.now(timezone.utc).isoformat(),
    }


def clear_pending_sell_confirm(state: dict[str, Any]) -> None:
    state.pop("pending_sell_confirm", None)


def pending_sell_confirm_symbol(state: dict[str, Any], *, max_age_sec: int = 1800) -> str | None:
    pending = state.get("pending_sell_confirm")
    if not isinstance(pending, dict):
        return None
    symbol = str(pending.get("symbol") or "").upper()
    if not symbol:
        return None
    raw_at = pending.get("at")
    if raw_at:
        try:
            at = datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - at).total_seconds() > max_age_sec:
                clear_pending_sell_confirm(state)
                return None
        except ValueError:
            pass
    return symbol


def try_confirm_pending_sell(state: dict[str, Any], text: str) -> str | None:
    """If user confirmed a pending natural-language sell, return the symbol."""
    symbol = pending_sell_confirm_symbol(state)
    if not symbol:
        return None
    if str(text).strip().lower() not in _SELL_CONFIRM_WORDS:
        return None
    clear_pending_sell_confirm(state)
    return symbol


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
    p = monthly_target_parts(cfg, state)
    pnl_s = f"+${p['month_pnl']:.2f}" if p["month_pnl"] > 0 else (
        f"-${abs(p['month_pnl']):.2f}" if p["month_pnl"] < 0 else "$0.00"
    )
    gap_s = f"${abs(p['gap_usd']):.0f}" if p["gap_usd"] <= 0 else f"${p['gap_usd']:.0f}"
    gap_word = "מעל היעד" if p["gap_usd"] <= 0 else "נותר ליעד"
    return (
        f"יעד ${p['target_usd']:.0f} · נוכחי ${p['equity']:.2f} · "
        f"חודש {pnl_s} ({p['month_pnl_pct']:+.1f}%) · "
        f"{gap_word} {gap_s} · {p['trading_days_left']} ימי מסחר"
    )


def monthly_target_parts(cfg: AgentConfig, state: dict[str, Any]) -> dict[str, Any]:
    equity = float(state.get("equity", cfg.initial_capital))
    target = float(cfg.monthly_target_usd)
    start = float(state.get("month_start_equity", cfg.initial_capital))
    month_pnl = equity - start
    month_pnl_pct = (month_pnl / start * 100) if start > 0 else 0.0
    gap = target - equity
    return {
        "equity": equity,
        "target_usd": target,
        "month_start_equity": start,
        "month_pnl": month_pnl,
        "month_pnl_pct": month_pnl_pct,
        "gap_usd": gap,
        "trading_days_left": count_us_trading_days_remaining(date.today()),
    }


class _SafeConsoleFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            stream = sys.stdout
            enc = getattr(stream, "encoding", None) or "utf-8"
            msg.encode(enc)
        except (UnicodeEncodeError, LookupError):
            record.msg = record.getMessage().encode("ascii", "replace").decode("ascii")
            record.args = ()
        return True


def setup_logger(log_file: Path | None = None) -> None:
    from trading_pulse.core.log_redact import RedactSecretsFilter

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
    redact = RedactSecretsFilter()
    for handler in logging.root.handlers:
        handler.addFilter(redact)
    for handler in handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.addFilter(_SafeConsoleFilter())


def get_next_us_trading_day(from_day: date) -> date:
    nxt = from_day + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def resolve_plan_target_day(run_day: date, *, force: bool = False) -> date:
    """Evening plan → next session. Manual תוכנית עכשיו on a trading day → today if not closed."""
    if force and is_us_trading_day(run_day) and not report_path(run_day).exists():
        return run_day
    return get_next_us_trading_day(run_day)


def is_us_trading_day(day: date) -> bool:
    return day.weekday() < 5


def _plan_time_hint(cfg: AgentConfig | None = None) -> str:
    """Israel wall-clock for evening plan (config stores UTC)."""
    from trading_pulse.core.schedule_tz import ISRAEL, utc_hhmm_to_zone

    cfg = cfg or load_config()
    hhmm = str(getattr(cfg, "planning_time", "20:15"))
    il = utc_hhmm_to_zone(hhmm, ISRAEL)
    return il or hhmm


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


def plan_is_protected(
    plan: dict[str, Any], *, state: dict[str, Any] | None = None, as_of: date | None = None
) -> bool:
    from trading_pulse.agent.plan_engine import plan_is_protected as _engine_protected

    return _engine_protected(plan, state=state, as_of=as_of)


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

    if str(rec.get("strategy") or "") == "method2":
        trig = escape_html(str(rec.get("trigger") or ""))
        entry = float(rec.get("method2_entry_ref") or rec.get("entry_ref_price") or 0)
        stop = float(rec.get("method2_stop_ref") or rec.get("stop_loss_price") or 0)
        parts = [
            f"דירוג #{rank} — נרות סיניים 2 · טריגר {trig}",
            f"כניסה ~${entry:.2f} · סטופ ~${stop:.2f}",
            f"שרוול ${float(rec.get('capital_usd', 0)):.0f}",
            str(rec.get("reason") or ""),
        ]
        return ". ".join(p for p in parts if p)

    if str(rec.get("strategy") or "") == "rising_three_methods":
        weak = " (חלש)" if rec.get("pattern_weak") else ""
        parts = [
            f"דירוג #{rank} — נרות · Rising Three Methods{weak}",
            f"ציון תבנית {float(rec.get('pattern_score', score)):.1f}",
            str(rec.get("reason") or ""),
        ]
        return ". ".join(p for p in parts if p)

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
    """Same plan UX as Telegram (banner + how-to), stripped for the app inbox."""
    from trading_pulse.telegram.app_notify import strip_html

    return strip_html(format_plan_message(plan))


def format_heartbeat_message(cfg: AgentConfig, state: dict[str, Any]) -> str:
    from trading_pulse.telegram.telegram_format import format_heartbeat
    from trading_pulse.core.schedule_tz import us_trading_session_date

    session_day = us_trading_session_date()
    market_day = is_us_trading_day(session_day)

    return format_heartbeat(
        cfg,
        state,
        summary_fn=risk_profile_summary,
        monthly_fn=monthly_target_summary,
        speculative_fn=is_speculative,
        market_day=market_day,
        next_trading_day=(
            get_next_us_trading_day(session_day).isoformat()
            if not market_day
            else None
        ),
    )


def send_heartbeat(cfg: AgentConfig, reason: str) -> None:
    state = load_state(cfg)
    today = date.today().isoformat()
    if state.get("last_heartbeat_date") == today:
        logging.info("Heartbeat skipped (%s): already sent today", reason)
        return
    logging.info("Sending heartbeat (%s)", reason)
    message = format_heartbeat_message(cfg, state)
    sent = False
    try:
        from trading_pulse.core.schedule_tz import us_trading_session_date
        from trading_pulse.telegram.reply_cards import card_heartbeat

        session_day = us_trading_session_date()
        market_day = is_us_trading_day(session_day)
        img = card_heartbeat(
            cfg,
            state,
            market_day=market_day,
            next_trading_day=(
                get_next_us_trading_day(session_day).isoformat()
                if not market_day
                else None
            ),
        )
        import re

        plain = re.sub(r"<[^>]+>", "", message).strip()
        sent = send_telegram_photo(
            cfg,
            img,
            "הסוכן חי",
            context="heartbeat",
            inbox_text=plain[:500],
        )
    except Exception as ex:
        logging.warning("Heartbeat card failed, HTML fallback: %s", ex)
        sent = send_user_notification(cfg, message, context="heartbeat", parse_mode="HTML")
    if sent:
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
        from trading_pulse.core.log_redact import redact_secrets

        safe = redact_secrets(ex)
        if parse_mode:
            logging.warning("Telegram HTML send failed (%s), retrying plain text: %s", context, safe)
            try:
                plain = re.sub(r"<[^>]+>", "", text)
                telegram_api_call(token, "sendMessage", {"chat_id": chat_id, "text": plain})
                logging.info("Telegram sent (%s) as plain text", context)
                if not uses_app_notifications(cfg):
                    log_telegram_message("out", context, plain, parse_mode=None)
                return True
            except Exception as retry_ex:
                logging.warning("Telegram send failed (%s): %s", context, redact_secrets(retry_ex))
                return False
        logging.warning("Telegram send failed (%s): %s", context, safe)
        return False


def send_telegram_photo(
    cfg: AgentConfig,
    image_bytes: bytes,
    caption: str,
    context: str = "photo",
    parse_mode: str | None = "HTML",
    *,
    inbox_text: str | None = None,
    log_inbox: bool = True,
) -> bool:
    """Send photo to Telegram. Caption should be short — details belong in the image.

    When called after notify_user already logged the same context (e.g. card
    replies), pass log_inbox=False so the app inbox is not duplicated — only
    the existing row is tagged with image_id.
    """
    from trading_pulse.telegram.app_notify import (
        notify_user,
        uses_app_notifications,
        uses_telegram_notifications,
    )

    token = str(cfg.telegram_bot_token).strip()
    chat_id = str(cfg.telegram_chat_id).strip()
    # Keep captions tiny — long RTL captions break on mobile Telegram.
    cap = re.sub(r"<[^>]+>", "", caption or "").strip()[:80]
    image_id = _save_telegram_image(image_bytes)

    if uses_app_notifications(cfg):
        if log_inbox:
            plain = inbox_text or cap or context
            notify_user(
                cfg,
                plain,
                context,
                parse_mode=None,
                telegram_sender=False,
            )
        _tag_last_message_image(context, image_id)

    if not token or not chat_id:
        logging.warning("Telegram photo skip (%s): missing token or chat_id", context)
        if uses_app_notifications(cfg):
            _tag_last_message_delivery(
                context,
                "failed" if uses_telegram_notifications(cfg) else "not_requested",
            )
        return bool(image_id) and not uses_telegram_notifications(cfg)

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    def _post(data: dict[str, Any]) -> requests.Response:
        files = {"photo": ("chart.png", image_bytes, "image/png")}
        return requests.post(url, data=data, files=files, timeout=30)

    data: dict[str, Any] = {"chat_id": chat_id}
    if cap:
        data["caption"] = cap
    try:
        res = _post(data)
        res.raise_for_status()
        body = res.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body}")
        logging.info("Telegram photo sent (%s)", context)
        if not uses_app_notifications(cfg):
            log_telegram_message(
                "out",
                context,
                inbox_text or cap or context,
                parse_mode=None,
                metadata={"image": True, "image_id": image_id},
            )
        else:
            _tag_last_message_delivery(context, "delivered")
        return True
    except Exception as ex:
        from trading_pulse.core.log_redact import redact_secrets

        logging.warning("Telegram photo send failed (%s): %s", context, redact_secrets(ex))
        # Text fallback so the user still gets the content (report/heartbeat/etc.)
        fallback = (inbox_text or caption or "").strip()
        if fallback and uses_telegram_notifications(cfg) and token and chat_id:
            try:
                from trading_pulse.telegram.telegram_format import escape_html

                # Prefer plain text if caption was already stripped; otherwise escape.
                plain = re.sub(r"<[^>]+>", "", fallback).strip()
                ok = _send_telegram_api(
                    cfg,
                    escape_html(plain) if plain else fallback,
                    context=f"{context}:text_fallback",
                    parse_mode="HTML",
                )
                if ok:
                    logging.info("Telegram photo fallback text sent (%s)", context)
                    if uses_app_notifications(cfg):
                        _tag_last_message_delivery(context, "delivered")
                    return True
            except Exception as fallback_ex:
                logging.warning(
                    "Telegram photo text fallback failed (%s): %s",
                    context,
                    redact_secrets(fallback_ex),
                )
        if uses_app_notifications(cfg):
            _tag_last_message_delivery(context, "failed")
        return False


def _save_telegram_image(image_bytes: bytes) -> str:
    from uuid import uuid4

    from trading_pulse.core.app_paths import TELEGRAM_DIR

    img_dir = TELEGRAM_DIR / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    image_id = uuid4().hex[:16]
    (img_dir / f"{image_id}.png").write_bytes(image_bytes)
    return image_id


def _tag_last_message_image(context: str, image_id: str) -> None:
    try:
        from trading_pulse.telegram.telegram_store import load_messages, save_messages

        messages = load_messages()
        for msg in messages:
            if msg.get("direction") == "out" and msg.get("context") == context:
                meta = dict(msg.get("metadata") or {})
                meta["image"] = True
                meta["image_id"] = image_id
                msg["metadata"] = meta
                save_messages(messages)
                return
    except Exception as ex:
        logging.debug("Could not tag message image: %s", ex)


def _tag_last_message_delivery(context: str, status: str) -> None:
    try:
        from trading_pulse.telegram.telegram_store import (
            load_messages,
            update_message_metadata,
        )

        for message in load_messages():
            if (
                message.get("direction") == "out"
                and message.get("context") == context
            ):
                metadata = dict(message.get("metadata") or {})
                delivery = dict(metadata.get("delivery") or {})
                delivery["telegram"] = {
                    "status": status,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
                update_message_metadata(
                    str(message["id"]),
                    {"delivery": delivery},
                )
                return
    except Exception as ex:
        logging.debug("Could not tag message delivery: %s", ex)


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
    """One Telegram photo per recommendation: chart + labeled details (short caption)."""
    from trading_pulse.telegram.app_notify import uses_telegram_notifications
    from trading_pulse.telegram.reply_cards import chart_with_recommendation_details
    from trading_pulse.telegram.telegram_format import format_recommendation
    from trading_pulse.telegram.telegram_images import render_recommendation_chart

    if not uses_telegram_notifications(cfg):
        return
    recs = plan.get("recommendations") or []
    if not recs:
        return
    day = str(plan.get("for_trading_day", ""))
    speculative = plan.get("risk_profile") == "speculative"
    held = {str(h.get("symbol")) for h in (plan.get("holdings") or [])}
    for idx, rec in enumerate(recs, start=1):
        try:
            signal_lines = format_rec_signal_block(rec, speculative).splitlines()
            sym = str(rec.get("symbol") or "?")
            img = chart_with_recommendation_details(
                rec,
                idx,
                day,
                signal_lines=signal_lines,
                held=sym in held,
            )
            if not img:
                continue
            # Details live in the PNG — keep caption tiny (Telegram RTL captions scramble).
            caption = f"#{idx} {sym}"
            send_telegram_photo(
                cfg,
                img,
                caption,
                context=f"plan:stock:{sym}",
                parse_mode="HTML",
                inbox_text=f"#{idx} {sym} · יום מסחר {day}",
            )
        except Exception as ex:
            logging.warning("Plan chart for %s failed: %s", rec.get("symbol"), ex)
            try:
                # Last resort: chart alone + fixed HTML caption (LTR islands).
                bare = render_recommendation_chart(rec, idx, day)
                if not bare:
                    continue
                caption = format_recommendation(
                    rec, idx, plan, signal_lines=format_rec_signal_block(rec, speculative).splitlines()
                )
                send_telegram_photo(
                    cfg,
                    bare,
                    caption,
                    context=f"plan:stock:{rec.get('symbol')}",
                    parse_mode="HTML",
                )
            except Exception as ex2:
                logging.warning("Plan chart fallback for %s failed: %s", rec.get("symbol"), ex2)


def send_stock_detail(cfg: AgentConfig, symbol: str) -> None:
    """Analyze any symbol (on or off watchlist): metrics card + price chart."""
    from trading_pulse.agent.stock_detail import analyze_symbol
    from trading_pulse.telegram.reply_cards import card_stock_detail
    from trading_pulse.telegram.telegram_images import render_recommendation_chart

    try:
        fresh = load_config()
        detail = analyze_symbol(fresh, symbol)
    except ValueError as ex:
        send_telegram_message(cfg, f"⚠️ <b>{ex}</b>", context="reply:stock_detail", parse_mode="HTML")
        return
    except Exception as ex:
        logging.warning("Stock detail failed for %s: %s", symbol, ex)
        send_telegram_message(
            cfg,
            f"❌ <b>ניתוח נכשל</b> — {escape_html(str(ex)[:120])}",
            context="reply:stock_detail",
            parse_mode="HTML",
        )
        return

    sym = str(detail.get("symbol", symbol)).upper()
    if not detail.get("ok"):
        send_telegram_message(
            cfg,
            f"❌ <b>{escape_html(sym)}</b> — {escape_html(str(detail.get('error', 'אין נתונים')))}",
            context="reply:stock_detail",
            parse_mode="HTML",
        )
        return

    try:
        card = card_stock_detail(detail)
        send_telegram_photo(
            cfg,
            card,
            f"ניתוח {sym}",
            context=f"reply:stock:{sym}",
            inbox_text=f"ניתוח {sym}",
        )
    except Exception as ex:
        logging.warning("Stock detail card failed for %s: %s", sym, ex)
        send_telegram_message(
            cfg,
            f"📊 <b>{escape_html(sym)}</b> · ציון {float((detail.get('rec') or {}).get('score', 0)):.1f}",
            context=f"reply:stock:{sym}",
            parse_mode="HTML",
        )

    rec = detail.get("rec") or {}
    day = str(detail.get("trading_day") or date.today().isoformat())
    try:
        chart = render_recommendation_chart(rec, 1, day)
        if chart:
            send_telegram_photo(
                cfg,
                chart,
                f"{sym} · גרף",
                context=f"reply:stock_chart:{sym}",
                inbox_text=f"גרף {sym}",
            )
    except Exception as ex:
        logging.warning("Stock detail chart failed for %s: %s", sym, ex)


def _plan_inbox_summary(plan: dict[str, Any]) -> str:
    """Short plain summary for app inbox / photo caption companion."""
    day = str(plan.get("for_trading_day", ""))
    held = {str(h.get("symbol")) for h in (plan.get("holdings") or [])}
    n_new = len(
        [
            r
            for r in (plan.get("recommendations") or [])
            if str(r.get("symbol")) not in held
        ]
    )
    if n_new:
        return f"תוכנית {day} · {n_new} קניות חדשות · שלח הכל לאישור"
    return f"תוכנית {day} · אין קניות חדשות ממזומן"


def send_plan_notifications(cfg: AgentConfig, plan: dict[str, Any]) -> None:
    """Plan as labeled HTML→PNG card, then portfolio snapshot + per-stock charts."""
    from trading_pulse.telegram.app_notify import notify_user, uses_app_notifications, uses_telegram_notifications

    summary = _plan_inbox_summary(plan)
    if uses_app_notifications(cfg):
        notify_user(
            cfg,
            summary,
            context="plan",
            plan=plan,
            telegram_sender=False,
        )
    if uses_telegram_notifications(cfg):
        try:
            from trading_pulse.telegram.reply_cards import card_from_plan_summary

            day = str(plan.get("for_trading_day", ""))
            send_telegram_photo(
                cfg,
                card_from_plan_summary(plan),
                f"תוכנית {day}",
                context="plan",
                parse_mode="HTML",
                inbox_text=summary,
                log_inbox=False,
            )
        except Exception as ex:
            logging.warning("Plan summary card failed, HTML fallback: %s", ex)
            fallback_ok = _send_telegram_api(
                cfg,
                format_plan_message(plan),
                context="plan",
                parse_mode="HTML",
            )
            if uses_app_notifications(cfg):
                _tag_last_message_delivery(
                    "plan",
                    "delivered" if fallback_ok else "failed",
                )
    send_plan_portfolio_image(cfg)
    # Summary details are in card_from_plan_summary (HTML tables) — skip English table.
    send_plan_stock_charts(cfg, plan)


def send_plan_portfolio_image(cfg: AgentConfig) -> None:
    """Numbered holdings snapshot before evening recommendations."""
    try:
        from trading_pulse.agent.portfolio import build_portfolio
        from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio
        from trading_pulse.telegram.reply_cards import card_portfolio

        pdata = attach_slots_to_portfolio(build_portfolio())
        holding = [p for p in pdata.get("open_positions", []) if p.get("status") == "holding"]
        if not holding:
            return
        img = card_portfolio(pdata)
        # No caption — details are in the image (mobile Telegram scrambles long captions).
        send_telegram_photo(cfg, img, "", context="plan:portfolio", inbox_text="תיק")
    except Exception as ex:
        logging.warning("Plan portfolio image failed: %s", ex)


def send_report_table_image(cfg: AgentConfig, report: dict[str, Any]) -> None:
    try:
        from trading_pulse.telegram.telegram_images import render_report_image

        img = render_report_image(report)
        day = report.get("trading_day", "")
        pnl = float(report.get("pnl_usd", 0))
        sign = "+" if pnl >= 0 else ""
        send_telegram_photo(
            cfg,
            img,
            f"דוח {day} · {sign}${pnl:.2f}",
            context="report:table",
            inbox_text=f"טבלת דוח {day}",
        )
    except Exception as ex:
        logging.warning("Report table image failed: %s", ex)


def send_report_notifications(cfg: AgentConfig, report: dict[str, Any]) -> None:
    """Daily report as Hebrew HTML table image (one photo). Avoids RTL HTML walls."""
    import re

    day = str(report.get("trading_day") or "")
    text = format_report_message(report)
    plain = re.sub(r"<[^>]+>", "", text).strip()
    try:
        from trading_pulse.telegram.reply_cards import card_daily_report

        send_telegram_photo(
            cfg,
            card_daily_report(report),
            f"דוח יומי {day}",
            context="report",
            inbox_text=plain[:500] or f"דוח יומי {day}",
        )
    except Exception as ex:
        logging.warning("Report card failed, HTML fallback: %s", ex)
        send_user_notification(cfg, text, context="report", parse_mode="HTML")


def send_weekly_watchlist_notification(
    cfg: AgentConfig,
    result: dict[str, Any],
    *,
    context: str = "weekly_watchlist",
) -> bool:
    """Weekly scan summary as labeled HTML table PNG (short caption)."""
    import re

    from trading_pulse.telegram.telegram_format import format_weekly_watchlist

    week = str(result.get("week") or "")
    text = format_weekly_watchlist(result)
    plain = re.sub(r"<[^>]+>", "", text).strip()
    try:
        from trading_pulse.telegram.reply_cards import card_weekly_watchlist

        return send_telegram_photo(
            cfg,
            card_weekly_watchlist(result),
            f"רשימת מסחר {week}" if week else "רשימת מסחר שבועית",
            context=context,
            inbox_text=plain[:500] or f"רשימת מסחר {week}",
        )
    except Exception as ex:
        logging.warning("Weekly watchlist card failed, HTML fallback: %s", ex)
        return send_user_notification(cfg, text, context=context, parse_mode="HTML")


def send_entry_notifications(
    cfg: AgentConfig,
    entries: list[dict[str, Any]],
    *,
    trading_day: str,
    subtitle: str | None = None,
    pending_method2: list[str] | None = None,
    context: str = "entry",
) -> None:
    """Morning / method2 fills as per-stock squares; short caption only."""
    import re

    from trading_pulse.telegram.telegram_format import format_entry_notification, escape_html

    parts: list[str] = []
    if entries:
        parts.append(
            format_entry_notification(entries, trading_day=trading_day, subtitle=subtitle)
        )
    if pending_method2:
        syms = ", ".join(escape_html(s) for s in pending_method2)
        parts.append(
            f"<b>⏳ נרות סיניים 2 ממתין לפריצה</b>\n"
            f"{syms}\n"
            "כניסה אוטומטית אם תיפרץ הרמה (או טריגר 5ד/1ד) במהלך היום"
        )
    text = "\n\n".join(p for p in parts if p)
    if not text:
        return
    plain = re.sub(r"<[^>]+>", "", text).strip()
    if entries:
        try:
            from trading_pulse.telegram.reply_cards import card_entry

            send_telegram_photo(
                cfg,
                card_entry(entries, trading_day=trading_day, subtitle=subtitle),
                subtitle or f"קנית {trading_day}",
                context=context,
                inbox_text=plain[:500],
            )
            if pending_method2:
                # Extra short HTML note for pending breakouts
                send_user_notification(
                    cfg,
                    (
                        f"<b>⏳ נרות סיניים 2 ממתין לפריצה</b>\n"
                        f"{', '.join(escape_html(s) for s in pending_method2)}\n"
                        "כניסה אוטומטית אם תיפרץ הרמה"
                    ),
                    context=f"{context}:method2_pending",
                    parse_mode="HTML",
                )
            return
        except Exception as ex:
            logging.warning("Entry card failed, HTML fallback: %s", ex)
    send_user_notification(cfg, text, context=context, parse_mode="HTML")


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
        telegram_sender=_send_telegram_as_card,
    )


def _send_telegram_as_card(
    cfg: AgentConfig,
    text: str,
    context: str = "message",
    parse_mode: str | None = None,
) -> bool:
    """Render HTML/text reply as a narrow card image for Telegram."""
    if not text or not str(text).strip():
        return False
    try:
        from trading_pulse.telegram.reply_cards import render_html_message_card

        accent = "cyan"
        ctx = context.lower()
        if any(k in ctx for k in ("error", "cancel", "reject")):
            accent = "red"
        elif "sell" in ctx:
            accent = "green"
        elif "buy" in ctx or "entry" in ctx or "approve" in ctx:
            accent = "green"
        elif "swap" in ctx or "funding" in ctx:
            accent = "pink"
        png = render_html_message_card(text, accent=accent)
        caption = _telegram_card_caption(text, context)
        # Inbox already logged by notify_user — only attach image_id.
        return send_telegram_photo(
            cfg,
            png,
            caption,
            context=context,
            parse_mode="HTML",
            inbox_text=re.sub(r"<[^>]+>", "", text),
            log_inbox=False,
        )
    except Exception as ex:
        logging.warning("Card render failed (%s), sending HTML text: %s", context, ex)
        return _send_telegram_api(cfg, text, context=context, parse_mode=parse_mode)


def send_telegram_message(
    cfg: AgentConfig,
    text: str,
    context: str = "message",
    parse_mode: str | None = None,
) -> bool:
    """User-facing reply — card image on Telegram + image in app inbox when configured."""
    from trading_pulse.telegram.app_notify import (
        notify_user,
        uses_app_notifications,
        uses_telegram_notifications,
    )

    if uses_telegram_notifications(cfg):
        return notify_user(
            cfg,
            text,
            context,
            parse_mode=parse_mode,
            telegram_sender=_send_telegram_as_card,
        )

    # App-only: still render a card so #/messages can show the image.
    ok = notify_user(cfg, text, context, parse_mode=parse_mode, telegram_sender=False)
    if uses_app_notifications(cfg):
        _attach_reply_card_image(text, context)
    return ok


def _attach_reply_card_image(text: str, context: str) -> None:
    """Save a reply card PNG and tag the latest inbox row (app-only path)."""
    try:
        from trading_pulse.telegram.reply_cards import render_html_message_card

        accent = "cyan"
        ctx = context.lower()
        if any(k in ctx for k in ("error", "cancel", "reject")):
            accent = "red"
        elif "sell" in ctx:
            accent = "green"
        elif "buy" in ctx or "entry" in ctx or "approve" in ctx:
            accent = "green"
        elif "swap" in ctx or "funding" in ctx:
            accent = "pink"
        png = render_html_message_card(text, accent=accent)
        image_id = _save_telegram_image(png)
        _tag_last_message_image(context, image_id)
    except Exception as ex:
        logging.debug("App card image skipped (%s): %s", context, ex)


def _telegram_card_caption(text: str, context: str) -> str:
    from trading_pulse.telegram.reply_cards import _strip_html

    plain = _strip_html(text)
    first = next((ln.strip() for ln in plain.splitlines() if ln.strip()), context)
    return first[:80]


def send_telegram_card(
    cfg: AgentConfig,
    png: bytes,
    caption: str,
    context: str,
) -> bool:
    return send_telegram_photo(cfg, png, caption[:100], context=context, parse_mode="HTML")



def parse_indices(
    raw: str,
    total: int,
    *,
    recs: list[dict[str, Any]] | None = None,
    include_below_bar: bool = False,
) -> list[int]:
    """Parse approve/reject indices. «הכל» skips below_bar (weak fallback) picks."""
    if raw.upper() == "ALL":
        if recs is not None and not include_below_bar:
            return [i for i, r in enumerate(recs) if not r.get("below_bar")]
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


def _build_swap_target_rec(cfg: AgentConfig, symbol: str, capital_usd: float) -> dict[str, Any]:
    """Recommendation stub for an intraday swap target not in the evening plan."""
    symbol = symbol.upper()
    sl = float(getattr(cfg, "stop_loss_pct", 0.12))
    tp = float(getattr(cfg, "take_profit_pct", 0.25))
    score = 0.0
    ref = 0.0

    universe = fetch_signal_universe([symbol], cfg)
    if not universe.empty:
        row = universe.iloc[0]
        ref = float(row.get("close") or 0)
        score = float(row.get("score") or 0)
        if row.get("stop_loss_pct") is not None:
            sl = float(row["stop_loss_pct"])
        if row.get("take_profit_pct") is not None:
            tp = float(row["take_profit_pct"])

    if ref <= 0:
        from trading_pulse.agent.intraday_monitor import fetch_intraday_quote

        quote = fetch_intraday_quote(symbol)
        if quote:
            ref = float(quote["last"])

    if ref <= 0:
        ref = 1.0

    floor = round(ref * (1 - sl), 4)
    return {
        "symbol": symbol,
        "side": "LONG",
        "capital_usd": round(capital_usd, 2),
        "entry_ref_price": round(ref, 4),
        "stop_loss_pct": sl,
        "take_profit_pct": tp,
        "stop_loss_price": floor,
        "floor_price": floor,
        "take_profit_price": round(ref * (1 + tp), 4),
        "approved": True,
        "score": score,
        "intraday_swap": True,
    }


def _open_position_now(
    cfg: AgentConfig,
    state: dict[str, Any],
    rec: dict[str, Any],
    trading_day: date,
) -> dict[str, Any] | None:
    """Open a position at the current intraday price (after morning entry)."""
    from trading_pulse.agent.intraday_monitor import fetch_intraday_quote
    from trading_pulse.agent.positions import fetch_day_ohlc, held_symbols, new_position_from_rec

    symbol = str(rec["symbol"]).upper()
    if symbol in held_symbols(state):
        return None
    if len(state.get("open_positions", [])) >= int(getattr(cfg, "max_open_positions", 4)):
        return None

    bar = fetch_day_ohlc(symbol, trading_day)
    price = float(bar["close"]) if bar else 0.0
    if price <= 0:
        quote = fetch_intraday_quote(symbol)
        if not quote:
            return None
        price = float(quote["last"])
    if price <= 0:
        return None

    pos = new_position_from_rec(rec, price, trading_day.isoformat())
    state.setdefault("open_positions", []).append(pos)
    commission = float(getattr(cfg, "commission_per_side_usd", 0.0))
    if commission > 0:
        state["equity"] = round(float(state["equity"]) - commission, 2)
    return pos


def resolve_sell_target(ref: str) -> str | None:
    """Slot number or held ticker → symbol for sell commands."""
    from trading_pulse.agent.portfolio_index import list_numbered_holdings, slot_to_symbol

    ref = ref.strip()
    if ref.isdigit():
        return slot_to_symbol(int(ref))
    sym = ref.upper()
    held = {str(h["symbol"]) for h in list_numbered_holdings()}
    return sym if sym in held else None


def resolve_buy_target(ref: str) -> str:
    """Slot number or ticker → symbol for buy leg of a swap."""
    from trading_pulse.agent.portfolio_index import slot_to_symbol

    ref = ref.strip()
    if ref.isdigit():
        sym = slot_to_symbol(int(ref))
        if sym:
            return sym
    return ref.upper()


def _sync_plan_after_manual_action(
    cfg: AgentConfig,
    state: dict[str, Any],
    action: str,
) -> None:
    try:
        from trading_pulse.agent.plan_engine import (
            sync_active_plan_after_manual_action,
        )

        sync_active_plan_after_manual_action(cfg, state, action=action)
    except OSError as ex:
        logging.warning("Could not refresh active plan after manual action: %s", ex)


def _buy_symbol_usd(
    cfg: AgentConfig,
    state: dict[str, Any],
    to_symbol: str,
    amount_usd: float,
    trading_day: date,
    *,
    rec: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from trading_pulse.agent.intraday_monitor import fetch_intraday_quote
    from trading_pulse.agent.positions import (
        add_lot_to_position,
        fetch_day_ohlc,
        free_cash,
        held_symbols,
    )

    amount_usd = round(min(float(amount_usd), free_cash(state, cfg)), 2)
    if amount_usd < 1:
        return None
    to_symbol = to_symbol.upper()

    def _fill_price() -> float:
        bar = fetch_day_ohlc(to_symbol, trading_day)
        price = float(bar["close"]) if bar else 0.0
        if price <= 0:
            quote = fetch_intraday_quote(to_symbol)
            if quote:
                price = float(quote["last"])
        if price <= 0 and rec:
            price = float(rec.get("entry_ref_price") or rec.get("entry_price") or 0)
        return price

    if to_symbol in held_symbols(state):
        fill = _fill_price()
        if fill <= 0:
            return None
        for pos in state.get("open_positions", []):
            if str(pos.get("symbol")) == to_symbol:
                add_lot_to_position(
                    pos,
                    amount_usd,
                    fill,
                    trading_day.isoformat(),
                )
                return pos
        return None
    stub = dict(rec) if rec else _build_swap_target_rec(cfg, to_symbol, amount_usd)
    stub["capital_usd"] = amount_usd
    stub["symbol"] = to_symbol
    return _open_position_now(cfg, state, stub, trading_day)


def execute_buy_command(
    cfg: AgentConfig,
    symbol: str,
    buy_usd: float | None = None,
) -> str:
    """Buy (or add to) a symbol using free cash.

    If buy_usd is None, spend all available free cash.
    """
    from trading_pulse.agent.positions import free_cash, held_symbols
    from trading_pulse.telegram.reply_cards import card_buy, card_error
    from trading_pulse.telegram.telegram_format import format_buy_reply

    symbol = symbol.upper()
    state = load_state(cfg)
    cash = free_cash(state, cfg)
    if buy_usd is None:
        if cash < 1:
            buy_usd = 0.0
        else:
            buy_usd = float(cash)
    else:
        buy_usd = float(buy_usd)

    if cash < 1:
        html = (
            "❌ <b>אין מזומן פנוי</b>\n"
            "קודם מכור חלק: <code>מכור 2 20$</code>\n"
            "או החלף: <code>מכור 2 תקנה 1 $20</code>"
        )
        try:
            send_telegram_card(
                cfg,
                card_error(
                    "אין מזומן פנוי",
                    "קודם מכור חלק מהתיק, ואז קנה",
                    chips=["מכור 2 20$", "מכור 2 תקנה 1 $20"],
                ),
                "❌ אין מזומן",
                "reply:buy",
            )
            return ""
        except Exception:
            return html
    if buy_usd < 1:
        return "❌ <b>סכום קטן מדי</b> — מינימום $1"
    if buy_usd > cash:
        return (
            f"❌ <b>אין מספיק מזומן</b> — פנוי <b>${cash:.0f}</b>, ביקשת ${buy_usd:.0f}\n"
            f"נסה: <code>תקנה {symbol}</code> (כל המזומן) או "
            f"<code>תקנה {symbol} ${cash:.0f}</code>"
        )

    trading_day = date.fromisoformat(resolve_trading_day(None))
    already_held = symbol in held_symbols(state)
    pos = _buy_symbol_usd(cfg, state, symbol, buy_usd, trading_day)
    if pos is None:
        return f"❌ <b>לא הצלחתי לקנות {symbol}</b> — נסה שוב או בדוק מחיר"
    save_json(STATE_FILE, state)
    _sync_plan_after_manual_action(
        cfg,
        state,
        f"קנייה ידנית של {symbol}",
    )
    cash_after = free_cash(state, cfg)
    html = format_buy_reply(
        symbol,
        bought_usd=buy_usd,
        entry_price=float(pos.get("entry_price") or pos.get("mark_price") or 0),
        cash=cash_after,
        added_to_existing=already_held,
    )
    try:
        send_telegram_card(
            cfg,
            card_buy(
                symbol,
                bought_usd=buy_usd,
                entry_price=float(pos.get("entry_price") or pos.get("mark_price") or 0),
                cash=cash_after,
                added_to_existing=already_held,
            ),
            f"✅ {symbol}",
            "reply:buy",
        )
        from trading_pulse.telegram.app_notify import notify_user, uses_app_notifications

        if uses_app_notifications(cfg):
            notify_user(cfg, html, "reply:buy", parse_mode="HTML", telegram_sender=False)
        return ""
    except Exception:
        return html


def execute_sell_command(
    cfg: AgentConfig,
    symbol: str,
    fraction: float = 1.0,
    *,
    sell_usd: float | None = None,
) -> str:
    from trading_pulse.agent.positions import free_cash, holdings_snapshot, partial_sell_position, partial_sell_usd
    from trading_pulse.telegram.reply_cards import card_sell
    from trading_pulse.telegram.telegram_format import format_sell_reply

    state = load_state(cfg)
    if sell_usd is not None:
        cap_before = 0.0
        for pos in state.get("open_positions", []):
            if str(pos.get("symbol")) == symbol.upper():
                cap_before = float(pos.get("capital_usd", 0))
                break
        trade = partial_sell_usd(cfg, state, symbol, sell_usd)
        if trade is None:
            return f"❌ <b>אין פוזיציה ב-{symbol}</b>"
        sold_usd = float(trade.get("capital_usd", 0))
        fraction = min(1.0, sold_usd / cap_before) if cap_before else 1.0
    else:
        trade = partial_sell_position(cfg, state, symbol, fraction)
        if trade is None:
            return f"❌ <b>אין פוזיציה ב-{symbol}</b>"
        sold_usd = float(trade.get("capital_usd", 0))
    save_json(STATE_FILE, state)
    # Drop Method2 / hourly watch when the position is gone (or fully sold).
    if fraction >= 0.999 or not any(
        str(p.get("symbol", "")).upper() == symbol.upper()
        for p in state.get("open_positions", [])
    ):
        try:
            from trading_pulse.agent.price_watch import remove_price_watch

            remove_price_watch(state, symbol)
            save_json(STATE_FILE, state)
        except Exception:
            pass
    _sync_plan_after_manual_action(
        cfg,
        state,
        f"מכירה ידנית של {symbol.upper()}",
    )
    cash = free_cash(state)
    html = format_sell_reply(
        symbol,
        fraction=fraction,
        pnl_usd=float(trade["pnl_usd"]),
        cash=cash,
        equity=float(state.get("equity", 0)),
        target_usd=sold_usd,
        holdings=holdings_snapshot(state),
    )
    try:
        send_telegram_card(
            cfg,
            card_sell(
                symbol,
                fraction=fraction,
                pnl_usd=float(trade["pnl_usd"]),
                cash=cash,
                equity=float(state.get("equity", 0)),
                sold_usd=sold_usd,
            ),
            f"✅ מכרת {symbol}",
            "reply:sell",
        )
        from trading_pulse.telegram.app_notify import notify_user, uses_app_notifications

        # Card already went to Telegram; put the detailed HTML only in the app inbox.
        if uses_app_notifications(cfg):
            notify_user(cfg, html, "reply:sell", parse_mode="HTML", telegram_sender=False)
        return ""
    except Exception:
        return html


def execute_buys_for_plan(
    cfg: AgentConfig,
    trading_day: str,
    *,
    notify: bool = True,
) -> list[dict[str, Any]]:
    """Run entry simulation only after scheduled market open (legacy helper)."""
    from trading_pulse.agent.trading_flow import before_market_entry

    td = date.fromisoformat(trading_day)
    if before_market_entry(cfg, td):
        return []
    path = plan_path(td)
    if not path.exists():
        return []
    plan = read_json(path)
    if plan.get("allocation", {}).get("status") != "applied":
        return []
    state = load_state(cfg)
    entries = run_entry_simulation(cfg, state, td)
    if notify and entries:
        send_entry_notifications(cfg, entries, trading_day=trading_day, context="entry:immediate")
    return entries


def execute_swap_command(
    cfg: AgentConfig,
    from_symbol: str,
    to_symbol: str,
    *,
    sell_fraction: float = 1.0,
    sell_usd: float | None = None,
    buy_usd: float | None = None,
) -> str:
    from trading_pulse.agent.positions import free_cash, holdings_snapshot, partial_sell_position, partial_sell_usd
    from trading_pulse.agent.trading_flow import before_market_entry
    from trading_pulse.telegram.telegram_format import format_swap_completed

    from_symbol = from_symbol.upper()
    to_symbol = to_symbol.upper()
    if from_symbol == to_symbol:
        return "❌ <b>אותה מניה</b> — ציין שני סימבולים שונים"

    state = load_state(cfg)
    # If user named a buy amount but not a sell amount, sell only that much
    # (e.g. "מכור 1 תקנה 2 $100" → sell $100 of #1, not the whole position).
    if sell_usd is None and buy_usd is not None and sell_fraction >= 1.0:
        sell_usd = float(buy_usd)

    if sell_usd is not None:
        trade = partial_sell_usd(cfg, state, from_symbol, sell_usd)
    else:
        trade = partial_sell_position(cfg, state, from_symbol, sell_fraction)
    if trade is None:
        return f"❌ <b>אין פוזיציה ב-{from_symbol}</b>"
    sold_usd = float(trade.get("capital_usd", 0))
    save_json(STATE_FILE, state)
    if sell_fraction >= 0.999 or not any(
        str(p.get("symbol", "")).upper() == from_symbol
        for p in state.get("open_positions", [])
    ):
        try:
            from trading_pulse.agent.price_watch import remove_price_watch

            remove_price_watch(state, from_symbol)
            save_json(STATE_FILE, state)
        except Exception:
            pass
    _sync_plan_after_manual_action(
        cfg,
        state,
        f"מכירה ידנית של {from_symbol} כחלק מהחלפה",
    )

    trading_day = resolve_trading_day(None)
    td = date.fromisoformat(trading_day)
    path = plan_path(td)
    cash = free_cash(state, cfg)
    purchase_usd = round(min(buy_usd if buy_usd is not None else cash, cash), 2)

    if purchase_usd < 1:
        return (
            f"✅ <b>מכרת {from_symbol}</b> — ${sold_usd:.0f}\n"
            f"❌ אין מספיק מזומן לקנות {to_symbol} (${cash:.0f})"
        )

    if not path.exists():
        if not before_market_entry(cfg, td):
            pos = _buy_symbol_usd(cfg, state, to_symbol, purchase_usd, td)
            if pos is None:
                return (
                    f"✅ <b>מכרת {from_symbol}</b> — ${sold_usd:.0f}\n"
                    f"❌ לא הצלחתי לקנות {to_symbol}"
                )
            save_json(STATE_FILE, state)
            _sync_plan_after_manual_action(
                cfg,
                state,
                f"החלפה ידנית של {from_symbol} ב־{to_symbol}",
            )
            return format_swap_completed(
                from_symbol=from_symbol,
                to_symbol=to_symbol,
                sold_usd=sold_usd,
                entry_price=float(pos.get("entry_price", 0)),
                bought_usd=purchase_usd,
                cash=free_cash(state, cfg),
                holdings=holdings_snapshot(state),
            )
        return (
            f"✅ <b>מכרת {from_symbol}</b> — ${sold_usd:.0f}\n"
            f"❌ אין תוכנית ל-{trading_day} — לא ניתן לקנות {to_symbol}"
        )

    plan = read_json(path)
    recs = plan.setdefault("recommendations", [])

    for rec in recs:
        if str(rec.get("symbol")) == from_symbol:
            rec["approved"] = False

    target_rec = next((r for r in recs if str(r.get("symbol")) == to_symbol), None)
    if target_rec is None:
        target_rec = _build_swap_target_rec(cfg, to_symbol, purchase_usd)
        recs.append(target_rec)
    target_rec["capital_usd"] = purchase_usd
    target_rec["approved"] = True

    if not before_market_entry(cfg, td):
        pos = _buy_symbol_usd(cfg, state, to_symbol, purchase_usd, td, rec=target_rec)
        if pos is None:
            save_json(STATE_FILE, state)
            save_json(path, plan)
            return (
                f"✅ <b>מכרת {from_symbol}</b> — ${sold_usd:.0f}\n"
                f"❌ לא הצלחתי לקנות {to_symbol} — נסה שוב"
            )
        save_json(STATE_FILE, state)
        save_json(path, plan)
        _sync_plan_after_manual_action(
            cfg,
            state,
            f"החלפה ידנית של {from_symbol} ב־{to_symbol}",
        )
        return format_swap_completed(
            from_symbol=from_symbol,
            to_symbol=to_symbol,
            sold_usd=sold_usd,
            entry_price=float(pos.get("entry_price", 0)),
            bought_usd=purchase_usd,
            cash=free_cash(state, cfg),
            holdings=holdings_snapshot(state),
        )

    indices = [i for i, r in enumerate(recs) if str(r.get("symbol")) == to_symbol]
    plan["last_manual_action"] = (
        f"החלפה ידנית של {from_symbol} ב־{to_symbol}"
    )
    plan["portfolio_snapshot_stale"] = False
    save_json(path, plan)
    approve_reply = set_plan_status(trading_day, "APPROVE", indices, cfg=cfg)
    return (
        f"✅ <b>מכרת {from_symbol}</b> — ${sold_usd:.0f} · קניית <b>{to_symbol}</b> ${purchase_usd:.0f}\n\n"
        f"{approve_reply}"
    )


def set_plan_status(
    trading_day: str,
    action: str,
    indices: list[int],
    *,
    cfg: AgentConfig | None = None,
    notify_allocation: bool = True,
) -> str:
    cfg_obj = cfg or load_config()
    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        return f"❌ <b>אין תוכנית ל-{trading_day}</b>\nחכה לתוכנית ב-{_plan_time_hint(cfg_obj)}."
    plan = read_json(path)
    recs = plan.get("recommendations", [])
    if not recs:
        return f"📭 <b>אין המלצות</b> בתוכנית של {trading_day}."

    approved_value = action.upper() == "APPROVE"
    symbols: list[str] = []
    for idx in indices:
        recs[idx]["approved"] = approved_value
        symbols.append(str(recs[idx]["symbol"]))

    state = load_state(cfg_obj)
    allocation_sent = False
    auto_allocated = False
    funding_sent = False
    all_approved = [str(r["symbol"]) for r in recs if r.get("approved")]

    if not any(x.get("approved") for x in recs):
        plan["status"] = "draft"
        plan.pop("allocation", None)
        plan.pop("confirmed_at", None)
    elif approved_value and len(all_approved) == len(recs):
        from trading_pulse.agent.plan_engine import apply_confirm
        from trading_pulse.agent.trading_flow import funding_gap

        gap = funding_gap(plan, state, cfg_obj)
        if gap and notify_allocation:
            plan["status"] = "draft"
            plan["allocation"] = {"status": "pending"}
            save_json(path, plan)
            send_funding_prompt(trading_day, plan, gap, cfg=cfg_obj)
            funding_sent = True
        else:
            plan = apply_confirm(plan, state, cfg_obj)
            auto_allocated = True
    else:
        plan["status"] = "draft"
        plan["approved_at"] = datetime.now(timezone.utc).isoformat()
        if approved_value:
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
    if (
        approved_value
        and notify_allocation
        and all_approved
        and len(all_approved) == len(recs)
        and not funding_sent
        and not auto_allocated
    ):
        from trading_pulse.agent.trading_flow import should_auto_allocate

        if should_auto_allocate(cfg_obj, plan, state):
            send_allocation_prompt(trading_day, cfg=cfg)
            allocation_sent = True
    elif (
        approved_value
        and notify_allocation
        and all_approved
        and len(all_approved) < len(recs)
    ):
        send_allocation_prompt(trading_day, cfg=cfg)
        allocation_sent = True

    from trading_pulse.telegram.telegram_format import format_approval_reply
    from trading_pulse.agent.plan_engine import _prune_holding_actions
    from trading_pulse.agent.positions import holdings_snapshot

    # Keep approval reminders in sync with live book (e.g. PATH closed at EOD).
    plan["holdings"] = holdings_snapshot(state)
    plan["holding_actions"] = _prune_holding_actions(plan.get("holding_actions") or [], state)
    save_json(path, plan)

    return format_approval_reply(
        trading_day=trading_day,
        picked_symbols=symbols,
        all_approved_symbols=all_approved,
        rejected=not approved_value,
        allocation_sent=allocation_sent,
        auto_allocated=auto_allocated,
        funding_sent=funding_sent,
        cfg=cfg_obj,
        trading_day_date=date.fromisoformat(trading_day),
        plan=plan,
    )


def send_funding_prompt(
    trading_day: str,
    plan: dict[str, Any],
    gap: dict[str, Any],
    *,
    cfg: AgentConfig | None = None,
) -> bool:
    from trading_pulse.telegram.app_notify import notify_user
    from trading_pulse.telegram.telegram_format import format_funding_prompt

    if cfg is None:
        cfg = load_config()
    text = format_funding_prompt(plan, gap, trading_day=trading_day)
    return notify_user(
        cfg,
        text,
        "funding:prompt",
        parse_mode="HTML",
        telegram_sender=send_telegram_message,
    )


def send_allocation_prompt(trading_day: str, *, cfg: AgentConfig | None = None) -> bool:
    from trading_pulse.telegram.app_notify import notify_user, uses_app_notifications
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
    try:
        from trading_pulse.telegram.reply_cards import card_allocation_prompt

        import re

        plain = re.sub(r"<[^>]+>", "", text).strip()
        img = card_allocation_prompt(plan, options, trading_day=trading_day, state=state)
        if uses_app_notifications(cfg):
            notify_user(cfg, plain[:500], "allocation:prompt", parse_mode=None, telegram_sender=False)
        return send_telegram_photo(
            cfg,
            img,
            f"חלוקת הון {trading_day}",
            context="allocation:prompt",
            inbox_text=plain[:500],
            log_inbox=not uses_app_notifications(cfg),
        )
    except Exception as ex:
        logging.warning("Allocation card failed, HTML fallback: %s", ex)
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
    from trading_pulse.agent.trading_flow import scheduled_entry_moment

    return (
        format_allocation_applied(chosen, trading_day)
        + f"\n\n⏰ כניסה לשוק: <b>{scheduled_entry_moment(cfg, date.fromisoformat(trading_day))}</b>"
    )


def ensure_plan_allocation(
    cfg: AgentConfig,
    plan: dict[str, Any],
    state: dict[str, Any],
    trading_day: date,
    *,
    purpose: str = "entry",
) -> None:
    """Entry runs only on user-confirmed plans. purpose=eod → quiet log (not a failed entry)."""
    from trading_pulse.agent.plan_engine import STATUS_CONFIRMED, normalize_status

    if normalize_status(plan) != STATUS_CONFIRMED:
        if purpose == "eod":
            logging.info(
                "EOD for %s: plan not confirmed (normal if no morning buys / hold-only day)",
                trading_day.isoformat(),
            )
        else:
            logging.warning(
                "Entry skipped for %s: plan not confirmed (send הכל or confirm in app)",
                trading_day.isoformat(),
            )
        return
    alloc = plan.get("allocation") or {}
    if alloc.get("status") != "applied":
        if purpose == "eod":
            logging.info(
                "EOD for %s: allocation not applied (entries may already have run)",
                trading_day.isoformat(),
            )
        else:
            logging.warning("Entry skipped for %s: allocation not applied", trading_day.isoformat())


def plan_status_text(trading_day: str) -> str:
    from trading_pulse.telegram.telegram_format import SEP, user_guide_done, user_guide_step1, user_guide_step2

    path = plan_path(date.fromisoformat(trading_day))
    if not path.exists():
        return f"❌ <b>אין תוכנית ל-{trading_day}</b>."
    plan = read_json(path)
    recs = plan.get("recommendations", [])
    intent = plan.get("flow_intent", "")
    lines = [
        f"<b>📋 סטטוס תוכנית</b>",
        f"<b>יום מסחר:</b> {trading_day}",
    ]
    if intent == "first_investment":
        lines.append("<b>🌟 יום ראשון</b> — שלח <code>הכל</code> לחלוקה על כמה מניות")
    elif intent == "add_needs_sell":
        lines.append("<b>💰 אין מספיק מזומן</b> — <code>מכור SYMBOL</code> ואז <code>הכל</code>")
    lines.append("")
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
    if alloc.get("status") == "applied":
        lines.append("")
        lines.append(f"✅ חלוקה: {alloc.get('title', '')}")
        amounts = alloc.get("amounts") or {}
        if amounts:
            parts = [f"{s} ${a:.0f}" for s, a in amounts.items()]
            lines.append(" · ".join(parts))
    elif approved_n and alloc.get("status") == "pending":
        lines.append("")
        lines.append("⏳ ממתין לחלוקה ידנית")
    lines.extend(["", SEP, "<b>מה לשלוח:</b>"])
    if alloc.get("status") == "applied":
        lines.append(user_guide_done())
    elif approved_n and alloc.get("status") == "pending":
        lines.append(user_guide_step2())
    else:
        lines.append(user_guide_step1())
    return "\n".join(lines)


def get_active_trading_day() -> str | None:
    from trading_pulse.agent.plan_engine import active_trading_day

    return active_trading_day()


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

    if lower in {"help", "עזרה", "?", "פקודות"}:
        return {"kind": "help"}

    if lower in {"אישור", "אשור", "אשר", "אישר", "confirm", "approval", "מאשר"}:
        return {"kind": "approve", "day": None, "indices_raw": "ALL"}

    if re.search(r"פקודה\s*מלאה|איזה\s+פקודה|מה\s+לשלוח|תוכל\s+לשלוח", raw, flags=re.IGNORECASE):
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

    if lower in {
        "בנה רשימה",
        "רשימה שבועית",
        "סריקה שבועית",
        "סרוק שבועי",
        "build watchlist",
        "weekly scan",
    }:
        return {"kind": "build_watchlist"}

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

    _sym = r"[A-Za-z][A-Za-z0-9.\-^]{0,9}"

    # Hourly price watch: ציון שעתי AAPL / AAPL ציון שעתי / מעקב AAPL
    watch_add = re.fullmatch(
        rf"(?:ציון\s+שעתי|מעקב(?:\s+שעתי)?|watch(?:\s+hourly)?)\s+({_sym})\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if watch_add:
        return {"kind": "price_watch_add", "symbol": watch_add.group(1).upper()}

    watch_add_rtl = re.fullmatch(
        rf"({_sym})\s+(?:ציון\s+שעתי|מעקב(?:\s+שעתי)?|watch(?:\s+hourly)?)\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if watch_add_rtl:
        return {"kind": "price_watch_add", "symbol": watch_add_rtl.group(1).upper()}

    watch_rm = re.fullmatch(
        rf"(?:הפסק\s+מעקב|בטל\s+מעקב|unwatch|stop\s+watch)\s+({_sym})\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if watch_rm:
        return {"kind": "price_watch_remove", "symbol": watch_rm.group(1).upper()}

    watch_rm_rtl = re.fullmatch(
        rf"({_sym})\s+(?:הפסק\s+מעקב|בטל\s+מעקב|unwatch)\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if watch_rm_rtl:
        return {"kind": "price_watch_remove", "symbol": watch_rm_rtl.group(1).upper()}

    if lower in {"מעקבים", "מעקב", "watches", "price watches"}:
        return {"kind": "price_watch_list"}

    stock_detail = re.fullmatch(
        rf"(?:מניה|ציון|ניתוח|score|stock|analyze|analysis)\s+({_sym})\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if stock_detail:
        return {"kind": "stock_detail", "symbol": stock_detail.group(1).upper()}

    # RTL typing often yields "AAPL ציון" instead of "ציון AAPL"
    stock_detail_rtl = re.fullmatch(
        rf"({_sym})\s+(?:מניה|ציון|ניתוח|score|stock|analyze|analysis)\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if stock_detail_rtl:
        return {"kind": "stock_detail", "symbol": stock_detail_rtl.group(1).upper()}

    _buy = r"(?:ו)?(?:ת)?(?:קנ(?:ה|ות|י)|לקנ(?:ות|ה|י)|buy)"
    _amt = r"\$?(\d+(?:\.\d+)?)\$?"

    # Two amounts: מכור 1 200$ קנה 2 100$  (sell $200 of #1, buy $100 of #2)
    swap_two_amt = re.fullmatch(
        rf"(?:מכור|sell)\s+(\d+|{_sym})\s+{_amt}\s+{_buy}\s+(\d+|{_sym})\s+{_amt}\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if swap_two_amt:
        return {
            "kind": "swap",
            "from_ref": swap_two_amt.group(1),
            "to_ref": swap_two_amt.group(3),
            "sell_usd": float(swap_two_amt.group(2)),
            "buy_usd": float(swap_two_amt.group(4)),
        }

    swap_slot_usd = re.fullmatch(
        rf"(?:מכור|sell)\s+(\d+)\s+{_buy}\s+(\d+|{_sym})\s+{_amt}\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if swap_slot_usd:
        buy_usd = float(swap_slot_usd.group(3))
        return {
            "kind": "swap",
            "from_ref": swap_slot_usd.group(1),
            "to_ref": swap_slot_usd.group(2),
            "buy_usd": buy_usd,
            "sell_usd": buy_usd,
        }

    swap_ref = re.fullmatch(
        rf"(?:מכור|sell)\s+(\d+|{_sym})\s+{_buy}\s+(\d+|{_sym})\s+{_amt}\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if swap_ref:
        buy_usd = float(swap_ref.group(3))
        return {
            "kind": "swap",
            "from_ref": swap_ref.group(1),
            "to_ref": swap_ref.group(2),
            "buy_usd": buy_usd,
            "sell_usd": buy_usd,
        }

    # Partial sell then swap: מכור 1 $100 תקנה 2
    swap_sell_amt = re.fullmatch(
        rf"(?:מכור|sell)\s+(\d+|{_sym})\s+{_amt}\s+{_buy}\s+(\d+|{_sym})\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if swap_sell_amt:
        amt = float(swap_sell_amt.group(2))
        return {
            "kind": "swap",
            "from_ref": swap_sell_amt.group(1),
            "to_ref": swap_sell_amt.group(3),
            "sell_usd": amt,
            "buy_usd": amt,
        }

    swap_full = re.fullmatch(
        rf"(?:מכור|sell)\s+(\d+)\s+{_buy}\s+(\d+|{_sym})\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if swap_full:
        return {
            "kind": "swap",
            "from_ref": swap_full.group(1),
            "to_ref": swap_full.group(2),
        }

    sell_usd_slot = re.fullmatch(
        rf"(?:מכור|sell)\s+(\d+)\s+{_amt}\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if sell_usd_slot:
        return {
            "kind": "sell",
            "slot": int(sell_usd_slot.group(1)),
            "sell_usd": float(sell_usd_slot.group(2)),
        }

    sell_usd_slot_rev = re.fullmatch(
        rf"(?:מכור|sell)\s+{_amt}\s+(\d+)\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if sell_usd_slot_rev:
        return {
            "kind": "sell",
            "slot": int(sell_usd_slot_rev.group(2)),
            "sell_usd": float(sell_usd_slot_rev.group(1)),
        }

    sell_pct_slot = re.fullmatch(
        r"(?:מכור|sell)\s+(\d+(?:\.\d+)?)%\s+(\d+)\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if sell_pct_slot:
        return {
            "kind": "sell",
            "slot": int(sell_pct_slot.group(2)),
            "fraction": float(sell_pct_slot.group(1)) / 100.0,
        }

    sell_pct_slot_rev = re.fullmatch(
        r"(?:מכור|sell)\s+(\d+)\s+(\d+(?:\.\d+)?)%\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if sell_pct_slot_rev:
        return {
            "kind": "sell",
            "slot": int(sell_pct_slot_rev.group(1)),
            "fraction": float(sell_pct_slot_rev.group(2)) / 100.0,
        }

    sell_slot = re.fullmatch(
        r"(?:מכור|sell)\s+(\d+)\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if sell_slot:
        return {"kind": "sell", "slot": int(sell_slot.group(1)), "fraction": 1.0}

    buy_cmd = re.fullmatch(
        rf"(?:תקנה|קנה|לקנות|buy)\s+(\d+|{_sym})\s+{_amt}\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if buy_cmd:
        return {
            "kind": "buy",
            "to_ref": buy_cmd.group(1),
            "buy_usd": float(buy_cmd.group(2)),
        }

    # Bare buy: תקנה ARWR / קנה NVDA → spend all free cash
    buy_bare = re.fullmatch(
        rf"(?:תקנה|קנה|לקנות|buy)\s+(\d+|{_sym})\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if buy_bare:
        return {
            "kind": "buy",
            "to_ref": buy_bare.group(1),
            "buy_usd": None,
            "all_cash": True,
        }

    natural_sell = re.fullmatch(
        rf"(?:מכירה|מכיר|למכור|תמכור)\s+(\d+|{_sym})\s*$",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if natural_sell:
        return {
            "kind": "sell_confirmation",
            "ref": natural_sell.group(1),
        }

    sell_match = re.fullmatch(
        r"(?:מכור|sell)\s+(?:(\d+(?:\.\d+)?)%\s+)?([A-Za-z][A-Za-z0-9.\-^]{0,9})",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if sell_match:
        pct_raw = sell_match.group(1)
        fraction = float(pct_raw) / 100.0 if pct_raw else 1.0
        return {"kind": "sell", "symbol": sell_match.group(2).upper(), "fraction": fraction}

    swap_match = re.fullmatch(
        r"(?:החלף|swap)\s+([A-Za-z][A-Za-z0-9.\-^]{0,9})\s+([A-Za-z][A-Za-z0-9.\-^]{0,9})",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if swap_match:
        return {
            "kind": "swap",
            "from_symbol": swap_match.group(1).upper(),
            "to_symbol": swap_match.group(2).upper(),
        }

    nl_swap = re.search(
        rf"(?:ל)?מכור\s+(\d+|{_sym})\s+"
        rf"(?:ו|ו)?(?:ל)?(?:קנ(?:ה|ות|י)|לקנ(?:ות|ה|י)|buy)\s+"
        rf"(\d+|{_sym})"
        rf"(?:\s+{_amt})?",
        raw.strip(),
        flags=re.IGNORECASE,
    )
    if nl_swap:
        cmd: dict[str, Any] = {
            "kind": "swap",
            "from_ref": nl_swap.group(1),
            "to_ref": nl_swap.group(2),
        }
        if nl_swap.group(3):
            amt = float(nl_swap.group(3))
            cmd["buy_usd"] = amt
            cmd["sell_usd"] = amt
        return cmd

    plan_now_phrases = {
        "תוכנית עכשיו",
        "תוכנית חדשה",
        "צור תוכנית",
        "plan now",
        "new plan",
    }
    start_phrases = {
        "התחל",
        "להתחיל",
        "התחל להשקיע",
        "start",
        "go",
        "יאללה",
        "בוא נתחיל",
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
    plan_cancel_phrases = {
        "בטל תוכנית",
        "ביטול תוכנית",
        "בטל את התוכנית",
        "מחק תוכנית",
        "בטל תוכנית למחר",
        "cancel plan",
        "cancel",
    }
    if lower in start_phrases:
        return {"kind": "start", "day": None}
    if lower in plan_cancel_phrases:
        return {"kind": "plan_cancel", "day": None}
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
    return "\n".join(
        [
            "<b>📋 פקודות שימושיות</b>",
            "",
            "אישור תוכנית: <code>הכל</code> · <code>אישור</code>",
            "ביטול תוכנית: <code>בטל תוכנית</code>",
            "החלפה: <code>החלף SOXL HOOD</code>",
            "או בשפה חופשית: <code>למכור SOXL ולקנות HOOD</code>",
            "מכירה: <code>מכור SYMBOL</code>",
            "",
            "<code>תיק</code> · <code>סטטוס</code> · <code>מדריך</code>",
        ]
    )


def telegram_unknown_reply() -> str:
    from trading_pulse.telegram.telegram_format import user_guide_step2

    if allocation_choice_pending_for_active_plan():
        return "\n".join(["❓ <b>לא הבנתי.</b> אולי התכוונת לחלוקה?", "", user_guide_step2()])
    return "\n".join(
        [
            "❓ <b>לא הבנתי את הפקודה.</b>",
            "דוגמאות: <code>תיק</code> · <code>תוכנית</code> · <code>מכור U</code>",
            "לכל האפשרויות: <code>עזרה</code>",
        ]
    )


def resend_plan_telegram(cfg: AgentConfig, plan: dict[str, Any]) -> None:
    """Resend existing plan as HTML card + charts (no regeneration)."""
    send_plan_notifications(cfg, plan)


def cancel_plan_telegram(cfg: AgentConfig) -> str:
    """Cancel the active plan (next open session) via Telegram."""
    from trading_pulse.agent.plan_engine import cancel_plan

    result = cancel_plan()
    if result.get("ok"):
        day = escape_html(str(result.get("day", "")))
        syms = result.get("symbols") or []
        syms_txt = ", ".join(escape_html(s) for s in syms) if syms else "—"
        return (
            f"<b>🗑️ התוכנית בוטלה</b>\n"
            f"<b>יום מסחר:</b> {day}\n"
            f"בוטלו: {syms_txt}\n\n"
            "שלח <code>תוכנית עכשיו</code> ליצירת תוכנית חדשה, "
            "או חכה לתוכנית הערב."
        )
    reason = result.get("reason")
    if reason == "already_executed":
        return (
            "❌ <b>אי אפשר לבטל</b>\n"
            "התוכנית כבר בוצעה (הפוזיציות נפתחו). "
            "למכירה שלח <code>מכור SYMBOL</code>."
        )
    return "ℹ️ <b>אין תוכנית פעילה לביטול</b>\nשלח <code>תוכנית עכשיו</code> ליצירת תוכנית."


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


def start_investing(cfg: AgentConfig) -> dict[str, Any]:
    """
    One-step flow: ensure plan for today (or next session) and approve all.
    Returns payload for API / Telegram.
    """
    state = load_state(cfg)
    target = resolve_plan_target_day(date.today(), force=True)
    td_str = target.isoformat()
    path = plan_path(target)
    created = False

    if path.exists() and not report_path(target).exists():
        plan = read_json(path)
    else:
        plan = generate_plan(cfg, state, date.today(), force=True)
        send_plan_notifications(cfg, plan)
        td_str = str(plan.get("for_trading_day", td_str))
        path = plan_path(date.fromisoformat(td_str))
        plan = read_json(path)
        created = True

    recs = plan.get("recommendations", [])
    if not recs:
        return {
            "ok": True,
            "status": "no_picks",
            "trading_day": td_str,
            "message": "אין המלצות היום — נסה שוב מחר או אחרי עדכון רשימת המניות.",
            "symbols": [],
        }

    alloc = plan.get("allocation") or {}
    from trading_pulse.agent.plan_engine import STATUS_CONFIRMED, apply_confirm, normalize_status, pending_buy_symbols
    from trading_pulse.agent.trading_flow import entries_already_run, funding_gap, scheduled_entry_moment

    already = normalize_status(plan) == STATUS_CONFIRMED and alloc.get("status") == "applied"
    if not already:
        gap = funding_gap(plan, state, cfg)
        if gap:
            return {
                "ok": False,
                "status": "needs_cash",
                "trading_day": td_str,
                "message": f"אין מספיק מזומן לקנייה. מכור מניה קיימת ואז אשר שוב.",
                "symbols": [r["symbol"] for r in recs],
            }
        plan = apply_confirm(plan, state, cfg)
        save_json(path, plan)

    symbols = [r["symbol"] for r in plan.get("recommendations", []) if r.get("approved")]
    entry_when = scheduled_entry_moment(cfg, date.fromisoformat(td_str))
    amounts = " · ".join(
        f"{r['symbol']} ${float(r.get('capital_usd', 0)):.0f}"
        for r in plan.get("recommendations", [])
        if r.get("approved")
    )
    pending = pending_buy_symbols(plan, state)
    td = date.fromisoformat(td_str)
    if entries_already_run(plan, td) or (already and not pending):
        status = "already_bought"
        message = (
            f"התיק מעודכן ({amounts}). צפה ב־<code>תיק</code>."
            if not pending
            else f"מאושר ({amounts}). כניסה לשוק ב-{entry_when}."
        )
    elif already and not created:
        status = "confirmed_pending_entry"
        message = f"מאושר ({amounts}). הקנייה תתבצע בפתיחת השוק — {entry_when}."
    else:
        status = "confirmed_pending_entry"
        message = f"אושר ({amounts}). הקנייה תתבצע בפתיחת השוק — {entry_when}."

    return {
        "ok": True,
        "status": status,
        "trading_day": td_str,
        "created_plan": created,
        "symbols": symbols,
        "entries": [],
        "entry_when": entry_when,
        "message": message,
    }


def run_start_investing_telegram(cfg: AgentConfig) -> str:
    from trading_pulse.telegram.telegram_format import format_start_investing_reply

    result = start_investing(cfg)
    return format_start_investing_reply(result)


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
            # Natural-language sell confirm: «מכירה X» then «כן» / «אישור»
            state = load_state(cfg)
            confirmed_sell = try_confirm_pending_sell(state, text)
            if confirmed_sell:
                save_json(STATE_FILE, state)
                reply = execute_sell_command(cfg, confirmed_sell, 1.0)
                if reply:
                    send_telegram_message(cfg, reply, context="reply:sell", parse_mode="HTML")
                handled += 1
                continue

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

            # Any other command clears a stale sell confirm (except repeating sell_confirmation)
            if kind not in {"sell_confirmation", "sell"} and pending_sell_confirm_symbol(state):
                clear_pending_sell_confirm(state)
                save_json(STATE_FILE, state)

            if kind == "help":
                reply = telegram_help_text()
                reply_context = "reply:help"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "guide_telegram":
                from trading_pulse.telegram.telegram_guide import (
                    format_telegram_guide_messages,
                    render_telegram_guide_images,
                )

                images = render_telegram_guide_images()
                if images:
                    for i, (png, caption) in enumerate(images):
                        send_telegram_photo(
                            cfg,
                            png,
                            caption,
                            context=f"reply:guide_telegram:img:{i}",
                            parse_mode="HTML",
                        )
                else:
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
                from trading_pulse.agent.portfolio_index import attach_slots_to_portfolio
                from trading_pulse.telegram.reply_cards import card_portfolio
                from trading_pulse.telegram.telegram_format import format_portfolio

                pdata = attach_slots_to_portfolio(build_portfolio())
                text_reply = format_portfolio(pdata)
                try:
                    img = card_portfolio(pdata)
                    # No caption — full details live in the image (mobile-safe).
                    send_telegram_photo(
                        cfg,
                        img,
                        "",
                        context="reply:portfolio",
                        inbox_text="תיק",
                    )
                except Exception as ex:
                    logging.warning("Portfolio image failed, sending text: %s", ex)
                    send_telegram_message(
                        cfg,
                        text_reply,
                        context="reply:portfolio",
                        parse_mode="HTML",
                    )
                handled += 1
                continue
            elif kind == "allocation_show":
                trading_day = resolve_trading_day(parsed.get("day"))
                send_allocation_prompt(trading_day, cfg=cfg)
                handled += 1
                continue
            elif kind == "plan_show":
                trading_day = resolve_trading_day(parsed.get("day"))
                path = plan_path(date.fromisoformat(trading_day))
                if not path.exists():
                    reply = (
                        f"❌ <b>אין תוכנית ל-{trading_day}</b>\n"
                        f"חכה ל-{_plan_time_hint(cfg)} או שלח <code>תוכנית עכשיו</code>"
                    )
                    reply_context = "reply:plan"
                    send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                else:
                    # Resend the plan bundle only — no extra «שלחתי שוב» card
                    # (it looked like a new approval ask after the real plan).
                    plan = read_json(path)
                    resend_plan_telegram(cfg, plan)
                handled += 1
                continue
            elif kind == "start":
                reply = run_start_investing_telegram(cfg)
                reply_context = "reply:start"
            elif kind == "plan_now":
                reply = run_plan_now_telegram(cfg)
                reply_context = "reply:plan"
                send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                handled += 1
                continue
            elif kind == "plan_cancel":
                reply = cancel_plan_telegram(cfg)
                send_telegram_message(cfg, reply, context="reply:plan_cancel", parse_mode="HTML")
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
            elif kind == "stock_detail":
                send_stock_detail(cfg, str(parsed.get("symbol", "")))
                handled += 1
                continue
            elif kind == "price_watch_add":
                from trading_pulse.agent.price_watch import (
                    add_price_watch,
                    format_watch_added,
                    mark_price_watch_sent,
                    send_price_watch_snapshot,
                )

                state = load_state(cfg)
                try:
                    result = add_price_watch(state, str(parsed.get("symbol", "")))
                    save_json(STATE_FILE, state)
                    if result.get("added"):
                        # One start payload (metrics + chart). Hourly ticks wait a full interval.
                        send_price_watch_snapshot(cfg, result["symbol"])
                        mark_price_watch_sent(state, result["symbol"])
                        save_json(STATE_FILE, state)
                    else:
                        reply = format_watch_added(cfg, result)
                        send_telegram_message(
                            cfg, reply, context="reply:price_watch_add", parse_mode="HTML"
                        )
                except ValueError as ex:
                    send_telegram_message(
                        cfg, f"⚠️ <b>{ex}</b>", context="reply:price_watch_add", parse_mode="HTML"
                    )
                handled += 1
                continue
            elif kind == "price_watch_remove":
                from trading_pulse.agent.price_watch import format_watch_removed, remove_price_watch

                state = load_state(cfg)
                try:
                    result = remove_price_watch(state, str(parsed.get("symbol", "")))
                    save_json(STATE_FILE, state)
                    reply = format_watch_removed(result)
                except ValueError as ex:
                    reply = f"⚠️ <b>{ex}</b>"
                send_telegram_message(cfg, reply, context="reply:price_watch_remove", parse_mode="HTML")
                handled += 1
                continue
            elif kind == "price_watch_list":
                from trading_pulse.agent.price_watch import format_watches_list

                state = load_state(cfg)
                reply = format_watches_list(cfg, state)
                send_telegram_message(cfg, reply, context="reply:price_watch_list", parse_mode="HTML")
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
            elif kind == "build_watchlist":
                import threading

                send_telegram_message(
                    cfg,
                    "🗓️ <b>בונה רשימה שבועית…</b>\nסריקה איטית של מאות מניות — ייקח כמה דקות. אשלח סיכום בסיום.",
                    context="reply:build_watchlist",
                    parse_mode="HTML",
                )

                def _run_weekly_scan() -> None:
                    from trading_pulse.agent.weekly_watchlist import build_weekly_watchlist
                    from trading_pulse.telegram.telegram_format import escape_html

                    try:
                        fresh_cfg = load_config()
                        result = build_weekly_watchlist(fresh_cfg)
                        send_weekly_watchlist_notification(
                            cfg, result, context="reply:build_watchlist_done"
                        )
                    except Exception as ex:
                        logging.exception("Weekly watchlist (telegram) failed: %s", ex)
                        send_telegram_message(
                            cfg,
                            f"❌ <b>בניית הרשימה נכשלה</b>\n{escape_html(str(ex))}",
                            context="reply:build_watchlist_err",
                            parse_mode="HTML",
                        )

                threading.Thread(target=_run_weekly_scan, daemon=True).start()
                handled += 1
                continue
            elif kind == "sell_confirmation":
                ref = str(parsed.get("ref") or "")
                symbol = resolve_sell_target(ref)
                if symbol:
                    state = load_state(cfg)
                    set_pending_sell_confirm(state, symbol)
                    save_json(STATE_FILE, state)
                    reply = (
                        f"❓ <b>למכור את {escape_html(symbol)}?</b>\n"
                        f"שלח <code>כן</code> / <code>אישור</code> לביצוע\n"
                        f"או <code>מכור {escape_html(symbol)}</code>\n"
                        "<i>לא בוצעה פעולה עדיין.</i>"
                    )
                else:
                    reply = (
                        "❌ <b>לא מצאתי את המניה בתיק</b>\n"
                        "שלח <code>תיק</code> כדי לראות את המספר או הסימבול."
                    )
                send_telegram_message(
                    cfg,
                    reply,
                    context="reply:sell_confirmation",
                    parse_mode="HTML",
                )
                handled += 1
                continue
            elif kind == "sell":
                symbol = parsed.get("symbol")
                if parsed.get("slot") is not None:
                    symbol = resolve_sell_target(str(parsed["slot"]))
                elif symbol:
                    symbol = resolve_sell_target(str(symbol)) or str(symbol).upper()
                if not symbol:
                    reply = "❌ <b>מספר מניה לא תקין</b> — שלח <code>תיק</code> לרשימה"
                else:
                    state = load_state(cfg)
                    clear_pending_sell_confirm(state)
                    save_json(STATE_FILE, state)
                    reply = execute_sell_command(
                        cfg,
                        symbol,
                        float(parsed.get("fraction", 1.0)),
                        sell_usd=parsed.get("sell_usd"),
                    )
                if reply:
                    send_telegram_message(cfg, reply, context="reply:sell", parse_mode="HTML")
                handled += 1
                continue
            elif kind == "buy":
                to_ref = str(parsed.get("to_ref") or parsed.get("symbol", ""))
                to_sym = resolve_buy_target(to_ref)
                if not to_sym:
                    reply = "❌ <b>מספר/מניה לא תקינים</b> — שלח <code>תיק</code>"
                else:
                    buy_usd = parsed.get("buy_usd")
                    if buy_usd is None or parsed.get("all_cash"):
                        buy_usd = None  # execute_buy_command uses all free cash
                    else:
                        buy_usd = float(buy_usd)
                    reply = execute_buy_command(cfg, to_sym, buy_usd)
                if reply:
                    send_telegram_message(cfg, reply, context="reply:buy", parse_mode="HTML")
                handled += 1
                continue
            elif kind == "swap":
                from_sym = resolve_sell_target(str(parsed.get("from_ref") or parsed.get("from_symbol", "")))
                to_ref = str(parsed.get("to_ref") or parsed.get("to_symbol", ""))
                to_sym = resolve_buy_target(to_ref)
                if not from_sym:
                    reply = "❌ <b>מספר/מניה למכירה לא תקינים</b> — שלח <code>תיק</code>"
                else:
                    reply = execute_swap_command(
                        cfg,
                        from_sym,
                        to_sym,
                        sell_fraction=float(parsed.get("sell_fraction", 1.0)),
                        sell_usd=parsed.get("sell_usd"),
                        buy_usd=parsed.get("buy_usd"),
                    )
                if reply:
                    send_telegram_message(cfg, reply, context="reply:swap", parse_mode="HTML")
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
                recs = plan.get("recommendations", []) or []
                total = len(recs)
                raw_idx = str(parsed.get("indices_raw", "ALL"))
                indices = parse_indices(raw_idx, total=total, recs=recs)
                if kind == "approve" and indices and raw_idx.upper() == "ALL":
                    # Cash buys only — skip names already held (e.g. after intraday swap)
                    # so we never confirm «ILMN $0 · מחר בפתיחה».
                    from trading_pulse.agent.positions import held_symbols

                    held_now = held_symbols(load_state(cfg))
                    indices = [
                        i
                        for i in indices
                        if 0 <= i < len(recs)
                        and str(recs[i].get("symbol") or "") not in held_now
                    ]
                if not indices:
                    from trading_pulse.telegram.telegram_format import (
                        format_below_bar_approve_hint,
                        format_nothing_to_approve,
                        user_guide_invalid_approve,
                    )

                    weak = [r for r in recs if r.get("below_bar")]
                    if raw_idx.upper() == "ALL" and kind == "approve":
                        if weak:
                            reply = format_below_bar_approve_hint(weak, plan_recs=recs)
                        else:
                            reply = format_nothing_to_approve(plan)
                    else:
                        reply = user_guide_invalid_approve()
                    reply_context = f"reply:{kind}"
                    send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                    handled += 1
                    continue
                else:
                    reply = set_plan_status(trading_day, kind.upper(), indices, cfg=cfg)
                    skipped_weak = [
                        str(r["symbol"])
                        for i, r in enumerate(recs)
                        if r.get("below_bar") and i not in indices and raw_idx.upper() == "ALL"
                    ]
                    if skipped_weak and kind == "approve":
                        from trading_pulse.telegram.telegram_format import format_below_bar_skipped_note

                        reply = reply + "\n\n" + format_below_bar_skipped_note(skipped_weak)
                    reply_context = f"reply:{kind}"
                    send_telegram_message(cfg, reply, context=reply_context, parse_mode="HTML")
                    handled += 1
                    continue
            else:
                reply = telegram_unknown_reply()
        except ValueError as ex:
            if str(ex) == "no_active_plan":
                reply = (
                    f"📭 <b>אין תוכנית פעילה.</b>\n"
                    f"חכה להודעה ב-{_plan_time_hint(cfg)} או שלח <code>סטטוס</code>."
                )
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

    # Reload — sell/buy/swap already saved a fresh state; don't overwrite with stale snapshot.
    state = load_state(cfg)
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


def _experimental_scan_pool(
    symbols: list[str],
    *,
    state: dict[str, Any],
    held: set[str],
    selected: set[str],
    max_leveraged: int,
    as_of: date,
) -> tuple[list[str], set[str]]:
    """Apply portfolio guards before each experimental strategy scan."""
    from trading_pulse.agent.symbol_cooldown import (
        LEVERAGED_ETF_SYMBOLS,
        is_symbol_in_cooldown,
        leveraged_symbols,
    )

    normalized_selected = {str(symbol).upper() for symbol in selected}
    excluded = {str(symbol).upper() for symbol in held}
    if (
        max_leveraged > 0
        and len(leveraged_symbols(excluded | normalized_selected)) >= max_leveraged
    ):
        excluded |= set(LEVERAGED_ETF_SYMBOLS) - normalized_selected
    eligible = [
        str(symbol)
        for symbol in symbols
        if str(symbol).upper() not in excluded
        and not is_symbol_in_cooldown(state, str(symbol), as_of=as_of)
    ]
    return eligible, excluded


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
    from trading_pulse.agent.trading_flow import (
        funding_gap,
        initial_deploy_slots,
        is_empty_portfolio,
        per_trade_cap_for_plan,
        plan_intent,
    )

    target_day = resolve_plan_target_day(run_day, force=force)
    existing_path = plan_path(target_day)
    if not force and existing_path.exists():
        existing = read_json(existing_path)
        if plan_is_protected(existing, state=state, as_of=run_day):
            logging.info(
                "Plan for %s is confirmed with pending fills — keeping until market open",
                target_day.isoformat(),
            )
            existing["_regeneration_skipped"] = True
            return existing
    strategy = profile_strategy(cfg)
    from trading_pulse.agent.strategies.registry import enabled_strategy_ids

    enabled_strategies = enabled_strategy_ids(cfg)
    capital = float(state["equity"])
    held = held_symbols(state)
    holdings = holdings_snapshot(state)
    scan_tickers = sorted(set(cfg.tickers) | held)
    logging.info("Scanning %d tickers (%s strategy)", len(scan_tickers), strategy)
    candidates = fetch_signal_universe(scan_tickers, cfg)
    candidates_before_quality = len(candidates)
    raw_universe = candidates.copy()
    universe_scores: dict[str, dict[str, Any]] = {}
    if not candidates.empty:
        for _, _row in candidates.iterrows():
            universe_scores[str(_row["symbol"])] = {
                "score": float(_row.get("score", 0) or 0),
                "close": float(_row.get("close", 0) or 0),
            }
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
    if is_empty_portfolio(state):
        new_trade_slots = min(initial_deploy_slots(cfg, state), open_slots or initial_deploy_slots(cfg, state))
    else:
        new_trade_slots = min(open_slots, int(cfg.max_trades_per_day))
    deployable = available_capital(cfg, state)
    if is_empty_portfolio(state):
        deployable = capital
    market_regime = None
    if bool(getattr(cfg, "market_regime_filter_enabled", False)):
        from trading_pulse.agent.strategies.market_regime import fetch_market_regime

        market_regime = fetch_market_regime()
        deployable = round(
            deployable * float(market_regime.get("exposure_multiplier", 1.0)),
            2,
        )
        if float(market_regime.get("exposure_multiplier", 1.0)) <= 0:
            new_trade_slots = 0

    if not candidates.empty and held:
        candidates = candidates[~candidates["symbol"].isin(held)]
    logging.info(
        "Plan slots: %d new | holding %d symbol(s) | deployed $%s",
        new_trade_slots,
        len(holdings),
        deployed_capital(state),
    )
    score_enabled = "score_momentum" in enabled_strategies
    candle_enabled = (
        "rising_three" in enabled_strategies
        and bool(getattr(cfg, "candle_fourth_enabled", True))
        and new_trade_slots >= 1
    )
    score_slots = (
        max(0, new_trade_slots - (1 if candle_enabled else 0))
        if score_enabled
        else 0
    )
    picks = candidates.head(score_slots) if score_slots > 0 and not candidates.empty else pd.DataFrame()
    fallback_used = False
    if score_enabled and picks.empty and score_slots > 0 and not raw_universe.empty:
        from trading_pulse.agent.symbol_cooldown import is_symbol_in_cooldown

        pool = raw_universe[~raw_universe["symbol"].isin(held)]
        if not pool.empty:
            pool = pool[
                ~pool["symbol"].apply(
                    lambda s: is_symbol_in_cooldown(state, str(s), as_of=run_day)
                )
            ]
        if not pool.empty:
            picks = pool.sort_values("score", ascending=False).head(1)
            fallback_used = True
            logging.info(
                "No pick passed quality bar — using best-available fallback: %s (score %.2f)",
                str(picks.iloc[0]["symbol"]),
                float(picks.iloc[0]["score"]),
            )

    candle_hit = None
    if candle_enabled:
        from trading_pulse.agent.candlestick_patterns import scan_rising_three_methods
        from trading_pulse.agent.symbol_cooldown import is_symbol_in_cooldown

        # Scan score picks too: the combiner records strategy agreement and
        # keeps only one portfolio position per symbol.
        exclude = set(held)
        scan_pool = [
            str(s)
            for s in scan_tickers
            if str(s).upper() not in exclude
            and not is_symbol_in_cooldown(state, str(s), as_of=run_day)
        ]
        candle_hit = scan_rising_three_methods(scan_pool, exclude=exclude, allow_partial=True)
        if candle_hit:
            logging.info(
                "Candle fourth pick: %s score=%.1f weak=%s",
                candle_hit.symbol,
                candle_hit.pattern_score,
                candle_hit.pattern_weak,
            )
        elif score_enabled and not candidates.empty and len(picks) < new_trade_slots:
            # No candle signal — fill remaining slot from score pipeline.
            already = {str(s).upper() for s in picks["symbol"].tolist()} if not picks.empty else set()
            extra = candidates[~candidates["symbol"].astype(str).str.upper().isin(already)]
            need = new_trade_slots - len(picks)
            if not extra.empty and need > 0:
                more = extra.head(need)
                picks = pd.concat([picks, more], ignore_index=True) if not picks.empty else more
                logging.info("No candle pattern — filled %d extra score pick(s)", len(more))

    method2_hit = None
    if "method2" in enabled_strategies and bool(getattr(cfg, "method2_enabled", True)):
        from trading_pulse.agent.candle_method2 import scan_method2
        from trading_pulse.agent.symbol_cooldown import (
            LEVERAGED_ETF_SYMBOLS,
            is_symbol_in_cooldown,
            leveraged_symbols,
        )

        # Do not exclude other strategy picks: duplicate symbols become
        # confluence in combine_recommendations().
        exclude_m2 = set(held)
        main_symbols = {
            str(symbol).upper()
            for symbol in (
                ([] if picks.empty else picks["symbol"].tolist())
                + ([candle_hit.symbol] if candle_hit else [])
            )
        }
        # Respect leveraged ETF cap across score + candle + method2
        max_lev = int(getattr(cfg, "max_leveraged_etf_positions", 1) or 0)
        if max_lev > 0:
            already_lev = leveraged_symbols(set(held) | main_symbols)
            if len(already_lev) >= max_lev:
                # Keep a selected leveraged symbol eligible for confluence, but
                # do not let Method2 add a different leveraged ETF.
                exclude_m2 |= set(LEVERAGED_ETF_SYMBOLS) - main_symbols
        # Need a free open slot beyond main picks
        main_count = len(main_symbols)
        if open_slots > main_count or (is_empty_portfolio(state) and main_count < int(cfg.max_open_positions)):
            scan_pool_m2 = [
                str(s)
                for s in scan_tickers
                if str(s).upper() not in exclude_m2
                and not is_symbol_in_cooldown(state, str(s), as_of=run_day)
            ]
            method2_hit = scan_method2(
                scan_pool_m2,
                exclude=exclude_m2,
                equity=capital,
                risk_pct=float(getattr(cfg, "method2_risk_pct", 0.02)),
                max_position_pct=float(getattr(cfg, "method2_max_position_pct", 0.15)),
                min_avg_volume=float(getattr(cfg, "min_avg_volume_20d", 1_000_000)),
                allow_short=bool(getattr(cfg, "method2_allow_short", True)),
            )
            if method2_hit:
                logging.info(
                    "Method2 fifth pick: %s %s trigger=%s capital=$%.0f",
                    method2_hit.symbol,
                    method2_hit.side,
                    method2_hit.trigger,
                    method2_hit.capital_usd,
                )

    m2_capital = float(method2_hit.capital_usd) if method2_hit else 0.0
    main_n = len(picks) + (1 if candle_hit else 0)
    main_budget = max(0.0, float(deployable) - m2_capital)
    if main_n > 0:
        per_trade_cap = round(main_budget / main_n, 2)
    else:
        per_trade_cap = per_trade_cap_for_plan(cfg, state, 1)
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
            "below_bar": fallback_used,
            "strategy": "score",
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

    if candle_hit:
        entry = float(candle_hit.close)
        uni = universe_scores.get(candle_hit.symbol) or {}
        score_fallback = float(uni.get("score", candle_hit.pattern_score) or candle_hit.pattern_score)
        candle_rec: dict[str, Any] = {
            "symbol": candle_hit.symbol,
            "side": "LONG",
            "capital_usd": round(per_trade_cap, 2),
            "entry_ref_price": round(entry, 4),
            "stop_loss_price": round(entry * (1 - cfg.stop_loss_pct), 4),
            "take_profit_price": round(entry * (1 + cfg.take_profit_pct), 4),
            "floor_price": round(entry * (1 - cfg.stop_loss_pct), 4),
            "stop_loss_pct": cfg.stop_loss_pct,
            "take_profit_pct": cfg.take_profit_pct,
            "score": round(score_fallback, 4),
            "score_technical": round(score_fallback, 4),
            "score_simple_avg": round(score_fallback, 4),
            "source_score_std": 0.0,
            "source_score_spread": 0.0,
            "source_disagreement": False,
            "ret_5d_pct": 0.0,
            "vol_ratio": 0.0,
            "volume_ok": True,
            "source_scores": {"candlestick": round(candle_hit.pattern_score, 2)},
            "sources_used": 1,
            "sources_list": ["candlestick"],
            "approved": False,
            "below_bar": bool(candle_hit.pattern_weak),
            "strategy": candle_hit.pattern,
            "pattern_score": candle_hit.pattern_score,
            "pattern_weak": candle_hit.pattern_weak,
            "reason": candle_hit.reason_he,
        }
        if speculative:
            atr = float((candle_hit.details or {}).get("atr") or 0)
            atr_pct = round((atr / entry * 100) if entry else 0, 2)
            candle_rec["atr_pct"] = atr_pct
            candle_rec["near_high_pct"] = 0.0
            candle_rec["breakout_ok"] = not candle_hit.pattern_weak
        recommendations.append(candle_rec)

    if method2_hit:
        entry = float(method2_hit.entry_ref)
        stop = float(method2_hit.stop_ref)
        side = str(method2_hit.side or "LONG")
        stop_pct = abs(entry - stop) / entry if entry else cfg.stop_loss_pct
        if side == "SHORT":
            tp_price = round(entry * (1 - cfg.take_profit_pct), 4)
        else:
            tp_price = round(entry * (1 + cfg.take_profit_pct), 4)
        method2_rec: dict[str, Any] = {
            "symbol": method2_hit.symbol,
            "side": side,
            "capital_usd": round(float(method2_hit.capital_usd), 2),
            "entry_ref_price": round(entry, 4),
            "stop_loss_price": round(stop, 4),
            "take_profit_price": tp_price,
            "floor_price": round(stop, 4),
            "stop_loss_pct": round(stop_pct, 4),
            "take_profit_pct": cfg.take_profit_pct,
            "score": round(float(method2_hit.pattern_score), 4),
            "score_technical": round(float(method2_hit.pattern_score), 4),
            "score_simple_avg": round(float(method2_hit.pattern_score), 4),
            "source_score_std": 0.0,
            "source_score_spread": 0.0,
            "source_disagreement": False,
            "ret_5d_pct": 0.0,
            "vol_ratio": 0.0,
            "volume_ok": True,
            "source_scores": {"method2": round(method2_hit.pattern_score, 2)},
            "sources_used": 1,
            "sources_list": ["method2"],
            "approved": False,
            "below_bar": False,
            "strategy": "method2",
            "trigger": method2_hit.trigger,
            "method2_entry_ref": round(entry, 4),
            "method2_stop_ref": round(stop, 4),
            "pattern_score": method2_hit.pattern_score,
            "reason": method2_hit.reason_he,
            "sleeve": True,
            "entry_style": "breakout",
        }
        if speculative:
            method2_rec["atr_pct"] = float((method2_hit.details or {}).get("atr_pct") or 0)
            method2_rec["near_high_pct"] = 0.0
            method2_rec["breakout_ok"] = True
        recommendations.append(method2_rec)

    if "trend_pullback" in enabled_strategies and new_trade_slots > 0:
        from trading_pulse.agent.strategies.trend_pullback import (
            scan_trend_pullback,
            signal_to_recommendation,
        )

        pullback = scan_trend_pullback(
            scan_tickers,
            exclude=set(held),
            stop_loss_pct=min(float(cfg.stop_loss_pct), 0.08),
            take_profit_pct=min(float(cfg.take_profit_pct), 0.16),
        )
        if pullback:
            recommendations.append(signal_to_recommendation(pullback))

    selected_symbols = {
        str(rec.get("symbol") or "").upper() for rec in recommendations
    }
    max_leveraged = int(getattr(cfg, "max_leveraged_etf_positions", 1) or 0)
    experimental_scan_pool, experimental_exclude = _experimental_scan_pool(
        scan_tickers,
        state=state,
        held=set(held),
        selected=selected_symbols,
        max_leveraged=max_leveraged,
        as_of=run_day,
    )

    if "vcp_breakout" in enabled_strategies and new_trade_slots > 0:
        from trading_pulse.agent.strategies.vcp_breakout import (
            scan_vcp_breakout,
            signal_to_recommendation,
        )

        vcp = scan_vcp_breakout(
            experimental_scan_pool,
            exclude=experimental_exclude,
            stop_loss_pct=min(float(cfg.stop_loss_pct), 0.08),
            take_profit_pct=min(float(cfg.take_profit_pct), 0.18),
            min_price_usd=float(getattr(cfg, "min_price_usd", 5.0)),
            min_avg_volume_20d=float(
                getattr(cfg, "min_avg_volume_20d", 500_000)
            ),
        )
        if vcp:
            recommendations.append(signal_to_recommendation(vcp))
            selected_symbols.add(vcp.symbol.upper())
            experimental_scan_pool, experimental_exclude = (
                _experimental_scan_pool(
                    scan_tickers,
                    state=state,
                    held=set(held),
                    selected=selected_symbols,
                    max_leveraged=max_leveraged,
                    as_of=run_day,
                )
            )

    if "relative_strength" in enabled_strategies and new_trade_slots > 0:
        from trading_pulse.agent.strategies.relative_strength import (
            scan_relative_strength,
            signal_to_recommendation,
        )

        relative_strength = scan_relative_strength(
            experimental_scan_pool,
            exclude=experimental_exclude,
            stop_loss_pct=min(float(cfg.stop_loss_pct), 0.09),
            take_profit_pct=min(float(cfg.take_profit_pct), 0.20),
            min_price_usd=float(getattr(cfg, "min_price_usd", 5.0)),
            min_avg_volume_20d=float(
                getattr(cfg, "min_avg_volume_20d", 500_000)
            ),
        )
        if relative_strength:
            recommendations.append(signal_to_recommendation(relative_strength))

    from trading_pulse.agent.strategies.combiner import (
        allocate_combined_capital,
        combine_recommendations,
    )

    selection_cap = min(
        open_slots,
        new_trade_slots + (1 if method2_hit else 0),
    )
    if market_regime and float(market_regime.get("exposure_multiplier", 1.0)) <= 0:
        selection_cap = 0
    recommendations = combine_recommendations(
        recommendations,
        max_picks=selection_cap,
        score_profile=strategy,
    )
    allocate_combined_capital(recommendations, deployable=deployable)
    main_caps = [
        float(r.get("capital_usd") or 0)
        for r in recommendations
        if str(r.get("strategy_id") or "") != "method2"
    ]
    if main_caps:
        per_trade_cap = round(main_caps[0], 2)

    enrich_recommendations(recommendations, cfg, speculative=speculative)
    # Order: score picks → Rising Three → שיטה 2 (dedicated slots).
    special_order = ("rising_three_methods", "method2")
    if any(str(r.get("strategy")) in special_order for r in recommendations):
        score_recs = [r for r in recommendations if str(r.get("strategy")) not in special_order]
        rising = [r for r in recommendations if str(r.get("strategy")) == "rising_three_methods"]
        m2 = [r for r in recommendations if str(r.get("strategy")) == "method2"]
        recommendations[:] = score_recs + rising + m2
        for rank, rec in enumerate(recommendations, start=1):
            rec["explanation"] = build_recommendation_explanation(
                rec, rank, speculative=speculative
            )

    from trading_pulse.agent.holdings_review import review_holdings

    holding_actions = [
        r.to_dict()
        for r in review_holdings(holdings, cfg, universe_scores, recommendations)
    ]
    no_cash = deployable < 1
    no_slots = open_slots <= 0 or new_trade_slots <= 0
    if market_regime and float(market_regime.get("exposure_multiplier", 1.0)) <= 0:
        blocked_reason = "market_regime"
    elif no_cash and no_slots:
        blocked_reason = "no_cash_and_slots"
    elif no_slots:
        blocked_reason = "no_open_slots"
    elif no_cash:
        blocked_reason = "no_cash"
    else:
        blocked_reason = None

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "for_trading_day": target_day.isoformat(),
        "risk_profile": cfg.risk_profile,
        "strategy": strategy,
        "strategy_mode": str(getattr(cfg, "strategy_mode", "balanced_mix")),
        "enabled_strategies": list(enabled_strategies),
        "market_regime": market_regime,
        "hold_mode": cfg.hold_mode,
        "risk_profile_summary": risk_profile_summary(cfg, capital),
        "equity_snapshot": round(capital, 2),
        "deployed_capital_usd": deployed_capital(state),
        "available_capital_usd": round(deployable, 2),
        "holdings": holdings,
        "holding_actions": holding_actions,
        "fallback_pick": fallback_used,
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
        "capacity": {
            "open_slots": open_slots,
            "new_trade_slots": new_trade_slots,
            "cash_free_usd": round(deployable, 2),
            "positions_open": len(holdings),
            "max_positions": int(cfg.max_open_positions),
            "blocked_reason": blocked_reason,
        },
    }
    if recommendations:
        plan["status"] = "draft"
    elif holdings:
        plan["status"] = "draft"
        plan["hold_only"] = True
    else:
        plan["status"] = "draft"
        if candidates_before_quality > 0 and candidates.empty:
            top = filter_stats.get("top_skipped_scores") or []
            if top:
                names = ", ".join(f"{r['symbol']} ({r['score']:.1f})" for r in top[:3])
                plan["no_picks_reason"] = (
                    f"סף ציון {cfg.min_entry_score:.0f} — הציונים הגבוהים: {names}"
                )
            else:
                plan["no_picks_reason"] = "הסינון האיכותי לא מצא מניה שעומדת בכל התנאים."
        elif not candidates.empty and (new_trade_slots <= 0 or deployable < 1):
            plan["no_picks_reason"] = (
                f"{len(candidates)} מניות עברו את סף האיכות, "
                "אך אין כרגע מזומן או מקום פנוי בתיק."
            )
        elif not candidates.empty:
            plan["no_picks_reason"] = (
                f"{len(candidates)} מניות עברו את סף האיכות, "
                "אך האסטרטגיות הפעילות לא נתנו אות כניסה מתאים."
            )
        else:
            plan["no_picks_reason"] = "לא נמצאו מועמדים בסריקת האותות להיום."
    if speculative:
        plan["monthly_target_summary"] = monthly_target_summary(cfg, state)
    plan["flow_intent"] = plan_intent(plan, state, cfg)
    gap = funding_gap(plan, state, cfg)
    if gap:
        plan["funding"] = gap
    # Align displayed capital with what «הכל» will allocate (single source of truth).
    try:
        from trading_pulse.agent.plan_engine import sync_plan_portfolio_snapshot

        sync_plan_portfolio_snapshot(plan, state, cfg)
    except Exception as ex:
        logging.debug("Plan amount sync skipped: %s", ex)
    from trading_pulse.agent.plan_engine import supersede_other_plans

    supersede_other_plans(target_day)
    save_json(plan_path(target_day), plan)
    try:
        from trading_pulse.agent.strategies.shadow import record_shadow_plan

        record_shadow_plan(plan)
    except OSError as ex:
        logging.warning("Could not update strategy shadow ledger: %s", ex)
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
    pnl_total = sum(
        float(h.get("pnl_applied_at_eod", h.get("pnl_usd", 0))) for h in prior
    )
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
    for row in state.get("intraday_floor_exits") or []:
        if row.get("trading_day") != day_str:
            continue
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        merged.insert(
            0,
            {
                **row,
                "symbol": symbol,
                "exit_reason": row.get("exit_reason", "floor_price"),
                "intraday_exit": True,
                "manual_exit": bool(row.get("manual_exit")),
            },
        )
    return merged


def _booked_exits_summary(
    state: dict[str, Any],
    trading_day: date,
) -> tuple[float, float]:
    """PnL already applied to equity before the EOD simulation runs."""
    rows = [
        row
        for row in (state.get("intraday_floor_exits") or [])
        if row.get("trading_day") == trading_day.isoformat()
    ]
    return (
        round(sum(float(row.get("pnl_usd", 0)) for row in rows), 2),
        round(sum(float(row.get("fees_usd", 0)) for row in rows), 2),
    )


def run_entry_simulation(
    cfg: AgentConfig,
    state: dict[str, Any],
    trading_day: date,
) -> list[dict[str, Any]]:
    """Morning job: open approved positions at market open price."""
    from trading_pulse.agent.positions import simulate_swing_day
    from trading_pulse.agent.trading_flow import entries_already_run, mark_entries_executed

    path = plan_path(trading_day)
    if not path.exists():
        return []
    plan = read_json(path)
    if entries_already_run(plan, trading_day):
        logging.info("Entry simulation skipped for %s: already executed", trading_day.isoformat())
        return []
    ensure_plan_allocation(cfg, plan, state, trading_day)
    plan = read_json(path)
    approved = [x for x in plan.get("recommendations", []) if x.get("approved")]
    if not approved:
        return []

    held_before = {str(p["symbol"]) for p in state.get("open_positions", [])}
    _, still_open, pnl_total, _fees = simulate_swing_day(
        cfg, state, trading_day, approved, entries_only=True
    )
    from datetime import datetime, time

    from trading_pulse.core.schedule_tz import UTC

    hour, minute = (int(x) for x in str(getattr(cfg, "entry_sim_time", "13:35")).split(":"))
    entry_at = datetime.combine(trading_day, time(hour, minute), tzinfo=UTC).isoformat()
    for pos in state.get("open_positions", []):
        if str(pos["symbol"]) not in held_before and pos.get("entry_day") == trading_day.isoformat():
            pos["entry_at"] = entry_at
    state["equity"] = round(float(state["equity"]) + pnl_total, 2)
    save_json(STATE_FILE, state)

    new_entries: list[dict[str, Any]] = []
    rec_by_sym = {str(r.get("symbol")): r for r in approved}
    for pos in still_open:
        if str(pos["symbol"]) not in held_before and pos.get("entry_day") == trading_day.isoformat():
            rec = rec_by_sym.get(str(pos["symbol"])) or {}
            if "entry_ref_price" not in pos:
                ref = rec.get("entry_ref_price") or rec.get("method2_entry_ref")
                if ref:
                    pos["entry_ref_price"] = float(ref)
            new_entries.append(pos)

    from trading_pulse.agent.method2_intraday import stamp_method2_after_morning
    from trading_pulse.agent.plan_engine import mark_executed, refresh_stale_draft_plan

    pending_m2 = stamp_method2_after_morning(plan, state, trading_day)
    # Mark executed when anything filled OR method2 is waiting / resolved
    if new_entries or pending_m2 or any(
        str(r.get("method2_status") or "") in {"filled", "invalidated"} for r in approved
    ):
        mark_executed(plan, trading_day, cfg=cfg)
        refresh_stale_draft_plan(cfg, state, trading_day)
    save_json(path, plan)
    return new_entries


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
    ensure_plan_allocation(cfg, plan, state, trading_day, purpose="eod")
    plan = read_json(path)
    approved = [x for x in plan.get("recommendations", []) if x.get("approved")]

    if getattr(cfg, "hold_mode", "swing") == "swing":
        from trading_pulse.agent.positions import enrich_held_unrealized, simulate_swing_day

        equity_before = float(state["equity"])
        daily_loss_limit = equity_before * cfg.max_daily_loss_pct
        from trading_pulse.agent.trading_flow import entries_already_run

        skip_entries = entries_already_run(plan, trading_day)
        executed, held_eod, pnl_total, fees_total = simulate_swing_day(
            cfg, state, trading_day, approved, eod_only=skip_entries
        )
        booked_pnl, booked_fees = _booked_exits_summary(state, trading_day)
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

        day_pnl_total = round(pnl_total + booked_pnl, 2)
        day_fees_total = round(fees_total + booked_fees, 2)
        equity_after = equity_before + pnl_total
        report_equity_before = equity_after - day_pnl_total
        held_eod, unrealized_pnl_usd = enrich_held_unrealized(held_eod, trading_day)
        report = {
            "trading_day": trading_day.isoformat(),
            "executed": executed,
            "held_eod": held_eod,
            "pnl_usd": day_pnl_total,
            "pnl_applied_at_eod": round(pnl_total, 2),
            "fees_usd": day_fees_total,
            "unrealized_pnl_usd": unrealized_pnl_usd,
            "equity_marked_usd": round(equity_after + unrealized_pnl_usd, 2),
            "equity_before": round(report_equity_before, 2),
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
    try:
        from trading_pulse.agent.plan_engine import mark_closed

        plan = read_json(plan_path(trading_day))
        mark_closed(plan)
        save_json(plan_path(trading_day), plan)
    except OSError:
        pass
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
    send_report_notifications(cfg, report)


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


def cmd_build_watchlist(args: argparse.Namespace) -> None:
    from trading_pulse.agent.weekly_watchlist import build_weekly_watchlist

    ensure_dirs()
    setup_logger(scheduler_log_file())
    cfg = load_config()
    size = getattr(args, "size", None)
    notify = bool(getattr(args, "notify", False))
    result = build_weekly_watchlist(cfg, target_size=size)
    print(json.dumps({k: v for k, v in result.items() if k != "symbols"}, indent=2, ensure_ascii=False))
    print("symbols:", ", ".join(result["symbols"]))
    if notify:
        send_weekly_watchlist_notification(cfg, result)


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
    from trading_pulse.core.schedule_tz import (
        schedule_daily_at,
        schedule_weekday_at,
        us_trading_session_date,
    )

    if not acquire_instance_lock("scheduler" if not service else "app-scheduler"):
        return

    ensure_dirs()
    log_file = scheduler_log_file() if service else None
    setup_logger(log_file)
    cfg = load_config()

    def run_plan_job() -> None:
        today = us_trading_session_date()
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

    def run_entry_job() -> None:
        today = us_trading_session_date()
        if not should_run_simulation_today(today):
            record_job("entry", "skipped", f"today={today.isoformat()}")
            return
        logging.info("JOB START: market entry")
        try:
            state = load_state(cfg)
            entries = run_entry_simulation(cfg, state, today)

            path = plan_path(today)
            pending_m2: list[str] = []
            if path.exists():
                plan = read_json(path)
                pending_m2 = [
                    str(r["symbol"])
                    for r in plan.get("recommendations") or []
                    if str(r.get("method2_status") or "") == "pending_breakout"
                ]
            if not entries and not pending_m2:
                from trading_pulse.telegram.telegram_format import format_no_entries_morning

                send_user_notification(
                    cfg,
                    format_no_entries_morning(trading_day=today.isoformat()),
                    context="entry",
                    parse_mode="HTML",
                )
                record_job("entry", "ok", f"no new entries; day={today.isoformat()}")
                logging.info("JOB END: market entry (nothing to open for %s — notified)", today.isoformat())
                return
            send_entry_notifications(
                cfg,
                entries,
                trading_day=today.isoformat(),
                pending_method2=pending_m2 or None,
                context="entry",
            )
            record_job(
                "entry",
                "ok",
                trading_day=today.isoformat(),
                count=len(entries),
                method2_pending=len(pending_m2),
            )
            logging.info(
                "JOB END: market entry (%d position(s), %d method2 pending)",
                len(entries),
                len(pending_m2),
            )
        except Exception as ex:
            record_job("entry", "failed", str(ex))
            logging.exception("JOB FAILED: market entry: %s", ex)

    def _clear_price_watches_eod() -> None:
        """Drop hourly watches at end of the trading-day job."""
        from trading_pulse.agent.price_watch import clear_all_price_watches, format_watches_cleared

        try:
            state = load_state(cfg)
            cleared = clear_all_price_watches(state)
            if not cleared:
                return
            save_json(STATE_FILE, state)
            msg = format_watches_cleared(cleared)
            if msg:
                send_user_notification(cfg, msg, context="price_watch:eod_clear", parse_mode="HTML")
            logging.info("Cleared %d price watch(es) at EOD: %s", len(cleared), ", ".join(cleared))
        except Exception as ex:
            logging.warning("EOD price-watch clear failed: %s", ex)

    def run_sim_job() -> None:
        today = us_trading_session_date()
        if not should_run_simulation_today(today):
            record_job("simulation", "skipped", f"today={today.isoformat()}")
            logging.info(
                "JOB SKIP: daily simulation (market closed or no plan; today=%s)",
                today.isoformat(),
            )
            # Do NOT clear watches on non-session days — שיטה 2 watches are
            # often attached Sunday evening for Monday's pending breakout.
            return
        logging.info("JOB START: daily simulation")
        try:
            state = load_state(cfg)
            report = simulate_day(cfg, state, today)
            if report.get("_skipped"):
                record_job("simulation", "skipped", f"already done; day={today.isoformat()}")
                logging.info("JOB SKIP: daily simulation (already completed for %s)", today)
                _clear_price_watches_eod()
                return
            logging.info(
                "Simulation done for %s | PnL $%s | equity $%s -> $%s",
                report["trading_day"],
                report["pnl_usd"],
                report["equity_before"],
                report["equity_after"],
            )
            send_report_notifications(cfg, report)
            record_job("simulation", "ok", trading_day=report["trading_day"], pnl=report["pnl_usd"])
            logging.info("JOB END: daily simulation")
        except Exception as ex:
            record_job("simulation", "failed", str(ex))
            logging.exception("JOB FAILED: daily simulation: %s", ex)
        finally:
            try:
                from trading_pulse.agent.method2_intraday import expire_method2_pending

                path = plan_path(today)
                if path.exists():
                    plan = read_json(path)
                    n_exp = expire_method2_pending(plan)
                    if n_exp:
                        save_json(path, plan)
                        logging.info("Expired %d method2 pending breakout(s)", n_exp)
            except Exception as ex:
                logging.debug("Method2 expire skipped: %s", ex)
            _clear_price_watches_eod()

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

        today = us_trading_session_date()
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
        from trading_pulse.agent.price_watch import send_price_watch_updates

        active_cfg = load_config()
        if not active_cfg.intraday_check_enabled:
            return
        today = us_trading_session_date()
        if not is_us_trading_day(today):
            return
        logging.info("JOB START: intraday check")
        try:
            state = load_state(active_cfg)
            sent = run_intraday_check(active_cfg, state)
            watch_sent = send_price_watch_updates(active_cfg, state)
            if sent or watch_sent:
                record_job(
                    "intraday_check",
                    "ok",
                    f"day={today.isoformat()} watches={watch_sent}",
                )
                logging.info(
                    "JOB END: intraday check (alerts=%s watches=%s)",
                    bool(sent),
                    watch_sent,
                )
            else:
                record_job("intraday_check", "skipped", "nothing noteworthy")
                logging.info("JOB END: intraday check (quiet)")
        except Exception as ex:
            record_job("intraday_check", "failed", str(ex))
            logging.exception("JOB FAILED: intraday check: %s", ex)

    schedule_daily_at(cfg.planning_time).do(run_plan_job)
    schedule_daily_at(cfg.entry_sim_time).do(run_entry_job)
    schedule_daily_at(cfg.market_close_sim_time).do(run_sim_job)
    schedule_daily_at(cfg.heartbeat_time).do(run_heartbeat_job)
    def run_weekly_scan_job() -> None:
        active_cfg = load_config()
        if not bool(getattr(active_cfg, "weekly_scan_enabled", True)):
            return
        logging.info("JOB START: weekly watchlist scan")
        try:
            from trading_pulse.agent.weekly_watchlist import build_weekly_watchlist

            result = build_weekly_watchlist(active_cfg)
            record_job("weekly_scan", "ok", f"{result['selected']} symbols")
            send_weekly_watchlist_notification(active_cfg, result)
            logging.info("JOB END: weekly watchlist scan (%d symbols)", result["selected"])
        except Exception as ex:
            record_job("weekly_scan", "failed", str(ex))
            logging.exception("JOB FAILED: weekly watchlist scan: %s", ex)

    schedule_daily_at(cfg.plan_reminder_time).do(run_plan_reminder_job)
    if bool(getattr(cfg, "weekly_scan_enabled", True)):
        _day = str(getattr(cfg, "weekly_scan_day", "sunday")).lower()
        _weekly = schedule_weekday_at(_day, cfg.weekly_scan_time)
        if _weekly is not None:
            _weekly.do(run_weekly_scan_job)
            logging.info("  weekly scan: %s at %s UTC", _day, cfg.weekly_scan_time)
        else:
            logging.warning("Unknown weekly_scan_day '%s' — weekly scan not scheduled", _day)
    cfg_holder: dict[str, AgentConfig] = {"cfg": cfg}

    def run_telegram_poll_job() -> None:
        try:
            handled = process_telegram_commands(cfg_holder["cfg"])
            if handled:
                record_job("telegram_poll", "ok", f"{handled} command(s)")
                logging.info("JOB DONE: telegram poll (%d command(s))", handled)
        except requests.exceptions.Timeout as ex:
            from trading_pulse.core.log_redact import redact_secrets

            logging.warning("Telegram poll timeout (will retry): %s", redact_secrets(ex))
            record_job("telegram_poll", "skipped", "timeout — will retry")
        except requests.exceptions.RequestException as ex:
            from trading_pulse.core.log_redact import redact_secrets

            logging.warning("Telegram poll network error (will retry): %s", redact_secrets(ex))
            record_job("telegram_poll", "skipped", f"network: {redact_secrets(ex)}")
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
    logging.info("  heartbeat: %s UTC", cfg.heartbeat_time)
    logging.info("  plan: %s UTC (~ after US close)", cfg.planning_time)
    logging.info("  entry: %s UTC (~ US market open)", cfg.entry_sim_time)
    logging.info("  report: %s UTC (~ US close)", cfg.market_close_sim_time)
    logging.info("  plan reminder: %s UTC", cfg.plan_reminder_time)
    logging.info("  simulation report: %s UTC", cfg.market_close_sim_time)
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

    watchlist_cmd = sub.add_parser("build-watchlist", help="Weekly scan: build the trading watchlist")
    watchlist_cmd.add_argument("--size", type=int, default=None, help="How many symbols to keep")
    watchlist_cmd.add_argument("--notify", action="store_true", help="Send summary to Telegram")
    watchlist_cmd.set_defaults(func=cmd_build_watchlist)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
