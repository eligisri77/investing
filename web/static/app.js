const app = document.getElementById("app");
const nav = document.getElementById("nav");
const charts = [];

function fmtUsd(n) {
  const v = Number(n);
  const sign = v >= 0 ? "+" : "";
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}

function fmtPct(n) {
  const v = Number(n);
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function pickStatus(p) {
  if (p.invested && p.trade) return { cls: "badge-invested", text: "השקעת" };
  if (p.approved && !p.trade) return { cls: "badge-pending", text: "אושר · לא בוצע" };
  return { cls: "badge-skipped", text: "לא השקעת" };
}

function pickPnl(p) {
  if (p.trade) return { val: p.trade.pnl_usd, pct: p.trade.pnl_pct, hypo: false };
  if (p.hypothetical_if_skipped) {
    return {
      val: p.hypothetical_if_skipped.pnl_usd,
      pct: p.hypothetical_if_skipped.pnl_pct,
      hypo: true,
    };
  }
  return null;
}

function getSourceBreakdown(p) {
  if (p.source_breakdown?.length) return p.source_breakdown;
  const scores = p.source_scores || {};
  const labels = {
    yahoo: "Yahoo Finance",
    finviz: "Finviz",
    cnbc: "CNBC",
    barchart: "Barchart",
    nasdaq: "Nasdaq",
  };
  return Object.entries(scores)
    .map(([id, score]) => ({
      id,
      label: labels[id] || id,
      score: Number(score),
    }))
    .sort((a, b) => b.score - a.score);
}

function renderSourceScores(p, compact = false) {
  const items = getSourceBreakdown(p);
  if (!items.length) return "";
  const used = p.sources_used || items.length;
  const maxScore = Math.max(...items.map((x) => x.score), 1);
  const scoreLabel = Number(p.score).toFixed(1);
  const disagree = p.source_disagreement
    ? `<div class="source-warning">⚠️ מקורות לא מסכימים · std ${Number(p.source_score_std || 0).toFixed(1)} · פער ${Number(p.source_score_spread || 0).toFixed(1)}</div>`
    : "";

  if (compact) {
    const chips = items
      .slice(0, 4)
      .map((x) => `<span class="source-chip">${x.label} ${x.score.toFixed(1)}</span>`)
      .join("");
    return `
      <div class="source-block compact">
        <div class="source-title">משוקלל מ-${used} אתרים · ${scoreLabel}</div>
        <div class="source-chips">${chips}</div>
        ${disagree}
      </div>`;
  }

  return `
    <div class="source-block">
      <div class="source-title">ציון משוקלל מ-${used} אתרים · ${scoreLabel}</div>
      ${disagree}
      <div class="source-bars">
        ${items
          .map(
            (x) => `
          <div class="source-row">
            <span class="source-name">${x.label}</span>
            <div class="source-bar-track">
              <div class="source-bar-fill" style="width:${Math.max((x.score / maxScore) * 100, 4).toFixed(1)}%"></div>
            </div>
            <span class="source-val">${x.score.toFixed(1)}</span>
          </div>`
          )
          .join("")}
      </div>
    </div>`;
}

function renderEnrichmentMeta(p) {
  const parts = [];
  if (p.sentiment_adjustment != null && Number(p.sentiment_adjustment) !== 0) {
    const tone = p.sentiment_tone || "neutral";
    parts.push(`חדשות (${tone}): ${Number(p.sentiment_adjustment) >= 0 ? "+" : ""}${Number(p.sentiment_adjustment).toFixed(1)}`);
  }
  if (p.backtest?.summary) {
    parts.push(`📊 ${p.backtest.summary}`);
  }
  if (!parts.length) return "";
  return `<div class="enrichment-meta">${parts.map((x) => `<span>${x}</span>`).join("")}</div>`;
}

function renderSignalMeta(p) {
  const parts = [];
  if (p.atr_pct != null) parts.push(`ATR ${Number(p.atr_pct).toFixed(1)}%`);
  if (p.ret_5d_pct != null) parts.push(`5 ימים ${fmtPct(p.ret_5d_pct)}`);
  if (p.vol_ratio != null) parts.push(`נפח ${Number(p.vol_ratio).toFixed(2)}x`);
  if (p.breakout_ok != null) {
    parts.push(p.breakout_ok ? "פריצה" : `מתחת לשיא ${fmtPct(p.near_high_pct || 0)}`);
  }
  if (!parts.length) return "";
  return `<div class="signal-meta">${parts.map((x) => `<span>${x}</span>`).join("")}</div>`;
}

function destroyCharts() {
  while (charts.length) charts.pop().destroy();
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderNav(symbols, inbox = {}) {
  const hash = location.hash || "#/";
  const planBadge =
    inbox.pending_plan_day && inbox.unread
      ? `<span class="nav-badge">${inbox.unread}</span>`
      : inbox.pending_plan_day
        ? `<span class="nav-badge">!</span>`
        : "";
  nav.innerHTML = `
    <a href="#/" class="${hash === "#/" ? "active" : ""}">דשבורד</a>
    <a href="#/portfolio" class="${hash === "#/portfolio" ? "active" : ""}">תיק</a>
    <a href="#/plan" class="${hash === "#/plan" ? "active" : ""}">תוכנית${planBadge}</a>
    <a href="#/messages" class="${hash === "#/messages" ? "active" : ""}">הודעות</a>
    <a href="#/guide" class="${hash === "#/guide" ? "active" : ""}">📖 מדריך</a>
    <a href="#/bot-guide" class="${hash === "#/bot-guide" ? "active" : ""}">🤖 חיבור בוט</a>
    <a href="#/selection" class="${hash === "#/selection" ? "active" : ""}">🎯 בחירה</a>
    <a href="#/settings" class="${hash === "#/settings" ? "active" : ""}">⚙ הגדרות</a>
    ${symbols
      .slice(0, 6)
      .map(
        (s) =>
          `<a href="#/stock/${s}" class="${hash === `#/stock/${s}` ? "active" : ""}">${s}</a>`
      )
      .join("")}
  `;
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("he-IL", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const JOB_LABELS = {
  scheduler: "Scheduler",
  plan: "תוכנית יומית",
  simulation: "סימולציה",
  heartbeat: "Heartbeat",
  telegram_poll: "Telegram poll",
};

function jobIcon(status) {
  if (status === "ok" || status === "running") return "🟢";
  if (status === "failed") return "🔴";
  if (status === "skipped") return "⏭";
  return "⚪";
}

function renderHealthPanel(health) {
  if (!health) return "";
  const online = health.status === "ok";
  const inst = health.instance || {};
  const jobs = health.jobs || {};
  const jobOrder = ["scheduler", "plan", "simulation", "heartbeat", "telegram_poll"];
  const jobRows = jobOrder
    .map((name) => {
      const j = jobs[name];
      if (!j) {
        return `<div class="health-row"><span>${JOB_LABELS[name] || name}</span><span class="health-muted">—</span></div>`;
      }
      return `
        <div class="health-row">
          <span>${jobIcon(j.status)} ${JOB_LABELS[name] || name}</span>
          <span class="health-muted">${fmtTime(j.at)}${j.detail ? ` · ${escapeHtml(String(j.detail).slice(0, 60))}` : ""}</span>
        </div>`;
    })
    .join("");

  const err = health.last_error
    ? `<div class="health-error">שגיאה אחרונה (${health.last_error.job}) · ${fmtTime(health.last_error.at)}: ${escapeHtml(health.last_error.detail || "")}</div>`
    : "";

  const logTail = (health.log_tail || [])
    .map((line) => `<div class="health-log-line">${escapeHtml(line)}</div>`)
    .join("");

  return `
    <section class="health-panel ${online ? "health-ok" : "health-offline"}">
      <div class="health-head">
        <h2 class="section-title">מצב מערכת</h2>
        <span class="health-badge">${online ? "פעיל" : "לא פעיל"}</span>
      </div>
      <div class="health-meta">
        <span>PID ${inst.pid ?? "—"} · ${health.notification_mode || "—"} · secrets: ${health.secrets_source || "—"}</span>
        <span>תוכנית אחרונה: ${health.latest_plan_day || "—"} · דוח: ${health.latest_report_day || "—"}</span>
      </div>
      <div class="health-jobs">${jobRows}</div>
      ${err}
      ${logTail ? `<details class="health-log"><summary>לוג אחרון</summary>${logTail}</details>` : ""}
    </section>`;
}

function renderDashboard(data, health) {
  const monthPnl = data.equity - data.month_start_equity;
  const monthPct = data.month_start_equity
    ? (monthPnl / data.month_start_equity) * 100
    : 0;

  const pendingBanner = data.inbox?.pending_plan_day
    ? `<a href="#/plan" class="pending-banner">👉 אשר את התיק (המלצות ל-${data.inbox.pending_plan_day})</a>`
    : "";

  app.innerHTML = `
    ${pendingBanner}
    ${renderHealthPanel(health)}
    <section class="hero">
      <h1>Dry Run Dashboard</h1>
      <p>כל ההמלצות · מה הרווחת אם השקעת · מה פספסת אם לא</p>
    </section>

    <div class="stats-grid">
      <div class="stat-card accent">
        <div class="label">הון נוכחי</div>
        <div class="value">$${data.equity.toFixed(2)}</div>
      </div>
      <div class="stat-card">
        <div class="label">יעד חודשי</div>
        <div class="value">$${data.monthly_target_usd.toFixed(0)}</div>
      </div>
      <div class="stat-card ${monthPnl >= 0 ? "positive" : "negative"}">
        <div class="label">החודש</div>
        <div class="value">${fmtUsd(monthPnl)}</div>
      </div>
      <div class="stat-card ${data.total_realized_pnl >= 0 ? "positive" : "negative"}">
        <div class="label">רווח מעסקאות שאושרו</div>
        <div class="value">${fmtUsd(data.total_realized_pnl)}</div>
      </div>
    </div>

    <h2 class="section-title">המלצות אחרונות</h2>
    <div class="cards-grid">
      ${data.recent_picks
        .map((p) => {
          const st = pickStatus(p);
          const pnl = pickPnl(p);
          const pnlClass = pnl ? (pnl.val >= 0 ? "up" : "down") : "neutral";
          const pnlLabel = pnl
            ? `${fmtUsd(pnl.val)} (${fmtPct(pnl.pct)})${pnl.hypo ? " · סימולציה" : ""}`
            : "—";
          return `
            <a class="pick-card" href="#/stock/${p.symbol}">
              <div class="pick-card-header">
                <span class="pick-symbol">${p.symbol}</span>
                <span class="badge ${st.cls}">${st.text}</span>
              </div>
              <div class="pick-date">${p.trading_day}</div>
              <div class="pick-meta">
                <span>$${p.capital_usd.toFixed(0)}</span>
                <span>ציון ${p.score.toFixed(1)}</span>
              </div>
              ${renderSourceScores(p, true)}
              ${renderEnrichmentMeta(p)}
              <div class="pick-pnl ${pnlClass}">${pnlLabel}</div>
            </a>`;
        })
        .join("")}
    </div>

    ${
      data.equity_history.length
        ? `<h2 class="section-title">עקומת הון</h2>
           <div class="chart-panel"><div class="chart-wrap"><canvas id="equityChart"></canvas></div></div>`
        : ""
    }
  `;

  if (data.equity_history.length) {
    const ctx = document.getElementById("equityChart");
    charts.push(
      new Chart(ctx, {
        type: "line",
        data: {
          labels: data.equity_history.map((h) => h.day),
          datasets: [
            {
              label: "Equity $",
              data: data.equity_history.map((h) => h.equity),
              borderColor: "#00f0ff",
              backgroundColor: "rgba(0, 240, 255, 0.1)",
              fill: true,
              tension: 0.35,
              pointRadius: 5,
              pointBackgroundColor: "#ff2d95",
            },
          ],
        },
        options: chartOptions(false),
      })
    );
  }
}

function chartOptions(showLegend) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: showLegend, labels: { color: "#9da3c2" } },
    },
    scales: {
      x: { ticks: { color: "#9da3c2" }, grid: { color: "rgba(255,255,255,0.05)" } },
      y: { ticks: { color: "#9da3c2" }, grid: { color: "rgba(255,255,255,0.05)" } },
    },
  };
}

