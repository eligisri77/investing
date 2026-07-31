// Public, static demo of Trading Pulse's guide pages.
//
// This is a snapshot rendered from `instance/config.example.json` (generic
// example settings) via `scripts/build_public_guides.py` — there is no live
// server, no financial data, and no connection whatsoever to anyone's actual
// running app, PC, or Telegram bot. It exists purely so visitors can see how
// the app explains itself. Regenerate + commit `docs/data/*.json` and
// `docs/style.css` after changing the guide content or example config.

const app = document.getElementById("app");
const nav = document.getElementById("nav");
// Resolve data/*.json under /investing/ even when currentScript is unavailable
// (some mobile browsers) or the URL is /investing without a trailing slash.
const ASSET_BASE = (() => {
  const fromScript = document.currentScript?.src;
  if (fromScript) return new URL(".", fromScript).href;
  return `${location.origin}/investing/`;
})();

async function fetchJson(url) {
  const res = await fetch(new URL(url, ASSET_BASE));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function fmtUsd(n, { signed = false } = {}) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  const body = `$${Math.abs(v).toFixed(v % 1 === 0 ? 0 : 2)}`;
  if (!signed) return body;
  if (v > 0) return `+${body}`;
  if (v < 0) return `-${body}`;
  return body;
}

function fmtPct(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}${Math.abs(v).toFixed(1)}%`;
}

const DEMO_BANNER = `
  <div class="guide-note" style="margin-bottom:1.25rem">
    👁 הדגמה ציבורית וסטטית בלבד (לא התיק החי) — תוכן גנרי מהגדרות דוגמה,
    בלי חיבור לאף מכשיר/חשבון/תיק אמיתי.
    <a href="https://github.com/eligisri77/investing" style="color:var(--cyan)">קוד המקור וההתקנה ב-GitHub</a>
  </div>`;

const ROUTES = [
  { hash: "#/", label: "דשבורד" },
  { hash: "#/portfolio", label: "תיק" },
  { hash: "#/plan", label: "תוכנית" },
  { hash: "#/messages", label: "הודעות" },
  { hash: "#/selection", label: "🎯 בחירה" },
  { hash: "#/guide", label: "📖 מדריך" },
  { hash: "#/bot-guide", label: "🤖 חיבור בוט" },
  { hash: "#/settings", label: "⚙ הגדרות" },
];

function renderNav() {
  const hash = location.hash || "#/";
  nav.innerHTML = ROUTES.map(
    (r) =>
      `<a href="/investing/${r.hash}" data-route="${r.hash}" class="${hash === r.hash ? "active" : ""}">${r.label}</a>`
  ).join("");
  nav.querySelectorAll("a[data-route]").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const route = a.getAttribute("data-route");
      if (location.hash !== route) location.hash = route;
      else router();
    });
  });
}

async function renderDashboardDemo() {
  const data = await fetchJson("data/dashboard.json");
  const monthPnl = Number(data.equity) - Number(data.month_start_equity || data.equity);
  const monthPct = data.month_start_equity
    ? (monthPnl / Number(data.month_start_equity)) * 100
    : 0;

  const holdingsHtml = (data.holdings || [])
    .map(
      (h, i) => `
      <tr>
        <td class="num">${i + 1}</td>
        <td class="sym">${escapeHtml(h.symbol)}</td>
        <td>${escapeHtml(h.method || "—")}</td>
        <td class="num">${fmtUsd(h.capital_usd)}</td>
        <td class="num">${fmtUsd(h.entry_price)}</td>
        <td class="num">${fmtUsd(h.value)}</td>
        <td class="num ${h.pnl_usd >= 0 ? "pos" : "neg"}">${fmtUsd(h.pnl_usd, { signed: true })}</td>
        <td class="muted">${escapeHtml(h.entry_at || "")}</td>
      </tr>`
    )
    .join("");

  const picksHtml = (data.recent_picks || [])
    .map((p) => {
      const pnlClass = p.pnl_usd >= 0 ? "up" : "down";
      const hypo = p.hypo ? " · סימולציה" : "";
      return `
        <article class="pick-card" style="cursor:default">
          <div class="pick-card-header">
            <span class="pick-symbol">${escapeHtml(p.symbol)}</span>
            <span class="badge badge-${p.status === "invested" ? "invested" : "skipped"}">${escapeHtml(p.status_label || "")}</span>
          </div>
          <div class="pick-date">${escapeHtml(p.trading_day)}</div>
          <div class="pick-meta">
            <span>${fmtUsd(p.capital_usd)}</span>
            <span>ציון ${Number(p.score).toFixed(1)}</span>
          </div>
          <div class="pick-pnl ${pnlClass}">${fmtUsd(p.pnl_usd, { signed: true })} (${fmtPct(p.pnl_pct)})${hypo}</div>
        </article>`;
    })
    .join("");

  const hist = data.equity_history || [];
  const maxEq = Math.max(...hist.map((h) => h.equity), 1);
  const barsHtml = hist
    .map(
      (h) => `
      <div class="demo-bar-col" title="${escapeHtml(h.day)}: ${fmtUsd(h.equity)}">
        <div class="demo-bar" style="height:${Math.max(8, (h.equity / maxEq) * 120)}px"></div>
        <span>${escapeHtml(h.day)}</span>
      </div>`
    )
    .join("");

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>⚡ ${escapeHtml(data.title || "דשבורד לדוגמה")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
    </section>

    <div class="stats-grid">
      <div class="stat-card accent">
        <div class="label">הון נוכחי</div>
        <div class="value">${fmtUsd(data.equity)}</div>
      </div>
      <div class="stat-card">
        <div class="label">מזומן פנוי</div>
        <div class="value">${fmtUsd(data.cash)}</div>
      </div>
      <div class="stat-card ${data.open_pnl >= 0 ? "positive" : "negative"}">
        <div class="label">רווח פתוח</div>
        <div class="value">${fmtUsd(data.open_pnl, { signed: true })}</div>
      </div>
      <div class="stat-card ${monthPnl >= 0 ? "positive" : "negative"}">
        <div class="label">החודש</div>
        <div class="value">${fmtUsd(monthPnl, { signed: true })} <span class="muted" style="font-size:0.85rem">${fmtPct(monthPct)}</span></div>
      </div>
    </div>

    <section class="guide-section">
      <h2 class="section-title">בתיק עכשיו (דוגמה)</h2>
      <div class="portfolio-table-wrap">
        <table class="portfolio-table">
          <thead>
            <tr>
              <th>#</th><th>סימול</th><th>שיטה</th><th>מושקע</th><th>כניסה</th><th>שווי</th><th>רווח</th><th>זמן</th>
            </tr>
          </thead>
          <tbody>${holdingsHtml || `<tr><td colspan="8" class="muted">אין החזקות בדוגמה</td></tr>`}</tbody>
        </table>
      </div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">המלצות אחרונות (דוגמה)</h2>
      <div class="cards-grid">${picksHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">עקומת הון (דוגמה)</h2>
      <div class="demo-bars">${barsHtml}</div>
      <p class="guide-note" style="margin-top:1rem">יעד חודשי לדוגמה: ${fmtUsd(data.monthly_target_usd)} · רווח ממומש: ${fmtUsd(data.realized_pnl, { signed: true })}</p>
    </section>
  `;
}

