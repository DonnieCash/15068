/* NK15068 — front page, phone numbers and calendar (owner: home pages).
   The HTML already holds every row; this only drops calendar rows that have passed on this device, puts my town
   first, writes the since-your-last-visit line, and builds .ics files on the device. */
(function () {
  "use strict";
  const S = window.NKS;
  if (!S) return;
  const { $, $$, esc } = S;
  const todayISO = () => S.isoDay(S.today());

  /* "Sept. 10" this year, "Sept. 10, 2025" otherwise */
  const shortDate = (iso) => {
    const s = S.apDate(iso);
    return iso.slice(0, 4) === String(new Date().getFullYear()) ? s.replace(/, \d{4}$/, "") : s;
  };

  /* ================= front page ================= */

  /* drop rows dated before today and top the list back up to 3 from the hidden <template id="cal-more"> */
  function calRows() {
    const list = $("#cal-rows");
    if (!list) return;
    const t = todayISO();
    $$(".cal-row", list).forEach((li) => { if (li.dataset.date < t) li.remove(); });
    const tpl = $("#cal-more");
    const spare = tpl && tpl.content ? [...tpl.content.querySelectorAll(".cal-row")] : [];
    for (const li of spare) {
      if ($$(".cal-row", list).length >= 3) break;
      if (li.dataset.date >= t && !$$(".cal-row", list).some((r) => r.dataset.id === li.dataset.id)) list.appendChild(document.importNode(li, true));
    }
    S.relabel(list);
  }

  /* my town's police button first, marked .mine (reorders, never hides) */
  function policeOrder() {
    const box = $("#nums-police");
    if (!box) return;
    const btns = $$("a.tel[data-town]", box), t = S.town();
    S.townFirst(S.TOWNS).forEach((name) => { const b = btns.find((x) => x.dataset.town === name); if (b) box.appendChild(b); });
    btns.forEach((b) => b.classList.toggle("mine", !!t && b.dataset.town === t));
  }

  /* "Since your last visit on Sept. 10: 1 new lost-pet listing · 2 data updates" — only after a day or more away */
  function sinceLine() {
    const el = $("#since");
    const prev = S.prevVisit;
    if (!el || !prev) return;
    const t = Date.parse(prev);
    if (!Number.isFinite(t) || Date.now() - t < 864e5) return;
    let changes = [];
    try { changes = JSON.parse(($("#changes") || {}).textContent || "[]"); } catch (e) { changes = []; }
    const prevDay = S.isoDay(new Date(t));
    const fresh = (Array.isArray(changes) ? changes : []).filter((c) => c && String(c.date) > prevDay);
    const draw = () => {
      const P = window.NKPets;
      const pets = P && P.board && P.board.known ? P.newSince(prev) : 0;
      const parts = [];
      if (pets > 0) parts.push(`<a href="${esc(S.url("lost-pets/"))}#board">${pets} new lost-pet listing${pets === 1 ? "" : "s"}</a>`);
      if (fresh.length) parts.push(`<a href="${esc(S.url("whats-new/"))}">${fresh.length === 1 ? "a data update" : `${fresh.length} data updates`} ›</a>`);
      if (!parts.length) { el.hidden = true; return; }
      el.innerHTML = `Since your last visit on ${esc(shortDate(prevDay))}: ${parts.join(" · ")}`;
      el.hidden = false;
    };
    draw();
    if (window.NKPets && typeof window.NKPets.loadBoard === "function") {
      try { window.NKPets.loadBoard({ ui: draw }); } catch (e) { console.error(e); }
    }
  }

  S.pages.home = () => {
    calRows();
    policeOrder();
    document.addEventListener("nk-town", policeOrder);
    sinceLine();
  };

  /* ================= /numbers/ ================= */
  S.pages.numbers = () => {
    const cards = $("#ncards"), tools = $("#ntools");
    if (!cards || !tools) return;
    const order0 = $$(".ncard", cards);
    const btns = $$(".picker button", tools), remember = $("#n-remember");
    let sel = S.town() || "";
    function apply() {
      btns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.town === sel)));
      const first = order0.filter((c) => sel && c.dataset.town === sel);
      [...first, ...order0.filter((c) => !first.includes(c))].forEach((c) => cards.appendChild(c));
      if (!remember) return;
      const saved = S.town();
      remember.hidden = !sel;
      remember.disabled = !!sel && saved === sel;
      remember.textContent = remember.disabled ? "Remembered on this device" : "Remember my town";
    }
    btns.forEach((b) => b.addEventListener("click", () => { sel = b.dataset.town || ""; apply(); }));
    if (remember) remember.addEventListener("click", () => { if (sel) { S.setTown(sel); apply(); } });
    tools.hidden = false;
    apply();
    const pr = $("#n-print");
    if (pr) { pr.hidden = false; pr.addEventListener("click", () => window.print()); }
  };

  /* ================= /calendar/ ================= */
  const icsText = (s) => String(s || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
  /* fold at 75 octets (continuation lines start with a space) */
  function fold(line) {
    const enc = new TextEncoder();
    let out = "", cur = "", n = 0, limit = 75;
    for (const ch of line) {
      const b = enc.encode(ch).length;
      if (n + b > limit) { out += cur + "\r\n "; cur = ""; n = 0; limit = 74; }
      cur += ch; n += b;
    }
    return out + cur;
  }
  function ics(d) {
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
    const url = location.href.split("#")[0].split("?")[0] + "#" + d.id;
    const lines = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//NK15068//Calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
      "BEGIN:VEVENT", `UID:${d.id}-${d.s || d.d}@nk15068.com`, `DTSTAMP:${stamp}`,
      d.s ? `DTSTART:${d.s}` : `DTSTART;VALUE=DATE:${d.d}`,
      d.s ? `DTEND:${d.e}` : `DTEND;VALUE=DATE:${d.e}`,
      `SUMMARY:${icsText(d.t)}`,
      d.w ? `LOCATION:${icsText(d.w)}` : "",
      d.x ? `DESCRIPTION:${icsText(d.x)}` : "",
      `URL:${url}`, "END:VEVENT", "END:VCALENDAR",
    ].filter(Boolean);
    return lines.map(fold).join("\r\n") + "\r\n";
  }
  function download(d) {
    const blob = new Blob([ics(d)], { type: "text/calendar;charset=utf-8" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${d.id}.ics` });
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  S.pages.calendar = () => {
    const t = todayISO();
    $$(".cal-item[data-date]").forEach((it) => { if (it.dataset.date < t) it.hidden = true; });
    $$(".cal-group").forEach((g) => {
      const items = $$(".cal-item", g);
      if (items.length && items.every((i) => i.hidden)) g.hidden = true;
    });
    $$("button[data-ics]").forEach((b) => {
      let d = null;
      try { d = JSON.parse(b.dataset.ics); } catch (e) { d = null; }
      if (!d || !d.id || !(d.s || d.d)) return;
      b.hidden = false;
      b.addEventListener("click", () => download(d));
    });
  };
})();