async function renderStock(symbol) {
  const data = await fetchJson(`/api/stock/${symbol}`);
  const stats = data.stats;

  app.innerHTML = `
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
    <div class="stock-hero">
      <span class="symbol-big">${symbol}</span>
      <div>
        <div class="badge badge-invested">${stats.invested_count} השקעות</div>
        <div class="badge badge-skipped" style="margin-right:0.5rem">${stats.skipped_count} דילגת</div>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card ${stats.realized_pnl_usd >= 0 ? "positive" : "negative"}">
        <div class="label">רווח/הפסד — השקעת</div>
        <div class="value">${fmtUsd(stats.realized_pnl_usd)}</div>
      </div>
      <div class="stat-card">
        <div class="label">סימולציה — לא השקעת</div>
        <div class="value">${fmtUsd(stats.skipped_hypothetical_pnl_usd)}</div>
      </div>
      <div class="stat-card accent">
        <div class="label">סה"כ המלצות</div>
        <div class="value">${stats.total_recommendations}</div>
      </div>
    </div>

    <div id="pick-sections"></div>
  `;

  const container = document.getElementById("pick-sections");

  for (let i = 0; i < data.picks.length; i++) {
    const p = data.picks[i];
    const st = pickStatus(p);
    const chartId = `chart-${symbol}-${i}`;
    const barId = `bar-${symbol}-${i}`;

    container.insertAdjacentHTML(
      "beforeend",
      `
      <div class="chart-panel">
        <h3>${p.trading_day} · <span class="badge ${st.cls}">${st.text}</span></h3>
        <div class="pick-meta" style="margin-bottom:1rem">
          <span>הון: $${p.capital_usd.toFixed(0)}</span>
          <span>SL -${(p.stop_loss_pct * 100).toFixed(0)}%</span>
          <span>TP +${(p.take_profit_pct * 100).toFixed(0)}%</span>
          <span>ציון ${p.score.toFixed(1)}</span>
        </div>
        ${renderSignalMeta(p)}
        ${renderSourceScores(p, false)}
        ${renderEnrichmentMeta(p)}
        <div class="chart-wrap"><canvas id="${chartId}"></canvas></div>
        <div class="compare-bars" id="${barId}"></div>
        ${p.news_summary ? `<p style="margin-top:1rem;color:var(--muted);font-size:0.9rem">📰 ${p.news_summary}</p>` : ""}
      </div>`
    );

    try {
      const chartData = await fetchJson(
        `/api/stock/${symbol}/chart?day=${p.trading_day}&window=5`
      );
      renderPriceChart(chartId, chartData, p);
    } catch {
      document.getElementById(chartId).parentElement.innerHTML =
        '<p class="empty">אין נתוני גרף ליום זה</p>';
    }

    renderCompareBars(barId, p);
  }
}