async function renderPlanDemo() {
  const data = await fetchJson("data/plan.json");

  const actionsHtml = (data.holding_actions || [])
    .map(
      (a) => `
      <article class="guide-card">
        <div class="guide-card-head">
          <span class="guide-card-icon">📌</span>
          <div>
            <h3>${escapeHtml(a.symbol)} — ${escapeHtml(a.action)}</h3>
            <p class="guide-card-when">${escapeHtml(a.detail || "")}</p>
          </div>
        </div>
      </article>`
    )
    .join("");

  const offersHtml = (data.offers || [])
    .map(
      (o) => `
      <article class="pick-card" style="cursor:default">
        <div class="pick-card-header">
          <span class="pick-symbol">#${o.position}/${o.total} ${escapeHtml(o.symbol)}</span>
          <span class="badge badge-pending">${escapeHtml(o.entry_timing || "")}</span>
        </div>
        <div class="pick-meta">
          <span>ציון ${Number(o.score).toFixed(1)}</span>
          <span>${escapeHtml(o.method || "")}</span>
          <span>מומלץ ${fmtUsd(o.suggested_usd)}</span>
        </div>
        <p class="guide-card-when" style="margin:0.65rem 0 0">${escapeHtml(o.note || "")}</p>
        <div class="pick-meta" style="margin-top:0.5rem">
          <span>ATR ${Number(o.atr_pct).toFixed(1)}%</span>
          <span>5י ${fmtPct(o.ret_5d_pct)}</span>
          <span>נפח ${Number(o.vol_ratio).toFixed(2)}×</span>
        </div>
      </article>`
    )
    .join("");

  const howToHtml = (data.how_to || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>📋 ${escapeHtml(data.title || "תוכנית")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
      <p class="guide-note">יום מסחר: ${escapeHtml(data.for_trading_day || "—")} · ${escapeHtml(data.status_label || "")}</p>
    </section>

    <div class="stats-grid">
      <div class="stat-card accent">
        <div class="label">מזומן פנוי</div>
        <div class="value">${fmtUsd(data.available_capital_usd)}</div>
      </div>
      <div class="stat-card">
        <div class="label">הצעות בסבב</div>
        <div class="value">${(data.offers || []).length}</div>
      </div>
      <div class="stat-card">
        <div class="label">סטטוס</div>
        <div class="value" style="font-size:1.1rem">${escapeHtml(data.status || "draft")}</div>
      </div>
    </div>

    <p class="guide-note">${escapeHtml(data.review_note || "")}</p>

    <section class="guide-section">
      <h2 class="section-title">סקירת החזקות</h2>
      <div class="guide-cards">${actionsHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">הצעות קנייה (אחת-אחת)</h2>
      <div class="cards-grid">${offersHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">איך מאשרים בטלגרם</h2>
      <ul class="guide-list guide-tips">${howToHtml}</ul>
    </section>
  `;
}

async function renderPortfolioDemo() {
  const data = await fetchJson("data/portfolio.json");

  const openRows = (data.open_positions || [])
    .map(
      (p) => `
      <tr>
        <td class="sym">${escapeHtml(p.symbol)}</td>
        <td>${escapeHtml(p.method || "—")}</td>
        <td>${escapeHtml(p.trading_day || "")}</td>
        <td class="num">${fmtUsd(p.capital_usd)}</td>
        <td class="num">${fmtUsd(p.entry_price)}</td>
        <td class="num">${fmtUsd(p.value)}</td>
        <td class="num ${p.pnl_usd >= 0 ? "pos" : "neg"}">${fmtUsd(p.pnl_usd, { signed: true })}</td>
        <td class="num muted">${fmtUsd(p.sl)} / ${fmtUsd(p.tp)}</td>
        <td>${escapeHtml(p.status || "")}</td>
      </tr>`
    )
    .join("");

  const symbolRows = (data.by_symbol || [])
    .map(
      (s) => `
      <tr>
        <td class="sym">${escapeHtml(s.symbol)}</td>
        <td class="num">${s.trades}</td>
        <td class="num">${fmtUsd(s.invested)}</td>
        <td class="num ${s.pnl_usd >= 0 ? "pos" : "neg"}">${fmtUsd(s.pnl_usd, { signed: true })}</td>
        <td class="num">${fmtPct(s.avg_pct)}</td>
        <td class="num">${Number(s.win_rate).toFixed(0)}%</td>
        <td>${escapeHtml(s.last_day || "")}</td>
      </tr>`
    )
    .join("");

  const histRows = (data.history || [])
    .map(
      (h) => `
      <tr>
        <td>${escapeHtml(h.day)}</td>
        <td class="sym">${escapeHtml(h.symbol)}</td>
        <td class="num">${fmtUsd(h.capital_usd)}</td>
        <td class="num ${h.pnl_usd >= 0 ? "pos" : "neg"}">${fmtUsd(h.pnl_usd, { signed: true })}</td>
        <td class="num ${h.pnl_pct >= 0 ? "pos" : "neg"}">${fmtPct(h.pnl_pct)}</td>
        <td>${escapeHtml(h.exit || "")}</td>
      </tr>`
    )
    .join("");

  const chips = (data.chips || [])
    .map((c) => `<code class="guide-cmd-chip">${escapeHtml(c)}</code>`)
    .join(" ");

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>💼 ${escapeHtml(data.title || "תיק")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
    </section>

    <div class="stats-grid">
      <div class="stat-card accent">
        <div class="label">הון</div>
        <div class="value">${fmtUsd(data.equity)}</div>
      </div>
      <div class="stat-card">
        <div class="label">מזומן פנוי</div>
        <div class="value">${fmtUsd(data.cash)}</div>
      </div>
      <div class="stat-card">
        <div class="label">שווי פתוח</div>
        <div class="value">${fmtUsd(data.open_value)}</div>
        <div class="sub">${data.open_count} פוזיציות</div>
      </div>
      <div class="stat-card ${data.open_pnl >= 0 ? "positive" : "negative"}">
        <div class="label">רווח פתוח</div>
        <div class="value">${fmtUsd(data.open_pnl, { signed: true })}</div>
      </div>
      <div class="stat-card ${data.total_realized_pnl >= 0 ? "positive" : "negative"}">
        <div class="label">רווח ממומש</div>
        <div class="value">${fmtUsd(data.total_realized_pnl, { signed: true })}</div>
        <div class="sub">${data.trade_count} עסקאות · ${data.symbol_count} מניות</div>
      </div>
    </div>

    <section class="guide-section">
      <h2 class="section-title">בתיק עכשיו</h2>
      <div class="portfolio-table-wrap">
        <table class="portfolio-table">
          <thead>
            <tr>
              <th>סימול</th><th>שיטה</th><th>יום</th><th>מושקע</th><th>כניסה</th><th>שווי</th><th>רווח</th><th>SL / TP</th><th>סטטוס</th>
            </tr>
          </thead>
          <tbody>${openRows}</tbody>
        </table>
      </div>
      <p class="guide-note" style="margin-top:0.75rem">דוגמאות פעולה: ${chips}</p>
    </section>

    <section class="guide-section">
      <h2 class="section-title">סיכום לפי מניה</h2>
      <div class="portfolio-table-wrap">
        <table class="portfolio-table">
          <thead>
            <tr>
              <th>סימול</th><th>עסקאות</th><th>הון</th><th>רווח</th><th>ממוצע %</th><th>Win</th><th>אחרונה</th>
            </tr>
          </thead>
          <tbody>${symbolRows}</tbody>
        </table>
      </div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">היסטוריית עסקאות</h2>
      <div class="portfolio-table-wrap">
        <table class="portfolio-table">
          <thead>
            <tr>
              <th>יום</th><th>סימול</th><th>הון</th><th>רווח</th><th>%</th><th>יציאה</th>
            </tr>
          </thead>
          <tbody>${histRows}</tbody>
        </table>
      </div>
    </section>
  `;
}

async function renderMessagesDemo() {
  const data = await fetchJson("data/messages.json");
  const rows = (data.messages || [])
    .map(
      (m) => `
      <article class="guide-card ${m.role === "user" ? "guide-card-highlight" : ""}">
        <div class="guide-card-head">
          <span class="guide-card-icon">${m.role === "user" ? "👤" : "🤖"}</span>
          <div>
            <h3>${escapeHtml(m.title || "")}</h3>
            <p class="guide-card-when">${escapeHtml(m.time || "")} · ${escapeHtml(m.context || "")}</p>
            <p class="guide-card-when" style="margin-top:0.35rem">${escapeHtml(m.body || "")}</p>
          </div>
        </div>
      </article>`
    )
    .join("");

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>💬 ${escapeHtml(data.title || "הודעות")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
    </section>
    <div class="guide-cards">${rows}</div>
  `;
}

async function renderSettingsDemo() {
  const data = await fetchJson("data/settings.json");
  const sections = (data.sections || [])
    .map(
      (sec) => `
      <section class="guide-section">
        <h2 class="section-title">${escapeHtml(sec.title)}</h2>
        <div class="guide-cmd-grid">
          ${(sec.fields || [])
            .map(
              (f) => `
            <div class="guide-cmd">
              <code class="guide-cmd-chip">${escapeHtml(f.label)}</code>
              <span>${escapeHtml(f.value)}</span>
            </div>`
            )
            .join("")}
        </div>
      </section>`
    )
    .join("");

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>⚙ ${escapeHtml(data.title || "הגדרות")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
      <p class="guide-note">${escapeHtml(data.note || "")}</p>
    </section>
    ${sections}
  `;
}

async function renderSelectionGuide() {
  const data = await fetchJson("data/selection.json");
  const strat = data.strategy || {};

  const userFlowHtml = (data.user_flow || [])
    .map(
      (step) => `
      <div class="guide-flow-step">
        <div class="guide-flow-marker">${escapeHtml(step.step)}</div>
        <div class="guide-flow-body">
          <div class="guide-flow-title">${escapeHtml(step.title)}</div>
          <div class="guide-flow-detail">${escapeHtml(step.detail)}</div>
        </div>
      </div>`
    )
    .join("");

  const pipelineHtml = (data.pipeline || [])
    .map(
      (step) => `
      <div class="guide-flow-step">
        <div class="guide-flow-marker">${step.step}</div>
        <div class="guide-flow-body">
          <div class="guide-flow-title">${escapeHtml(step.title)}</div>
          <div class="guide-flow-detail">${escapeHtml(step.detail)}</div>
        </div>
      </div>`
    )
    .join("");

  const scoringHtml = (strat.scoring || [])
    .map((s) => `<li>${escapeHtml(s)}</li>`)
    .join("");

  const sourcesHtml = (data.sources?.items || [])
    .map(
      (s) => `
      <div class="guide-cmd">
        <code class="guide-cmd-chip">${escapeHtml(s.label)}</code>
        <span>משקל ${s.weight.toFixed(2)}</span>
      </div>`
    )
    .join("");

  const enrichHtml = (data.enrichment || [])
    .map(
      (e) => `
      <article class="guide-card">
        <div class="guide-card-head">
          <span class="guide-card-icon">${e.icon}</span>
          <div><h3>${escapeHtml(e.title)}</h3></div>
        </div>
        <p class="guide-card-when" style="margin:0">${escapeHtml(e.detail)}</p>
      </article>`
    )
    .join("");

  const limitsHtml = (data.limits || [])
    .map(
      (l) => `
      <div class="guide-cmd">
        <code class="guide-cmd-chip">${escapeHtml(l.label)}</code>
        <span>${escapeHtml(l.value)}</span>
      </div>`
    )
    .join("");

  const tickers = data.tickers_preview || [];
  const tickersNote =
    data.tickers_total > tickers.length
      ? ` (+${data.tickers_total - tickers.length} נוספות)`
      : "";

  const intraday = data.intraday || {};
  const intradayHtml = intraday.title
    ? `
    <section class="guide-section">
      <h2 class="section-title">🔍 ${escapeHtml(intraday.title)}</h2>
      <p class="guide-card-when">${escapeHtml(intraday.detail || "")}</p>
    </section>`
    : "";

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>🎯 ${escapeHtml(data.title || "איך בוחרים מניות?")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
    </section>

    <p class="guide-disclaimer">${escapeHtml(data.disclaimer || "")}</p>

    ${
      userFlowHtml
        ? `<section class="guide-section">
      <h2 class="section-title">זרימה יומית (מה אתה עושה)</h2>
      <div class="guide-flow">${userFlowHtml}</div>
    </section>`
        : ""
    }

    <section class="guide-section">
      <h2 class="section-title">איך המערכת בוחרת מניות</h2>
      <div class="guide-flow">${pipelineHtml}</div>
    </section>

    ${intradayHtml}

    <section class="guide-section">
      <h2 class="section-title">אסטרטגיה לדוגמה: ${escapeHtml(strat.profile_label || "")}</h2>
      <p class="guide-strategy-mode">${escapeHtml(strat.mode_title || "")}</p>
      <p class="guide-warning">${escapeHtml(strat.must_pass || "")}</p>
      <ul class="guide-list">${scoringHtml}</ul>
      <div class="guide-strategy-meta">
        <span>${escapeHtml(strat.stops || "")}</span>
        <span>${escapeHtml(strat.hold || "")}</span>
      </div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">מקורות אותות</h2>
      <div class="guide-cmd-grid">${sourcesHtml}</div>
      <p class="guide-flow-detail" style="margin-top:0.85rem">${escapeHtml(data.sources?.disagreement || "")}</p>
    </section>

    <section class="guide-section">
      <h2 class="section-title">העשרה אחרי הסינון</h2>
      <div class="guide-cards">${enrichHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">מגבלות הון וסיכון</h2>
      <div class="guide-cmd-grid">${limitsHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">רשימת מניות לדוגמה</h2>
      <p class="guide-tickers">${tickers.map((t) => `<code>${escapeHtml(t)}</code>`).join(" ")}${escapeHtml(tickersNote)}</p>
    </section>
  `;
}

async function renderTelegramGuide() {
  const data = await fetchJson("data/telegram.json");

  const flowHtml = (data.flow || [])
    .map(
      (step, i) => `
      <div class="guide-flow-step">
        <div class="guide-flow-marker">${escapeHtml(step.time)}</div>
        <div class="guide-flow-body">
          <div class="guide-flow-title">${escapeHtml(step.label)}</div>
          <div class="guide-flow-detail">${escapeHtml(step.detail)}</div>
        </div>
        ${i < data.flow.length - 1 ? '<div class="guide-flow-line"></div>' : ""}
      </div>`
    )
    .join("");

  const outgoingHtml = (data.outgoing || [])
    .map(
      (msg) => `
      <article class="guide-card">
        <div class="guide-card-head">
          <span class="guide-card-icon">${msg.icon}</span>
          <div>
            <h3>${escapeHtml(msg.title)}</h3>
            <p class="guide-card-when">${escapeHtml(msg.when)}</p>
          </div>
        </div>
        <ul class="guide-list">
          ${(msg.parts || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("")}
        </ul>
      </article>`
    )
    .join("");

  const commandsHtml = (data.commands || [])
    .map(
      (group) => `
      <section class="guide-section">
        <h2 class="section-title">${escapeHtml(group.title)}</h2>
        ${group.warning ? `<p class="guide-warning">⚠️ ${escapeHtml(group.warning)}</p>` : ""}
        <div class="guide-cmd-grid">
          ${(group.items || [])
            .map(
              (item) => `
            <div class="guide-cmd">
              <code class="guide-cmd-chip">${escapeHtml(item.cmd)}</code>
              <span>${escapeHtml(item.desc)}</span>
            </div>`
            )
            .join("")}
        </div>
      </section>`
    )
    .join("");

  const examplesHtml = (data.examples || [])
    .map(
      (ex) => `
      <div class="guide-example ${ex.title.includes("טעות") ? "is-warn" : "is-ok"}">
        <div class="guide-example-title">${escapeHtml(ex.title)}</div>
        <div class="guide-example-steps">
          ${(ex.steps || []).map((s) => `<code>${escapeHtml(s)}</code>`).join('<span class="guide-arrow">→</span>')}
        </div>
        <p>${escapeHtml(ex.note)}</p>
      </div>`
    )
    .join("");

  const tipsHtml = (data.tips || [])
    .map((t) => `<li>${escapeHtml(t)}</li>`)
    .join("");

  const configHelpHtml = (data.config_help || [])
    .map(
      (block) => `
      <section class="guide-section">
        <h2 class="section-title">⚙️ ${escapeHtml(block.title)} <span class="guide-badge">${escapeHtml(block.status || "")}</span></h2>
        <div class="guide-cmd-grid">
          ${(block.fields || [])
            .map(
              (f) => `
            <div class="guide-cmd">
              <code class="guide-cmd-chip">${escapeHtml(f.key)}</code>
              <span><b>${escapeHtml(f.label)}</b>: ${escapeHtml(String(f.value))}</span>
              ${f.hint ? `<div class="guide-flow-detail">${escapeHtml(f.hint)}</div>` : ""}
            </div>`
            )
            .join("")}
        </div>
        ${(block.examples || []).length ? `<ul class="guide-list guide-tips">${block.examples.map((ex) => `<li>💡 ${escapeHtml(ex)}</li>`).join("")}</ul>` : ""}
      </section>`
    )
    .join("");

  const gettingStartedHtml = (data.getting_started || [])
    .map(
      (item) => `
      <article class="guide-card guide-card-highlight">
        <div class="guide-card-head">
          <span class="guide-card-icon">${item.icon}</span>
          <div>
            <h3>${escapeHtml(item.title)}</h3>
            <p class="guide-card-when">${escapeHtml(item.detail)}</p>
            ${item.cmd ? `<p><code>${escapeHtml(item.cmd)}</code></p>` : ""}
          </div>
        </div>
      </article>`
    )
    .join("");

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>📖 ${escapeHtml(data.title || "מדריך טלגרם")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
      ${data.schedule_note ? `<p class="guide-note">${escapeHtml(data.schedule_note)}</p>` : ""}
    </section>

    ${
      gettingStartedHtml
        ? `<section class="guide-section">
      <h2 class="section-title">התחלה מהירה</h2>
      <div class="guide-cards">${gettingStartedHtml}</div>
    </section>`
        : ""
    }

    <section class="guide-section">
      <h2 class="section-title">זרימת יום מסחר</h2>
      <div class="guide-flow">${flowHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">הודעות שהבוט שולח אליך</h2>
      <div class="guide-cards">${outgoingHtml}</div>
    </section>

    ${commandsHtml}

    ${configHelpHtml}

    <section class="guide-section">
      <h2 class="section-title">דוגמאות</h2>
      <div class="guide-examples">${examplesHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">טיפים</h2>
      <ul class="guide-list guide-tips">${tipsHtml}</ul>
    </section>
  `;
}

async function renderBotGuide() {
  const data = await fetchJson("data/bot.json");

  const whereHtml = (data.where?.items || [])
    .map(
      (item) => `
      <article class="guide-card">
        <div class="guide-card-head">
          <span class="guide-card-icon">${item.icon || "📌"}</span>
          <div>
            <h3>${escapeHtml(item.label)}</h3>
            <p class="guide-card-when">${escapeHtml(item.detail)}</p>
          </div>
        </div>
      </article>`
    )
    .join("");

  const sectionsHtml = (data.sections || [])
    .map(
      (sec, i, arr) => `
      <div class="guide-flow-step">
        <div class="guide-flow-marker">${sec.step}</div>
        <div class="guide-flow-body">
          <div class="guide-flow-title">${sec.icon || ""} ${escapeHtml(sec.title)}</div>
          <ol class="guide-numbered">
            ${(sec.steps || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}
          </ol>
          ${sec.tip ? `<p class="guide-tip-inline">💡 ${escapeHtml(sec.tip)}</p>` : ""}
        </div>
        ${i < arr.length - 1 ? '<div class="guide-flow-line"></div>' : ""}
      </div>`
    )
    .join("");

  const faqHtml = (data.faq || [])
    .map(
      (row) => `
      <details class="guide-faq-item">
        <summary>${escapeHtml(row.q)}</summary>
        <p>${escapeHtml(row.a)}</p>
      </details>`
    )
    .join("");

  const newInstall = data.new_install || {};
  const tipsHtml = (data.tips || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");

  app.innerHTML = `
    ${DEMO_BANNER}
    <section class="hero">
      <h1>🤖 ${escapeHtml(data.title || "חיבור בוט")}</h1>
      <p>${escapeHtml(data.subtitle || "")}</p>
    </section>

    <section class="guide-section">
      <h2 class="section-title">${escapeHtml(data.where?.title || "איפה מעדכנים?")}</h2>
      <div class="guide-cards">${whereHtml}</div>
      ${data.where?.note ? `<p class="guide-note">${escapeHtml(data.where.note)}</p>` : ""}
    </section>

    <section class="guide-section">
      <h2 class="section-title">שלב אחר שלב</h2>
      <div class="guide-flow">${sectionsHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">${escapeHtml(newInstall.title || "התקנה חדשה")}</h2>
      <ol class="guide-numbered">${(newInstall.steps || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>
    </section>

    <section class="guide-section">
      <h2 class="section-title">שאלות נפוצות</h2>
      <div class="guide-faq">${faqHtml}</div>
    </section>

    <section class="guide-section">
      <h2 class="section-title">טיפים</h2>
      <ul class="guide-tips">${tipsHtml}</ul>
    </section>
  `;
}

async function router() {
  renderNav();
  const hash = location.hash || "#/";
  try {
    if (hash === "#/guide") await renderTelegramGuide();
    else if (hash === "#/bot-guide") await renderBotGuide();
    else if (hash === "#/selection") await renderSelectionGuide();
    else if (hash === "#/plan") await renderPlanDemo();
    else if (hash === "#/portfolio") await renderPortfolioDemo();
    else if (hash === "#/messages") await renderMessagesDemo();
    else if (hash === "#/settings") await renderSettingsDemo();
    else await renderDashboardDemo();
  } catch (err) {
    app.innerHTML = `${DEMO_BANNER}<p class="empty">שגיאה: ${escapeHtml(err.message)}</p>`;
  }
}

window.addEventListener("hashchange", router);
document.querySelectorAll("a[data-route]").forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    const route = a.getAttribute("data-route");
    if (location.hash !== route) location.hash = route;
    else router();
  });
});
if (!location.hash) location.replace(`${location.pathname}${location.search}#/`);
else router();
