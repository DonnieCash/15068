/* NK15068 — crime, policing and incidents (renders #safety; filters also drive the map layer) */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n, d = 0) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  // publication-name credits and AP dates are defined in app.js (loaded after this file, called at render time)
  const src = (u) => (u ? window.NKpub(u) : "");
  const credit = (urls, pre) => window.NKpub.credit(urls, pre);
  const TOWNS = ["New Kensington", "Arnold", "Lower Burrell"];
  const CAT = { violent: "Violent", property: "Property", police: "Police and other" };
  const TYPE = {
    homicide: "Homicide", shooting: "Shooting", stabbing: "Stabbing", robbery: "Robbery", assault: "Assault",
    burglary: "Burglary", theft: "Theft", vehicle_theft: "Vehicle theft", arson: "Arson", fire: "Fire",
    drugs: "Drug case", weapons: "Weapons", pursuit: "Police pursuit", standoff: "Standoff",
    police_shooting: "Police shooting", use_of_force: "Use of force", crash: "Crash", vandalism: "Vandalism",
    fraud: "Fraud", other: "Other",
  };
  const OFFENSES = [["murder", "Murder & manslaughter"], ["rape", "Rape"], ["robbery", "Robbery"], ["agg_assault", "Aggravated assault"],
    ["burglary", "Burglary"], ["larceny", "Larceny-theft"], ["mvt", "Motor vehicle theft"], ["arson", "Arson"]];
  const PREC = { block: "hundred-block", intersection: "intersection", place: "named place", street: "street only (approximate)" };
  const monthName = (d) => window.NKapDate(d);

  function agencyFor(fbi, town) {
    return (fbi.agencies || []).find((a) => a.municipality === town || (a.agency || "").includes(town));
  }
  const val = (y, k) => (typeof k === "function" ? k(y) : y?.[k]);
  const rate = (y, k) => { const v = val(y, k); return v != null && y.population ? v / y.population * 1000 : null; };

  const partialMark = (y) => (y && y.months_reported && y.months_reported < 12 ? "†" : "");
  const partialNote = (y) => (y && y.months_reported && y.months_reported < 12 ? ` · only ${y.months_reported} of 12 months reported` : "");

  /* ---------- box score: one row per department, latest year ---------- */
  function boxScore(fbi, policing) {
    const rows = TOWNS.map((t) => {
      const ag = agencyFor(fbi, t);
      const yrs = (ag?.years || []).filter((y) => y.violent != null && y.property != null && y.population);
      const last = yrs[yrs.length - 1];
      const offYr = [...(ag?.years || [])].reverse().find((y) => y.officers != null && y.population);
      const pol = (policing.agencies || []).find((a) => a.municipality === t);
      const officers = offYr ? offYr.officers : pol?.officers;
      const offYear = offYr ? offYr.year : pol?.officers_year;
      const pop = offYr ? offYr.population : last?.population;
      const sub = (y) => `${fmt(y[1])} in ${y[0].year}${partialMark(y[0]) ? `, only ${y[0].months_reported} of 12 months †` : ""}`;
      const cell = (b, s) => `<td><b>${b}</b><small>${s}</small></td>`;
      return `<tr><th scope="row">${esc(t)}<small>${esc(ag?.agency || pol?.name || "")}${ag?.ori ? " · ORI " + esc(ag.ori) : ""}</small></th>
        ${last ? cell(fmt(rate(last, "violent"), 1), sub([last, last.violent])) + cell(fmt(rate(last, "property"), 1), sub([last, last.property])) : `<td colspan="2"><small>No FBI figures found</small></td>`}
        ${officers != null && pop ? cell(fmt(officers / pop * 1000, 1), `${fmt(officers)} sworn, ${offYear || "latest"}`) : cell("–", "not reported")}</tr>`;
    }).join("");
    return `<table class="box-score"><thead><tr><th scope="col">Department</th><th scope="col">Violent</th><th scope="col">Property</th><th scope="col">Officers</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="credit">† Partial year. Officers are sworn officers per 1,000 residents. ${credit("https://github.com/jacobkap/crimedatatool_helper")}.</p>`;
  }

  /* ---------- small-multiple trend panels ---------- */
  function niceMax(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v || 1)));
    for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }
  function panels(fbi, key, colorVar, label, count = false) {
    const series = TOWNS.map((t) => {
      const ag = agencyFor(fbi, t);
      return { t, pts: (ag?.years || []).filter((y) => val(y, key) != null && (count || y.population)).map((y) => ({ year: y.year, v: count ? val(y, key) : rate(y, key), n: val(y, key), est: !!y.population_estimated_from, m: y.months_reported, c: count ? 1 : 0 })) };
    });
    const all = series.flatMap((s) => s.pts);
    if (!all.length) return `<p class="empty">No ${esc(label.toLowerCase())} figures available.</p>`;
    const y0 = Math.min(...all.map((p) => p.year)), y1 = Math.max(...all.map((p) => p.year));
    const vmax = niceMax(Math.max(...all.map((p) => p.v)) * 1.08);
    const W = 320, H = 172, L = 34, R = 34, T = 12, B = 24;
    const x = (yr) => L + (y1 === y0 ? 0.5 : (yr - y0) / (y1 - y0)) * (W - L - R);
    const y = (v) => T + (1 - v / vmax) * (H - T - B);
    const ticks = [0, vmax / 2, vmax];
    const xt = y1 - y0 > 12 ? [y0, Math.round((y0 + y1) / 2), y1] : [y0, y1];
    return series.map((s) => {
      // break the line at missing years: never interpolate across a gap
      const runs = [];
      s.pts.forEach((p, i) => { if (!i || p.year !== s.pts[i - 1].year + 1) runs.push([]); runs[runs.length - 1].push(p); });
      const paths = runs.map((r) => r.length > 1
        ? `<path d="${r.map((p, i) => (i ? "L" : "M") + x(p.year).toFixed(1) + " " + y(p.v).toFixed(1)).join(" ")}" fill="none" stroke="var(${colorVar})" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`
        : `<circle cx="${x(r[0].year)}" cy="${y(r[0].v)}" r="3" fill="var(${colorVar})"/>`).join("");
      const partial = s.pts.filter((p, i) => p.m && p.m < 12 && i < s.pts.length - 1).map((p) => `<circle cx="${x(p.year)}" cy="${y(p.v)}" r="4" fill="var(--ground)" stroke="var(${colorVar})" stroke-width="2"><title>${p.year}: ${p.m} of 12 months reported</title></circle>`).join("");
      const last = s.pts[s.pts.length - 1];
      const lastPartial = last && last.m && last.m < 12;
      const end = last ? `<circle cx="${x(last.year)}" cy="${y(last.v)}" r="4" fill="${lastPartial ? "var(--ground)" : `var(${colorVar})`}" stroke="${lastPartial ? `var(${colorVar})` : "var(--ground)"}" stroke-width="2"/>
        <text x="${x(last.year) + 7}" y="${y(last.v) + 4}" font-size="12" fill="var(--ink)" font-family="var(--f-sans)" font-weight="600">${fmt(last.v, count ? 0 : 1)}${lastPartial ? "†" : ""}</text>` : "";
      const data = esc(JSON.stringify(s.pts));
      return `<div class="panel-chart" data-pts="${data}" data-y0="${y0}" data-y1="${y1}" data-vmax="${vmax}" data-label="${esc(label)}">
        <h4><i style="background:var(${colorVar})"></i>${esc(s.t)}</h4>
        <svg viewBox="0 0 ${W} ${H}" role="img" tabindex="0" aria-label="${esc(label)}${count ? "" : " per 1,000 residents"} in ${esc(s.t)}, ${y0}–${y1}${last ? `; latest ${last.year}: ${fmt(last.v, count ? 0 : 1)}${last.m && last.m < 12 ? ` (only ${last.m} of 12 months reported)` : ""}` : ""}">
          ${ticks.map((t) => `<line x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)" stroke-width="1"/>
            <text x="${L - 6}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--muted)" font-family="var(--f-sans)">${fmt(t, t < 10 && t % 1 ? 1 : 0)}</text>`).join("")}
          ${xt.map((t) => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle" font-size="11" fill="var(--muted)" font-family="var(--f-sans)">${t}</text>`).join("")}
          ${s.pts.length ? paths + partial + end : `<text x="${(L + W - R) / 2}" y="${H / 2}" text-anchor="middle" font-size="12" fill="var(--muted)">no data</text>`}
          <line class="xh" y1="${T}" y2="${H - B}" stroke="var(--muted)" stroke-width="1" visibility="hidden"/>
        </svg><div class="tip" hidden></div></div>`;
    }).join("");
  }
  function wirePanels(root) {
    root.querySelectorAll(".panel-chart").forEach((pc) => {
      const pts = JSON.parse(pc.dataset.pts || "[]");
      if (!pts.length) return;
      const svg = pc.querySelector("svg"), tip = pc.querySelector(".tip"), xh = svg.querySelector(".xh");
      const y0 = +pc.dataset.y0, y1 = +pc.dataset.y1, vmax = +pc.dataset.vmax;
      const W = 320, H = 172, L = 34, R = 34, T = 12, B = 24;
      const x = (yr) => L + (y1 === y0 ? 0.5 : (yr - y0) / (y1 - y0)) * (W - L - R);
      const y = (v) => T + (1 - v / vmax) * (H - T - B);
      let idx = pts.length - 1;
      const show = (i) => {
        idx = Math.max(0, Math.min(pts.length - 1, i));
        const p = pts[idx], k = svg.getBoundingClientRect().width / W;
        xh.setAttribute("x1", x(p.year)); xh.setAttribute("x2", x(p.year)); xh.setAttribute("visibility", "visible");
        tip.hidden = false;
        tip.style.left = x(p.year) * k + "px"; tip.style.top = (y(p.v) * k + 22) + "px";
        tip.textContent = "";
        const b = document.createElement("b"); b.textContent = p.c ? `${fmt(p.n)} ${pc.dataset.label.toLowerCase()}` : fmt(p.v, 1) + " per 1,000";
        const s = document.createElement("span"); s.textContent = p.c ? String(p.year) : `${p.year} · ${fmt(p.n)} total${p.m && p.m < 12 ? ` · ${p.m} of 12 months` : ""}${p.est ? " · population estimated" : ""}`;
        tip.append(b, s);
      };
      const hide = () => { tip.hidden = true; xh.setAttribute("visibility", "hidden"); };
      svg.addEventListener("pointermove", (e) => {
        const r = svg.getBoundingClientRect(), yr = y0 + ((e.clientX - r.left) / r.width * W - L) / (W - L - R) * (y1 - y0);
        let best = 0; pts.forEach((p, i) => { if (Math.abs(p.year - yr) < Math.abs(pts[best].year - yr)) best = i; });
        show(best);
      });
      svg.addEventListener("pointerleave", hide);
      svg.addEventListener("focus", () => show(idx));
      svg.addEventListener("blur", hide);
      svg.addEventListener("keydown", (e) => {
        if (e.key === "ArrowLeft") { show(idx - 1); e.preventDefault(); }
        if (e.key === "ArrowRight") { show(idx + 1); e.preventDefault(); }
      });
    });
  }


  const bt = (cls = "") => `<div class="dir-table-wrap"><table class="dir${cls ? " " + cls : ""}">`;
  const FBI_CREDIT = () => credit("https://github.com/jacobkap/crimedatatool_helper");

  function fbiTable(fbi) {
    const rows = [];
    TOWNS.forEach((t) => (agencyFor(fbi, t)?.years || []).forEach((y) => rows.push({ t, ...y })));
    rows.sort((a, b) => a.t.localeCompare(b.t) || b.year - a.year);
    const n = (v) => (v == null ? "–" : fmt(v));
    return `<table class="dir"><thead><tr><th>Department</th><th class="num">Year</th><th class="num">Months</th><th class="num">Population</th><th class="num">Violent</th><th class="num">per 1,000</th><th class="num">Property</th><th class="num">per 1,000</th><th class="num">Arrests</th><th class="num">Officers</th><th>Source</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td>${esc(r.t)}</td><td class="num">${r.year}</td><td class="num">${r.months_reported ?? "–"}</td><td class="num">${n(r.population)}${r.population_estimated_from ? "*" : ""}</td><td class="num">${n(r.violent)}</td><td class="num">${rate(r, "violent") == null ? "–" : fmt(rate(r, "violent"), 1)}</td><td class="num">${n(r.property)}</td><td class="num">${rate(r, "property") == null ? "–" : fmt(rate(r, "property"), 1)}</td><td class="num">${n(r.arrests?.total)}</td><td class="num">${n(r.officers)}</td><td>${(r.sources || []).slice(0, 1).map(src).join(" ")}${r.note ? `<span class="sub">${esc(r.note)}</span>` : ""}</td></tr>`).join("")}
    </tbody></table><p class="table-note">Months is the number of months that year the department reported to the FBI. * Population carried over from the nearest year that reported one.</p>`;
  }

  function offenseTable(fbi) {
    const lasts = TOWNS.map((t) => {
      const yrs = (agencyFor(fbi, t)?.years || []).filter((y) => OFFENSES.some(([k]) => y[k] != null));
      return yrs[yrs.length - 1];
    });
    if (!lasts.some(Boolean)) return "";
    const cell = (y, k) => (y && y[k] != null ? fmt(y[k]) : "–");
    return `<div class="viz"><h3 class="gh">Reported offenses, by type</h3>
      <p class="chatter">The most recent year each department reported offense detail to the FBI.</p>
      ${bt()}<thead><tr><th>Offense</th>${TOWNS.map((t, i) => `<th class="num">${esc(t)}${lasts[i] ? ", " + lasts[i].year + partialMark(lasts[i]) : ""}</th>`).join("")}</tr></thead>
      <tbody>${OFFENSES.map(([k, l]) => `<tr><td>${l}</td>${lasts.map((y) => `<td class="num">${cell(y, k)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="table-note">${lasts.some((y) => partialMark(y)) ? `† Partial year: ${lasts.filter((y) => partialMark(y)).map((y) => `${esc(TOWNS[lasts.indexOf(y)])} reported ${y.months_reported} of 12 months`).join("; ")}. ` : ""}${FBI_CREDIT()}</p></div>`;
  }

  function policeWork(fbi) {
    const pct = (a, b) => (a != null && b ? Math.round(a / b * 100) + "%" : "–");
    // a zero clearance count against a meaningful number of offenses is almost certainly unreported
    const clr = (c, n, min) => (c === 0 && n >= min ? "–*" : pct(c, n));
    const pctPair = (y) => [clr(y.cleared_violent, y.violent, 10), clr(y.cleared_property, y.property, 20)];
    const n = (v) => (v == null ? "–" : fmt(v));
    const rows = [];
    TOWNS.forEach((t) => {
      const yrs = (agencyFor(fbi, t)?.years || []).filter((y) => y.arrests || y.cleared_violent != null || y.officers_assaulted != null);
      yrs.slice(-4).reverse().forEach((y) => rows.push({ t, ...y }));
    });
    if (!rows.length) return "";
    return `<div class="viz"><h3 class="gh">Police work, by the FBI's count</h3>
      <p class="chatter">Arrests made, the share of reported crimes cleared, and assaults on officers, for each department's last four reporting years.</p>
      ${bt()}<thead><tr><th>Department</th><th class="num">Year</th><th class="num">Arrests</th><th class="num">Drug</th><th class="num">DUI</th><th class="num">Violent-crime arrests</th><th class="num">Violent crimes cleared</th><th class="num">Property crimes cleared</th><th class="num">Officers assaulted</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td>${esc(r.t)}</td><td class="num">${r.year}${r.months_reported && r.months_reported < 12 ? "†" : ""}</td><td class="num">${n(r.arrests?.total)}</td><td class="num">${n(r.arrests?.drugs)}</td><td class="num">${n(r.arrests?.dui)}</td><td class="num">${n(r.arrests?.violent)}</td><td class="num">${pctPair(r)[0]}</td><td class="num">${pctPair(r)[1]}</td><td class="num">${n(r.officers_assaulted)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="table-note">"Cleared" means the FBI counts the case as closed, usually by an arrest. Arrests include people who don't live in the city. A dash means the department didn't report that figure. Drug arrests reported as zero next to hundreds of total arrests (2017–18) are shown as a dash, since that category most likely went unreported. † Partial year. * Zero clearances reported against 10 or more violent or 20 or more property crimes, which almost certainly means clearances weren't reported. ${FBI_CREDIT()}</p></div>`;
  }

  const LABELS = {
    sworn_officers_authorized: "Authorized full-time officers", part_time_officers: "Part-time officers",
    starting_salary_patrol_officer: "Starting patrol salary", body_camera_funding: "Body-camera funding from DA forfeiture",
    pct_arrests_low_level_nonviolent: "Arrests for low-level, nonviolent offenses (2013–2023)",
    people_killed_by_police: "People killed by police (2013–2023)", fatal_police_shootings_wapo: "Fatal police shootings (Washington Post, 2015–2024)",
    police_shooting: "Police shooting", officer_killed: "Officer killed in the line of duty", misconduct_charge: "Officer charged",
    death_in_custody: "Death in custody", use_of_force: "Use of force", body_cameras: "Body cameras", regionalization: "Regionalization talks",
    community_program: "Community program", staffing: "Staffing", lawsuit: "Lawsuit", complaint: "Complaint", policy: "Policy",
  };
  const pretty = (m) => LABELS[m] || String(m).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const stop = (s) => (/[.!?]$/.test(s) ? s : s + ".");

  /* rail: who patrols 15068 */
  function deptsBox(policing) {
    const ags = policing.agencies || [];
    if (!ags.length) return "";
    return `<div class="box depts"><h3 class="lh">Who patrols 15068</h3>${ags.map((a) => `<div class="dept">
        <h4>${esc(a.name)}</h4>
        ${a.chief ? `<p>Chief: ${esc(a.chief)}</p>` : ""}
        ${a.officers != null ? `<p>${fmt(a.officers)} sworn officers${a.officers_year ? ` (${a.officers_year})` : ""}</p>` : ""}
        ${a.covers ? `<p>${esc(a.covers)}</p>` : ""}
        ${a.address ? `<p>${esc(a.address)}</p>` : ""}
        ${a.phone_nonemergency ? `<p><b class="num">${esc(a.phone_nonemergency)}</b> · Emergency 911</p>` : ""}
        ${a.notes ? `<p class="notes">${esc(a.notes)}</p>` : ""}
        <p class="credit">${credit((a.sources || []).slice(0, 3))}</p></div>`).join("")}</div>`;
  }

  /* police shootings, lawsuits and policy changes: blotter entries */
  function interactionsBlock(policing) {
    const stats = policing.stats || [];
    const inter = [...(policing.interactions || [])].sort((a, b) => String(b.date).localeCompare(String(a.date)));
    return `${stats.length ? `<div class="viz"><h3 class="gh">Police activity</h3><p class="chatter">Figures the departments or news reports have published.</p>
        ${bt()}<thead><tr><th>Department</th><th class="num">Year</th><th>Measure</th><th class="num">Value</th><th>Source</th></tr></thead><tbody>
        ${stats.sort((a, b) => (a.agency || "").localeCompare(b.agency || "") || (b.year || 0) - (a.year || 0)).map((s) => `<tr><td>${esc(s.agency)}</td><td class="num">${s.year ?? "–"}</td><td>${esc(pretty(s.metric))}${s.note ? `<span class="sub">${esc(s.note)}</span>` : ""}</td><td class="num">${/percent/i.test(s.unit || "") ? fmt(s.value) + "%" : /USD/.test(s.unit || "") ? "$" + fmt(s.value) : fmt(s.value)}</td><td>${src(s.source)}</td></tr>`).join("")}
        </tbody></table></div></div>` : ""}
      ${inter.length ? `<div class="viz"><h3 class="sub-h">Police shootings, lawsuits and policy changes since 2010</h3>
        <p class="chatter">Shootings, use of force, lawsuits, policy changes and programs reported in the news, newest first.</p>
        <div class="blotter">${inter.map((i) => `<div class="entry">
          <p class="bl"><b class="lead-in">${esc(i.municipality)}.</b> <b class="what">${esc(stop(pretty(i.kind)))}</b> ${esc(i.summary)}</p>
          <p class="meta">${esc(monthName(i.date))}${i.location_text ? ` · ${esc(i.location_text)}` : ""} · ${credit(i.source)}</p></div>`).join("")}</div></div>` : ""}`;
  }

  function crashBlock(crashes) {
    const st = crashes?.stats || [];
    if (!st.length) return "";
    const seen = st.map((r) => r.year);
    const y0 = Math.min(...seen), y1 = Math.max(...seen);
    const years = Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i);
    // years with no serious crash are real zeros in this dataset, not gaps
    const fake = { agencies: TOWNS.map((t) => ({ municipality: t, years: years.map((y) => {
      const r = st.find((x) => x.t === t && x.year === y);
      return { year: y, crashes: r ? r.crashes : 0 };
    }) })) };
    const tot = (t, k, from = y0) => st.filter((r) => r.t === t && r.year >= from).reduce((a, r) => a + r[k], 0);
    return `<div class="viz"><h3 class="gh">Serious and fatal crashes per year</h3>
      <p class="chatter">Police-reported crashes that killed or seriously injured someone, ${y0}–${y1}. Every panel uses the same scale.</p>
      <div class="multiples" id="safety-crashes">${panels(fake, "crashes", "--ink-2", "Crashes", true)}</div>
      <p class="credit">${credit(crashes.source)}</p>
      <details class="tableview"><summary>Every year as a table ›</summary>${bt()}<thead><tr><th class="num">Year</th>${TOWNS.map((t) => `<th class="num">${esc(t)}</th>`).join("")}</tr></thead><tbody>
        ${years.slice().reverse().map((y) => `<tr><td class="num">${y}</td>${TOWNS.map((t) => { const r = st.find((x) => x.t === t && x.year === y); return `<td class="num">${r ? `${r.crashes} (${r.fatal} killed)` : "0"}</td>`; }).join("")}</tr>`).join("")}
      </tbody></table></div></details>
      <div class="gap">${bt()}<thead><tr><th>Town</th><th class="num">Crashes ${y0}–${y1}</th><th class="num">Killed</th><th class="num">Seriously injured</th><th class="num">Crashes ${y1 - 4}–${y1}</th></tr></thead><tbody>
      ${TOWNS.map((t) => `<tr><td>${esc(t)}</td><td class="num">${fmt(tot(t, "crashes"))}</td><td class="num">${fmt(tot(t, "fatal"))}</td><td class="num">${fmt(tot(t, "serious"))}</td><td class="num">${fmt(tot(t, "crashes", y1 - 4))}</td></tr>`).join("")}
      </tbody></table></div></div>
      <p class="crash-note">${esc(crashes.notes || "")} ${credit(crashes.source)}</p>
      <button class="btn-line inline" type="button" data-crashes="1">Show the crashes on the map</button></div>`;
  }

  /* ---------- police blotter + shared filter ---------- */
  function incidentsBlock(safety, api) {
    const inc = safety.incidents || [];
    const years = [...new Set(inc.map((i) => String(i.d).slice(0, 4)))].sort().reverse();
    const counts = { violent: 0, property: 0, police: 0 };
    inc.forEach((i) => { counts[i.c] = (counts[i.c] || 0) + 1; });
    const host = $("#inc-block");
    host.innerHTML = `
      <h3 class="lh big blotter-h">Police blotter</h3>
      <p class="chatter">Incidents local news reported with a street location · ${fmt(inc.length)} on the map</p>
      <div class="filters" role="group" aria-label="Filter incidents">
        <button class="chip" type="button" data-c="*" aria-pressed="true">All ${fmt(inc.length)}</button>
        ${Object.entries(CAT).map(([k, v]) => `<button class="chip" type="button" data-c="${k}" aria-pressed="false"><span class="inc-key" style="background:var(--inc-${k})"></span>${v} ${fmt(counts[k] || 0)}</button>`).join("")}
        <select id="inc-town" aria-label="Town"><option value="">All towns</option>${TOWNS.map((t) => `<option>${esc(t)}</option>`).join("")}</select>
        <select id="inc-year" aria-label="Year"><option value="">All years</option>${years.map((y) => `<option>${y}</option>`).join("")}</select>
        <button class="text-btn" type="button" id="inc-map">Show these on the map ›</button>
      </div>
      <p class="count" id="inc-count"></p>
      <div class="blotter" id="inc-list"></div>
      <button class="btn-line" type="button" id="inc-more">Show 50 more</button>`;
    const state = { c: "*", t: "", y: "", limit: 25 };
    const pass = (i) => (state.c === "*" || i.c === state.c) && (!state.t || i.t === state.t) && (!state.y || String(i.d).startsWith(state.y));
    const draw = () => {
      const f = inc.filter(pass);
      $("#inc-count").textContent = `${fmt(f.length)} incident${f.length === 1 ? "" : "s"} with a mappable location`;
      $("#inc-list").innerHTML = f.slice(0, state.limit).map((i) => `<div class="entry">
        <p class="bl"><b class="lead-in">${esc(i.t)}.</b> <span class="inc-key k${i.pi ? " pi" : ""}" style="background:var(--inc-${i.c})"></span><b class="what">${esc(TYPE[i.k] || i.k)}.</b> ${esc(i.s)}</p>
        <p class="meta"><time datetime="${esc(i.d)}">${esc(monthName(i.d))}</time> · ${esc(i.l)}${i.p === "street" ? " · approximate location" : ""} · <button type="button" class="linkbtn" data-inc="${inc.indexOf(i)}">Map it</button> · ${credit(i.src)}</p></div>`).join("") || `<p class="empty">No incidents match these filters.</p>`;
      $("#inc-more").hidden = f.length <= state.limit;
      $("#inc-more").textContent = `Show ${fmt(Math.min(50, f.length - state.limit))} more`;
      api.setFilter(pass);
    };
    host.addEventListener("click", (e) => {
      const b = e.target.closest("[data-c]");
      if (b) {
        state.c = b.dataset.c; state.limit = 25;
        host.querySelectorAll("[data-c]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        draw(); return;
      }
      const a = e.target.closest("[data-inc]");
      if (a) { e.preventDefault(); api.focus(inc[+a.dataset.inc]); }
    });
    $("#inc-town").onchange = (e) => { state.t = e.target.value; state.limit = 25; draw(); };
    $("#inc-year").onchange = (e) => { state.y = e.target.value; state.limit = 25; draw(); };
    $("#inc-more").onclick = () => { state.limit += 50; draw(); };
    $("#inc-map").onclick = () => api.showLayer();
    draw();
  }

  function render(safety, api) {
    const root = $("#safety");
    if (!root) return;
    if (!safety || !safety.fbi) { $("#safety-body").innerHTML = `<p class="empty">Crime data didn't load.</p>`; return; }
    const fbi = safety.fbi, pol = safety.policing || {};
    $("#safety-tiles").innerHTML = boxScore(fbi, pol);
    root.querySelectorAll("[data-credit='fbi']").forEach((el) => { el.innerHTML = `${FBI_CREDIT()} · Hollow dots are partial-year reports`; });
    $("#safety-violent").innerHTML = panels(fbi, "violent", "--inc-violent", "Violent crimes");
    $("#safety-property").innerHTML = panels(fbi, "property", "--inc-property", "Property crimes");
    wirePanels($("#safety-violent")); wirePanels($("#safety-property"));
    $("#safety-table").innerHTML = fbiTable(fbi);
    $("#safety-offenses").innerHTML = offenseTable(fbi);
    $("#safety-arrests").innerHTML = panels(fbi, (y) => y.arrests?.total ?? null, "--inc-police", "Arrests");
    wirePanels($("#safety-arrests"));
    $("#safety-policing").innerHTML = policeWork(fbi) + interactionsBlock(pol) + crashBlock(safety.crashes);
    if ($("#safety-crashes")) wirePanels($("#safety-crashes"));
    root.addEventListener("click", (e) => { if (e.target.closest("[data-crashes]")) { e.preventDefault(); api.showCrashes(); } });
    incidentsBlock(safety, api);
    const pc = safety.precision_counts || {};
    $("#safety-depts").innerHTML = deptsBox(pol) + `<div class="box about"><h3 class="lh">About this data</h3><div id="safety-method">
      <p><b>Crime counts</b> come from the FBI's Uniform Crime Reporting program, as reported by each city's police department. ${esc(fbi.method || "")}</p>
      ${fbi.gaps ? `<p><b>Gaps:</b> ${esc(fbi.gaps)}</p>` : ""}
      <p><b>Rates</b> are per 1,000 residents using the population the FBI published for that department and year. Small towns swing a lot from year to year: a handful of incidents moves the rate.</p>
      <p><b>Mapped incidents</b> are ones local news reported with a street location, verified against their source. They are a sample, not a complete record. Locations are rounded to the hundred-block (${fmt(pc.block || 0)}), an intersection (${fmt(pc.intersection || 0)}) or a named place (${fmt(pc.place || 0)}); ${fmt(pc.street || 0)} are placed on the street only, shown with a dashed ring.${safety.unplaced ? ` ${fmt(safety.unplaced)} verified incidents couldn't be placed and are left off.` : ""}</p>
      <p><b>Left out on purpose:</b> names of suspects, victims and line officers (public officials such as chiefs and mayors may be named); exact house numbers; anything identifying a juvenile. Individual sexual-offense incidents are never mapped or listed; the FBI totals above include them. An arrest or charge is not a conviction. The linked source articles are the original news reports and may name people; this site does not.</p>
      ${pol.notes ? `<p><b>Policing research notes:</b> ${esc(pol.notes)}</p>` : ""}</div></div>`;
  }

  window.NKSafety = { render, CAT, TYPE, PREC, monthName };
})();