function renderPriceChart(canvasId, chartData, pick) {
  const ctx = document.getElementById(canvasId);
  const labels = chartData.prices.map((x) => x.date);
  const closes = chartData.prices.map((x) => x.close);
  const highlightIdx = chartData.prices.findIndex((x) => x.highlight);

  const pointColors = chartData.prices.map((_, i) =>
    i === highlightIdx ? "#ff2d95" : "#00f0ff"
  );
  const pointRadius = chartData.prices.map((_, i) => (i === highlightIdx ? 8 : 3));

  const datasets = [
    {
      label: "מחיר סגירה",
      data: closes,
      borderColor: "#a855f7",
      backgroundColor: "rgba(168, 85, 247, 0.08)",
      fill: true,
      tension: 0.3,
      pointBackgroundColor: pointColors,
      pointRadius,
    },
  ];

  if (pick.trade) {
    datasets.push({
      label: "כניסה",
      data: labels.map((d) => (d === pick.trading_day ? pick.trade.entry_price : null)),
      borderColor: "#b8ff00",
      pointRadius: 6,
      showLine: false,
      pointStyle: "triangle",
    });
    datasets.push({
      label: "יציאה",
      data: labels.map((d) => (d === pick.trading_day ? pick.trade.exit_price : null)),
      borderColor: "#ff3366",
      pointRadius: 6,
      showLine: false,
      pointStyle: "rectRot",
    });
  }

  charts.push(
    new Chart(ctx, {
      type: "line",
      data: { labels, datasets },
      options: chartOptions(true),
    })
  );
}

function renderCompareBars(containerId, p) {
  const el = document.getElementById(containerId);
  const invested = p.trade
    ? { usd: p.trade.pnl_usd, pct: p.trade.pnl_pct }
    : null;
  const skipped = p.hypothetical_if_skipped
    ? {
        usd: p.hypothetical_if_skipped.pnl_usd,
        pct: p.hypothetical_if_skipped.pnl_pct,
      }
    : null;

  if (!invested && !skipped) {
    el.innerHTML = "";
    return;
  }

  el.innerHTML = `
    ${
      invested
        ? `<div class="compare-box invested">
            <div class="title">השקעת · ${p.trade.exit_reason}</div>
            <div class="amount" style="color:${invested.usd >= 0 ? "var(--green)" : "var(--red)"}">
              ${fmtUsd(invested.usd)}<br><small>${fmtPct(invested.pct)}</small>
            </div>
          </div>`
        : `<div class="compare-box invested"><div class="title">${p.approved ? "אושר · לא בוצע" : "לא השקעת"}</div><div class="amount" style="color:var(--muted)">—</div></div>`
    }
    ${
      skipped
        ? `<div class="compare-box skipped">
            <div class="title">${p.approved ? "סימולציה · לא בוצע" : "סימולציה · דילגת"}</div>
            <div class="amount" style="color:${skipped.usd >= 0 ? "var(--green)" : "var(--red)"}">
              ${fmtUsd(skipped.usd)}<br><small>${fmtPct(skipped.pct)}</small>
            </div>
          </div>`
        : `<div class="compare-box skipped"><div class="title">סימולציה</div><div class="amount" style="color:var(--muted)">—</div></div>`
    }
  `;
}

function stripHtml(html) {
  const el = document.createElement("div");
  el.innerHTML = html;
  return el.textContent || el.innerText || "";
}

function formatMsgTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("he-IL", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 16).replace("T", " ");
  }
}

function contextLabel(ctx) {
  const map = {
    plan: "תוכנית יומית",
    report: "דוח יומי",
    heartbeat: "Heartbeat",
    user: "אתה",
    "app:approve": "אישור באפליקציה",
    "app:reject": "דחייה באפליקציה",
    "app:allocation": "חלוקה באפליקציה",
    "reply:APPROVE": "תשובה · אישור",
    "reply:REJECT": "תשובה · דחייה",
    "reply:STATUS": "תשובה · סטטוס",
    "reply:portfolio": "תשובה · תיק",
    "reply:HELP": "תשובה · עזרה",
  };
  if (map[ctx]) return map[ctx];
  if (ctx.startsWith("app:")) return `פעולה · ${ctx.replace("app:", "")}`;
  if (ctx.startsWith("reply:")) return `תשובה · ${ctx.replace("reply:", "")}`;
  return ctx;
}

