/* Monitor Korekt USA — frontend (statyczny, czyta data.json) */
const ORDER = ["SPX", "NDX", "RUT", "DJI"];
const SERIES = { SPX: "#3987e5", NDX: "#d95926", RUT: "#199e70", DJI: "#c98500" };
const ST = {
  far: ["Daleko od dna", "st-far"], approach: ["Zbliżamy się", "st-approach"],
  zone: ["Strefa dna", "st-zone"], past: ["Dno prawdopodobnie za nami", "st-past"],
  risk: ["Ryzyko pogłębienia", "st-risk"], neutral: ["Bez kierunku", "st-far"],
};
let D = null;
let TAB = "USA";

const $ = (s) => document.querySelector(s);
const fmt = (x, d = 0) => x == null ? "—" : Number(x).toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (x, d = 1, sign = false) => x == null ? "—" : (sign && x > 0 ? "+" : "") + (x * 100).toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d }) + "%";
const arrow = (x, inv = false, eps = 0) => {
  if (x == null) return '<span class="flat">—</span>';
  const c = Math.abs(x) <= eps ? "flat" : ((x > 0) !== inv ? "up" : "down");
  return `<span class="${c}">${x > eps ? "▲" : x < -eps ? "▼" : "■"}</span>`;
};
const pill = (st, txt) => `<span class="pill ${ST[st] ? ST[st][1] : "st-far"}">${txt || (ST[st] ? ST[st][0] : st)}</span>`;
const phasePill = (p) => `<span class="pill" style="color:${p.color};border-color:${p.color}">● ${p.short}</span>`;

const LAYOUT = (extra = {}) => Object.assign({
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  font: { family: "Inter, sans-serif", color: "#b4b2a9", size: 12 },
  margin: { l: 52, r: 16, t: 10, b: 36 },
  xaxis: { gridcolor: "#1f242b", linecolor: "#262b33", zeroline: false },
  yaxis: { gridcolor: "#1f242b", linecolor: "#262b33", zeroline: false },
  hovermode: "x unified", hoverlabel: { bgcolor: "#1a1e25", bordercolor: "#3a404a", font: { color: "#eceae4" } },
  legend: { orientation: "h", y: 1.12, x: 0, font: { size: 12 } },
  showlegend: true,
}, extra);
const CFG = { displayModeBar: false, responsive: true };
const plot = (id, traces, layout) => Plotly.newPlot(id, traces, LAYOUT(layout), CFG);
const BS = () => D.models && D.models.bottom && D.models.bottom.pass;
const FC = () => D.models && D.models.forecast && D.models.forecast.pass;

/* ---------------- boot ---------------- */
async function load(refresh = false) {
  const r = await fetch("data.json?t=" + Date.now());
  const nd = await r.json();
  if (refresh && D && nd.generated === D.generated) return;
  D = nd;
  $("#updated").innerHTML = `Aktualizacja: ${D.generated} · dane do ${D.indices[ORDER.find(k => D.indices[k])].last_date}` +
    (D.synthetic ? '<span class="badge-syn">DANE TESTOWE</span>' : "");
  const tabs = [["USA", "🇺🇸 USA"], ...ORDER.filter(k => D.indices[k]).map(k => [k, D.indices[k].name]), ["LEAD", "Liderzy spadków"], ["CHECK", "✓ Sprawdzalność"], ["META", "Metodologia"]];
  $("#tabs").innerHTML = tabs.map(([k, n]) => {
    const c = D.indices[k] ? D.indices[k].phase.color : (k === "USA" ? D.usa.consensus.color : null);
    return `<button data-t="${k}">${c ? `<span class="dot" style="background:${c}"></span>` : ""}${n}</button>`;
  }).join("");
  $("#tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) go(b.dataset.t); };
  go(refresh ? TAB : (location.hash.slice(1) || "USA"), refresh);
}
window.addEventListener("hashchange", () => { const t = location.hash.slice(1); if (D && t && t !== TAB) go(t); });
function go(t, keepScroll = false) {
  if (!(t === "USA" || t === "META" || t === "CHECK" || t === "LEAD" || (D.indices && D.indices[t]))) t = "USA";
  TAB = t;
  if (location.hash.slice(1) !== t) history.replaceState(null, "", "#" + t);
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === t));
  if (!keepScroll) window.scrollTo(0, 0);
  if (t === "USA") renderUSA();
  else if (t === "META") renderMeta();
  else if (t === "CHECK") renderCheck();
  else if (t === "LEAD") renderLead();
  else renderIndex(D.indices[t]);
}

/* ---------------- USA ---------------- */
function renderUSA() {
  const u = D.usa, c = u.consensus;
  const fg = u.fg;
  let h = `
  <div class="hero" style="--phase-bg:${c.color}33">
    <span class="pill" style="color:${c.color};border-color:${c.color}">KONSENSUS USA · ${pct(c.share, 0)} wagi</span>
    <h2>${c.name}</h2>
    <div class="action">→ ${c.action}</div>
    <div class="headline">${u.headline}</div>
  </div>
  <div class="section">Indeksy <small>kliknij, aby przejść do szczegółów</small></div>
  <div class="grid g4">${ORDER.filter(k => D.indices[k]).map(tileHTML).join("")}</div>
  <div class="section">Makro / cały rynek</div>
  <div class="grid g6">
    ${kpi("VIX", fmt(u.vix, 1), u.vix >= 30 ? "panika" : u.vix >= 22 ? "strach" : "spokój")}
    ${kpi("VIX / VIX3M", fmt(u.vix_term, 2), u.vix_term >= 1 ? "backwardation — panika" : "contango — normalnie")}
    ${kpi("Kredyt HYG/IEF 20d", pct(u.credit_20d, 1, true), u.credit_20d <= -0.025 ? "stres kredytowy" : "spokojnie")}
    ${kpi("HY OAS", u.oas == null ? "—" : fmt(u.oas, 2) + "%", u.oas_20d == null ? "" : (u.oas_20d > 0 ? "+" : "") + fmt(u.oas_20d, 2) + " pp / 20 sesji")}
    ${kpi("Stress USA", fmt(u.stress, 0) + "/100", `${arrow(u.stress_d10, false, 1)} ${fmt(u.stress_d10, 1)} vs śr. 10d`)}
    ${BS() ? kpi("Bottom Score USA", u.bottom == null ? "—" : fmt(u.bottom, 0) + "/100", "P(dno blisko), średnia ważona") : ""}
    ${fg ? kpi("CNN Fear & Greed", fg.score, `${fg.rating} · tydz. temu ${fg.prev_week} · mies. ${fg.prev_month}`) : ""}
  </div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h3>Drawdown od rekordu — 3 lata</h3><div id="c_dd" class="chart"></div></div>
    ${BS() ? `<div class="card"><h3>Bottom Score — ostatnie 120 sesji</h3><div id="c_bs" class="chart"></div>
      <div class="note">Bottom Score = prawdopodobieństwo (z analogów), że do końca korekty cena nie spadnie już więcej niż 3%. Rośnie → zbliżamy się do dna / dno za nami.</div></div>` : `<div class="card"><h3>Stress — ostatnie 120 sesji</h3><div id="c_bs" class="chart"></div><div class="note">Stress = ile strachu jest teraz na tle historii (0–100).</div></div>`}
  </div>
  ${fg && fg.hist && fg.hist.length ? `<div class="card" style="margin-top:14px"><h3>CNN Fear & Greed — rok</h3><div id="c_fg" class="chart sm"></div></div>` : ""}
  `;
  $("#app").innerHTML = h;
  document.querySelectorAll(".tile").forEach(el => el.onclick = () => go(el.dataset.k));

  const ks = ORDER.filter(k => D.indices[k]);
  plot("c_dd", ks.map(k => ({ x: D.indices[k].chart.d, y: D.indices[k].chart.dd, name: D.indices[k].name, type: "scatter", mode: "lines",
    line: { color: SERIES[k], width: 2 }, hovertemplate: "%{y:.1%}" })),
    { yaxis: { tickformat: ".0%", gridcolor: "#1f242b" }, shapes: [-0.1, -0.2].map(y => hline(y, "#3a404a")) });
  plot("c_bs", ks.map(k => { const c = D.indices[k].chart, n = c.d.length, ser = BS() ? c.bottom : c.stress; return { x: c.d.slice(n - 120), y: ser.slice(n - 120), name: D.indices[k].name,
    type: "scatter", mode: "lines", connectgaps: false, line: { color: SERIES[k], width: 2 }, hovertemplate: "%{y:.0f}" }; }),
    { yaxis: { range: [0, 100], gridcolor: "#1f242b" }, shapes: [hline(50, "#3a404a"), hline(70, "#2fb36b55")] });
  if (fg && fg.hist && fg.hist.length) plot("c_fg", [{ x: fg.hist.map(p => p[0]), y: fg.hist.map(p => p[1]), type: "scatter", mode: "lines",
    line: { color: "#3987e5", width: 2 }, name: "F&G", hovertemplate: "%{y:.0f}" }],
    { showlegend: false, yaxis: { range: [0, 100], gridcolor: "#1f242b" }, shapes: [hline(25, "#e5484d66"), hline(75, "#2fb36b66")] });
}
const hline = (y, c) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y, line: { color: c, width: 1, dash: "dot" } });
const kpi = (l, v, m) => `<div class="card kpi"><div class="lbl">${l}</div><div class="val">${v}</div><div class="meta">${m || ""}</div></div>`;

