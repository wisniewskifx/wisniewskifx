/* Szczyty i wzrosty — frontend (czyta peaks.json) */
const ORDER = ["SPX", "NDX", "DJI", "RUT"];
const IXC = { NDX: "#d95926", SPX: "#3987e5", DJI: "#c98500", RUT: "#199e70" };
let P = null, IX = "SPX";
const $ = (s) => document.querySelector(s);
const fmt = (x, d = 0) => x == null ? "—" : Number(x).toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (x, d = 1, sign = false) => x == null ? "—" : (sign && x > 0 ? "+" : "") + (x * 100).toLocaleString("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d }) + "%";
const CFG = { responsive: true, displaylogo: false, displayModeBar: "hover", doubleClick: "reset", modeBarButtons: [["zoomIn2d", "zoomOut2d", "autoScale2d"]] };
const LAYOUT = (x = {}) => Object.assign({
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { family: "Inter, sans-serif", color: "#b4b2a9", size: 12 },
  margin: { l: 52, r: 16, t: 10, b: 36 }, xaxis: { gridcolor: "#1f242b", linecolor: "#262b33", zeroline: false },
  yaxis: { gridcolor: "#1f242b", linecolor: "#262b33", zeroline: false }, hovermode: "x unified",
  hoverlabel: { bgcolor: "#1a1e25", bordercolor: "#3a404a", font: { color: "#eceae4" } }, legend: { orientation: "h", y: 1.12, x: 0 },
}, x);
const plot = (id, t, l) => Plotly.newPlot(id, t, LAYOUT(l), CFG);
const ok = (b) => b ? '<b style="color:var(--past)">✓ zaliczony</b>' : '<b style="color:var(--zone)">✗ niezaliczony</b>';

async function load() {
  P = await (await fetch("peaks.json?t=" + Date.now())).json();
  $("#updated").innerHTML = `Przeliczono: ${P.generated}` + (P.synthetic ? ' <span class="badge-syn">DANE TESTOWE</span>' : "");
  const ks = ORDER.filter(k => P.indices[k]);
  $("#tabs").innerHTML = `<a href="index.html" class="navback">← Monitor korekt</a>` + ks.map(k => `<button data-k="${k}"><span class="dot" style="background:${IXC[k]}"></span>${P.indices[k].name}</button>`).join("");
  $("#tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) { IX = b.dataset.k; location.hash = IX; render(); } };
  IX = ks.includes(location.hash.slice(1)) ? location.hash.slice(1) : ks[0];
  render();
}

function render() {
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.k === IX));
  const x = P.indices[IX], C = P.comp, S = P.summary;
  const keys = Object.keys(C).filter(k => x.tests[k] !== undefined);
  const passedKeys = Object.keys(S).filter(k => S[k].pass);
  const litNow = keys.filter(k => x.now[k]);
  const rn = x.rally_now || {};
  let h = `
  <div class="hero" style="--phase-bg:#2fb36b22">
    <span class="pill st-far">${x.name} · ${x.near ? "blisko rekordu (" + pct(x.dd) + ")" : pct(x.dd) + " od rekordu"}</span>
    <h2>${x.near ? `Świeci teraz: ${litNow.length} z ${keys.length} składników` : x.dd > -0.10 ? `Indeks ${pct(x.dd)} pod rekordem — poza strefą rekordu (≤3%), składniki pokazane informacyjnie` : "Indeks w korekcie ≥10% — szczyt już był, sygnały szczytu nieaktualne"}</h2>
    <ul style="margin:8px 0 0;padding-left:18px;line-height:1.75;color:var(--text-2)">${P.conclusions.map(c => `<li>${c}</li>`).join("")}</ul>
  </div>

  <div class="section">Stan dziś — ${x.name} <small>status · ile dni świecił w ostatnich 60 sesjach · wynik testu</small></div>
  <div class="grid g4">${keys.map(k => compCard(k, x)).join("")}</div>

  <div class="section">Test: czy składnik zapowiadał korektę? <small>dni blisko rekordu (≤3%); korekta = −10% w ciągu 120 sesji; ${P.rules.comp}</small></div>
  <div class="card tbl">${testTable()}</div>

  <div class="section">Wyprzedzenie: kiedy zapala się sygnał i ile rynek jeszcze rośnie <small>pierwszy dzień każdego epizodu sygnału → szczyt przed następną korektą ≥10%</small></div>
  <div class="grid g2">
    <div class="card"><h3>${x.name}: sesje od sygnału do szczytu (25–75%, kropka = mediana)</h3><div id="c_lead" class="chart sm"></div></div>
    <div class="card"><h3>${x.name}: ile indeks urósł od sygnału do szczytu</h3><div id="c_gain" class="chart sm"></div></div>
  </div>
  <div class="card note" style="margin-top:10px">Jak czytać: sygnał, który świeci średnio 150 sesji przed szczytem, gdy indeks w tym czasie rośnie jeszcze o 20%, nie jest sygnałem do sprzedaży — co najwyżej ostrzeżeniem, że cykl się starzeje. „Późno” = odsetek sygnałów, po których szczyt przyszedł dopiero po ponad 60 sesjach.</div>

  <div class="section">Profil szczytów — ${x.name} <small>co świeciło przed każdym szczytem, który otworzył korektę ≥10%</small></div>
  <div class="card tbl">${profileTable(x, keys)}</div>

  <div class="section">Termometr łączny <small>regresja logistyczna, walk-forward; ${P.rules.therm}</small></div>
  <div class="grid g2">
    <div class="card"><h3>Kalibracja (${x.name})</h3><div id="c_cal" class="chart sm"></div></div>
    <div class="card" style="font-size:13.5px;line-height:1.7">
      <p>Wynik testu: ${ok(P.therm.pass)} — zaliczony na: ${P.therm.passed_on.length ? P.therm.passed_on.join(", ") : "żadnym indeksie"}.</p>
      ${x.therm ? `<p class="mono" style="font-size:12px">${x.name}: skill ${pct(x.therm.skill, 1, true)} · Brier ${fmt(x.therm.brier, 3)} vs ${fmt(x.therm.brier_base, 3)} · kalibracja ${x.therm.monotone ? "rośnie" : "nie rośnie"} · n=${x.therm.n}</p>` : ""}
      ${P.therm.pass && x.therm_now != null ? `<p><b>Dziś:</b> P(korekta ≥10% w 120 sesji) = <b>${pct(x.therm_now, 0)}</b>.</p>` : `<p>Termometr ${P.therm.pass ? "nieaktywny (indeks nie jest blisko rekordu)" : "nie przeszedł testu, więc nie pokazuję prognozy"}.</p>`}
    </div>
  </div>

  <div class="section">Wzrosty: od dna korekty do kolejnego szczytu <small>odpowiednik „średniego spadku” dla hossy</small></div>
  <div class="grid g2">
    <div class="card">${rallyHTML(x)}</div>
    <div class="card"><h3>Wzrost od dna do szczytu — każda hossa (${x.name})</h3><div id="c_rally" class="chart sm"></div></div>
  </div>

  <div class="section">Czy kupno na rekordzie było złym pomysłem? <small>zwroty od dni z nowym zamknięciem na rekordzie vs dowolny dzień</small></div>
  <div class="card tbl">${athTable(x)}</div>

  <div class="section">Ostatnie 3 lata: kurs i liczba świecących składników</div>
  <div class="card"><div id="c_hist" class="chart"></div></div>`;
  $("#app").innerHTML = h;
  draws(x, keys);
}