async function planAction(tradingDay, action, indices) {
  const res = await fetch(`/api/plan/${tradingDay}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, indices }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function planAllocation(tradingDay, optionId) {
  const res = await fetch(`/api/plan/${tradingDay}/allocation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ option_id: optionId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function stripHtml(html) {
  return String(html || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function renderAllocationPanel(data) {
  const alloc = data.plan.allocation;
  if (data.allocation_applied && alloc?.status === "applied") {
    const amounts = alloc.amounts
      ? Object.entries(alloc.amounts)
          .map(([sym, amt]) => `${sym} $${Number(amt).toFixed(0)}`)
          .join(" · ")
      : "";
    return `
      <section class="plan-allocation applied">
        <h2>✅ חלוקה נשמרה · ח${alloc.selected_option || "?"}</h2>
        <p>${escapeHtml(alloc.title || "")}</p>
        ${amounts ? `<p class="allocation-amounts">${escapeHtml(amounts)}</p>` : ""}
        <p class="allocation-done">הכל מוכן — אין צורך בפעולה נוספת עד דוח המסחר.</p>
      </section>`;
  }
  if (!data.allocation_pending || !data.allocation_options?.length) return "";
  const cards = data.allocation_options
    .map(
      (opt) => `
    <div class="allocation-option ${opt.full_invest ? "full" : "partial"}">
      <div class="allocation-option-head">
        <strong>ח${opt.id} — ${escapeHtml(opt.title)}</strong>
        <span class="allocation-badge">${opt.full_invest ? "השקעה מלאה" : "עם מזומן"}</span>
      </div>
      <p class="allocation-desc">${escapeHtml(opt.description)}</p>
      <ul class="allocation-summary">${(opt.summary_lines || [])
        .map((line) => `<li>${escapeHtml(line)}</li>`)
        .join("")}</ul>
      <button type="button" class="btn btn-allocation" data-option-id="${opt.id}">בחר ח${opt.id}</button>
    </div>`
    )
    .join("");
  return `
    <section class="plan-allocation">
      <h2>💵 חלוקה ידנית (אופציונלי)</h2>
      <p class="allocation-hint">ברוב המקרים <strong>אשר הכל</strong> מספיק — החלוקה אוטומטית. אם תרצה לבחור ידנית:</p>
      <div class="allocation-options">${cards}</div>
    </section>`;
}

async function startInvesting() {
  const btn = document.getElementById("planStartBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "רגע…";
  }
  try {
    const res = await fetch("/api/plan/start", { method: "POST" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || res.statusText);
    await renderActivePlan();
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "אשר והתחל";
    }
    alert(err.message || "שגיאה");
  }
}

async function generatePlanNow() {
  const btn = document.getElementById("planNowBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "יוצר תוכנית…";
  }
  try {
    const res = await fetch("/api/plan/generate-now", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    await renderActivePlan();
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "תוכנית עכשיו";
    }
    alert(`שגיאה: ${err.message}`);
  }
}

function renderPlanRecCard(rec, idx) {
  const label = strategyLabel(rec);
  const contributors = Array.isArray(rec.contributing_strategies)
    ? rec.contributing_strategies
    : [];
  const why =
    contributors.length > 1
      ? `זוהה בכמה שיטות: ${contributors.map(strategyIdLabel).join(" + ")}`
      : label;
  return `
    <div class="plan-rec-card">
      <div class="plan-rec-head">
        <span class="pick-symbol">#${idx} ${rec.symbol}</span>
        <span>$${Number(rec.capital_usd).toFixed(0)}</span>
      </div>
      <div class="pick-meta">
        <span>SL -${(rec.stop_loss_pct * 100).toFixed(0)}%</span>
        <span>TP +${(rec.take_profit_pct * 100).toFixed(0)}%</span>
        <span>ציון ${Number(rec.score).toFixed(1)}</span>
      </div>
      ${why ? `<div class="muted">${escapeHtml(why)}</div>` : ""}
      ${rec.reason ? `<div class="settings-hint">${escapeHtml(rec.reason)}</div>` : ""}
    </div>`;
}

async function renderActivePlan() {
  let data;
  try {
    data = await fetchJson("/api/plan/active");
  } catch {
    app.innerHTML = `
      <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
      <section class="hero plan-simple">
        <h1>💰 מוכנים לקנות?</h1>
        <p>לחיצה אחת — קונים 3 מניות ומחלקים את $1,000.</p>
        <button type="button" class="btn btn-start plan-cta" id="planStartBtn">אשר והתחל</button>
      </section>`;
    document.getElementById("planStartBtn")?.addEventListener("click", startInvesting);
    return;
  }

  await fetch("/api/inbox/read", { method: "POST" });
  const plan = data.plan;
  const day = data.trading_day;
  const recs = plan.recommendations || [];
  const symbols = recs.map((r) => r.symbol).join(" · ");

  if (data.confirmed && !data.bought) {
    const entryWhen = data.entry_when ? escapeHtml(data.entry_when) : "";
    app.innerHTML = `
      <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
      <section class="hero plan-simple">
        <h1>✅ מאושר — ממתין לפתיחת השוק</h1>
        <p><b>${escapeHtml(symbols)}</b> — $${recs.reduce((s, r) => s + Number(r.capital_usd || 0), 0).toFixed(0)} סה״כ</p>
        <p class="plan-simple-sub">⏰ כניסה לשוק: <b>${entryWhen}</b></p>
        <a href="#/portfolio" class="btn btn-start plan-cta">צפה בתיק →</a>
      </section>
      <details class="plan-details">
        <summary>פרטי ההזמנה</summary>
        <div id="planRecs" class="plan-recs"></div>
      </details>`;
    const doneContainer = document.getElementById("planRecs");
    recs.forEach((rec, i) => {
      doneContainer.insertAdjacentHTML("beforeend", renderPlanRecCard(rec, i + 1));
    });
    return;
  }

  if (data.bought) {
    app.innerHTML = `
      <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
      <section class="hero plan-simple plan-simple-done">
        <h1>✅ בתיק</h1>
        <p><b>${escapeHtml(symbols)}</b> — מחזיק</p>
        <a href="#/portfolio" class="btn btn-start plan-cta">צפה בתיק שלך →</a>
      </section>`;
    return;
  }

  if (data.ready || recs.length) {
    app.innerHTML = `
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
    <section class="hero plan-simple">
      <h1>📋 המלצות ליום ${escapeHtml(day)}</h1>
      <p>${recs.length} מניות: <b>${escapeHtml(symbols)}</b></p>
      <p class="plan-simple-sub">אישור = הזמנה לפתיחת השוק. הקנייה במחיר פתיחה.</p>
      <button type="button" class="btn btn-start plan-cta" id="planStartBtn">אשר הזמנה</button>
    </section>
    <details class="plan-details" open>
      <summary>מה בחרנו?</summary>
      <div id="planRecs" class="plan-recs"></div>
    </details>
    <p id="planStatus" class="plan-status-msg"></p>`;

    const container = document.getElementById("planRecs");
    recs.forEach((rec, i) => {
      container.insertAdjacentHTML("beforeend", renderPlanRecCard(rec, i + 1));
    });
    document.getElementById("planStartBtn")?.addEventListener("click", startInvesting);
    return;
  }

  app.innerHTML = `
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
    <section class="hero plan-simple">
      <h1>📋 אין המלצות פעילות</h1>
      <p>ממתין לסריקת ערב (~23:15) או שלח <code>תוכנית עכשיו</code> בטלגרם.</p>
    </section>`;
}

function strategyLabel(p) {
  const strat = p && (p.strategy_id || p.strategy);
  if (strat === "method2") {
    const parts = ["שיטה 2", "נרות סיניים"];
    if (p.trigger) parts.push(String(p.trigger));
    if (String(p.side || "").toUpperCase() === "SHORT") parts.push("שורט");
    return parts.join(" · ");
  }
  if (strat === "rising_three" || strat === "rising_three_methods") {
    return p.pattern_weak ? "נרות Rising Three (חלש)" : "נרות Rising Three";
  }
  if (strat === "score" || strat === "score_momentum") return "מומנטום וציון";
  if (strat === "trend_pullback") return "תיקון במגמה · ניסיוני";
  return strategyIdLabel(strat);
}

function strategyIdLabel(id) {
  const labels = {
    score_momentum: "מומנטום וציון",
    rising_three: "Rising Three",
    rising_three_methods: "Rising Three",
    method2: "שיטה 2",
    trend_pullback: "Trend Pullback · ניסיוני",
  };
  return labels[String(id || "")] || String(id || "");
}

function renderPortfolio(data) {
  const hasPending = data.open_positions.some(
    (p) => p.status === "pending_execution" || p.status === "pending_market_entry"
  );
  const openRows = data.open_positions.length
    ? data.open_positions
        .map((p) => {
          const strat = strategyLabel(p);
          const stratHtml = strat
            ? `<div class="muted" style="font-size:0.85em;margin-top:2px">${escapeHtml(strat)}</div>`
            : "";
          return `
        <tr>
          <td><a href="#/stock/${p.symbol}" class="pick-symbol">${p.symbol}</a>${stratHtml}</td>
          <td>${p.entry_day || p.trading_day || "—"}</td>
          <td>$${p.capital_usd.toFixed(0)}</td>
          <td>${p.entry_price ? `$${Number(p.entry_price).toFixed(2)}` : p.entry_ref_price ? `$${Number(p.entry_ref_price).toFixed(2)}` : "—"}</td>
          <td>${p.stop_loss_pct != null ? `-${(p.stop_loss_pct * 100).toFixed(0)}% / +${(p.take_profit_pct * 100).toFixed(0)}%` : "—"}</td>
          <td><span class="badge ${p.status === "holding" ? "badge-invested" : "badge-pending"}">${
            p.status === "holding"
              ? `מחזיק ${p.days_held || 0} ימים`
              : p.status === "pending_market_entry"
                ? `מאושר · כניסה ${p.scheduled_entry || "בפתיחה"}`
                : "ממתין לקנייה"
          }</span></td>
        </tr>`;
        })
        .join("")
    : `<tr><td colspan="6" class="empty-cell">אין מניות בתיק — שלח התחל או לחץ קנה בדשבורד</td></tr>`;

  const symbolRows = data.by_symbol.length
    ? data.by_symbol
        .map((s) => {
          const pnlClass = s.total_pnl_usd >= 0 ? "up" : "down";
          return `
        <tr>
          <td><a href="#/stock/${s.symbol}" class="pick-symbol">${s.symbol}</a></td>
          <td>${s.trade_count}</td>
          <td>$${s.total_capital_usd.toFixed(0)}</td>
          <td class="pnl ${pnlClass}">${fmtUsd(s.total_pnl_usd)}</td>
          <td class="pnl ${pnlClass}">${fmtPct(s.avg_pnl_pct)}</td>
          <td>${s.win_rate_pct}% (${s.wins}/${s.trade_count})</td>
          <td>${s.last_trading_day || "—"}</td>
        </tr>`;
        })
        .join("")
    : `<tr><td colspan="7" class="empty-cell">עדיין לא בוצעו עסקאות</td></tr>`;

  const tradeRows = data.trades.length
    ? data.trades
        .slice(0, 30)
        .map((t) => {
          const pnlClass = t.pnl_usd >= 0 ? "up" : "down";
          return `
        <tr>
          <td>${t.trading_day}</td>
          <td><a href="#/stock/${t.symbol}" class="pick-symbol">${t.symbol}</a></td>
          <td>$${t.capital_usd.toFixed(0)}</td>
          <td class="pnl ${pnlClass}">${fmtUsd(t.pnl_usd)}</td>
          <td class="pnl ${pnlClass}">${fmtPct(t.pnl_pct)}</td>
          <td>${t.exit_reason || "—"}</td>
        </tr>`;
        })
        .join("")
    : `<tr><td colspan="6" class="empty-cell">—</td></tr>`;

  app.innerHTML = `
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
    <section class="hero">
      <h1>💼 תיק השקעות</h1>
      <p>איפה הכסף מושקע · רווח/הפסד לפי מניה · עסקאות שבוצעו</p>
    </section>

    <div class="stats-grid portfolio-stats">
      <div class="stat-card accent">
        <div class="label">הון נוכחי</div>
        <div class="value">$${data.equity.toFixed(2)}</div>
      </div>
      <div class="stat-card">
        <div class="label">מושקע בתיק</div>
        <div class="value">$${data.open_capital_usd.toFixed(0)}</div>
        <div class="sub">${data.open_count} עסקאות</div>
      </div>
      <div class="stat-card ${data.total_realized_pnl >= 0 ? "positive" : "negative"}">
        <div class="label">רווח/הפסד מצטבר</div>
        <div class="value">${fmtUsd(data.total_realized_pnl)}</div>
        <div class="sub">${data.trade_count} עסקאות · ${data.symbol_count} מניות</div>
      </div>
    </div>

    <h2 class="section-title">מושקע עכשיו</h2>
    <p class="section-hint">${
      hasPending
        ? "מאושר — הקנייה תתבצע בפתיחת השוק (ראה עמודת סטטוס)"
        : data.open_positions.length
          ? "המניות בתיק שלך — המערכת מטפלת במכירות אוטומטיות (SL/TP)"
          : "אין מניות בתיק — אשר המלצות ב־#/plan"
    }</p>
    <div class="portfolio-table-wrap">
      <table class="portfolio-table">
        <thead>
          <tr>
            <th>מניה</th>
            <th>יום מסחר</th>
            <th>סכום</th>
            <th>מחיר ייחוס</th>
            <th>SL / TP</th>
            <th>סטטוס</th>
          </tr>
        </thead>
        <tbody>${openRows}</tbody>
      </table>
    </div>

    <h2 class="section-title">סיכום לפי מניה</h2>
    <div class="portfolio-table-wrap">
      <table class="portfolio-table">
        <thead>
          <tr>
            <th>מניה</th>
            <th>עסקאות</th>
            <th>הון שהושקע</th>
            <th>רווח/הפסד</th>
            <th>ממוצע %</th>
            <th>Win rate</th>
            <th>עסקה אחרונה</th>
          </tr>
        </thead>
        <tbody>${symbolRows}</tbody>
      </table>
    </div>

    <h2 class="section-title">היסטוריית עסקאות</h2>
    <div class="portfolio-table-wrap">
      <table class="portfolio-table">
        <thead>
          <tr>
            <th>יום</th>
            <th>מניה</th>
            <th>הון</th>
            <th>רווח/הפסד</th>
            <th>%</th>
            <th>יציאה</th>
          </tr>
        </thead>
        <tbody>${tradeRows}</tbody>
      </table>
    </div>
  `;
}

function renderMessages(data) {
  app.innerHTML = `
    <section class="hero">
      <h1>הודעות</h1>
      <p>${data.total} הודעות · מהמערכת וממך</p>
    </section>
    <div class="msg-filter">
      <button class="filter-btn active" data-filter="all">הכל</button>
      <button class="filter-btn" data-filter="out">מהמערכת</button>
      <button class="filter-btn" data-filter="in">ממך</button>
    </div>
    <div class="msg-thread" id="msgThread"></div>
  `;

  const thread = document.getElementById("msgThread");
  const msgs = [...data.messages].sort(
    (a, b) => new Date(a.timestamp) - new Date(b.timestamp)
  );

  function draw(filter) {
    thread.innerHTML = msgs
      .filter((m) => filter === "all" || m.direction === filter)
      .map((m) => {
        const isOut = m.direction === "out";
        const body =
          m.parse_mode === "HTML" ? stripHtml(m.text) : m.text;
        const preview =
          body.length > 1200 ? body.slice(0, 1200) + "…" : body;
        return `
          <div class="msg-bubble ${isOut ? "out" : "in"}">
            <div class="msg-meta">
              <span class="msg-ctx">${contextLabel(m.context)}</span>
              <span class="msg-time">${formatMsgTime(m.timestamp)}</span>
              ${m.backfilled ? '<span class="msg-tag">ארכיון</span>' : ""}
            </div>
            ${
              m.metadata?.image_id
                ? `<img class="msg-image" src="/api/telegram/images/${encodeURIComponent(m.metadata.image_id)}" alt="" loading="lazy" />`
                : `<pre class="msg-body">${escapeHtml(preview)}</pre>`
            }
          </div>`;
      })
      .join("");
    thread.scrollTop = thread.scrollHeight;
  }

  draw("all");

  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      draw(btn.dataset.filter);
    });
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatDualUtc(hhmm) {
  if (!/^\d{2}:\d{2}$/.test(String(hhmm || ""))) return "";
  const [h, m] = String(hhmm).split(":").map(Number);
  const now = new Date();
  const utc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), h, m));
  const il = utc.toLocaleTimeString("he-IL", {
    timeZone: "Asia/Jerusalem",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${hhmm} UTC · ${il} ישראל`;
}

function renderSettingsField(field, value, dualTimes) {
  const id = `setting-${field.key}`;
  const hint = field.hint
    ? `<p class="settings-hint">${escapeHtml(field.hint)}</p>`
    : "";
  const dualRaw = dualTimes?.[field.key] || (field.type === "time" ? formatDualUtc(value) : "");
  const dualHint =
    field.type === "time" && dualRaw
      ? `<p class="settings-dual-time" data-dual-for="${field.key}">${escapeHtml(dualRaw)}</p>`
      : "";
  const restart = field.restart_required
    ? `<span class="settings-restart-tag">דורש הפעלה מחדש</span>`
    : "";

  if (field.type === "boolean") {
    const checked = value ? "checked" : "";
    return `
      <label class="settings-field settings-field-check">
        <span class="settings-label-row">
          <span class="settings-label">${escapeHtml(field.label)}</span>
          ${restart}
        </span>
        <input type="checkbox" id="${id}" name="${field.key}" ${checked} />
        ${hint}
      </label>`;
  }

  if (field.type === "select") {
    const options = (field.options || [])
      .map(
        (opt) =>
          `<option value="${escapeHtml(opt.value)}" ${String(value) === String(opt.value) ? "selected" : ""}>${escapeHtml(opt.label)}</option>`
      )
      .join("");
    return `
      <div class="settings-field">
        <label class="settings-label-row" for="${id}">
          <span class="settings-label">${escapeHtml(field.label)}</span>
          ${restart}
        </label>
        <select id="${id}" name="${field.key}" class="settings-input">${options}</select>
        ${hint}
      </div>`;
  }

  const inputType = field.type === "time" ? "time" : "number";
  const step = field.step != null ? `step="${field.step}"` : "";
  const min = field.min != null ? `min="${field.min}"` : "";
  const max = field.max != null ? `max="${field.max}"` : "";
  const displayValue =
    field.type === "time" && value && /^\d{2}:\d{2}$/.test(String(value))
      ? String(value)
      : value ?? "";

  return `
    <div class="settings-field">
      <label class="settings-label-row" for="${id}">
        <span class="settings-label">${escapeHtml(field.label)}</span>
        ${restart}
      </label>
      <input
        type="${inputType}"
        id="${id}"
        name="${field.key}"
        class="settings-input"
        value="${escapeHtml(displayValue)}"
        ${step} ${min} ${max}
      />
      ${dualHint}
      ${hint}
    </div>`;
}

async function saveSettings(formEl, statusEl) {
  const data = new FormData(formEl);
  const values = {};
  for (const [key, raw] of data.entries()) {
    const input = formEl.querySelector(`[name="${key}"]`);
    if (input?.type === "checkbox") {
      values[key] = input.checked;
    } else if (input?.type === "number") {
      values[key] = raw === "" ? null : Number(raw);
    } else {
      values[key] = raw;
    }
  }
  formEl.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    if (!(input.name in values)) values[input.name] = false;
  });

  statusEl.textContent = "שומר...";
  statusEl.className = "settings-status";
  try {
    const res = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = body.detail;
      const msg = Array.isArray(detail)
        ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
        : detail || res.statusText;
      throw new Error(msg);
    }
    statusEl.textContent = body.restart_recommended
      ? "✅ נשמר. הפעל מחדש את האפליקציה כדי שהשינויים ייכנסו לתוקף."
      : "✅ ההגדרות נשמרו.";
    statusEl.className = "settings-status ok";
  } catch (err) {
    statusEl.textContent = `שגיאה: ${err.message}`;
    statusEl.className = "settings-status err";
  }
}

async function renderSelectionGuide() {
  const data = await fetchJson("/api/selection/guide");
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
      ${intraday.enabled ? `<p><a href="#/settings" style="color:var(--cyan)">שנה תדירות או כבה בהגדרות</a></p>` : ""}
    </section>`
    : "";

  app.innerHTML = `
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
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
      <h2 class="section-title">אסטרטגיה נוכחית: ${escapeHtml(strat.profile_label || "")}</h2>
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
      <h2 class="section-title">רשימת מניות נסרקות</h2>
      <p class="guide-tickers">${tickers.map((t) => `<code>${escapeHtml(t)}</code>`).join(" ")}${escapeHtml(tickersNote)}</p>
      <p class="guide-flow-detail">ניתן לערוך ברשימה ב-config.json או בהגדרות (פרופיל סיכון).</p>
    </section>
  `;
}

async function renderTelegramGuide() {
  const data = await fetchJson("/api/telegram/guide");

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
        <p class="guide-card-when">ניתן לשנות ב-<a href="${escapeHtml(block.dashboard_path || "#/settings")}" style="color:var(--cyan)">הגדרות</a> או ב-config.json</p>
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
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
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

async function saveTelegramSettings(formEl, statusEl) {
  const token = formEl.querySelector('[name="bot_token"]')?.value?.trim() || "";
  const chatId = formEl.querySelector('[name="chat_id"]')?.value?.trim() || "";
  statusEl.textContent = "שומר...";
  statusEl.className = "settings-status";
  try {
    const res = await fetch("/api/settings/telegram", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bot_token: token, chat_id: chatId }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.detail || res.statusText);
    }
    statusEl.textContent = "✅ הבוט נשמר ב-.env — ייכנס לתוקף תוך דקה (או הפעל מחדש).";
    statusEl.className = "settings-status ok";
    await renderSettings();
  } catch (err) {
    statusEl.textContent = `שגיאה: ${err.message}`;
    statusEl.className = "settings-status err";
  }
}

async function testTelegramConnection(formEl, statusEl) {
  const token = formEl.querySelector('[name="bot_token"]')?.value?.trim() || "";
  const chatId = formEl.querySelector('[name="chat_id"]')?.value?.trim() || "";
  statusEl.textContent = "שולח הודעת בדיקה...";
  statusEl.className = "settings-status";
  try {
    const res = await fetch("/api/settings/telegram/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bot_token: token, chat_id: chatId }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.detail || res.statusText);
    }
    statusEl.textContent = body.message || "✅ החיבור עובד!";
    statusEl.className = "settings-status ok";
  } catch (err) {
    statusEl.textContent = `שגיאה: ${err.message}`;
    statusEl.className = "settings-status err";
  }
}

function renderUpdateSection(info) {
  const current = info?.current_version || "—";
  const upgrades = Array.isArray(info?.upgrades) ? info.upgrades : [];
  const msg = info?.message || "";
  const repo = info?.repo || "";
  let body;
  if (!info) {
    body = `<p class="settings-section-note">לא ניתן לבדוק עדכונים כרגע.</p>`;
  } else if (upgrades.length === 0) {
    body = `<p class="settings-section-note">${escapeHtml(msg || "אין עדכון זמין.")}</p>`;
  } else {
    const rows = upgrades
      .map((u, i) => {
        const latest = i === 0 ? ' <span class="update-badge">מומלץ</span>' : "";
        const sizeMb =
          u.size_bytes != null ? ` · ${(Number(u.size_bytes) / (1024 * 1024)).toFixed(1)} MB` : "";
        return `
        <label class="update-option">
          <input type="radio" name="update_version" value="${escapeHtml(u.version)}" ${i === 0 ? "checked" : ""} />
          <span>
            <b>${escapeHtml(u.version)}</b>${latest}${sizeMb}
            ${u.name ? `<span class="settings-hint">${escapeHtml(u.name)}</span>` : ""}
          </span>
        </label>`;
      })
      .join("");
    body = `
      <p class="settings-section-note">רק שדרוג קדימה · מוצגות עד 3 גרסאות חדשות יותר מהנוכחית.</p>
      <div class="update-options">${rows}</div>
      <div class="settings-actions telegram-actions">
        <button type="button" id="updateInstallBtn" class="btn btn-save">הורד והתקן</button>
        <button type="button" id="updateRefreshBtn" class="btn btn-sm">בדוק שוב</button>
        <p id="updateStatus" class="settings-status"></p>
      </div>`;
  }
  return `
    <section class="settings-section update-settings">
      <h2 class="section-title">⬆ עדכון גרסה</h2>
      <p class="telegram-intro">גרסה מותקנת: <b>${escapeHtml(current)}</b>
        ${repo ? ` · מקור: <code>${escapeHtml(repo)}</code> Releases` : ""}</p>
      ${body}
    </section>`;
}

function bindUpdateSection() {
  const refreshBtn = document.getElementById("updateRefreshBtn");
  if (refreshBtn) {
    refreshBtn.onclick = () => renderSettings();
  }
  const installBtn = document.getElementById("updateInstallBtn");
  if (!installBtn) return;
  installBtn.onclick = async () => {
    const statusEl = document.getElementById("updateStatus");
    const selected = document.querySelector('input[name="update_version"]:checked');
    if (!selected) {
      statusEl.textContent = "בחרו גרסה";
      statusEl.className = "settings-status err";
      return;
    }
    const version = selected.value;
    if (!confirm(`להוריד ולהתקין את גרסה ${version}?\nאחרי שהמתקין נפתח — סגרו את האפליקציה מה-tray.`)) {
      return;
    }
    statusEl.textContent = "מוריד…";
    statusEl.className = "settings-status";
    installBtn.disabled = true;
    try {
      const res = await fetch("/api/update/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = body.detail || res.statusText;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      statusEl.textContent = body.message || "המתקין נפתח.";
      statusEl.className = "settings-status ok";
    } catch (err) {
      statusEl.textContent = `שגיאה: ${err.message}`;
      statusEl.className = "settings-status err";
    } finally {
      installBtn.disabled = false;
    }
  };
}

function renderTelegramSettingsSection(tg) {
  const statusBadge = tg.configured
    ? `<span class="telegram-status ok">מחובר · ${escapeHtml(tg.bot_token_masked)} · chat ${escapeHtml(tg.chat_id_masked)}</span>`
    : `<span class="telegram-status warn">לא מוגדר</span>`;
  const steps = (tg.setup_steps || [])
    .map((s, i) => `<li>${i + 1}. ${escapeHtml(s)}</li>`)
    .join("");
  return `
    <section class="settings-section telegram-settings">
      <h2 class="section-title">🤖 בוט טלגרם</h2>
      <p class="telegram-intro">כל משתמש יכול לחבר בוט משלו — הסודות נשמרים בקובץ <code>.env</code> ולא ב-git.
        <a href="#/bot-guide" class="telegram-guide-link">📖 מדריך מלא: יצירת בוט וחיבור</a></p>
      ${statusBadge}
      <ol class="telegram-setup-steps">${steps}</ol>
      <form id="telegramForm" class="settings-form telegram-form">
        <div class="settings-grid">
          <div class="settings-field">
            <label class="settings-label-row" for="tg-token">
              <span class="settings-label">Bot Token</span>
            </label>
            <input
              type="password"
              id="tg-token"
              name="bot_token"
              class="settings-input"
              autocomplete="off"
              placeholder="${tg.configured ? "השאר ריק כדי לא לשנות" : "123456789:ABC pattern from BotFather"}"
            />
            ${tg.configured ? `<p class="settings-hint">נוכחי: ${escapeHtml(tg.bot_token_masked)}</p>` : ""}
          </div>
          <div class="settings-field">
            <label class="settings-label-row" for="tg-chat">
              <span class="settings-label">Chat ID</span>
            </label>
            <input
              type="text"
              id="tg-chat"
              name="chat_id"
              class="settings-input"
              inputmode="numeric"
              placeholder="${tg.configured ? "השאר ריק כדי לא לשנות" : "163470607"}"
              value="${tg.configured ? "" : ""}"
            />
            ${tg.configured && tg.chat_id ? `<p class="settings-hint">נוכחי: ${escapeHtml(tg.chat_id)}</p>` : ""}
          </div>
        </div>
      </form>
      <div class="settings-actions telegram-actions">
        <button type="button" class="btn btn-save" id="telegramTestBtn">בדיקת חיבור</button>
        <button type="submit" form="telegramForm" class="btn btn-approve">שמור בוט</button>
        <p id="telegramStatus" class="settings-status"></p>
      </div>
    </section>`;
}

async function renderBotGuide() {
  const data = await fetchJson("/api/telegram/bot-guide");

  const whereHtml = (data.where?.items || [])
    .map(
      (item) => `
      <article class="guide-card">
        <div class="guide-card-head">
          <span class="guide-card-icon">${item.icon || "📌"}</span>
          <div>
            <h3>${escapeHtml(item.label)}</h3>
            <p class="guide-card-when">${escapeHtml(item.detail)}</p>
            ${
              item.action_route
                ? `<a href="${item.action_route}" class="btn btn-sm btn-save" style="margin-top:0.5rem;display:inline-block;text-decoration:none;">${escapeHtml(item.action_label || "פתח")}</a>`
                : ""
            }
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
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
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

    <div class="guide-footer-actions">
      <a href="#/settings" class="btn btn-approve">⚙ עבור להגדרות וחבר בוט</a>
      <a href="#/guide" class="btn btn-save">📖 מדריך פקודות טלגרם</a>
    </div>
  `;
}

function renderStrategyPerformance(perf) {
  const rows = Array.isArray(perf?.strategies) ? perf.strategies : [];
  if (!rows.length) {
    return `
      <section class="settings-section">
        <h2 class="section-title">מעקב סימולציה לפי אסטרטגיה</h2>
        <p class="settings-section-note">נתוני shadow תיאורטיים, לא עסקאות שבוצעו. המעקב יתחיל מהתוכנית הבאה.</p>
      </section>`;
  }
  const body = rows
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(row.label_he || row.strategy_id)}</td>
        <td>${Number(row.signals || 0)}</td>
        <td>${Number(row.closed_trades || 0)}</td>
        <td>${Number(row.win_rate_pct || 0).toFixed(1)}%</td>
        <td class="pnl ${Number(row.pnl_usd || 0) >= 0 ? "positive" : "negative"}">${fmtUsd(Number(row.pnl_usd || 0))}</td>
        <td>${row.ready_for_comparison ? "מספיק להשוואה" : `נדרשות ${perf.minimum_closed_trades || 20} סגירות`}</td>
      </tr>`
    )
    .join("");
  return `
    <section class="settings-section">
      <h2 class="section-title">מעקב סימולציה לפי אסטרטגיה</h2>
      <p class="settings-section-note">נתוני shadow תיאורטיים, לא עסקאות שבוצעו. השוואה ראשונית רק אחרי 20–30 סגירות ולפחות ${escapeHtml(perf.recommended_weeks || "4–6")} שבועות.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>אסטרטגיה</th><th>אותות</th><th>נסגרו</th><th>שיעור הצלחה</th><th>תוצאה מדומה</th><th>מדגם</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>`;
}

async function renderSettings() {
  const [data, tg, updateInfo, strategyPerf] = await Promise.all([
    fetchJson("/api/settings"),
    fetchJson("/api/settings/telegram"),
    fetchJson("/api/update").catch(() => null),
    fetchJson("/api/strategies/performance").catch(() => null),
  ]);
  const timeDual = data.time_dual || {};
  const sections = (data.sections || [])
    .map(
      (section) => `
      <section class="settings-section">
        <h2 class="section-title">${escapeHtml(section.title)}</h2>
        ${section.note ? `<p class="settings-section-note">${escapeHtml(section.note)}</p>` : ""}
        <div class="settings-grid">
          ${section.fields.map((field) => renderSettingsField(field, data.values[field.key], timeDual)).join("")}
        </div>
      </section>`
    )
    .join("");

  app.innerHTML = `
    <a href="#/" style="color:var(--cyan);text-decoration:none;font-weight:600;">← חזרה לדשבורד</a>
    <section class="hero">
      <h1>⚙ הגדרות</h1>
      <p>הגדרות כלליות ב־config.json · בוט טלגרם ב־.env (לכל משתמש בוט משלו)</p>
    </section>
    ${renderUpdateSection(updateInfo)}
    ${renderStrategyPerformance(strategyPerf)}
    ${renderTelegramSettingsSection(tg)}
    <div class="settings-meta">
      <span>מקור סודות: <b>${escapeHtml(data.secrets_source || "—")}</b></span>
      <span>${escapeHtml(data.config_path || "")}</span>
      ${data.user_data_dir ? `<span>נתונים: ${escapeHtml(data.user_data_dir)}</span>` : ""}
    </div>
    <form id="settingsForm" class="settings-form">${sections}</form>
    <div class="settings-actions">
      <button type="submit" form="settingsForm" class="btn btn-save">שמור הגדרות</button>
      <p id="settingsStatus" class="settings-status"></p>
    </div>
  `;

  const form = document.getElementById("settingsForm");
  const statusEl = document.getElementById("settingsStatus");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    saveSettings(form, statusEl);
  });

  const tgForm = document.getElementById("telegramForm");
  const tgStatus = document.getElementById("telegramStatus");
  tgForm.addEventListener("submit", (e) => {
    e.preventDefault();
    saveTelegramSettings(tgForm, tgStatus);
  });
  document.getElementById("telegramTestBtn").onclick = () =>
    testTelegramConnection(tgForm, tgStatus);

  bindUpdateSection();

  form.querySelectorAll('input[type="time"]').forEach((input) => {
    input.addEventListener("input", () => {
      const dualEl = form.querySelector(`[data-dual-for="${input.name}"]`);
      if (dualEl) dualEl.textContent = formatDualUtc(input.value);
    });
  });
}

async function router() {
  destroyCharts();
  app.innerHTML = '<p class="empty">טוען...</p>';

  try {
    const dash = await fetchJson("/api/dashboard");
    renderNav(dash.symbols, dash.inbox || {});

    const hash = location.hash || "#/";
    const stockMatch = hash.match(/^#\/stock\/([A-Z0-9.^-]+)$/i);

    if (hash === "#/plan") {
      await renderActivePlan();
    } else if (hash === "#/portfolio") {
      const portfolio = await fetchJson("/api/portfolio");
      renderPortfolio(portfolio);
    } else if (hash === "#/messages") {
      const msgs = await fetchJson("/api/telegram/messages");
      renderMessages(msgs);
    } else if (hash === "#/selection") {
      await renderSelectionGuide();
    } else if (hash === "#/guide") {
      await renderTelegramGuide();
    } else if (hash === "#/bot-guide") {
      await renderBotGuide();
    } else if (hash === "#/settings") {
      await renderSettings();
    } else if (stockMatch) {
      await renderStock(stockMatch[1].toUpperCase());
    } else {
      const health = await fetchJson("/api/health");
      renderDashboard(dash, health);
    }
  } catch (err) {
    app.innerHTML = `<p class="empty">שגיאה: ${err.message}</p>`;
  }
}

window.addEventListener("hashchange", router);
router();
