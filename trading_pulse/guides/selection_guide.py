"""How stock recommendations are selected — dashboard guide content."""

from __future__ import annotations

from typing import Any

from trading_pulse.agent.signal_sources import SOURCE_LABELS

RISK_PROFILE_LABELS = {
    "conservative": "שמרני",
    "balanced": "מאוזן",
    "aggressive": "אגרסיבי",
    "speculative": "ספקולטיבי",
}

STRATEGY_MODE_LABELS = {
    "balanced_mix": "משולב מאוזן",
    "score_only": "מומנטום וציון בלבד",
    "rising_three_only": "Rising Three בלבד",
    "method2_only": "נרות סיניים 2 בלבד",
}


def _intraday_selection_block(cfg: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(cfg.get("intraday_check_enabled", True))
    interval = int(cfg.get("intraday_check_interval_minutes", 60))
    open_t = str(cfg.get("market_open_sim_time", "13:30"))
    close_t = str(cfg.get("market_close_sim_time", "20:20"))
    if not enabled:
        return {
            "enabled": False,
            "title": "מעקב במהלך יום המסחר",
            "detail": "כבוי (intraday_check_enabled=false). ניתן להפעיל בהגדרות #/settings",
        }
    hours = interval // 60 if interval % 60 == 0 else None
    freq = f"כל {hours} שעות" if hours and hours > 1 else ("כל שעה" if interval == 60 else f"כל {interval} דקות")
    return {
        "enabled": True,
        "title": "מעקב במהלך יום המסחר",
        "detail": (
            f"בין {open_t} ל-{close_t} UTC ({freq}) נשלחת תמונת PNG "
            "(כיתוב קצר «מעקב שעתי») כשיש מה לדווח — טבלת HTML עם כותרות עבריות לכל מספר "
            "(מושקע, מחיר, רף יציאה, שווי, מהכניסה, היום, רווח). "
            "אחוזים ודולרים חתומים: -3.5% / -$4.00 (מינוס לפני המספר). "
            "יציאות רף, חריגות וצ׳יפים להצעות (פקודה להעתקה) בתוך התמונה. "
            "אם יצירת התמונה נכשלת — נשלח טקסט HTML כגיבוי. "
            "לא מציע לקנות מניות שמסומנות למכירה/החלפה בתוכנית, ב-cooldown, או שנסגרו היום. "
            "הגדרות: #/settings."
        ),
        "interval_minutes": interval,
        "window": f"{open_t}–{close_t}",
    }


def get_selection_guide(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    risk = str(cfg.get("risk_profile", "speculative"))
    speculative = risk == "speculative"
    strategy_mode = str(cfg.get("strategy_mode", "balanced_mix"))
    strategy_mode_label = STRATEGY_MODE_LABELS.get(strategy_mode, STRATEGY_MODE_LABELS["balanced_mix"])
    signal_sources = cfg.get("signal_sources") or []
    tickers = cfg.get("tickers") or []

    source_rows = [
        {
            "id": sid,
            "label": SOURCE_LABELS.get(sid, sid),
            "weight": float((cfg.get("source_weights") or {}).get(sid, 0.5)),
        }
        for sid in signal_sources
    ]

    deploy_n = int(cfg.get("initial_deploy_stocks", 3))
    review_t = str(cfg.get("portfolio_review_time", "15:00"))
    entry_t = str(cfg.get("entry_sim_time", "13:35"))
    close_t = str(cfg.get("market_close_sim_time", "20:20"))
    topup_min = float(cfg.get("intraday_cash_topup_min_usd", 20) or 20)
    from trading_pulse.core.schedule_tz import format_dual_time, format_dual_time_from_israel

    review_dual = format_dual_time_from_israel(review_t)
    entry_dual = format_dual_time(entry_t)
    close_dual = format_dual_time(close_t)
    max_trades = int(cfg.get("max_trades_per_day", 3))

    user_flow = [
        {
            "step": "א",
            "title": "לפני הפתיחה — סקירה + הצעות",
            "detail": (
                f"~{review_dual}: תיק ריק — סריקת שוק מלאה ואז הצעת קנייה אחת-אחת "
                "(גרף PNG → כרטיס קוביות מדדים + איך לבצע: כן/קנה ממזומן, "
                "או החלף/מכור עם סימבולים מהתיק — לא SYMBOL); "
                "עונים כן / קנה / סכום / החלף כמו בכרטיס / דלג ועוברים להצעה הבאה. "
                "«החלף AMZN TSLL» כש־TSLL היא ההצעה = אישור (מוכר עכשיו · מאשר קנייה בפתיחה) "
                "ועוברים הלאה — בלי כן/דלג ובלי «שלב 2 — חלוקת הון». "
                "תיק לא ריק — תמונת קוביות «סקירת תיק» (לכל החזקה: הון · PnL% · ציון · המלצה) "
                "+ רצועת פעולה קצרה; החלפה לפי ציון (~2+ נקודות) גם בירוק "
                "(אלא אם ממש רווח / קרוב לרצפה) — ואז אותו סבב הצעות אם יש מקום. "
                "בלי תשובה כ-10 דקות — תזכורת עדינה אחת. הפקודות הרגילות (מכור, קנה, תיק) עובדות תמיד."
            ),
        },
        {
            "step": "ב",
            "title": "בוקר — כניסה",
            "detail": (
                f"~{entry_dual}: קנייה במחיר פתיחה למניות שאושרו — רק אם נשאר מזומן פנוי; "
                "בלי מזומן הקנייה נדלגת (אין קנייה שנייה «בקסם»). "
                "תמונת טבלת HTML (# · סימול · שיטת כניסה · סכום · מחיר; HTML טקסט רק אם התמונה נכשלת). "
                "אם סבב ההצעות לא נגמר עד אז — מה שכבר אושר (גם ב־החלף) נשאר לפתיחה; "
                "רק «לא נענו» יורדים להיום."
            ),
        },
        {
            "step": "ג",
            "title": "ערב — דוח",
            "detail": (
                f"~{close_dual}: תמונת טבלאות HTML אחת "
                "(סיכום הון + מוחזקות/מכירות); "
                "רווח ממומש + רווח עתידי בפורמט -3.5% / -$4.00. "
                "אם האפליקציה/המתזמן היה תקוע — הדוח מדלג עד שהאפליקציה בריאה שוב."
            ),
        },
        {
            "step": "ד",
            "title": "לאורך יום המסחר — מעקב שעתי",
            "detail": (
                "שינוי חד במניה מוחזקת, הצעת מכירה/החלפה, ואם אין מקום לפוזיציה חדשה "
                f"אבל יש ≥${topup_min:.0f} מזומן פנוי — הצעה לחזק החזקה קיימת (תקנה SYMBOL)."
            ),
        },
    ]

    return {
        "title": "איך בוחרים מניות?",
        "subtitle": "סקירה אוטומטית לפני הפתיחה — אתה מאשר הצעה-הצעה בטלגרם או בדשבורד",
        "disclaimer": (
            "זה Dry Run לצורכי למידה וסימולציה בלבד. "
            "אין כאן ייעוץ השקעות ואין הבטחה לרווח."
        ),
        "user_flow": user_flow,
        "pipeline": [
            {
                "step": 0,
                "title": "סריקה שבועית (יקום גדול)",
                "detail": (
                    "בסוף השבוע (או בפקודה סריקה שבועית) נסרקות כ־420 מניות/ETF. "
                    "דירוג: מומנטום + תנודתיות (ATR) + נפח"
                    + (
                        " + אותות מהאסטרטגיות הפעילות "
                        "(Rising Three, נרות סיניים 2, ואם הופעלו — גם ניסיוניות)."
                        if cfg.get("weekly_strategy_rank_enabled", True)
                        else " (דירוג אסטרטגיה כבוי)."
                    )
                    + f" נשמרות {int(cfg.get('weekly_watchlist_size', 60))} הראשונות "
                    "לרשימת המסחר היומית. "
                    "בטלגרם: תמונת טבלת HTML (נסרקו / נבחרו / דירוג / שיטות) · "
                    "Top 10 כטבלה · דוגמאות עריכה (הוסף / הסר / מניות) · "
                    "ועוד N ברשימה המלאה (דשבורד או מניות). "
                    "סריקה אוטומטית: יום ראשון ~09:00 ישראל. "
                    "הגדרות (#/settings · לוח זמנים): "
                    "weekly_scan_enabled · weekly_watchlist_size · weekly_strategy_rank_enabled."
                ),
            },

            {
                "step": 1,
                "title": "סריקת רשימת מניות",
                "detail": (
                    f"בכל יום מסחר, לפני הפתיחה (~{review_dual}) נסרקות "
                    f"{len(tickers)} מניות/ETF מהרשימה השבועית (או כל הרשימה השבועית עצמה — תיק ריק). "
                    "עריכה ידנית: הוסף / הסר · חפש מניות מוסיף עד 3 (לא מחליף את הסריקה השבועית)."
                ),
            },
            {
                "step": 2,
                "title": "איסוף אותות ממקורות",
                "detail": (
                    f"לכל מניה נשלפת תשובה מ-{len(signal_sources)} מקורות לפחות "
                    f"(מינימום {cfg.get('min_signal_sources', 3)}). "
                    "מניה בלי מספיק מקורות — נפסלת."
                ),
            },
            {
                "step": 3,
                "title": "סינון איכות",
                "detail": (
                    f"נפח ≥ {cfg.get('min_volume_ratio', 1.3)}× ממוצע · "
                    f"ציון מינימום {cfg.get('min_entry_score', 10)} · "
                    f"{'פסילה כשמקורות לא מסכימים' if cfg.get('exclude_on_source_disagreement') else 'קנס על חוסר הסכמה'}. "
                    f"מניה שהפסידה — cooldown {cfg.get('symbol_cooldown_days_after_loss', 5)} ימים. "
                    f"ETF ממונף 3x — מקסימום {cfg.get('max_leveraged_etf_positions', 1)} בתוכנית."
                ),
            },
            {
                "step": 4,
                "title": "סינון בסיסי",
                "detail": (
                    f"מחיר מעל ${cfg.get('min_price_usd', 5)} · "
                    f"נזילות ממוצעת 20 יום מעל {int(cfg.get('min_avg_volume_20d', 0)):,} מניות. "
                    "מניות שכבר מוחזקות בתיק — לא מוצעות שוב לכניסה."
                ),
            },
            {
                "step": 5,
                "title": "הרצת מצב האסטרטגיה",
                "detail": (
                    f"בהגדרות נבחר כרגע ״{strategy_mode_label}״. "
                    "אפשר לבחור גם מומנטום וציון בלבד, Rising Three בלבד או נרות סיניים 2 בלבד. "
                    "VCP מחפשת התכווצות בתנודתיות ובנפח ואחריה פריצה מאושרת; "
                    "חוזק יחסי מחפש מגמה עולה וביצועי יתר מול SPY בשלושה חודשים ובחודש האחרון. "
                    "שתיהן הרחבות ניסיוניות וכבויות כברירת מחדל. "
                    "נרות סיניים 2 נכנסת רק בפריצה, לא אוטומטית בפתיחה. "
                    "שורט בנרות סיניים 2: רווח כשהמחיר יורד. "
                    "מעקב מחיר לנרות סיניים 2 שקט יותר ומציג מרחק לפריצה; "
                    "נעצר אחרי מכירה או כשהפוזיציה נעלמת."
                ),
            },

            {
                "step": 6,
                "title": "שילוב, דירוג ומגבלות תיק",
                "detail": (
                    "במצב משולב, אותות כפולים לא יוצרים שתי פוזיציות: "
                    "הסכמה על אותה מניה מקבלת עדיפות והכרטיס מציג אילו אסטרטגיות תמכו בה. "
                    f"נבחרות עד {max_trades} כניסות עיקריות ליום ועד "
                    f"{cfg.get('max_open_positions', 5)} פוזיציות, בכפוף למזומן ולסיכון. "
                    f"בתיק ריק אפשר לפרוס את ההון על עד {deploy_n} מניות."
                ),
            },
            {
                "step": 7,
                "title": "אישור שלך — הצעה אחת בכל פעם",
                "detail": (
                    "בטלגרם לכל מניה: (1) גרף PNG (כולל שורת «שיטת כניסה» + בפתיחה/בפריצה), "
                    "(2) כרטיס קוביות אחד «הצעה N/M» — מדדים "
                    "(שיטת כניסה · ציון ותנודתיות · מומנטום ומחיר · נפח · חדשות ומקורות · בדיקה לאחור) "
                    "+ מזומן וקנייה · החלפה מומלצת אם רלוונטי · איך לבצע — בלי הודעת פעולה נפרדת. "
                    "ב«איך לבצע»: כן / קנה ממזומן, או פקודות עם סימבולים אמיתיים מהתיק "
                    "(למשל החלף AMZN TSLL · מכור AMZN) — לא המילה SYMBOL. "
                    "או בדשבורד (#/plan) — עונים כן / קנה (בסכום המומלץ) / סכום מדויק / "
                    "החלף כמו בכרטיס / דלג. "
                    "כל הצעה מושווית להחזקות: יש מזומן — קנייה ממזומן ו/או החלפת החזקה חלשה; "
                    "מזומן $0 — מימון רק בהחלף/מכור עם סימבולים אמיתיים מהתיק "
                    "(לא SYMBOL) כשהציון ברור (~2+), או דלג. "
                    "«כן» בלי מזומן מציע החלף עם סימבולים מהתיק במקום לאשר $0. "
                    "אישור כמה הצעות ממזומן: כל אישור מוריד מהמזומן — "
                    "אי אפשר לבזבז את אותו מזומן פעמיים. "
                    "«החלף AMZN TSLL» על ההצעה הנוכחית = אישור ועוברים הלאה "
                    "(מוכר עכשיו · אושרה לקנייה בפתיחה — בלי חלוקת הון ח1…ח5). "
                    "אחרי כל ההצעות: סיכום «עברנו על כל ההמלצות» עם מה שנקנה; כניסה לשוק — ישראל קודם "
                    "(‎16:35‎ ישראל). "
                    "הסכום שנבחר בכל הצעה = מה שנקנה בפועל (לא חלוקה שווה אוטומטית). "
                    "יום ראשון (תיק ריק): הסכום המומלץ מתחלק שווה בשווה בין ההצעות שנשארו. "
                    "הצעות החלפה בסקירה מוגבלות (עד ~2) — בלי כמה פעמים לאותה מניית יעד. "
                    "יש מזומן פנוי: אפשר גם להוסיף למניה שכבר בתיק עם תקנה "
                    "(בלי סכום = כל המזומן; עם $N = סכום מדויק) — "
                    "שכבת קנייה נפרדת (רווח לפי שכבה; מחיר כניסה = ממוצע משוקלל)."
                ),
            },
        ],
        "intraday": _intraday_selection_block(cfg),
        "strategy": {
            "profile": risk,
            "profile_label": RISK_PROFILE_LABELS.get(risk, risk),
            "mode": strategy_mode,
            "mode_title": f"מצב בחירה: {strategy_mode_label}",
            "scoring": (
                [
                    "ATR% — תנודתיות יומית (יותר גבוה = ציון גבוה יותר)",
                    "יחס נפח (vol ratio) מול ממוצע 20 יום",
                    "קרבה לשיא 20 יום / פריצה",
                    "תשואה ב-5 ימים האחרונים",
                ]
                if speculative
                else [
                    "מעל MA20 — מגמה חיובית",
                    "יחס נפח מול ממוצע",
                    "תשואה ב-5 ימים האחרונים",
                ]
            ),
            "must_pass": (
                "הסינון בפועל תלוי במצב האסטרטגיה; כל בחירה עדיין כפופה למגבלות הון וסיכון."
            ),
            "stops": (
                f"מחיר תחתון -{int(float(cfg.get('stop_loss_pct', 0.12)) * 100)}% (מכירה אוטומטית) · "
                f"יעד +{int(float(cfg.get('take_profit_pct', 0.25)) * 100)}%"
            ),
            "hold": (
                f"מצב {cfg.get('hold_mode', 'swing')} · "
                f"עד {cfg.get('max_hold_days', 5)} ימי החזקה"
            ),
        },
        "sources": {
            "items": source_rows,
            "disagreement": (
                f"אם מקורות לא מסכימים (פער std ≥ {cfg.get('max_source_score_std', 4.5)} "
                f"או spread ≥ {cfg.get('max_source_score_spread', 9)}): "
                + (
                    "המניה נפסלת."
                    if cfg.get("exclude_on_source_disagreement")
                    else f"הציון מוכפל ב-{cfg.get('disagreement_score_penalty', 0.75)} (קנס)."
                )
            ),
        },
        "enrichment": [
            {
                "icon": "🧩",
                "title": "מצב משולב והסכמה",
                "detail": (
                    "משולב מאוזן הוא ברירת המחדל. כשכמה אסטרטגיות מזהות אותה מניה, "
                    "היא נשארת פוזיציה אחת, מקבלת עדיפות ומוצג למה נבחרה."
                ),
            },
            {
                "icon": "🧪",
                "title": "אפשרויות ניסיוניות",
                "detail": (
                    "VCP, חוזק יחסי, Trend Pullback ומסנן מצב שוק לפי SPY/QQQ "
                    "כבויים כברירת מחדל. אפשר להפעיל בהגדרות › מסחר וסיכון; "
                    "הם ניסיוניים ואינם מבטיחים תוצאה."
                ),
            },
            {
                "icon": "📰",
                "title": "חדשות",
                "detail": (
                    f"עד {cfg.get('news_headlines_count', 3)} כותרות מ-"
                    f"{', '.join(cfg.get('news_sources') or ['yahoo', 'google', 'finviz'])}. "
                    "מילות מפתח חיוביות/שליליות מזיזות את הציון."
                ),
            },
            {
                "icon": "📊",
                "title": "בדיקת עבר",
                "detail": (
                    f"סימולציה על {cfg.get('backtest_days', 90)} ימים אחורה עם אותם סטופ/יעד — "
                    "win rate וממוצע לעסקה מופיעים בהסבר המניה. "
                    "בדיקת walk-forward לתיק מדמה כמה ימי מסחר, פוזיציות ומגבלות סיכון; "
                    "זו סימולציה בלבד, ללא חיבור לברוקר."
                ),
            },
            {
                "icon": "📈",
                "title": "ביצועי אסטרטגיות (shadow)",
                "detail": (
                    "הדוח בהגדרות מרכז אותות ותוצאות סגורות לפי אסטרטגיה, "
                    "כולל VCP וחוזק יחסי כשהן פעילות. "
                    "משווים רק אחרי 20–30 עסקאות סגורות ולפחות 4–6 שבועות."
                ),
            },
            {
                "icon": "🧮",
                "title": "דירוג סופי",
                "detail": "אחרי חדשות — מיון מחדש לפי ציון סופי. רק הראשונות נכנסות לתוכנית.",
            },
        ],
        "limits": [
            {
                "label": "הון פנוי",
                "value": "רק מה שלא מושקע בפוזיציות פתוחות",
            },
            {
                "label": "יום ראשון",
                "value": f"{deploy_n} מניות — חלוקה שווה אחרי הכל",
            },
            {
                "label": "גודל פוזיציה",
                "value": f"עד {int(float(cfg.get('max_position_pct', 0.34)) * 100)}% מההון לכניסה",
            },
            {
                "label": "הפסד יומי מקס",
                "value": f"{int(float(cfg.get('max_daily_loss_pct', 0.5)) * 100)}% מההון — מגבלת סיכון",
            },
            {
                "label": "עמלות בסימולציה",
                "value": f"${cfg.get('commission_per_side_usd', 1)} לצד",
            },
        ],
        "tickers_preview": tickers[:12],
        "tickers_total": len(tickers),
    }


def format_selection_guide_messages(cfg: dict[str, Any] | None = None) -> list[str]:
    """Stock selection guide as one or more HTML messages."""
    from trading_pulse.telegram.telegram_format import chunk_telegram_html, escape_html

    g = get_selection_guide(cfg)
    parts: list[str] = []

    parts.append(
        "\n".join(
            [
                f"<b>🔍 {escape_html(g['title'])}</b>",
                f"<i>{escape_html(g['subtitle'])}</i>",
                f"<i>{escape_html(g['disclaimer'])}</i>",
            ]
        )
    )

    pipe_lines = ["<b>📋 תהליך הבחירה</b>"]
    user_flow = g.get("user_flow") or []
    if user_flow:
        pipe_lines.append("<b>זרימה למשתמש</b>")
        for step in user_flow:
            pipe_lines.append(
                f"<b>{step['step']}. {escape_html(step['title'])}</b> — {escape_html(step['detail'])}"
            )
        pipe_lines.append("")
    for step in g["pipeline"]:
        pipe_lines.append(
            f"<b>{step['step']}. {escape_html(step['title'])}</b>\n{escape_html(step['detail'])}"
        )
    parts.append("\n".join(pipe_lines))

    intraday = g.get("intraday") or {}
    if intraday.get("title"):
        parts.append(
            "\n".join(
                [
                    f"<b>🔍 {escape_html(intraday['title'])}</b>",
                    escape_html(intraday.get("detail", "")),
                ]
            )
        )

    strat = g["strategy"]
    strat_lines = [
        f"<b>🎯 אסטרטגיה — {escape_html(strat['profile_label'])}</b>",
        escape_html(strat["mode_title"]),
        "<b>ציון לפי:</b>",
    ]
    for row in strat["scoring"]:
        strat_lines.append(f"• {escape_html(row)}")
    strat_lines.extend(
        [
            f"<b>חובה:</b> {escape_html(strat['must_pass'])}",
            f"<b>סטופ/יעד:</b> {escape_html(strat['stops'])}",
            f"<b>החזקה:</b> {escape_html(strat['hold'])}",
        ]
    )
    parts.append("\n".join(strat_lines))

    src_lines = ["<b>📡 מקורות אותות</b>"]
    for item in g["sources"]["items"]:
        src_lines.append(
            f"• {escape_html(item['label'])} — משקל {item['weight']:.2f}"
        )
    src_lines.append(escape_html(g["sources"]["disagreement"]))
    parts.append("\n".join(src_lines))

    enrich_lines = ["<b>➕ העשרה לפני דירוג סופי</b>"]
    for item in g["enrichment"]:
        enrich_lines.append(
            f"{item['icon']} <b>{escape_html(item['title'])}</b> — {escape_html(item['detail'])}"
        )
    parts.append("\n".join(enrich_lines))

    lim_lines = ["<b>💰 מגבלות הון</b>"]
    for row in g["limits"]:
        lim_lines.append(f"• <b>{escape_html(row['label'])}:</b> {escape_html(row['value'])}")
    preview = g["tickers_preview"]
    if preview:
        more = g["tickers_total"] - len(preview)
        tickers_str = ", ".join(escape_html(t) for t in preview)
        if more > 0:
            tickers_str += f" … +{more}"
        lim_lines.append(f"<b>רשימת סריקה ({g['tickers_total']}):</b> {tickers_str}")
    lim_lines.append(
        "<i>עדכון רשימה: <code>מניות</code> · <code>סריקה שבועית</code> · "
        "<code>הוסף SYM</code> · <code>חפש מניות</code></i>"
    )
    parts.append("\n".join(lim_lines))

    return chunk_telegram_html(parts)