function compCard(k, x) {
  const t = x.tests[k], s = P.summary[k], now = x.now[k];
  const st = now == null ? ["brak danych", "st-far"] : now ? ["ŚWIECI", "st-zone"] : ["nie świeci", "st-far"];
  return `<div class="card ind">
    <div class="row1"><div class="name">${P.comp[k].label}</div><span class="pill ${st[1]}">${st[0]}</span></div>
    <div class="mom"><span>w ostatnich 60 sesjach: <b>${x.last60[k]}</b> dni</span></div>
    <div class="verdict" style="font-size:12.5px">${s.pass ? '<span style="color:var(--past)">✓ przeszedł test</span>' : '<span style="color:var(--muted)">✗ nie przeszedł testu — tylko opis</span>'}${t && t.lift120 != null ? ` · lift ${fmt(t.lift120, 2)}× · ${t.n_eps} epizodów` : ""}</div>
    ${t && t.lead_med != null ? `<div class="mono" style="font-size:12px;color:var(--text-2)">typowo ~${fmt(t.lead_med)} sesji przed szczytem, indeks jeszcze ${pct(t.gain_med, 0, true)}</div>` : ""}
    <div class="explain">${P.comp[k].desc}</div></div>`;
}

function testTable() {
  const ks = ORDER.filter(k => P.indices[k]);
  return `<table><tr><th>Składnik</th>${ks.map(k => `<th class="n">${P.indices[k].name}<br><span style="font-weight:400">świeci → korekta / baza · lift · epizody</span></th>`).join("")}<th>Wynik</th></tr>
  ${Object.keys(P.comp).map(c => `<tr><td><b>${P.comp[c].label}</b></td>${ks.map(k => { const t = P.indices[k].tests[c];
    if (!t) return '<td class="n" style="color:var(--muted)">n/d</td>';
    const col = t.passed ? "var(--past)" : (t.lift120 != null && t.lift120 < 1 ? "var(--zone)" : "var(--text-2)");
    return `<td class="n">${pct(t.p120, 0)} / ${pct(t.base120, 0)}<br><span style="color:${col};font-weight:700">${t.lift120 == null ? "—" : fmt(t.lift120, 2) + "×"}</span> · ${t.n_eps} ep.</td>`; }).join("")}
    <td>${ok(P.summary[c].pass)}<br><span class="note">${P.summary[c].passed_on.join(", ") || "—"}</span></td></tr>`).join("")}
  </table><div class="note">Baza = jak często korekta ≥10% zaczynała się w ciągu 120 sesji od losowego dnia blisko rekordu. Lift 1,5× = gdy składnik świeci, korekta przychodziła 1,5 raza częściej niż zwykle. Lift &lt; 1 = świecenie było wręcz uspokajające.</div>`;
}

