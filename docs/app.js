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

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

const DEMO_BANNER = `
  <div class="guide-note" style="margin-bottom:1.25rem">
    👁 הדגמה ציבורית וסטטית — תוכן גנרי מהגדרות דוגמה, בלי חיבור לאף מכשיר/חשבון אמיתי.
    <a href="https://github.com/eligisri77/investing" style="color:var(--cyan)">קוד המקור וההתקנה ב-GitHub</a>
  </div>`;

function renderNav() {
  const hash = location.hash || "#/selection";
  nav.innerHTML = `
    <a href="#/selection" class="${hash === "#/selection" ? "active" : ""}">🎯 בחירה</a>
    <a href="#/guide" class="${hash === "#/guide" ? "active" : ""}">📖 מדריך</a>
    <a href="#/bot-guide" class="${hash === "#/bot-guide" ? "active" : ""}">🤖 חיבור בוט</a>
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
  const hash = location.hash || "#/selection";
  try {
    if (hash === "#/guide") await renderTelegramGuide();
    else if (hash === "#/bot-guide") await renderBotGuide();
    else await renderSelectionGuide();
  } catch (err) {
    app.innerHTML = `<p class="empty">שגיאה: ${err.message}</p>`;
  }
}

window.addEventListener("hashchange", router);
router();
