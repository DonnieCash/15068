/* NK15068 — towns hub, town pages, news, history, poster and privacy (owner: towns pages).
   Every page's text is already in the HTML; this adds town chips, "New to you", My town, the street poster,
   PNG export and "Forget my settings". */
(function () {
  "use strict";
  const S = window.NKS;
  if (!S) return;
  const { $, $$, esc } = S;

  /* a link to an item inside a closed <details> (news/#n-…) opens it */
  function openTarget() {
    let id = "";
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (e) { return; }
    const el = id && document.getElementById(id);
    if (!el) return;
    const d = el.closest("details");
    if (d && !d.open) { d.open = true; el.scrollIntoView(); }
  }
  addEventListener("hashchange", openTarget);

  /* town chips: All · New Kensington · Arnold · Lower Burrell, filtering items by data-towns="A|B" */
  function wireChips(what, items, noun, after) {
    const row = $(`[data-chips="${what}"]`);
    if (!row || !items.length) return;
    row.hidden = false;
    const btns = $$("button[data-town]", row), count = $(".chip-count", row);
    function apply(town) {
      btns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.town === town)));
      let n = 0;
      items.forEach((el) => {
        const ok = !town || (el.dataset.towns || "").split("|").includes(town);
        el.hidden = !ok;
        if (ok) n++;
      });
      count.textContent = town ? `${n} of ${items.length} ${noun} mention ${town}.` : "";
      if (after) after(town, n);
    }
    row.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-town]");
      if (b) apply(b.dataset.town);
    });
  }

  /* ================= /towns/ : my town's card first ================= */
  S.pages.towns = () => {
    const t = S.town(), grid = $("#towns-grid");
    if (!t || !grid) return;
    const card = $$(".tw-card", grid).find((c) => c.dataset.town === t);
    if (card) { grid.prepend(card); card.classList.add("mine"); }
  };

  /* ================= /towns/<town>/ ================= */
  S.pages.town = () => {
    const btn = $("[data-my-town]"), note = $(".cc-mine-note");
    if (btn) {
      const t = btn.dataset.myTown;
      const sync = () => {
        const mine = S.town() === t;
        btn.setAttribute("aria-pressed", String(mine));
        btn.textContent = mine ? `${t} is my town` : `Make ${t} my town`;
      };
      btn.hidden = false;
      sync();
      btn.addEventListener("click", () => {
        const was = S.town() === t;
        S.setTown(was ? null : t);
        sync();
        if (note) {
          note.hidden = false;
          note.textContent = was ? "Done. No town is saved on this device now."
            : `Saved on this device. ${t} now comes first on the front page, Phone numbers, Lost pets and Crime.`;
        }
      });
      document.addEventListener("nk-town", sync);
    }
    const P = window.NKPets;
    if (P && P.renderTownList) $$("[data-pets-town]").forEach((el) => P.renderTownList(el, el.dataset.petsTown));
    openTarget();
  };

  /* ================= /news/ ================= */
  S.pages.news = () => {
    const arts = $$("article.brief");
    /* "New to you": briefs this device hasn't listed before (the first visit marks nothing) */
    const seen = S.getJSONKey("nk-seen-news", null);
    if (Array.isArray(seen)) {
      const set = new Set(seen);
      arts.forEach((a) => { if (!set.has(a.id)) { const tag = $(".new-tag", a); if (tag) tag.hidden = false; } });
    }
    const ids = arts.map((a) => a.id);
    const keep = [...new Set([...(Array.isArray(seen) ? seen : []).filter((i) => typeof i === "string"), ...ids])].slice(-300);
    S.local.set("nk-seen-news", JSON.stringify(keep));
    const earlier = $("#earlier"), none = $("#news-none");
    wireChips("news", arts, "briefs", (town, n) => {
      if (earlier) earlier.hidden = !!town && !$$(".brief", earlier).some((a) => !a.hidden);
      if (none) none.hidden = n > 0;
    });
    openTarget();
  };

  /* ================= /history/ ================= */
  S.pages.history = () => {
    const items = $$(".era .tl-item"), none = $("#tl-none");
    wireChips("history", items, "events", (town, n) => {
      $$(".era").forEach((sec) => { sec.hidden = !!town && !$$(".tl-item", sec).some((i) => !i.hidden); });
      if (none) none.hidden = n > 0;
    });
    openTarget();
  };

  /* ================= /privacy/ : Forget my settings ================= */
  S.pages.privacy = () => {
    const b = $("#forget"), msg = $("#forget-msg");
    if (!b) return;
    b.hidden = false;
    b.addEventListener("click", () => {
      [S.local, S.session].forEach((st) => st.keys().filter((k) => k.startsWith("nk-")).forEach((k) => st.del(k)));
      delete document.documentElement.dataset.theme;
      S.syncTheme();
      S.setBadge(0);
      if (msg) msg.textContent = "Done. Your settings on this device are cleared.";
    });
  };

  /* ================= /poster/ ================= */
  const getJSON = (p) => fetch(S.url(p)).then((r) => (r.ok ? r.json() : Promise.reject(new Error(p + " " + r.status))));
  const getText = (u) => fetch(u).then((r) => (r.ok ? r.text() : Promise.reject(new Error(u + " " + r.status))));

  function download(blob, name) {
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  /* rasterize an SVG document to PNG on this device (3600 x 4800, smaller if the browser's canvas limit is lower) */
  async function savePNG(svgText, name, msg) {
    if (msg) msg.textContent = "Drawing the PNG…";
    const url = URL.createObjectURL(new Blob([svgText], { type: "image/svg+xml" }));
    try {
      const img = new Image();
      await new Promise((res, rej) => { img.onload = res; img.onerror = () => rej(new Error("svg")); img.src = url; });
      for (const [w, h] of [[3600, 4800], [3000, 4000], [2400, 3200]]) {
        let c = document.createElement("canvas");
        c.width = w; c.height = h;
        const ctx = c.getContext("2d");
        if (!ctx) continue;
        ctx.drawImage(img, 0, 0, w, h);
        const out = await new Promise((r) => { try { c.toBlob(r, "image/png"); } catch (e) { r(null); } });
        c.width = c.height = 0; c = null;
        if (!out) continue;
        download(out, name);
        if (msg) msg.textContent = w === 3600 ? "Saved a 3600 × 4800 PNG." : `Saved a ${w} × ${h} PNG, the largest this browser can make.`;
        return;
      }
      if (msg) msg.textContent = "This browser couldn't make the PNG. Download the SVG instead; it prints at any size.";
    } catch (e) {
      if (msg) msg.textContent = "This browser couldn't make the PNG. Download the SVG instead; it prints at any size.";
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  /* street names: the same key pets.js and nkpages.fmt use ('Fifth Avenue' and '5th Ave' -> {core: '5', type: 'ave'}) */
  const ORD = Object.assign(Object.create(null), { first: "1", second: "2", third: "3", fourth: "4", fifth: "5", sixth: "6", seventh: "7", eighth: "8", ninth: "9", tenth: "10",
    eleventh: "11", twelfth: "12", thirteenth: "13", fourteenth: "14", fifteenth: "15", sixteenth: "16", seventeenth: "17", eighteenth: "18",
    nineteenth: "19", twentieth: "20" });
  const TYPES = Object.assign(Object.create(null), { street: "st", st: "st", avenue: "ave", ave: "ave", av: "ave", road: "rd", rd: "rd", drive: "dr", dr: "dr", boulevard: "blvd",
    blvd: "blvd", lane: "ln", ln: "ln", court: "ct", ct: "ct", place: "pl", pl: "pl", way: "way", alley: "aly", aly: "aly", terrace: "ter",
    ter: "ter", highway: "hwy", hwy: "hwy", pike: "pike", circle: "cir", cir: "cir" });
  function streetKey(name) {
    if (window.NKPets && window.NKPets.streetKey) return window.NKPets.streetKey(name);
    let t = String(name || "").toLowerCase().replace(/[.,#']/g, " ").split(/\s+/).filter(Boolean);
    t = t.map((w) => ORD[w] || w.replace(/^(\d+)(st|nd|rd|th)$/, "$1"));
    let type = null;
    while (t.length && TYPES[t[t.length - 1]]) { type = type || TYPES[t[t.length - 1]]; t.pop(); }
    if (t.length > 1 && /^(n|s|e|w|north|south|east|west)$/.test(t[0])) t.shift();
    const core = t.join(" ");
    return core ? { core, type } : null;
  }
  /* the streets a query could mean, best first: an exact name, then the same street key (Fifth Ave = 5th Avenue),
     then names that start with or contain the text */
  function findStreets(q, streets) {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    const big = (a, b) => (b.a || 0) - (a.a || 0) || b.m - a.m;
    const out = [], add = (list) => list.sort(big).forEach((x) => { if (!out.includes(x)) out.push(x); });
    add(streets.filter((x) => x.n.toLowerCase() === s));
    const k = streetKey(q);
    if (k) add(streets.filter((x) => { const kk = streetKey(x.n); return kk && kk.core === k.core && (!k.type || kk.type === k.type); }));
    add(streets.filter((x) => x.n.toLowerCase().startsWith(s)));
    add(streets.filter((x) => x.n.toLowerCase().includes(s)));
    return out;
  }

  let world = null;
  function loadWorld() {
    if (!world) {
      world = Promise.all([getJSON("data/meta.json"), getJSON("data/roads.json"), getJSON("data/streets.json")]).then(([meta, roads, streets]) => {
        const q = meta.q;
        const lines = roads.r.map(([rank, ni, , c]) => ({ rank, n: ni >= 0 ? roads.names[ni] : null, c }));
        return { meta, q, lines, streets };
      });
      world.catch(() => { world = null; });
    }
    return world;
  }
  const dec = (c, q) => { const out = []; let x = 0, y = 0; for (let i = 0; i + 1 < c.length; i += 2) { x += c[i]; y += c[i + 1]; out.push([x / q, y / q]); } return out; };
  const TOWN_NAME = { Allegheny: "Allegheny Township" };
  const niceLen = (m) => { const e = 10 ** Math.floor(Math.log10(Math.max(m, 1))); return Math.max(...[1, 2, 5].map((f) => f * e).filter((v) => v <= m)); };
  const r1 = (v) => Math.round(v * 10) / 10;

  /* the poster cropped to one street: viewBox around it, line weights kept the same on paper, the street in the
     highlight colour at 3x its width, and its name and towns in the title */
  function streetPoster(svgText, street, W) {
    const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
    const root = doc.documentElement, map = doc.getElementById("map");
    if (!map || root.nodeName !== "svg") throw new Error("poster");
    const mine = W.lines.filter((l) => l.n === street.n).map((l) => ({ rank: l.rank, pts: dec(l.c, W.q) }));
    if (!mine.length) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    mine.forEach((l) => l.pts.forEach(([x, y]) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }));
    const pad = 400, mw = +map.getAttribute("width"), mh = +map.getAttribute("height");
    let w = x1 - x0 + 2 * pad, h = y1 - y0 + 2 * pad;
    const k = Math.max(w / mw, h / mh);
    w = mw * k; h = mh * k;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    map.setAttribute("viewBox", `${Math.round(cx - w / 2)} ${Math.round(cy - h / 2)} ${Math.round(w)} ${Math.round(h)}`);
    /* the same line weights on paper, a touch bolder so a few streets don't look faint */
    const kk = k * 1.25;
    $$("[data-w]", map).forEach((el) => el.setAttribute("stroke-width", r1(+el.dataset.w * kk)));
    const zl = doc.getElementById("zipline");
    if (zl && zl.dataset.dash) zl.setAttribute("stroke-dasharray", zl.dataset.dash.split(" ").map((v) => Math.round(v * kk)).join(" "));
    $$("text[data-fs]", map).forEach((t) => {
      const fs = +t.dataset.fs * k;
      t.setAttribute("font-size", r1(fs));
      t.setAttribute("stroke-width", r1(fs * 0.24));
      t.setAttribute("letter-spacing", r1(fs * 0.14));
    });
    /* the street itself, over the roads and under the town names */
    const NS = "http://www.w3.org/2000/svg";
    const top = Math.min(...mine.map((l) => l.rank));
    const base = { 0: 7, 1: 6.2, 2: 5.2, 3: 3.8, 4: 2.8, 5: 2.1, 6: 1.3, 7: 1.1 }[top] || 2;
    const hi = doc.createElementNS(NS, "path");
    hi.setAttribute("d", mine.map((l) => "M" + l.pts.map(([x, y]) => `${Math.round(x)} ${Math.round(y)}`).join("L")).join(""));
    hi.setAttribute("fill", "none");
    hi.setAttribute("stroke", root.dataset.focus || "#0b63c4");
    hi.setAttribute("stroke-width", r1(Math.max(base * 3, 6) * kk));
    hi.setAttribute("stroke-linecap", "round");
    hi.setAttribute("stroke-linejoin", "round");
    const towns = doc.getElementById("towns");
    map.insertBefore(hi, towns);
    /* title, subtitle, scale */
    const names = (street.t || []).map((t) => TOWN_NAME[t] || t);
    const title = `${street.n}${names.length ? " · " + names.join(" · ") : ""}, PA 15068`.toUpperCase();
    const tt = doc.getElementById("title");
    if (tt) {
      const fs = Math.min(118, 3300 / (title.length * 0.72));
      tt.textContent = title;
      tt.setAttribute("font-size", r1(fs));
      tt.setAttribute("letter-spacing", r1(fs * 0.05));
    }
    const st = doc.getElementById("subtitle"), m = W.meta;
    if (st) {
      const lon = m.origin[0] + cx / m.kx, lat = m.origin[1] - cy / m.ky;
      st.textContent = `ZIP 15068 · ${Math.abs(lat).toFixed(2)}° N, ${Math.abs(lon).toFixed(2)}° W`;
    }
    const sc = doc.getElementById("scale");
    if (sc) {
      const ink = root.dataset.ink || "#191a1b", y = +sc.querySelector("rect").getAttribute("y");
      const len = niceLen(520 * k), L = len / k, sx = 1800 - L / 2;
      const lab = len >= 1000 ? `${len / 1000} km` : `${len} m`, half = len >= 1000 ? `${len / 2000}` : `${len / 2}`;
      const txt = (x, s) => `<text x="${Math.round(x)}" y="${y + 62}" font-family="'Radio Canada', 'Helvetica Neue', Arial, sans-serif" font-size="36" text-anchor="middle" fill="${ink}">${s}</text>`;
      const g = new DOMParser().parseFromString(`<svg xmlns="${NS}"><g id="scale">`
        + `<rect x="${Math.round(sx)}" y="${y}" width="${Math.round(L / 2)}" height="14" fill="${ink}"/>`
        + `<rect x="${Math.round(sx + L / 2)}" y="${y}" width="${Math.round(L / 2)}" height="14" fill="none" stroke="${ink}" stroke-width="3"/>`
        + txt(sx, "0") + txt(sx + L / 2, half) + txt(sx + L, lab) + "</g></svg>", "image/svg+xml").documentElement.firstChild;
      sc.replaceWith(doc.importNode(g, true));
    }
    const ti = doc.querySelector("title");
    if (ti) ti.textContent = `${street.n} in ZIP 15068, with every road around it`;
    return new XMLSerializer().serializeToString(doc);
  }

  S.pages.poster = () => {
    const png = $("#poster-png"), msg = $("#poster-msg");
    const posterSrc = () => (S.isDark() ? "15068-roads-dark.svg" : "15068-roads.svg");
    if (png) {
      png.hidden = false;
      png.addEventListener("click", async () => {
        png.disabled = true;
        try { await savePNG(await getText(posterSrc()), S.isDark() ? "15068-roads-dark.png" : "15068-roads.png", msg); }
        catch (e) { if (msg) msg.textContent = "The poster didn't load just now. Try again, or download the SVG."; }
        png.disabled = false;
      });
    }
    const form = $("#street-form"), input = $("#street-q"), smsg = $("#street-msg"), out = $("#street-out");
    if (!form || !input) return;
    form.hidden = false;
    let listed = false, current = null;
    const fill = () => {
      if (listed) return;
      listed = true;
      loadWorld().then((W) => {
        const names = [...new Set(W.streets.map((s) => s.n))].sort((a, b) => a.localeCompare(b));
        $("#street-list").innerHTML = names.map((n) => `<option value="${esc(n)}">`).join("");
      }).catch(() => { listed = false; });
    };
    input.addEventListener("focus", fill, { once: true });
    /* a failed lookup must not leave the previous street's poster and downloads on screen */
    const clearOut = () => {
      out.hidden = true;
      current = null;
      const alt = $("#street-alt");
      if (alt) { alt.innerHTML = ""; alt.hidden = true; }
    };
    async function make(pick) {
      const q = input.value;
      if (!q.trim()) { smsg.textContent = "Type a street name first, like Leishman Avenue."; input.focus(); return; }
      smsg.textContent = "Making your poster…";
      try {
        const W = await loadWorld();
        const found = findStreets(q, W.streets);
        const street = pick ? found.find((x) => x.n === pick) || found[0] : found[0];
        if (!street) { clearOut(); smsg.textContent = `We couldn't find “${q.trim()}” in 15068. Try the full name, like Leishman Avenue.`; return; }
        const svg = streetPoster(await getText(posterSrc()), street, W);
        if (!svg) { clearOut(); smsg.textContent = `${street.n} has no mapped lines to draw.`; return; }
        current = { svg, file: S.slug(street.n) + "-15068" };
        const fig = $("#street-fig");
        const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
        fig.innerHTML = `<img src="${url}" width="900" height="1200" alt="Poster of ${esc(street.n)} and the roads around it in ZIP 15068">`;
        const a = $("#street-svg");
        if (a.dataset.url) URL.revokeObjectURL(a.dataset.url);
        a.href = a.dataset.url = url;
        a.download = current.file + ".svg";
        out.hidden = false;
        const where = (street.t || []).map((t) => TOWN_NAME[t] || t).join(" and ");
        smsg.textContent = `Here's ${street.n}${where ? " in " + where : ""}.`;
        const others = found.filter((x) => x !== street).slice(0, 3);
        const alt = $("#street-alt");
        if (alt) {
          alt.innerHTML = others.length ? "Or: " + others.map((x) => `<button type="button" class="linkbtn" data-street="${esc(x.n)}">${esc(x.n)}${x.t && x.t.length ? " (" + esc(x.t.map((t) => TOWN_NAME[t] || t).join(", ")) + ")" : ""}</button>`).join(" · ") : "";
          alt.hidden = !others.length;
        }
        out.scrollIntoView({ block: "nearest" });
      } catch (err) {
        smsg.textContent = "The map data didn't load just now. Try again in a moment.";
      }
    }
    form.addEventListener("submit", (e) => { e.preventDefault(); make(); });
    const altBox = $("#street-alt");
    if (altBox) altBox.addEventListener("click", (e) => {
      const b = e.target.closest("[data-street]");
      if (b) { input.value = b.dataset.street; make(b.dataset.street); }
    });
    const spng = $("#street-png");
    if (spng) spng.addEventListener("click", async () => {
      if (!current) return;
      spng.disabled = true;
      await savePNG(current.svg, current.file + ".png", smsg);
      spng.disabled = false;
    });
  };

  /* pages with nothing live but <details> targets */
  ["towns", "people", "eat", "whats-new", "about", "sources"].forEach((p) => {
    const prev = S.pages[p];
    S.pages[p] = () => { if (prev) prev(); openTarget(); };
  });
})();