function profileTable(x, keys) {
  const rows = [...x.profile].reverse();
  const cell = (c) => {
    if (!c || c.at == null) return '<td style="color:var(--muted)">n/d</td>';
    if (c.at) return `<td style="color:var(--zone);font-weight:700">● w dniu szczytu${c.lead ? ` <span style="font-weight:400;color:var(--text-2)">(od ${c.lead} ses.)</span>` : ""}</td>`;
    if (c.lead != null) return `<td style="color:var(--approach)">○ ${c.last === 0 ? "" : c.last + "–"}${c.lead} ses. przed</td>`;
    return '<td style="color:var(--muted)">—</td>';
  };
  return `<table><tr><th>Szczyt</th><th class="n">Korekta</th>${keys.map(k => `<th>${P.comp[k].label}</th>`).join("")}<th class="n">Świeciło (60 ses.)</th></tr>
  ${rows.map(r => `<tr><td>${r.peak}${r.complete ? "" : " *"}</td><td class="n">${pct(r.depth, 0)}</td>${keys.map(k => cell(r.c[k])).join("")}<td class="n">${r.lit_60}</td></tr>`).join("")}
  </table><div class="note">● = świecił w dniu szczytu; ○ X–Y ses. przed = ostatnia seria sygnału zaczęła się Y i skończyła X sesji przed szczytem (okno 250 sesji). Średnio w losowy dzień blisko rekordu świeci ${fmt(x.rand_lit, 1)} składników — porównaj z kolumną po prawej, żeby zobaczyć, czy przed szczytami świeciło wyraźnie więcej. * = trwająca korekta.</div>`;
}

function rallyHTML(x) {
  const s = x.rally_sum, n = x.rally_now || {};
  return `<h3>Typowa hossa między korektami ≥10% (${s.n})</h3>
  <div class="big-fc">${pct(s.gain_med, 0, true)} <span style="font-size:18px;color:var(--text-2)">w ~${fmt(s.sess_med)} sesji</span></div>
  <div style="color:var(--text-2);margin:6px 0 12px">połowa przypadków: ${pct(s.gain_p25, 0, true)} – ${pct(s.gain_p75, 0, true)}, ${fmt(s.sess_p25)}–${fmt(s.sess_p75)} sesji.
  Od powrotu na rekord do szczytu: mediana ${fmt(s.after_rec_sess_med)} sesji, ${pct(s.after_rec_gain_med, 0, true)}.</div>
  ${n.in_correction ? `<div class="note">Indeks jest obecnie w korekcie ≥10% (szczyt ${n.peak}) — bieżąca hossa jeszcze się nie zaczęła.</div>`
    : `<div style="font-size:13.5px"><b>Obecna hossa</b> (od dna ${n.from}): <b>${pct(n.gain, 0, true)}</b> w <b>${fmt(n.sessions)}</b> sesji.<br>
       Historycznie ${pct(n.ended_before_gain, 0)} hoss skończyło się przy mniejszym wzroście, a ${pct(n.ended_before_time, 0)} trwało krócej.</div>`}`;
}

