/* NK15068 — lost & found pets pages: /lost-pets/ (board, Call now card, checklists, near-me sort), post/, flyer/
   and the deploy-only gh-N/ listing pages. Also keeps the home pets box and town-page lists live when their own page
   modules haven't wired them. Needs pets.js (window.NKPets); every element is looked up and guarded. */
(function () {
  "use strict";
  const S = window.NKS;
  if (!S) return;
  const { $, $$, esc } = S;
  const Pets = () => window.NKPets || null;
  const localToday = () => S.isoDay(new Date());
  const flash = (btn, text) => {
    const was = btn.textContent;
    btn.textContent = text;
    setTimeout(() => { btn.textContent = was; }, 1800);
  };
  const openTab = (url) => {
    const a = Object.assign(document.createElement("a"), { href: url, target: "_blank", rel: "noopener" });
    document.body.appendChild(a); a.click(); a.remove();
  };

  /* ================= /lost-pets/ ================= */
  S.pages["lost-pets"] = () => {
    const P = Pets(), main = $("#main"), board = $("#board"), list = $("#pets-list"), status = $("#pets-status");
    if (!P || !board || !list || !status) return;
    const d = board.dataset;
    const B = P.board;
    let spot = null; // {x, y, label}: in memory only; only the label is ever saved
    let mode = "lost";
    let firstDraw = true;

    /* ---- I lost / I found ---- */
    const RANK = {
      lost: { shelter: 0, police: 1, aco: 2, county: 3, warden: 4, vet: 5 },
      found: { police: 0, aco: 1, warden: 2, shelter: 3, county: 4, vet: 5 },
    };
    function setMode(m) {
      mode = m === "found" ? "found" : "lost";
      main.dataset.mode = mode;
      $$(".lp-toggles .seg").forEach((a) => a.setAttribute("aria-current", String(a.dataset.mode === mode)));
      $$("#call-now .cn-cap").forEach((p) => { p.hidden = p.dataset.for !== mode; });
      const ul = $("#call-now .cn-rows");
      if (ul) $$(".cn-row", ul).sort((a, b) => (RANK[mode][a.dataset.k] ?? 9) - (RANK[mode][b.dataset.k] ?? 9)).forEach((r) => ul.appendChild(r));
    }
    $$(".lp-toggles .seg").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); setMode(a.dataset.mode); }));
    setMode(location.hash === "#found" ? "found" : "lost");
    addEventListener("hashchange", () => { if (location.hash === "#found" || location.hash === "#lost") setMode(location.hash.slice(1)); });

    /* ---- town picker: the town's police (and Lower Burrell's animal control) ---- */
    let town = "New Kensington";
    const picker = $("#call-now .picker");
    function pickTown(t, save) {
      if (!S.TOWNS.includes(t)) return;
      town = t;
      $$("button[data-town]", picker || document.createElement("div")).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.town === t)));
      $$("#call-now .cn-row[data-town]").forEach((r) => { r.hidden = r.dataset.town !== t; });
      if (save) { S.setTown(t); S.setQS({ town: t }); }
    }
    if (picker) {
      picker.hidden = false;
      picker.addEventListener("click", (e) => { const b = e.target.closest("button[data-town]"); if (b) pickTown(b.dataset.town, true); });
    }
    const qTown = S.qs().get("town");
    pickTown(S.TOWNS.includes(qTown) ? qTown : S.town() || "New Kensington", false);

    /* ---- the owner's checklist, remembered on this device ---- */
    const loadChecks = () => { const v = S.getJSONKey("nk-checklist", {}); return v && typeof v === "object" && !Array.isArray(v) ? v : {}; };
    const checks = loadChecks();
    $$(".checklist input[data-check]").forEach((cb) => {
      cb.checked = !!checks[cb.dataset.check];
      cb.addEventListener("change", () => {
        const s = loadChecks();
        if (cb.checked) s[cb.dataset.check] = 1; else delete s[cb.dataset.check];
        S.local.set("nk-checklist", JSON.stringify(s));
      });
    });

    /* ---- board copy ---- */
    const telInline = () => (d.shelterTel ? `<a class="tel-inline" href="tel:+1${d.shelterTel.replace(/\D/g, "").slice(-10)}">${esc(d.shelterTel)}</a>` : "");
    const ext = (u, t) => (u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>` : t);
    function statusHTML() {
      const when = esc(P.checkedText(B.fetched)), whenStop = /\.$/.test(when) ? when : when + ".";
      switch (B.state) {
        case "listed":
          return B.mode === "db"
            ? "Listings posted here are shared with everyone who opens this page. Mark yours reunited when your pet is home."
            : `Listings posted by neighbors through the NK15068 form. Checked ${whenStop} A post comes down when its owner closes it.`;
        case "stale":
          return `The live board didn't answer. These are the listings as of ${whenStop}`;
        case "empty":
          return `No open listings on this board right now (checked ${when}). It only covers posts made here, so also check ${ext(d.pawboost, "PawBoost")} and ${ext(d.petco, "Petco Love Lost")}, and call the shelter, ${telInline()}.`;
        case "unknown":
          return `The board didn't load just now, so we can't tell you what's posted. ${ext(d.issues || P.ISSUES, "See the posts on GitHub ›")} or call ${esc(d.shelterName || "Animal Protectors")}, ${telInline()}.`;
        default:
          return "Checking the board…";
      }
    }
    const distOf = new Map();
    function sorted() {
      distOf.clear();
      const posts = B.posts.slice();
      if (!spot) return posts;
      posts.forEach((p) => distOf.set(p.id, P.distanceFrom(p, spot)));
      const m = (p) => (distOf.get(p.id) ? distOf.get(p.id).m : Infinity);
      return posts.sort((a, b) => m(a) - m(b));
    }
    function summaryHTML(posts) {
      if (B.state === "unknown") {
        return `The board didn't load just now. ${ext(d.issues || P.ISSUES, "See the posts on GitHub ›")}`;
      }
      if (B.state === "empty") {
        return `<a href="#board">The board: no open listings right now (checked ${esc(P.checkedText(B.fetched))}). <span class="bs-go">See the board ›</span></a>`;
      }
      const n = posts.length;
      const newest = posts.map((p) => (p.date || p.created || "").slice(0, 10)).filter(Boolean).sort().pop();
      let near = "";
      const first = posts[0], dist = first && distOf.get(first.id);
      if (spot && dist) {
        const how = dist.mi < 0.1 ? `${Math.max(50, Math.round(dist.m * 3.28084 / 50) * 50)} ft` : `${dist.mi.toFixed(1)} mi`;
        near = ` The nearest, a ${first.status} ${P.animalWord(first)}, is about ${how} from ${esc(P.shortStreet(spot.label))}.`;
      }
      return `<a href="#board">The board: ${n} open listing${n === 1 ? "" : "s"}${newest ? `, newest ${esc(P.shortDate(newest))}` : ""}.${near} <span class="bs-go">See the listings ›</span></a>`;
    }
    let dbBox = null;
    function draw() {
      if (B.state === "loading") {
        if (d.state === "nosnap") status.textContent = "Checking the board…";
        return;
      }
      d.state = B.state;
      status.innerHTML = statusHTML();
      const cnt = $("#board-count");
      if (cnt) cnt.textContent = B.state === "listed" || B.state === "stale" ? `${B.posts.length} open` : "";
      const chk = $("#board-checked");
      if (chk) chk.textContent = B.fetched && B.state !== "unknown" ? ` · Board checked ${P.checkedText(B.fetched)}` : "";
      const posts = sorted();
      $$(":scope > .listing:not(.listing-post)", list).forEach((n) => n.remove());
      const html = posts.map((p) => P.cardHTML(p, { dist: spot ? P.distText(distOf.get(p.id), spot.label) : "" })).join("")
        + (B.state === "empty" ? '<div class="listing listing-empty"><p>Nothing is posted on this board right now.</p></div>' : "");
      const postBox = $("#pets-post", list);
      if (postBox) postBox.insertAdjacentHTML("beforebegin", html); else list.insertAdjacentHTML("beforeend", html);
      if (B.mode === "db" && B.canPost && !dbBox && postBox) { dbBox = buildDbBox(); postBox.replaceWith(dbBox); }
      const sum = $("#board-sum");
      if (sum) { sum.innerHTML = summaryHTML(posts); sum.dataset.state = B.state; }
      S.relabel(list);
      if (firstDraw) {
        firstDraw = false;
        const h = location.hash.slice(1);
        const target = h && /^[\w-]+$/.test(h) ? document.getElementById(h) : null;
        if (target && target.classList.contains("listing")) { target.classList.add("is-target"); target.scrollIntoView({ block: "start" }); }
      }
      if (boardSeen) P.markSeen();
    }

    /* ---- share, reunite ---- */
    list.addEventListener("click", async (e) => {
      const sh = e.target.closest("[data-share]");
      if (sh) {
        const p = B.posts.find((x) => x.id === sh.dataset.share);
        if (!p) return;
        const r = await P.sharePost(p);
        if (r === "copied") flash(sh, "Link copied"); else if (r === "failed") flash(sh, "Couldn't share");
        return;
      }
      const r = e.target.closest("[data-reunite]");
      if (r) {
        r.disabled = true;
        try { await P.markReunited(r.dataset.reunite); } catch (err) { r.disabled = false; status.textContent = err.message || "That didn't save. Try again in a minute."; }
      }
    });

    /* ---- the listings count as seen once the board is on screen (clears the badge) ---- */
    let boardSeen = false;
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((es) => {
        if (es.some((x) => x.isIntersecting)) { boardSeen = true; if (B.known) P.markSeen(); io.disconnect(); }
      }, { threshold: 0.15 });
      io.observe(list);
    } else boardSeen = true;

    /* ---- your corner: typed, saved, or from this device's location ---- */
    const corner = $("#pets-corner"), input = $("#pets-near"), msg = $("#pets-corner-msg"), remember = $("#pets-remember");
    const say = (t) => { if (msg) msg.textContent = t; };
    function saveLabel(label) {
      if (remember && remember.checked && label) S.local.set("nk-corner", label); else S.local.del("nk-corner");
    }
    async function runCorner(text, opts = {}) {
      text = String(text || "").trim();
      if (!text) { spot = null; say(""); S.setQS({ near: null }); draw(); return; }
      say("Finding that corner…");
      try { await P.ensureIndex(); } catch (e) { say("The street map didn't load just now. Try again in a minute."); return; }
      const g = P.geocodeNear(text, town);
      if (!g) { spot = null; say("We couldn't find that corner. Try two street names, like 5th Avenue & 9th Street."); draw(); return; }
      spot = { x: g.x, y: g.y, label: g.label };
      say(`Sorted by distance from ${P.shortStreet(g.label)}.`);
      if (!opts.quiet) { S.setQS({ near: text }); saveLabel(text); }
      draw();
    }
    if (corner && input) {
      corner.hidden = false;
      $("#pets-sort").addEventListener("click", () => runCorner(input.value));
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); runCorner(input.value); } });
      if (remember) remember.addEventListener("change", () => saveLabel(input.value.trim()));
      const consent = $("#pets-consent");
      $("#pets-loc").addEventListener("click", () => {
        if (!navigator.geolocation) { say("This browser can't share a location. Type a corner instead."); return; }
        if (consent) consent.hidden = false;
        $("#pets-consent-go")?.focus();
      });
      $("#pets-consent-no")?.addEventListener("click", () => { consent.hidden = true; $("#pets-loc").focus(); });
      $("#pets-consent-go")?.addEventListener("click", () => {
        consent.hidden = true;
        say("Finding your nearest street…");
        navigator.geolocation.getCurrentPosition(async (pos) => {
          try {
            const [meta] = await Promise.all([P.loadMeta(), P.ensureIndex()]);
            const lon = pos.coords.longitude, lat = pos.coords.latitude;
            const x = (lon - meta.origin[0]) * meta.kx, y = (meta.origin[1] - lat) * meta.ky;
            const [x0, y0, x1, y1] = meta.bounds;
            if (x < x0 || x > x1 || y < y0 || y > y1) { say("You look to be outside 15068. Type a corner instead."); return; }
            const names = P.nearestStreets(x, y, 150);
            if (!names.length) { say("We couldn't find a street near you. Type a corner instead."); return; }
            const label = "Near " + names.map(P.shortStreet).join(" & ");
            input.value = label;
            spot = { x, y, label: names.join(" & ") };
            say(`Sorted by distance from ${P.shortStreet(spot.label)}.`);
            saveLabel(label);
            draw();
          } catch (e) { say("The street map didn't load just now. Type a corner instead."); }
        }, () => say("Your location isn't available. Type a corner instead."), { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
      });
      const qNear = S.qs().get("near"), saved = S.local.get("nk-corner");
      if (saved && remember) remember.checked = true;
      const start = qNear || saved;
      if (start) { input.value = start; runCorner(start, { quiet: !qNear }); }
    }

    /* ---- in the artifact preview the board is a shared store: post right here ---- */
    function buildDbBox() {
      const box = document.createElement("div");
      box.className = "listing listing-post";
      box.id = "pets-post";
      const today = localToday(), L = P.LIMITS;
      box.innerHTML = `<h3>Place a free listing</h3>
        <p>Lost, found or spotted a pet in 15068? Post it here and everyone who opens this page sees it.</p>
        <button type="button" class="btn-line" id="pets-open" aria-expanded="false" aria-controls="pets-form">Write a listing</button>
        <form id="pets-form" class="petform" hidden>
          <label>Lost, found or spotted?<select name="status" required><option value="lost">Lost</option><option value="found">Found</option><option value="spotted">Spotted</option></select></label>
          <label>Animal<select name="animal"><option value="dog">Dog</option><option value="cat">Cat</option><option value="other">Other</option></select></label>
          <label>Pet's name (if known)<input name="name" maxlength="${L.name}" autocomplete="off"></label>
          <label>Description<textarea name="desc" maxlength="${L.desc}" required placeholder="Breed, color, size, collar or tags"></textarea></label>
          <label>Last seen near<input name="near" maxlength="${L.near}" required placeholder="Fifth Avenue &amp; 9th Street" autocomplete="off"></label>
          <label>Town<select name="town">${P.TOWNS.map((t) => `<option>${esc(t)}</option>`).join("")}</select></label>
          <label>Date<input type="date" name="date" required value="${today}" max="${today}"></label>
          <label>How to reach you (public)<input name="contact" maxlength="${L.contact}" required autocomplete="off"></label>
          <p class="fine">Everyone who can open this page sees the listing. Give a street and cross street rather than a house number; house numbers are removed.</p>
          <button type="submit" class="btn-line">Post the listing</button>
          <p class="form-msg" role="status"></p>
        </form>`;
      const form = box.querySelector("form"), openBtn = box.querySelector("#pets-open"), fmsg = box.querySelector(".form-msg");
      openBtn.onclick = () => { form.hidden = !form.hidden; openBtn.setAttribute("aria-expanded", String(!form.hidden)); if (!form.hidden) form.status.focus(); };
      form.onsubmit = async (e) => {
        e.preventDefault();
        const f = new FormData(form), post = {};
        for (const k of ["status", "animal", "name", "desc", "near", "town", "date", "contact"]) post[k] = String(f.get(k) || "").trim().slice(0, L[k] || 40);
        post.near = P.cleanNear(post.near);
        try {
          await P.ensureIndex();
          const g = P.geocodeNear(post.near, post.town);
          if (g) Object.assign(post, { x: Math.round(g.x), y: Math.round(g.y), prec: g.prec, placeLabel: g.label });
        } catch (err) { /* posts without a pin are fine */ }
        fmsg.textContent = "Posting…";
        try {
          await P.addPost(post);
          form.reset(); form.date.value = form.date.max = localToday();
          fmsg.textContent = typeof post.x === "number" ? "Posted. It's on the board and the map." : "Posted. That street wasn't found on the map, so the listing has no pin.";
        } catch (err) {
          fmsg.textContent = err.message || "It didn't post. Try again in a minute.";
          if (B.readOnly) form.querySelectorAll("input, select, textarea, button").forEach((el) => { el.disabled = true; });
        }
      };
      return box;
    }

    P.loadBoard({ ui: { onChange: draw } });
    draw();
  };

  /* ================= /lost-pets/post/ ================= */
  S.pages["lost-pets-post"] = () => {
    const P = Pets(), form = $("#post-form");
    if (!P || !form) return;
    const f = (id) => $("#" + id);
    const msg = (t) => { const m = f("post-msg"); if (m) m.textContent = t; };
    const today = localToday();
    const date = f("f-date");
    if (date) { date.max = today; if (!date.value) date.value = today; }
    /* coming back from the flyer: the draft is still in this tab */
    let old = null;
    try { old = JSON.parse(S.session.get("nk-flyer-draft") || "null"); } catch (e) { old = null; }
    if (old && typeof old === "object") {
      const set = (id, v) => { if (f(id) && v) f(id).value = v; };
      set("f-status", P.STATUS[old.status]); set("f-animal", old.animal ? old.animal[0].toUpperCase() + old.animal.slice(1) : "");
      set("f-name", old.name); set("f-desc", old.desc); set("f-near", old.near); set("f-town", old.town);
      set("f-date", old.date); set("f-contact", old.contact);
    }
    f("f-near")?.addEventListener("change", () => {
      const el = f("f-near"), v = P.cleanNear(el.value);
      if (v !== el.value.trim()) { el.value = v; msg("House numbers are removed. The street and cross street are what gets posted."); }
    });
    const draft = () => ({
      status: f("f-status").value.toLowerCase(), animal: f("f-animal").value.toLowerCase(), name: f("f-name").value.trim(),
      desc: f("f-desc").value.trim(), near: P.cleanNear(f("f-near").value), town: f("f-town").value, date: f("f-date").value,
      contact: f("f-contact").value.trim(),
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!form.reportValidity()) return;
      openTab(P.issueUrl(draft()));
      msg("GitHub's form opened in a new tab with your details typed in. Check them, add a photo if you like, and submit.");
    });

    /* photo for the flyer only: kept in this tab, shrunk if it's big */
    async function photoURL() {
      const file = f("f-photo")?.files?.[0];
      if (!file || !/^image\//.test(file.type)) return "";
      const read = (blob) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(blob); });
      if (file.size < 1.5e6) return read(file);
      try {
        const bmp = await createImageBitmap(file);
        const k = Math.min(1, 1400 / Math.max(bmp.width, bmp.height));
        const c = Object.assign(document.createElement("canvas"), { width: Math.round(bmp.width * k), height: Math.round(bmp.height * k) });
        c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
        const url = c.toDataURL("image/jpeg", 0.85);
        return url.length < 2e6 ? url : "";
      } catch (e) { return ""; }
    }
    const fl = f("post-flyer");
    if (fl) {
      fl.hidden = false;
      fl.addEventListener("click", async () => {
        if (!form.reportValidity()) return;
        const d = draft();
        d.photo = await photoURL();
        if (!S.session.set("nk-flyer-draft", JSON.stringify(d))) {
          delete d.photo;
          S.session.set("nk-flyer-draft", JSON.stringify(d));
        }
        location.href = S.url("lost-pets/flyer/");
      });
    }
    const sh = f("post-share");
    if (sh) {
      sh.hidden = false;
      sh.addEventListener("click", async () => {
        if (!form.reportValidity()) return;
        const d = draft();
        const r = await S.share({ title: P.headline(d), text: P.shareText(d), url: S.abs("lost-pets/") });
        if (r === "copied") flash(sh, "Copied"); else if (r === "failed") flash(sh, "Couldn't share");
      });
    }
    const mail = f("post-mail");
    if (mail && form.dataset.email) {
      mail.addEventListener("click", (e) => {
        if (!form.reportValidity()) { e.preventDefault(); return; }
        mail.href = P.mailtoUrl(draft(), form.dataset.email);
      });
    }
  };

  /* ================= /lost-pets/flyer/ ================= */
  S.pages["lost-pets-flyer"] = async () => {
    const P = Pets(), note = $("#fl-note");
    const pb = $("#fl-print");
    if (pb) pb.addEventListener("click", () => window.print());
    const post_ = S.url("lost-pets/post/"), board_ = S.url("lost-pets/");
    if (note) note.innerHTML = `There&rsquo;s no pet on this flyer yet. Fill in the <a href="${esc(post_)}">Post a pet</a> form and tap Make a flyer, or tap Flyer on a listing on <a href="${esc(board_)}#board">the board</a>.`;
    const back = $("#fl-back");
    if (back) {
      let same = false;
      try { same = !!document.referrer && new URL(document.referrer).origin === location.origin; } catch (e) { same = false; }
      if (same && history.length > 1) back.addEventListener("click", (e) => { e.preventDefault(); history.back(); });
    }
    if (!P) return;
    const id = S.qs().get("pet");
    let post = null, photo = "";
    if (id) {
      if (note) note.textContent = "Getting that listing from the board…";
      await P.loadBoard();
      post = P.board.posts.find((p) => p.id === id) || null;
      if (!post) {
        if (note) note.textContent = P.board.state === "unknown"
          ? "The board didn't load just now, so the flyer can't be filled in. Try again in a minute."
          : "That listing isn't on the board now. Its owner may have closed it.";
        return;
      }
      photo = post.photo || "";
    } else {
      let dr = null;
      try { dr = JSON.parse(S.session.get("nk-flyer-draft") || "null"); } catch (e) { dr = null; }
      if (dr && typeof dr === "object") {
        post = P.sanitize({ ...dr, id: "draft" }, "board");
        photo = typeof dr.photo === "string" && /^data:image\//.test(dr.photo) ? dr.photo : "";
      }
      if (!post) return;
    }
    const animal = P.animalWord(post);
    const h = `${P.STATUS[post.status].toUpperCase()} ${animal.toUpperCase()}`;
    const q = post.status === "lost" ? (post.name ? `Have you seen ${post.name}?` : `Have you seen this ${animal}?`)
      : post.status === "found" ? `Is this your ${animal}?` : (post.name ? `Is this ${post.name}?` : `Have you lost this ${animal}?`);
    const day = post.date || String(post.created || "").slice(0, 10);
    const w = P.where(post);
    const seen = w ? `${P.nearLine({ ...post, prec: null }).replace(/ \(no cross street given\)$/, "")}${day ? ", " + S.apLong(day, false) : ""}` : "";
    let contact = post.contact || "";
    if (!contact || /^comment\b/i.test(contact)) {
      const u = new URL(P.shareUrl(post), location.href);
      contact = `Details: ${u.host}${u.pathname}${u.hash}`;
    }
    const set = (sel, t) => { const el = $(sel); if (el) el.textContent = t; };
    /* phone numbers never break across lines on paper */
    const nobreak = (t) => esc(t).replace(/\(?\b\d{3}\)?[-. ]?\d{3}[-. ]\d{4}\b/g, '<span class="nw">$&</span>');
    set("#fl-h", h); set("#fl-q", q); set("#fl-desc", post.desc || ""); set("#fl-seen", seen);
    const ce = $("#fl-contact");
    if (ce) ce.innerHTML = nobreak(contact);
    const img = $("#fl-photo");
    if (img && photo) { img.src = photo; img.alt = post.name ? `Photo of ${post.name}` : `Photo of the ${animal}`; img.hidden = false; }
    const tabs = $("#fl-tabs");
    if (tabs) {
      const t = `${post.name || cap(animal)} · ${contact.replace(/^Details: /, "")}`;
      tabs.innerHTML = Array.from({ length: 8 }, () => `<li>${nobreak(t)}</li>`).join("");
    }
    const flyer = $("#flyer");
    if (flyer) flyer.dataset.status = post.status;
    if (note) note.hidden = true;
    if (pb) pb.hidden = false;
    $(".flyer-page")?.classList.add("filled");
    document.title = `${h}${post.name ? ": " + post.name : ""} · NK15068`;
  };
  const cap = (s) => String(s || "").replace(/^./, (c) => c.toUpperCase());

  /* ================= /lost-pets/gh-N/ ================= */
  S.pages["lost-pets-listing"] = () => {
    const P = Pets();
    if (!P) return;
    P.loadBoard();
    $$("[data-share]").forEach((b) => {
      b.hidden = false;
      b.addEventListener("click", async () => {
        await P.loadBoard();
        const p = P.board.posts.find((x) => x.id === b.dataset.share);
        const url = location.href.split(/[?#]/)[0];
        const r = p ? await S.share({ title: P.headline(p), text: P.shareText(p), url })
          : await S.share({ title: document.title, text: ($("h1") || {}).textContent || "", url });
        if (r === "copied") flash(b, "Link copied"); else if (r === "failed") flash(b, "Couldn't share");
      });
    });
  };

  /* ================= home box and town lists, if their page modules didn't wire them ================= */
  function wire() {
    const P = Pets();
    if (!P) return;
    const box = $("#pets-box");
    if (box) P.renderHomeBox(box);
    $$("[data-pets-town]").forEach((el) => P.renderTownList(el, el.dataset.petsTown));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire); else setTimeout(wire, 0);
})();