function tileHTML(k) {
  const x = D.indices[k], f = x.forecast, p = x.phase;
  const b = x.bottom;
  return `<div class="card tile" data-k="${k}" style="border-top:3px solid ${p.color}">
    <div style="display:flex;justify-content:space-between;align-items:center"><span class="name">${x.name}</span>${phasePill(p)}</div>
    <div class="kpi"><div class="val">${fmt(x.close, 0)}</div>
    <div class="meta"><span class="${x.chg1d >= 0 ? "up" : "down"}">${pct(x.chg1d, 2, true)}</span> · drawdown <b>${pct(x.dd)}</b> · ${x.days_from_peak} sesji</div></div>
    ${BS() ? `<div style="margin-top:10px;font-size:12px;color:var(--muted)">Bottom Score ${b == null ? "—" : `<b class="mono" style="color:var(--text)">${fmt(b, 0)}</b>/100 ${arrow(x.bottom_d10, false, 2)} ${x.bottom_d10 == null ? "" : fmt(x.bottom_d10, 0) + " vs 10d"}`}</div>
    <div class="bar"><i style="width:${b || 0}%;background:${b >= 70 ? "var(--past)" : b >= 50 ? "var(--approach)" : "#5b6170"}"></i></div>` : ""}
    <div style="font-size:12px;color:var(--muted);margin-top:8px">Stress <b class="mono" style="color:var(--text)">${fmt(x.stress, 0)}</b> ${arrow(x.stress_d10, false, 1)} · ${x.vol_name} <b class="mono" style="color:var(--text)">${fmt(x.vol, 1)}</b></div>
    <div style="font-size:12.5px;margin-top:8px">${f ? `Dno: <b class="mono">${fmt(f.trough_med, 0)}</b> (${pct(f.depth_med)}) za ~${fmt(f.days_med)} sesji · P(zaliczone) ${pct(f.p_bottomed, 0)}` : x.naive ? `Historycznie od ${pct(x.naive.dd_low)}: mediana dna <b class="mono">${pct(x.naive.p50)}</b> (${fmt(x.naive.lvl_p50, 0)}) · n=${x.naive.n}` : '<span class="flat">Brak aktywnej korekty</span>'}</div>
  </div>`;
}

/* ---------------- INDEKS ---------------- */
function renderIndex(x) {
  const p = x.phase, f = x.forecast;
  const leanSt = p.lean === "past" ? "past" : p.lean === "approach" ? "approach" : p.lean === "far" ? "risk" : "neutral";
  const steps = [1, 2, 3, 4, 5, 6].map(i => {
    const q = D.phases[i];
    return `<div class="step ${i === p.id ? "on" : ""}" style="--c:${q.color}"><b>${i}. ${q.short}</b>${i === p.id ? `pewność ${pct(p.conf, 0)} · od ${p.since} sesji` : ""}</div>`;
  }).join("");
  let h = `
  <div class="hero" style="--phase-bg:${p.color}40">
    ${phasePill(p)} <span class="pill st-far">${x.name} · ${x.last_date}</span>
    <h2>${p.name}</h2>
    <div class="action">→ ${p.action}</div>
    <div class="headline">${x.headline}</div>
    <div class="lean">${pill(leanSt, "Momentum")} ${p.lean_txt}</div>
    ${p.raw != null && p.raw !== p.id && D.phases[p.raw] ? `<div class="note">Dzisiejsze warunki wskazują fazę „${D.phases[p.raw].short}” — czeka na potwierdzenie (2 sesje).</div>` : ""}
    <div class="stepper">${steps}</div>
  </div>

  <div class="grid g6" style="margin-top:14px">
    ${kpi("Kurs", fmt(x.close, 0), `<span class="${x.chg1d >= 0 ? "up" : "down"}">${pct(x.chg1d, 2, true)}</span> · rekord ${fmt(x.peak, 0)}`)}
    ${kpi("Drawdown", pct(x.dd), `${x.days_from_peak} sesji od szczytu`)}
    ${BS() ? kpi("Bottom Score", x.bottom == null ? "—" : fmt(x.bottom, 0) + "/100",
      x.bottom == null ? "aktywny od −5%" : `3d ${arrow(x.bottom_d3, false, 1)} ${fmt(x.bottom_d3, 1)} · 10d ${arrow(x.bottom_d10, false, 1)} ${fmt(x.bottom_d10, 1)}`) : ""}
    ${kpi("Stress", fmt(x.stress, 0) + "/100", `3d ${arrow(x.stress_d3, false, 1)} ${fmt(x.stress_d3, 1)} · 10d ${arrow(x.stress_d10, false, 1)} ${fmt(x.stress_d10, 1)}`)}
    ${f ? kpi("P(dno już zaliczone)", pct(f.p_bottomed, 0), `P(>10% niżej) ${pct(f.p_deep, 0)} · P(bessa) ${pct(f.p_bear, 0)}`)
        : x.naive ? kpi("Historycznie: głębiej niż −20%", pct(x.naive.p_beyond["-20"], 0), `−15%: ${pct(x.naive.p_beyond["-15"], 0)} · −25%: ${pct(x.naive.p_beyond["-25"], 0)} · −30%: ${pct(x.naive.p_beyond["-30"], 0)}`) : ""}
    ${kpi(x.vol_name + (x.vol_fallback ? " (VIX)" : ""), fmt(x.vol, 1), "indeks zmienności tego rynku")}
  </div>

  ${f ? `<div class="section">Prognoza dna <small>analogi historyczne + Monte Carlo — przeszła test walk-forward</small></div>${forecastHTML(x)}`
     : `<div class="section">Gdzie kończyły się takie korekty <small>historia tego indeksu — fakty, nie model</small></div>${naiveHTML(x)}`}

  <div class="section">${BS() ? "Bottom Score i Stress" : "Stress"} na tle faz <small>tło = faza rynku</small></div>
  <div class="card"><div id="c_tl" class="chart"></div>
  <div class="note">${BS() ? "Bottom Score (zielony) = P(dno blisko), walk-forward. " : ""}Stress (czerwony) = ile strachu teraz na tle historii. Klasyczny dołek: Stress szczytuje w Kapitulacji (czerwone tło), potem spada.</div></div>

  <div class="section">Wskaźniki <small>wartość · percentyl historii · momentum vs średnia 3d i 10d</small></div>
  <div class="grid g3">${x.cards.map((c, i) => cardHTML(c, i)).join("")}</div>

  <div class="section">Warunki faz dzisiaj <small>ile brakuje do każdej fazy</small></div>
  <div class="conds">${[4, 6, 5, 3, 2, 1].map(i => condHTML(i, p.conditions[i])).join("")}</div>

  <div class="section">Statystyki faz <small>historia tego indeksu, zakończone epizody</small></div>
  <div class="card tbl">${phaseStatsHTML(x)}</div>

  <div class="section">Historia korekt ≥10%</div>
  <div class="grid g2">
    <div class="card tbl">${corrHTML(x)}</div>
    <div class="card"><h3>Drawdown — cała historia</h3><div id="c_ddh" class="chart"></div></div>
  </div>`;
  $("#app").innerHTML = h;

  if (f) drawForecast(x); else drawNaive(x);
  drawTimeline(x);
  x.cards.forEach((c, i) => drawSpark(c, i));
  plot("c_ddh", [{ x: x.dd_hist.d, y: x.dd_hist.dd, type: "scatter", mode: "lines", fill: "tozeroy",
    line: { color: "#e5484d", width: 1.5 }, fillcolor: "rgba(229,72,77,.15)", hovertemplate: "%{y:.1%}", name: "Drawdown" }],
    { showlegend: false, yaxis: { tickformat: ".0%", gridcolor: "#1f242b" }, shapes: [-0.1, -0.2].map(y => hline(y, "#3a404a")) });
}

function naiveHTML(x) {
  const v = x.naive;
  if (!v) return `<div class="card note">Brak aktywnej korekty (spadek płytszy niż −5%). Sekcja włączy się automatycznie.</div>`;
  return `<div class="grid g2"><div class="card">
    <h3>Korekty ${x.name}, które doszły do ${pct(v.dd_low)} (n=${v.n})</h3>
    <div class="big-fc">${pct(v.p50)} <span style="font-size:20px;color:var(--text-2)">→ ${fmt(v.lvl_p50, 0)}</span></div>
    <div style="margin:6px 0 12px;color:var(--text-2)">mediana końcowej głębokości · mediana <b class="mono">${fmt(v.days_med)}</b> sesji od tego poziomu do dna (IQR ${fmt(v.days_p25)}–${fmt(v.days_p75)})</div>
    <table><tr><th>Percentyl historii</th><th class="n">Głębokość</th><th class="n">Poziom</th></tr>
      <tr><td>Płytko (90.)</td><td class="n">${pct(v.p90)}</td><td class="n">${fmt(v.lvl_p90, 0)}</td></tr>
      <tr><td>Górny kwartyl (75.)</td><td class="n">${pct(v.p75)}</td><td class="n">${fmt(v.lvl_p75, 0)}</td></tr>
      <tr><td><b>Mediana</b></td><td class="n"><b>${pct(v.p50)}</b></td><td class="n"><b>${fmt(v.lvl_p50, 0)}</b></td></tr>
      <tr><td>Dolny kwartyl (25.)</td><td class="n">${pct(v.p25)}</td><td class="n">${fmt(v.lvl_p25, 0)}</td></tr>
      <tr><td>Głęboko (10.)</td><td class="n">${pct(v.p10)}</td><td class="n">${fmt(v.lvl_p10, 0)}</td></tr></table>
    <div class="note">Prognoza z analogów nie przeszła testu walk-forward (zakładka Sprawdzalność), więc pokazuję czystą historię: jak kończyły się wszystkie wcześniejsze korekty, które doszły co najmniej tak głęboko jak obecna.</div></div>
    <div class="card"><h3>Szansa, że korekta pójdzie głębiej niż…</h3><div id="c_naive" class="chart sm"></div>
    <div class="note">Na podstawie ${v.n} zakończonych korekt tego indeksu od 2004 roku.</div></div></div>`;
}
function drawNaive(x) {
  const v = x.naive; if (!v) return;
  const ks = ["-15", "-20", "-25", "-30"];
  plot("c_naive", [{ x: ks.map(k => k + "%"), y: ks.map(k => v.p_beyond[k]), type: "bar", marker: { color: ["#e0a019", "#e5484d", "#b3343a", "#7f1d1d"] },
    text: ks.map(k => pct(v.p_beyond[k], 0)), textposition: "outside", hovertemplate: "%{x}: %{y:.0%}<extra></extra>" }],
    { showlegend: false, hovermode: "closest", yaxis: { tickformat: ".0%", range: [0, 1], gridcolor: "#1f242b" } });
}

function forecastHTML(x) {
  const f = x.forecast;
  return `<div class="grid g2">
    <div class="card">
      <h3>Najbardziej prawdopodobne dno</h3>
      <div class="big-fc">${fmt(f.trough_med, 0)} <span style="font-size:20px;color:var(--text-2)">(${pct(f.depth_med)})</span></div>
      <div style="margin:6px 0 14px;color:var(--text-2)">za ~<b class="mono">${fmt(f.days_med)}</b> sesji (IQR ${fmt(f.days_p25)}–${fmt(f.days_p75)}) · dalszy spadek od kursu: <b class="mono">${pct(f.further_med)}</b></div>
      <table>
        <tr><th>Scenariusz</th><th class="n">Poziom</th><th class="n">Od szczytu</th></tr>
        <tr><td>Optymistyczny (90. pct)</td><td class="n">${fmt(f.trough_p90, 0)}</td><td class="n">${pct(f.depth_p90)}</td></tr>
        <tr><td>Strefa kupna — górna (75.)</td><td class="n">${fmt(f.trough_p75, 0)}</td><td class="n">${pct(f.trough_p75 / f.peak - 1)}</td></tr>
        <tr><td><b>Mediana</b></td><td class="n"><b>${fmt(f.trough_med, 0)}</b></td><td class="n"><b>${pct(f.depth_med)}</b></td></tr>
        <tr><td>Strefa kupna — dolna (25.)</td><td class="n">${fmt(f.trough_p25, 0)}</td><td class="n">${pct(f.trough_p25 / f.peak - 1)}</td></tr>
        <tr><td>Pesymistyczny (10. pct)</td><td class="n">${fmt(f.trough_p10, 0)}</td><td class="n">${pct(f.depth_p10)}</td></tr>
      </table>
      <div class="grid g4" style="margin-top:12px;grid-template-columns:repeat(4,1fr)">
        ${mini("Dno zaliczone", f.p_bottomed)}${mini("Dno blisko (<3%)", f.p_near)}${mini(">10% niżej", f.p_deep)}${mini("Bessa (≤−20%)", f.p_bear)}
      </div>
      <div class="note">Próba: ${f.n_analogs} najbliższych dni z ${f.n_episodes} epizodów; ${pct(f.shrink, 0)} wagi przesunięte do base rate (mało epizodów = mniej zaufania).
      Najbliższe epizody: ${f.analog_eps.map(e => `${e.start.slice(0, 7)} (${pct(e.final_dd, 0)})`).join(", ")}.</div>
    </div>
    <div class="card"><h3>Kurs + ścieżki Monte Carlo (60 sesji)</h3><div id="c_fc" class="chart"></div></div>
    <div class="card"><h3>Rozkład głębokości dna (od szczytu)</h3><div id="c_hist" class="chart sm"></div></div>
  </div>`;
}
const mini = (l, v) => `<div><div style="font-size:11px;color:var(--muted)">${l}</div><div class="mono" style="font-size:18px;font-weight:700">${pct(v, 0)}</div></div>`;

function drawForecast(x) {
  const f = x.forecast, c = x.chart, n = c.d.length, s = Math.max(0, n - 180);
  const d = c.d.slice(s), cl = c.close.slice(s);
  const tr = [{ x: d, y: cl, name: "Kurs", type: "scatter", mode: "lines", line: { color: "#eceae4", width: 2 }, hovertemplate: "%{y:,.0f}" },
    { x: d, y: c.peak.slice(s), name: "Rekord", type: "scatter", mode: "lines", line: { color: "#7d7b74", width: 1, dash: "dot" }, hovertemplate: "%{y:,.0f}" }];
  if (f.fan && x.fan_dates) {
    const fd = [d[d.length - 1], ...x.fan_dates], last = cl[cl.length - 1];
    const P = (k) => [last, ...f.fan[k]];
    tr.push({ x: fd, y: P("p95"), line: { width: 0 }, showlegend: false, hoverinfo: "skip", type: "scatter", mode: "lines" });
    tr.push({ x: fd, y: P("p5"), fill: "tonexty", fillcolor: "rgba(57,135,229,.12)", line: { width: 0 }, name: "MC 5–95%", type: "scatter", mode: "lines", hoverinfo: "skip" });
    tr.push({ x: fd, y: P("p75"), line: { width: 0 }, showlegend: false, hoverinfo: "skip", type: "scatter", mode: "lines" });
    tr.push({ x: fd, y: P("p25"), fill: "tonexty", fillcolor: "rgba(57,135,229,.25)", line: { width: 0 }, name: "MC 25–75%", type: "scatter", mode: "lines", hoverinfo: "skip" });
    tr.push({ x: fd, y: P("p50"), line: { color: "#3987e5", width: 2, dash: "dash" }, name: "MC mediana", type: "scatter", mode: "lines", hovertemplate: "%{y:,.0f}" });
  }
  const x1 = x.fan_dates ? x.fan_dates[x.fan_dates.length - 1] : d[d.length - 1];
  plot("c_fc", tr, {
    yaxis: { tickformat: ",.0f", gridcolor: "#1f242b" },
    shapes: [{ type: "rect", xref: "x", x0: d[0], x1, y0: f.trough_p25, y1: f.trough_p75, fillcolor: "rgba(47,179,107,.10)", line: { width: 0 } },
      { type: "line", xref: "x", x0: d[0], x1, y0: f.trough_med, y1: f.trough_med, line: { color: "#2fb36b", width: 1.5, dash: "dash" } }],
    annotations: [{ xref: "paper", x: 0.01, y: f.trough_med, text: `Dno (mediana) ${fmt(f.trough_med, 0)}`, showarrow: false, font: { color: "#2fb36b", size: 11 }, yshift: 10, xanchor: "left" }],
  });
  plot("c_hist", [{ x: f.hist.x.map(v => v / 100), y: f.hist.y, type: "bar", marker: { color: "#3987e5", line: { color: "#13161b", width: 1 } }, hovertemplate: "%{x:.1%}: %{y:.1f}%<extra></extra>", name: "" }],
    { showlegend: false, bargap: 0.05, hovermode: "closest", xaxis: { tickformat: ".0%", gridcolor: "#1f242b" }, yaxis: { ticksuffix: "%", gridcolor: "#1f242b" },
      shapes: [{ type: "line", x0: f.depth_med, x1: f.depth_med, yref: "paper", y0: 0, y1: 1, line: { color: "#2fb36b", width: 2, dash: "dash" } },
        { type: "line", x0: x.dd, x1: x.dd, yref: "paper", y0: 0, y1: 1, line: { color: "#eceae4", width: 1, dash: "dot" } }],
      annotations: [{ x: x.dd, yref: "paper", y: 1, text: "dziś", showarrow: false, font: { size: 11 }, yshift: 6 },
        { x: f.depth_med, yref: "paper", y: 0.9, text: "mediana", showarrow: false, font: { size: 11, color: "#2fb36b" }, xshift: -30 }] });
}

function drawTimeline(x) {
  const c = x.chart, n = c.d.length, s = Math.max(0, n - 250);
  const d = c.d.slice(s), ph = c.phase.slice(s);
  const shapes = [];
  let st = 0;
  for (let i = 1; i <= d.length; i++) {
    if (i === d.length || ph[i] !== ph[st]) {
      if (ph[st]) shapes.push({ type: "rect", xref: "x", yref: "paper", x0: d[st], x1: d[Math.min(i, d.length - 1)], y0: 0, y1: 1,
        fillcolor: D.phases[ph[st]].color + "26", line: { width: 0 }, layer: "below" });
      st = i;
    }
  }
  plot("c_tl", [
    ...(BS() && c.bottom ? [{ x: d, y: c.bottom.slice(s), name: "Bottom Score", type: "scatter", mode: "lines", line: { color: "#2fb36b", width: 2.5 }, hovertemplate: "%{y:.0f}" }] : []),
    { x: d, y: c.stress.slice(s), name: "Stress", type: "scatter", mode: "lines", line: { color: "#e5484d", width: 2 }, hovertemplate: "%{y:.0f}" },
    { x: d, y: ph.map(v => v ? D.phases[v].short : null), name: "Faza", type: "scatter", mode: "none", hovertemplate: "%{y}", yaxis: "y2", showlegend: false },
  ], { yaxis: { range: [0, 100], gridcolor: "#1f242b" }, yaxis2: { overlaying: "y", visible: false, type: "category" }, shapes });
}

function cardHTML(c, i) {
  const v = c.key === "div" ? (c.value >= 1 ? "TAK" : "NIE") : c.value == null ? "—" : fmt(c.value, c.dec) + (c.unit || "");
  const p = c.pct;
  return `<div class="card ind">
    <div class="row1"><div><div class="name">${c.label}</div><div class="value">${v}</div></div>${pill(c.status)}</div>
    <div class="mom"><span>vs 3d ${arrow(c.d3, false, 1e-6)} <b>${c.d3 == null ? "—" : (c.d3 > 0 ? "+" : "") + fmt(c.d3, Math.max(c.dec, 1))}</b></span>
      <span>vs 10d ${arrow(c.d10, false, 1e-6)} <b>${c.d10 == null ? "—" : (c.d10 > 0 ? "+" : "") + fmt(c.d10, Math.max(c.dec, 1))}</b></span></div>
    ${p == null ? "" : `<div><div class="pctbar"><i style="width:${p * 100}%"></i></div><div class="pctlbl"><span>percentyl historii</span><span class="mono">${fmt(p * 100)}%</span></div></div>`}
    <div id="sp${i}" class="spark"></div>
    <div class="verdict">${c.verdict}</div>
    <div class="explain">${c.explain}</div>
  </div>`;
}
function drawSpark(c, i) {
  const col = { far: "#7d7b74", approach: "#e0a019", zone: "#e5484d", past: "#2fb36b", risk: "#a855f7" }[c.status] || "#b4b2a9";
  Plotly.newPlot("sp" + i, [
    { x: c.spark.d, y: c.spark.v, type: "scatter", mode: "lines", line: { color: col, width: 2 }, hovertemplate: "%{x}: %{y:.2f}<extra></extra>" },
    { x: c.spark.d, y: c.spark.ma, type: "scatter", mode: "lines", line: { color: "#7d7b74", width: 1, dash: "dot" }, hoverinfo: "skip" },
  ], LAYOUT({ margin: { l: 0, r: 0, t: 2, b: 2 }, showlegend: false, hovermode: "closest",
    xaxis: { visible: false }, yaxis: { visible: false } }), CFG);
}

function condHTML(i, c) {
  const q = D.phases[i];
  const ok = c.items.filter(t => t[1]).length;
  return `<div class="cond" style="border-left:3px solid ${q.color}">
    <h4><span>${i}. ${q.short}</span><span class="mono" style="color:${c.ok ? q.color : "var(--muted)"}">${ok}/${c.items.length}${c.ok ? " ✓" : ""}</span></h4>
    <ul>${c.items.map(t => `<li class="${t[1] ? "ok" : ""}">${t[0]}</li>`).join("")}</ul></div>`;
}

function phaseStatsHTML(x) {
  return `<table><tr><th>Faza</th><th class="n">Dni w historii</th><th class="n">Śr. długość</th><th class="n">Mediana dalszego spadku</th>
    <th class="n">P(dno blisko)</th><th class="n">Zwrot 20 sesji</th><th class="n">Zwrot 60 sesji</th><th class="n">Dołki w tej fazie</th></tr>
    ${x.phase_stats.map(s => `<tr class="${s.phase === x.phase.id ? "cur" : ""}"><td><span style="color:${D.phases[s.phase].color}">●</span> ${s.phase}. ${D.phases[s.phase].short}</td>
      <td class="n">${s.days}</td><td class="n">${s.avg_run == null ? "—" : fmt(s.avg_run, 1)}</td><td class="n">${pct(s.further_med)}</td>
      <td class="n">${pct(s.p_near, 0)}</td><td class="n">${pct(s.ret20_med, 1, true)}</td><td class="n">${pct(s.ret60_med, 1, true)}</td>
      <td class="n">${s.troughs_here}/${s.troughs_total}</td></tr>`).join("")}</table>
    <div class="note">„Dołki w tej fazie” = w ilu historycznych korektach ≥10% dzień dna wypadł w danej fazie. „Mediana dalszego spadku” = ile jeszcze typowo spadało do dna epizodu.</div>`;
}
function corrHTML(x) {
  const rows = [...x.corrections].reverse();
  return `<table><tr><th>Szczyt</th><th>Dno</th><th class="n">Głębokość</th><th class="n">Sesji do dna</th><th class="n">Sesji do odrobienia</th><th class="n">Max ${x.vol_name}</th></tr>
    ${rows.map(r => `<tr class="${r.ongoing ? "cur" : ""}"><td>${r.peak}</td><td>${r.trough}${r.ongoing ? " *" : ""}</td><td class="n">${pct(r.depth)}</td>
      <td class="n">${r.days}</td><td class="n">${r.recovery == null ? "trwa" : r.recovery}</td><td class="n">${fmt(r.vol_peak, 1)}</td></tr>`).join("")}</table>
    <div class="note">* trwająca korekta (dno = najniższe zamknięcie do dziś).</div>`;
}

/* ---------------- METODOLOGIA ---------------- */
function renderMeta() {
  const ks = ORDER.filter(k => D.indices[k]);
  let h = `<div class="section">Walidacja walk-forward <small>czy „60%” znaczy 60%?</small></div>
  <div class="grid g2">
    <div class="card"><h3>Kalibracja Bottom Score</h3><div id="c_cal" class="chart"></div>
      <div class="note">Oś X: co model przewidywał, oś Y: jak często się sprawdziło. Idealnie = przekątna. Liczone walk-forward: każdy dzień tylko na epizodach zakończonych wcześniej.</div></div>
    <div class="card tbl"><h3>Skuteczność</h3><table><tr><th>Indeks</th><th class="n">Dni testu</th><th class="n">Brier model</th><th class="n">Brier base</th><th class="n">Skill</th></tr>
      ${ks.map(k => { const v = D.indices[k].validation; return v ? `<tr><td>${D.indices[k].name}</td><td class="n">${v.n}</td><td class="n">${fmt(v.brier, 3)}</td><td class="n">${fmt(v.brier_base, 3)}</td>
        <td class="n" style="color:${v.skill > 0.03 ? "var(--past)" : v.skill < -0.03 ? "var(--zone)" : "var(--text-2)"}">${pct(v.skill, 1, true)}</td></tr>` : ""; }).join("")}</table>
      <div class="note">Skill = o ile model lepszy od samego drawdownu (base rate). &gt;0 = wskaźniki dodają informację. ≤0 = traktuj Bottom Score jak base rate.</div></div>
  </div>
  <div class="section">Historyczne dołki — co pokazywał system</div>
  ${ks.map(k => troughTable(D.indices[k])).join("")}
  <div class="section">Jak to działa</div>
  <div class="card" style="font-size:13.5px;line-height:1.65">
    <p><b>Fazy (1–6)</b> — reguły na percentylach indeksu zmienności danego rynku (VIX/VXN/RVX/VXD), strukturze VIX/VIX3M, VVIX, kredycie (HYG/IEF, HY OAS), breadth, RSI, dywergencji. Priorytet: Kapitulacja → Bessa → Dno zaliczone → Eskalacja → Pullback → Hossa. Zmiana fazy wymaga 2 sesji potwierdzenia (Eskalacja, Kapitulacja i Bessa wchodzą natychmiast).</p>
    <p><b>Bottom Score</b> = P(do końca korekty cena nie spadnie więcej niż 3%). k-NN na 7 cechach (drawdown, percentyl zmienności, odwrót zmienności od szczytu 10d, zmienność vs średnia 10d, VIX/VIX3M, kredyt 20d, log dni od szczytu), ważone odległością, tylko epizody zakończone przed danym dniem. Shrinkage do base rate: p = (n·p_analog + 6·p_base)/(n+6), n = liczba niezależnych epizodów.</p>
    <p><b>Prognoza dna</b> = rozkład z dwóch źródeł: (A) faktyczny dalszy spadek do dna w analogach, (B) Monte Carlo — 4000 ścieżek 120 sesji z bootstrapu blokowego (bloki 10 sesji, wyrównane w czasie) zwrotów następujących po analogach. Dno epizodu = min(dotychczasowy dołek, przyszłe minimum). Mediana i percentyle z połączonego rozkładu.</p>
    <p><b>Stress</b> = średnia percentyli: zmienność, VIX/VIX3M, VVIX, kredyt, RSI, drawdown (0–100).</p>
    <p><b>Ograniczenia:</b> efektywna próba to kilkanaście–kilkadziesiąt epizodów, nie tysiące dni. Przedziały są szerokie, bo taka jest prawda o rynku. Dane: Yahoo Finance (opóźnione ~15 min w sesji), FRED, CNN.</p>
  </div>`;
  $("#app").innerHTML = h;
  const tr = [{ x: [0, 1], y: [0, 1], type: "scatter", mode: "lines", line: { color: "#3a404a", dash: "dot" }, name: "Idealna", hoverinfo: "skip" }];
  ks.forEach(k => { const v = D.indices[k].validation; if (v) tr.push({ x: v.calib.map(c => c.pred), y: v.calib.map(c => c.real), text: v.calib.map(c => "n=" + c.n),
    type: "scatter", mode: "lines+markers", marker: { size: 9, line: { color: "#13161b", width: 2 } }, line: { color: SERIES[k], width: 2 }, name: D.indices[k].name,
    hovertemplate: "przewidywane %{x:.0%} → realnie %{y:.0%} (%{text})<extra></extra>" }); });
  plot("c_cal", tr, { hovermode: "closest", xaxis: { range: [0, 1], tickformat: ".0%", gridcolor: "#1f242b", title: "przewidywane" },
    yaxis: { range: [0, 1], tickformat: ".0%", gridcolor: "#1f242b", title: "zrealizowane" } });
}
function troughTable(x) {
  return `<div class="card tbl" style="margin-bottom:12px"><h3>${x.name}</h3>
  <table><tr><th>Szczyt</th><th>Dno</th><th class="n">Głębokość</th><th class="n">Sesji</th><th>Faza w dniu dna</th><th>Kapitulacja ±5 sesji</th><th class="n">Bottom Score w dniu dna</th><th class="n">Sygnał „Dno zaliczone” po</th><th class="n">…cena vs dno</th></tr>
  ${[...x.troughs].reverse().map(t => `<tr><td>${t.peak}</td><td>${t.trough}</td><td class="n">${pct(t.depth)}</td><td class="n">${t.days}</td>
    <td>${t.phase_at ? `<span style="color:${D.phases[t.phase_at].color}">●</span> ${D.phases[t.phase_at].short}` : "—"}</td><td>${t.phase4_near ? "✓" : "—"}</td>
    <td class="n">${t.score_at == null ? "—" : fmt(t.score_at, 0)}</td><td class="n">${t.p5_lag == null ? "brak" : t.p5_lag + " sesji"}</td><td class="n">${t.p5_vs_low == null ? "—" : pct(t.p5_vs_low, 1, true)}</td></tr>`).join("")}
  </table></div>`;
}

/* ---------------- LIDERZY SPADKÓW ---------------- */
let LEV = null;
const IXC = { NDX: "#d95926", SPX: "#3987e5", DJI: "#c98500", RUT: "#199e70" };
function renderLead() {
  const R = D.rotation;
  if (!R) { $("#app").innerHTML = '<div class="loading">Brak danych długiej historii (spróbuj przy następnym przeliczeniu).</div>'; return; }
  const N = R.names, S = R.sectors, c = R.current, lv = R.leader_vs_laggard, cap = R.cap_vs_calm;
  const done = R.events.filter(e => e.complete);
  if (!LEV) LEV = R.events[R.events.length - 1].start;
  const lvRow = (lab, g) => g && g.n ? ["60", "120", "250"].map(h => g[h] && g[h].n ? `<td class="n">${pct(g[h].lead_med, 1, true)} / ${pct(g[h].lag_med, 1, true)}<br><span style="color:${g[h].rel_med > 0 ? "var(--past)" : "var(--zone)"}">${pct(g[h].rel_med, 1, true)} · lider lepszy ${pct(g[h].lead_wins, 0)}</span></td>` : "<td>—</td>").join("") : "";
  const capS = cap && cap.summary;
  let h = `
  <div class="hero" style="--phase-bg:#3987e533">
    <span class="pill st-far">${R.since.slice(0, 4)}–${R.last.slice(0, 4)} · indeksy + sektory S&amp;P</span>
    <h2>Czy korekty mają swoich liderów i co wtedy kupować?</h2>
    <ul style="margin:8px 0 0;padding-left:18px;line-height:1.7;color:var(--text-2)">${R.conclusion.map(x => `<li>${x}</li>`).join("")}</ul>
  </div>

  <div class="section">Dziś: kto prowadzi spadki <small>spadek od 52-tygodniowego szczytu</small></div>
  <div class="grid g2">
    <div class="card"><div id="c_now" class="chart"></div></div>
    <div class="card"><h3>Siła Nasdaq vs S&amp;P 500 (NDX/SPX) i szerokość rynku (RSP/SPY)</h3><div id="c_rs" class="chart sm"></div><div id="c_ew" class="chart sm"></div>
      <div class="note">NDX/SPX spada = technologia słabsza od rynku. RSP/SPY rośnie = przeciętna spółka radzi sobie lepiej niż giganci (rotacja, nie wyprzedaż wszystkiego). 20 sesji: NDX/SPX ${pct(c.rs_20d, 1, true)}, 60 sesji ${pct(c.rs_60d, 1, true)}${c.ew_60d != null ? `, RSP/SPY 60 sesji ${pct(c.ew_60d, 1, true)}` : ""}.</div></div>
  </div>

  <div class="section">Co kupować: lider spadków czy indeks, który się trzyma? <small>mediany zwrotów: lider / najsilniejszy · różnica · jak często lider wygrał</small></div>
  <div class="card tbl"><table>
    <tr><th>Sytuacja</th><th class="n">n</th><th class="n">60 sesji</th><th class="n">120 sesji</th><th class="n">250 sesji</th></tr>
    <tr><td><b>Selektywna korekta</b> (lider −10%, najsilniejszy płycej niż −6%)<br><span class="note">kupno w dniu, gdy lider dotknął −10%</span></td><td class="n">${lv.selective.n}</td>${lvRow("", lv.selective)}</tr>
    <tr><td><b>Szeroka korekta</b><br><span class="note">kupno w dniu, gdy lider dotknął −10%</span></td><td class="n">${lv.broad.n}</td>${lvRow("", lv.broad)}</tr>
    <tr><td>Wszystkie zdarzenia</td><td class="n">${lv.all.n}</td>${lvRow("", lv.all)}</tr>
    ${capS ? `<tr class="cur"><td><b>Indeks wchodzi w KAPITULACJĘ, inny jest w hossie</b> (DD &gt; −5%)<br><span class="note">od 2006, kupno w dniu wejścia w Kapitulację</span></td><td class="n">${capS["250"].n}</td>
      ${["60", "120", "250"].map(k => capS[k].n ? `<td class="n">${pct(capS[k].L_med, 1, true)} / ${pct(capS[k].O_med, 1, true)}<br><span style="color:${capS[k].rel_med > 0 ? "var(--past)" : "var(--zone)"}">${pct(capS[k].rel_med, 1, true)} · lider lepszy ${pct(capS[k].lead_wins, 0)}</span><br><span class="note">% zysk: ${pct(capS[k].L_win, 0)} / ${pct(capS[k].O_win, 0)}</span></td>` : "<td>—</td>").join("")}</tr>` : ""}
  </table>
  <div class="note">Uwaga na małą próbę i jeden gigantyczny wyjątek: po pęknięciu bańki dot-com (2000) kupowanie lidera (Nasdaq) było katastrofą przez lata. Kiedy lider spada z powodu przewartościowania, a nie paniki, „odbicie lidera” nie jest pewnikiem. Szczegóły każdego zdarzenia niżej.</div></div>

  <div class="section">Wszystkie zdarzenia od ${R.since.slice(0, 4)} <small>kliknij wiersz → ścieżki indeksów od szczytu</small></div>
  <div class="card tbl"><table>
    <tr><th>Start</th><th>Dno</th><th>Lider</th><th class="n">NDX</th><th class="n">SPX</th><th class="n">DJI</th><th class="n">RUT</th><th>Sektor lider</th><th>Sektor najodporniejszy</th><th>Typ</th><th class="n">Odbudowa rekordu (lata) NDX / SPX / DJI / RUT</th><th class="n">250 ses. lider vs najsilniejszy</th></tr>
    ${[...R.events].reverse().map(e => { const r = e.recovery_years, f = e.fwd["250"] || e.fwd[250] || {};
      const rel = f[e.leader] != null && f[e.laggard_at10] != null ? f[e.leader] - f[e.laggard_at10] : null;
      return `<tr class="lerow ${e.start === LEV ? "cur" : ""}" data-s="${e.start}" style="cursor:pointer"><td>${e.start}</td><td>${e.trough}${e.complete ? "" : " *"}</td>
      <td><span style="color:${IXC[e.leader]}">●</span> ${N[e.leader]}</td>
      ${["NDX", "SPX", "DJI", "RUT"].map(k => `<td class="n" style="${k === e.leader ? "font-weight:800" : ""}">${pct(e.depth[k], 0)}</td>`).join("")}
      <td>${e.lead_sector ? `${S[e.lead_sector]} ${pct(e.depth[e.lead_sector], 0)}` : "—"}</td><td>${e.best_sector ? `${S[e.best_sector]} ${pct(e.depth[e.best_sector], 0)}` : "—"}</td>
      <td>${e.selective ? '<span class="pill st-approach">selektywna</span>' : '<span class="pill st-far">szeroka</span>'}</td>
      <td class="n">${["NDX", "SPX", "DJI", "RUT"].map(k => r[k] == null ? "—" : fmt(r[k], 1)).join(" / ")}</td>
      <td class="n" style="color:${rel == null ? "inherit" : rel > 0 ? "var(--past)" : "var(--zone)"}">${rel == null ? "—" : pct(rel, 0, true)}</td></tr>`; }).join("")}
  </table><div class="note">Korekta = spadek od 52-tygodniowego szczytu (standard rynkowy). Głębokości = max spadek każdego indeksu w czasie zdarzenia. Sektory dostępne od 1999. Odbudowa = lata od początku zdarzenia do powrotu na szczyt z roku przed zdarzeniem. * = trwa.</div></div>
  <div id="ledet"></div>`;
  $("#app").innerHTML = h;
  // dziś: słupki
  const keys = ["NDX", "SPX", "DJI", "RUT", ...Object.keys(S)].filter(k => c[k] != null);
  plot("c_now", [{ y: keys.map(k => N[k] || S[k]), x: keys.map(k => c[k]), type: "bar", orientation: "h",
    marker: { color: keys.map(k => IXC[k] || "#5b6170") }, text: keys.map(k => pct(c[k], 1)), textposition: "inside", insidetextanchor: "start", textfont: { color: "#fff" }, hovertemplate: "%{y}: %{x:.1%}<extra></extra>" }],
    { showlegend: false, hovermode: "closest", margin: { l: 120, r: 40, t: 10, b: 30 }, xaxis: { tickformat: ".0%", gridcolor: "#1f242b" }, yaxis: { autorange: "reversed" },
      shapes: [{ type: "line", x0: -0.1, x1: -0.1, yref: "paper", y0: 0, y1: 1, line: { color: "#3a404a", dash: "dot" } }] });
  plot("c_rs", [{ x: R.rs_chart.d, y: R.rs_chart.v, type: "scatter", mode: "lines", line: { color: "#d95926", width: 2 }, name: "NDX/SPX", hovertemplate: "%{y:.3f}" }], { showlegend: false, margin: { l: 52, r: 16, t: 6, b: 24 } });
  if (R.ew_chart) plot("c_ew", [{ x: R.ew_chart.d, y: R.ew_chart.v, type: "scatter", mode: "lines", line: { color: "#3987e5", width: 2 }, name: "RSP/SPY", hovertemplate: "%{y:.3f}" }], { showlegend: false, margin: { l: 52, r: 16, t: 6, b: 24 } });
  document.querySelectorAll(".lerow").forEach(el => el.onclick = () => { LEV = el.dataset.s; document.querySelectorAll(".lerow").forEach(r => r.classList.toggle("cur", r === el)); drawLeadDet(); });
  drawLeadDet();
}
function drawLeadDet() {
  const R = D.rotation, e = R.events.find(z => z.start === LEV); if (!e) return;
  const N = R.names, p = e.path;
  $("#ledet").innerHTML = `<div class="section">Zdarzenie ${e.start} <small>lider: ${N[e.leader]} · indeksy znormalizowane do 100 w dniu startu</small></div>
    <div class="card"><div id="c_path" class="chart"></div></div>`;
  plot("c_path", ["NDX", "SPX", "DJI", "RUT"].filter(k => p[k] && p[k].length).map(k => ({ x: p.t.map(t => t / 365.25), y: p[k], name: N[k], type: "scatter", mode: "lines",
    line: { color: IXC[k], width: k === e.leader ? 3 : 2 }, hovertemplate: "%{y:.0f}" })),
    { xaxis: { title: "lata od startu", gridcolor: "#1f242b" }, yaxis: { gridcolor: "#1f242b" }, shapes: [hline(100, "#3a404a")] });
}

/* ---------------- SPRAWDZALNOŚĆ ---------------- */
let CK = "NDX", CKT = null;
const VCOL = { "KAPITULACJA": "var(--past)", "TYLKO ESKALACJA": "var(--approach)", "BESSA": "#c4553f", "PRZEGAPIONE": "var(--zone)", "TRWA": "var(--muted)" };
const MCOL = { good: "var(--past)", weak: "var(--approach)", bad: "var(--zone)", na: "var(--muted)" };
function cnt(c, p, best) {
  if (!c || !c[p]) return "—";
  const x = c[p], col = x.must ? D.phases[p].color : (x.ok >= x.n - 1 ? "var(--text)" : "var(--muted)");
  return `<span class="mono" style="color:${col};font-weight:${x.must ? 800 : 500}">${x.ok}/${x.n}${x.must ? " ✓" : ""}</span>` +
    (best != null ? `<span class="mono" style="color:var(--muted);font-size:11px"> (max ±5: ${best}/6)</span>` : "");
}
function renderCheck() {
  const ks = ORDER.filter(k => D.indices[k] && D.indices[k].verify);
  if (!ks.includes(CK)) CK = ks[0];
  const tiles = ks.map(k => {
    const v = D.indices[k].verify, s = v.summary, m = v.model;
    return `<div class="card tile ${k === CK ? "on" : ""}" data-ck="${k}" style="border-top:3px solid ${MCOL[m.level]}">
      <div class="name">${D.indices[k].name}</div>
      ${s ? `<div style="margin-top:8px;font-size:12.5px;line-height:1.7">
        Dołki ≥10%: <b class="mono">${s.n}</b><br>
        Kapitulacja w oknie ±5 sesji: <b class="mono" style="color:${s.hit >= .6 ? "var(--past)" : "var(--approach)"}">${pct(s.hit, 0)}</b><br>
        Tylko eskalacja / bessa: <b class="mono">${pct(s.esc_only, 0)}</b> · przegapione: <b class="mono" style="color:${s.missed > 0 ? "var(--zone)" : "inherit"}">${pct(s.missed, 0)}</b><br>
        Sygnał „Dno zaliczone” po dołku: <b class="mono">${pct(s.p5_found, 0)}</b>${s.p5_lag_med != null ? ` · mediana ${fmt(s.p5_lag_med)} sesji, ${pct(s.p5_slip_med, 1, true)} nad dołkiem` : ""}</div>` : ""}
      <div style="margin-top:8px;font-size:12px;color:${MCOL[m.level]}"><b>Bottom Score:</b> ${m.text}</div></div>`;
  }).join("");
  const x = D.indices[CK], v = x.verify;
  const rows = [...v.troughs].reverse();
  if (!CKT || !rows.find(t => t.trough === CKT)) CKT = rows[0] && rows[0].trough;
  const sig = v.signals || {};
  const sigRow = (lab, s, col) => s ? `<tr><td>${col ? `<span style="color:${col}">●</span> ` : ""}${lab}</td><td class="n">${s.signals}</td><td class="n">${pct(s.further_med)}</td>
    <td class="n">${pct(s.within3, 0)}</td><td class="n">${pct(s.deeper10, 0)}</td><td class="n">${pct(s.ret20_med, 1, true)}</td><td class="n">${pct(s.ret60_med, 1, true)}</td><td class="n">${pct(s.win60, 0)}</td></tr>` : "";
  let h = `
  <div class="hero" style="--phase-bg:#2fb36b33">
    <span class="pill st-past">SPRAWDZALNOŚĆ</span>
    <h2>Czy system działał w historii?</h2>
    <div class="headline">Dla każdego dołka ≥8% pokazujemy dokładnie to, co system widział <b>w dniu dna</b>: fazę, checklisty warunków (np. Kapitulacja 4/6), wartości strachu, kredytu i Bottom Score oraz po ilu sesjach przyszedł sygnał „Dno zaliczone”. Wszystko liczone przyczynowo — bez znajomości przyszłości (fazy z danych do dnia t, Bottom Score walk-forward).</div>
  </div>
  ${testsHTML()}
  <div class="grid g4" style="margin-top:14px">${tiles}</div>
  ${(v.conclusions || []).length ? `<div class="card" style="margin-top:14px;border-left:4px solid var(--past)"><h3>Wnioski z danych — ${x.name}</h3>
    <ul style="margin:0;padding-left:18px;line-height:1.7">${v.conclusions.map(c => `<li>${c}</li>`).join("")}</ul>
    <div class="note">Liczone automatycznie z historii — zmieniają się razem z danymi.</div></div>` : ""}
  <div class="card" style="margin-top:14px;border-left:4px solid var(--approach)"><h3>Bottom line</h3>
    <div style="font-size:14px;line-height:1.7">Przewaga matematyczna to <b>kupowanie korekt ≥10% w transzach</b>. Kapitulacja to miejsce, gdzie historycznie powstaje większość den — dlatego tam największa transza — ale sama w sobie nie gwarantuje lepszego wyniku niż zakup w innym dniu korekty (w bessie kapitulacji bywa kilka). <b>Nie czekaj wyłącznie na panikę</b>: część den przychodzi bez niej (np. NDX lipiec 2026). Zawsze licz się z tym, że może zejść niżej.</div></div>

  <div class="section">${x.name}: dołki i stan systemu w dniu dna <small>kliknij wiersz, aby zobaczyć szczegóły</small></div>
  <div class="card tbl"><table>
    <tr><th>Szczyt</th><th>Dno</th><th class="n">Głęb.</th><th class="n">Sesji</th><th>Faza w dniu dna</th><th>Werdykt</th>
      <th>Kapitulacja</th><th>Dno zal.</th><th>Eskalacja</th><th>Bessa</th>
      <th class="n">Max ${x.vol_name} (pct)</th><th class="n">Max VIX/VIX3M</th><th class="n">Max VVIX</th><th class="n">Min RSI</th><th class="n">Kredyt 20d</th>${BS() ? '<th class="n">Bottom Score</th>' : ""}<th class="n">Sygnał 5</th></tr>
    ${rows.map(t => `<tr class="ckrow ${t.trough === CKT ? "cur" : ""}" data-t="${t.trough}" style="cursor:pointer">
      <td>${t.peak}</td><td>${t.trough}${t.complete ? "" : " *"}</td><td class="n">${pct(t.depth)}</td><td class="n">${t.days}</td>
      <td>${t.phase ? `<span style="color:${D.phases[t.phase].color}">●</span> ${D.phases[t.phase].short}` : "—"}${t.phase_raw && t.phase_raw !== t.phase ? ` <span style="color:var(--muted);font-size:11px">(dziś: ${D.phases[t.phase_raw].short})</span>` : ""}</td>
      <td style="color:${VCOL[t.verdict]};font-weight:700">${t.verdict}</td>
      <td>${cnt(t.counts, "4", t.best4_win)}</td><td>${cnt(t.counts, "5")}</td><td>${cnt(t.counts, "3")}</td><td>${cnt(t.counts, "6")}</td>
      <td class="n">${fmt(t.vol_max_win, 1)} (${t.vol_max_pct == null ? "—" : fmt(t.vol_max_pct * 100) + "%"})</td>
      <td class="n" style="color:${t.term_max_win >= 1 ? "var(--zone)" : "inherit"}">${fmt(t.term_max_win, 2)}</td>
      <td class="n">${fmt(t.vvix_max_win, 0)}</td><td class="n" style="color:${t.rsi_min_win <= 30 ? "var(--zone)" : "inherit"}">${fmt(t.rsi_min_win, 0)}</td>
      <td class="n" style="color:${t.credit_20d <= -0.025 ? "var(--risk)" : "inherit"}">${pct(t.credit_20d, 1, true)}</td>
      ${BS() ? `<td class="n">${t.bottom2 == null ? "—" : fmt(t.bottom2, 0)}</td>` : ""}
      <td class="n">${t.p5_lag == null ? "brak" : `${t.p5_lag} ses. ${pct(t.p5_vs_low, 1, true)}`}</td></tr>`).join("")}
  </table>
  <div class="note">Liczby x/n = ile warunków danej fazy było spełnionych w dniu dna; „✓” = spełnione warunki obowiązkowe (faza mogła się włączyć). Max ±5 = najlepszy wynik Kapitulacji w oknie 5 sesji wokół dna. Max wartości liczone w oknie ±5 sesji. Werdykt: KAPITULACJA = w ±5 sesji od dna system pokazał Kapitulację (sygnał T2 trafił w dno). TYLKO ESKALACJA = dno bez paniki, system dawał tylko T1 (to słabszy sygnał — w dniu dna cena i tak jest przy 10-dniowym dołku). BESSA = dno w fazie Bessy. PRZEGAPIONE = system pokazywał Hossę/Pullback. * = trwająca korekta.</div></div>

  <div id="ckdet"></div>

  <div class="section">Mapa dołków: wszystkie 4 indeksy naraz <small>każde dno ≥10% od 2006; w komórce: głębokość · Kapitulacja w dniu dna (max ±5) · werdykt</small></div>
  <div class="card tbl">${mapHTML()}</div>

  <div class="section">Jakość sygnałów faz <small>co działo się po wejściu w fazę vs losowy dzień przy spadku ≥10%</small></div>
  <div class="card tbl"><table>
    <tr><th>Sygnał</th><th class="n">Ile razy</th><th class="n">Mediana dalszego spadku</th><th class="n">Dno w 3%</th><th class="n">&gt;10% niżej</th><th class="n">Zwrot 20 ses.</th><th class="n">Zwrot 60 ses.</th><th class="n">% zysk po 60</th></tr>
    ${sigRow("Dowolny dzień w historii", sig.all)}
    ${sigRow("Losowy dzień przy DD ≤ −10% (punkt odniesienia)", sig.base)}
    ${sigRow("Wejście w 3. ESKALACJA", sig["3"], D.phases[3].color)}${sigRow("Wejście w 4. KAPITULACJA", sig["4"], D.phases[4].color)}${sigRow("Wejście w 5. DNO ZALICZONE", sig["5"], D.phases[5].color)}
  </table><div class="note">Sygnał ma wartość, jeśli po nim dalszy spadek jest mniejszy, a zwroty i % zysku wyższe niż w wierszu odniesienia.</div></div>

  <div class="section">Kalibracja Bottom Score (stara wersja, k-NN) <small>walk-forward — model usunięty, pokazany dla przejrzystości</small></div>
  <div class="grid g2"><div class="card"><div id="c_cal2" class="chart"></div></div>
  <div class="card" style="font-size:13.5px;line-height:1.6">
    <h3>Jak to czytać</h3>
    <p>Każdy punkt: „gdy model mówił X%, dno było blisko w Y% przypadków”. Dobrze skalibrowany model leży na przekątnej i rośnie. Płaska albo opadająca linia = model nie odróżnia sytuacji.</p>
    <p><b>Werdykt dla ${x.name}:</b> <span style="color:${MCOL[v.model.level]}">${v.model.text}</span></p>
    ${x.validation ? `<p class="mono" style="font-size:12px;color:var(--text-2)">Brier model ${fmt(x.validation.brier, 3)} · base ${fmt(x.validation.brier_base, 3)} · skill ${pct(x.validation.skill, 1, true)} · n=${x.validation.n}</p>` : ""}
  </div></div>`;
  $("#app").innerHTML = h;
  document.querySelectorAll("[data-ck]").forEach(el => el.onclick = () => { CK = el.dataset.ck; CKT = null; renderCheck(); });
  document.querySelectorAll(".ckrow").forEach(el => el.onclick = () => { CKT = el.dataset.t; document.querySelectorAll(".ckrow").forEach(r => r.classList.toggle("cur", r === el)); drawCheckDetail(x); });
  drawCheckDetail(x);
  if (x.validation) {
    const vv = x.validation;
    plot("c_cal2", [{ x: [0, 1], y: [0, 1], type: "scatter", mode: "lines", line: { color: "#3a404a", dash: "dot" }, name: "idealnie", hoverinfo: "skip" },
      { x: vv.calib.map(c => c.pred), y: vv.calib.map(c => c.real), text: vv.calib.map(c => "n=" + c.n), type: "scatter", mode: "lines+markers",
        marker: { size: 10, line: { color: "#13161b", width: 2 } }, line: { color: SERIES[CK], width: 2 }, name: x.name,
        hovertemplate: "model %{x:.0%} → realnie %{y:.0%} (%{text})<extra></extra>" }],
      { hovermode: "closest", xaxis: { range: [0, 1], tickformat: ".0%", gridcolor: "#1f242b", title: "model mówił" }, yaxis: { range: [0, 1], tickformat: ".0%", gridcolor: "#1f242b", title: "zrealizowane" } });
  }
}
function testsHTML() {
  const m = D.models; if (!m) return "";
  const ks = ORDER.filter(k => D.indices[k]);
  const ok = (b) => `<b style="color:${b ? "var(--past)" : "var(--zone)"}">${b ? "ZALICZONY" : "NIEZALICZONY"}</b>`;
  const row = (k) => { const md = D.indices[k].models || {}, v1 = md.v1, v2 = md.v2, fc = md.fc;
    return `<tr><td>${D.indices[k].name}</td>
      <td class="n">${v1 ? pct(v1.skill, 1, true) : "—"}</td>
      <td class="n" style="color:${v2 && v2.skill >= .05 ? "var(--past)" : "var(--zone)"}">${v2 ? pct(v2.skill, 1, true) : "—"}</td><td>${v2 ? (v2.monotone ? "rośnie ✓" : "nie ✗") : "—"}</td>
      <td class="n" style="color:${fc && fc.cov_analog >= .7 && fc.cov_analog <= .9 ? "var(--past)" : "var(--zone)"}">${fc ? pct(fc.cov_analog, 0) : "—"}</td>
      <td class="n">${fc ? pct(fc.mae_analog, 1) + " / " + pct(fc.mae_naive, 1) : "—"}</td><td class="n">${fc ? pct(fc.cov_naive, 0) : "—"}</td></tr>`; };
  return `<div class="card" style="margin-top:14px"><h3>Testy modeli (kryteria ustalone przed testem)</h3>
    <div style="font-size:13.5px;line-height:1.7;margin-bottom:8px">
      Bottom Score v2: ${ok(m.bottom.pass)} (${m.bottom.passed}/4) — wymóg: ${m.bottom.rule}. ${m.bottom.pass ? "Pokazywany na stronie." : "<b>Usunięty ze strony.</b>"}<br>
      Prognoza dna z analogów: ${ok(m.forecast.pass)} (${m.forecast.passed}/4) — wymóg: ${m.forecast.rule}. ${m.forecast.pass ? "Pokazywana na stronie." : "<b>Zastąpiona tabelą historyczną.</b>"}</div>
    <table><tr><th>Indeks</th><th class="n">Skill BS v1 (k-NN)</th><th class="n">Skill BS v2</th><th>Kalibracja v2</th><th class="n">Pokrycie 80% (analogi)</th><th class="n">Błąd mediany analogi / naiwna</th><th class="n">Pokrycie 80% (naiwna)</th></tr>
    ${ks.map(row).join("")}</table>
    <div class="note">Skill = poprawa Brier score względem base rate (sam drawdown). Pokrycie 80% = jak często faktyczne dno mieściło się w przedziale 10–90% prognozy (idealnie ~80%). Wszystko walk-forward.</div></div>`;
}
function mapHTML() {
  const tm = D.trough_map || []; const ks = ORDER.filter(k => D.indices[k]);
  return `<table><tr><th>Okres</th>${ks.map(k => `<th>${D.indices[k].name}</th>`).join("")}</tr>
  ${[...tm].reverse().map(r => `<tr><td class="mono">${r.date.slice(0, 7)}</td>${ks.map(k => { const c = r.cells[k];
    if (!c) return "<td>—</td>";
    if (!c.trough) return `<td style="color:var(--muted)">${c.depth == null ? "—" : pct(c.depth, 0)} · bez osobnego dna</td>`;
    return `<td><b class="mono">${pct(c.depth, 0)}</b> · <span class="mono" style="color:${c.k4best >= 4 ? "var(--zone)" : c.k4best >= 3 ? "var(--approach)" : "var(--muted)"}">K ${c.k4}/6 (${c.k4best})</span> · <span style="color:${VCOL[c.verdict] || "var(--muted)"};font-weight:700;font-size:11.5px">${c.verdict}</span></td>`; }).join("")}</tr>`).join("")}
  </table><div class="note">K x/6 (y) = warunki Kapitulacji w dniu dna (najlepszy wynik w ±5 sesjach). „bez osobnego dna” = indeks spadał, ale nie miał w tym oknie własnego dołka ≥8% (pokazany max spadek w ±45 dniach).</div>`;
}
function drawCheckDetail(x) {
  const t = x.verify.troughs.find(z => z.trough === CKT);
  if (!t) { $("#ckdet").innerHTML = ""; return; }
  const c = t.chart;
  $("#ckdet").innerHTML = `<div class="section">Szczegóły: dno ${t.trough} <small>${pct(t.depth)} · ${t.days} sesji od szczytu · ${t.verdict}</small></div>
  <div class="grid g2">
    <div class="card"><h3>Kurs i ${x.vol_name} wokół dna (tło = faza)</h3><div id="ck_px" class="chart sm"></div><div id="ck_vol" class="chart sm" style="height:180px"></div></div>
    <div class="card"><h3>Ile warunków Kapitulacji i „Dno zaliczone” dzień po dniu</h3><div id="ck_cnt" class="chart sm"></div>
      <div class="conds" style="margin-top:10px">${["4", "5", "3"].map(p => condHTML(+p, { ok: t.counts[p].must, items: t.counts[p].items })).join("")}</div>
      <div class="note">Checklisty powyżej = stan w dniu dna.</div></div>
  </div>`;
  const shapes = [];
  let st = 0;
  for (let i = 1; i <= c.d.length; i++) if (i === c.d.length || c.phase[i] !== c.phase[st]) {
    if (c.phase[st]) shapes.push({ type: "rect", xref: "x", yref: "paper", x0: c.d[st], x1: c.d[Math.min(i, c.d.length - 1)], y0: 0, y1: 1, fillcolor: D.phases[c.phase[st]].color + "30", line: { width: 0 }, layer: "below" });
    st = i;
  }
  const vline = { type: "line", xref: "x", yref: "paper", x0: c.t, x1: c.t, y0: 0, y1: 1, line: { color: "#2fb36b", width: 1.5, dash: "dash" } };
  plot("ck_px", [{ x: c.d, y: c.close, type: "scatter", mode: "lines", line: { color: "#eceae4", width: 2 }, name: "Kurs", hovertemplate: "%{y:,.0f}" },
    { x: c.d, y: c.phase.map(p => p ? D.phases[p].short : null), yaxis: "y2", mode: "none", type: "scatter", hovertemplate: "%{y}", showlegend: false }],
    { showlegend: false, shapes: [...shapes, vline], yaxis: { tickformat: ",.0f", gridcolor: "#1f242b" }, yaxis2: { overlaying: "y", visible: false, type: "category" } });
  plot("ck_vol", [{ x: c.d, y: c.vol, type: "scatter", mode: "lines", line: { color: "#e5484d", width: 2 }, name: x.vol_name, hovertemplate: "%{y:.1f}" }],
    { showlegend: false, shapes: [vline], margin: { l: 52, r: 16, t: 4, b: 30 }, yaxis: { gridcolor: "#1f242b" } });
  plot("ck_cnt", [{ x: c.d, y: c.c4, type: "bar", name: "Kapitulacja (z 6)", marker: { color: "#ef4444" } },
    { x: c.d, y: c.c5, type: "bar", name: "Dno zaliczone (z 6)", marker: { color: "#22c55e" } }],
    { barmode: "group", bargap: .15, shapes: [vline], yaxis: { range: [0, 6.2], dtick: 1, gridcolor: "#1f242b" } });
}

load().catch(e => { $("#app").innerHTML = `<div class="loading">Błąd ładowania danych: ${e}</div>`; });
setInterval(() => { load(true).catch(() => {}); }, 5 * 60 * 1000);