function athTable(x) {
  const a = x.ath;
  return `<table><tr><th>Horyzont</th><th class="n">Kupno na rekordzie: mediana</th><th class="n">% zysku</th><th class="n">Dowolny dzień: mediana</th><th class="n">% zysku</th><th class="n">Dni z rekordem</th></tr>
  ${["60", "120", "250"].map(h => `<tr><td>${h} sesji</td><td class="n">${pct(a[h].ath_med, 1, true)}</td><td class="n">${pct(a[h].ath_win, 0)}</td><td class="n">${pct(a[h].all_med, 1, true)}</td><td class="n">${pct(a[h].all_win, 0)}</td><td class="n">${a[h].n_ath}</td></tr>`).join("")}
  </table><div class="note">Jeśli kupno na rekordzie daje podobnie jak w dowolny dzień, to sam rekord nie jest powodem do sprzedaży ani do czekania.</div>`;
}

function draws(x, keys) {
  const lab = keys.map(k => P.comp[k].label);
  const tl = keys.map(k => x.tests[k]);
  plot("c_lead", [{ x: lab, y: tl.map(t => t && t.lead_p75 != null ? t.lead_p75 - t.lead_p25 : null), base: tl.map(t => t && t.lead_p25), type: "bar",
    marker: { color: "#3987e566" }, hoverinfo: "skip", width: .5 },
    { x: lab, y: tl.map(t => t && t.lead_med), type: "scatter", mode: "markers", marker: { size: 11, color: "#3987e5", line: { color: "#fff", width: 2 } },
      text: tl.map(t => t ? `późno: ${pct(t.late_share, 0)} · n=${t.first_n}` : ""), hovertemplate: "%{x}: mediana %{y} sesji<br>%{text}<extra></extra>" }],
    { showlegend: false, hovermode: "closest", margin: { l: 52, r: 16, t: 10, b: 90 }, xaxis: { tickangle: -30 }, yaxis: { title: "sesje", gridcolor: "#1f242b" },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 60, y1: 60, line: { color: "#e0a019", dash: "dot" } }] });
  plot("c_gain", [{ x: lab, y: tl.map(t => t && t.gain_med), type: "bar", marker: { color: "#2fb36b" }, text: tl.map(t => t ? pct(t.gain_med, 0, true) : ""), textposition: "outside",
    hovertemplate: "%{x}: %{y:.1%}<extra></extra>" }], { showlegend: false, hovermode: "closest", margin: { l: 52, r: 16, t: 10, b: 90 }, xaxis: { tickangle: -30 }, yaxis: { tickformat: ".0%", gridcolor: "#1f242b" } });
  if (x.therm) plot("c_cal", [{ x: [0, 1], y: [0, 1], mode: "lines", line: { color: "#3a404a", dash: "dot" }, hoverinfo: "skip", name: "idealnie" },
    { x: x.therm.calib.map(c => c.pred), y: x.therm.calib.map(c => c.real), mode: "lines+markers", marker: { size: 9 }, line: { color: IXC[IX], width: 2 }, name: x.name,
      hovertemplate: "model %{x:.0%} → realnie %{y:.0%}<extra></extra>" }],
    { hovermode: "closest", xaxis: { range: [0, 1], tickformat: ".0%", title: "model mówił" }, yaxis: { range: [0, 1], tickformat: ".0%", title: "zrealizowane" } });
  const r = x.rallies;
  plot("c_rally", [{ x: r.map(z => z.from.slice(0, 7)), y: r.map(z => z.gain), type: "bar", marker: { color: IXC[IX] },
    text: r.map(z => `${z.sessions} ses.`), hovertemplate: "od %{x}: %{y:.0%} (%{text})<extra></extra>" }].concat(
    x.rally_now && !x.rally_now.in_correction ? [{ x: ["teraz"], y: [x.rally_now.gain], type: "bar", marker: { color: "#eceae4" }, hovertemplate: "obecna: %{y:.0%}<extra></extra>" }] : []),
    { showlegend: false, hovermode: "closest", xaxis: { type: "category" }, yaxis: { tickformat: ".0%", gridcolor: "#1f242b" } });
  const c = x.chart;
  plot("c_hist", [{ x: c.d, y: c.close, type: "scatter", mode: "lines", line: { color: "#eceae4", width: 2 }, name: "Kurs", hovertemplate: "%{y:,.0f}" },
    { x: c.d, y: c.lit, type: "bar", yaxis: "y2", marker: { color: "#e5484d66" }, name: "Świecące składniki", hovertemplate: "%{y}" }],
    { yaxis: { gridcolor: "#1f242b" }, yaxis2: { overlaying: "y", side: "right", range: [0, keys.length * 2.5], showgrid: false, title: "świeci" }, bargap: 0 });
}

load().catch(e => { $("#app").innerHTML = `<div class="loading">Błąd: ${e}</div>`; });
