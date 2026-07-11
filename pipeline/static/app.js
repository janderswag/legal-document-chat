/* SAM-style local UI — vanilla JS, no framework, no CDN. Client-side view router +
   per-view data fetches.

   UX-2 information architecture: five destinations — Matters (the case file: its
   documents, uploads, chats, and tools live INSIDE a matter), Chat (with past
   conversations in a rail), Search, Review & Compare (contract checklist + document
   comparison as tabs, with an explicit document picker), Settings.

   UX-3 state rule: views are built ONCE and then shown/hidden — switching views never
   rebuilds a view's DOM, so an in-progress chat, a finished contract review, or a
   streaming comparison grid survives navigation. Refresh functions update data
   (pickers, tables, rails) without ever touching result containers. */
(function () {
  "use strict";
  var VIEWS = ["chat", "history", "hub", "review", "settings", "billing", "referrals"];
  // The active matter persists across launches (P1.4) — localStorage holds the slug
  // only (never document content); it is re-validated against /matters on every load.
  var MATTER_KEY = "docuchat.activeMatter";
  var state = { matter: null, matters: [] };
  try { state.matter = localStorage.getItem(MATTER_KEY) || null; } catch (e) {}
  window.appState = state;
  window.viewHooks = window.viewHooks || {};

  // --- helpers ---------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  window.esc = esc;

  async function api(path, opts) {
    var r = await fetch(path, opts);
    var data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) throw new Error((data && data.detail) || ("HTTP " + r.status));
    return data;
  }
  window.api = api;

  function parseSseBlock(block) {
    var ev = null, data = null;
    block.split("\n").forEach(function (line) {
      if (line.indexOf("event:") === 0) ev = line.slice(6).trim();
      else if (line.indexOf("data:") === 0) { try { data = JSON.parse(line.slice(5).trim()); } catch (e) {} }
    });
    return ev ? { event: ev, data: data } : null;
  }

  // Build-once guard (UX-3): the first call builds the view's skeleton; later calls
  // are no-ops so results already rendered in the view are never destroyed.
  function ensureBuilt(name, buildFn) {
    var inner = document.querySelector("#view-" + name + " .view-inner");
    if (!inner || inner.dataset.built) return false;
    inner.dataset.built = "1";
    buildFn(inner);
    return true;
  }

  function setActiveMatter(slug, label) {
    state.matter = slug || null;
    try {
      if (state.matter) localStorage.setItem(MATTER_KEY, state.matter);
      else localStorage.removeItem(MATTER_KEY);
    } catch (e) {}
    document.querySelectorAll(".matter-picker").forEach(function (sel) {
      if (sel.value !== state.matter) sel.value = state.matter || "";
    });
    if (typeof window.onMatterChange === "function") window.onMatterChange();
  }
  window.setActiveMatter = setActiveMatter;

  // A shared <select> matter picker (reused across views). Also enforces the P1.4
  // default: a stale stored matter is dropped, and when none is active the first
  // matter (preferring the seeded sample) becomes active — so the app never presents a
  // "no matter selected" dead-end while matters exist.
  async function fillMatterPickers() {
    var data = await api("/matters");
    var matters = (data && data.matters) || [];
    state.matters = matters;
    document.querySelectorAll(".matter-picker").forEach(function (sel) {
      sel.innerHTML = '<option value="">— choose matter —</option>' +
        matters.map(function (m) {
          return '<option value="' + esc(m.slug) + '">' + esc(m.display_name) +
            " (" + m.doc_count + ")</option>";
        }).join("");
      if (state.matter) sel.value = state.matter;
    });
    var current = null;
    matters.forEach(function (m) { if (m.slug === state.matter) current = m; });
    if (state.matter && !current) setActiveMatter(null);          // stale -> clear
    if (!state.matter && matters.length) {
      var pick = matters.filter(function (m) { return m.sample; })[0] || matters[0];
      setActiveMatter(pick.slug, pick.display_name);
    } else if (current) {
      setActiveMatter(current.slug, current.display_name);        // refresh the label
    }
    return matters;
  }
  window.fillMatterPickers = fillMatterPickers;

  // Active-matter change dispatcher: refresh matter-scoped surfaces that are already
  // built. Never calls fillMatterPickers (which calls setActiveMatter -> here).
  window.onMatterChange = function () {
    if (document.getElementById("chat-guide")) renderChatGuide();
    if (document.getElementById("grid-docs")) refreshGridDocs();
  };

  // --- profile + onboarding (UX-5) --------------------------------------------
  // The attorney's LOCAL identity: first name + practice areas, stored only in the
  // local (encrypted) catalog via /profile. Every field has a visible use — the
  // greeting, and practice-tailored suggested prompts. Nothing is collected that
  // the product does not use.
  state.profile = {};

  var photoVer = 0;   // cache-buster for /profile/photo after an upload

  async function loadProfile() {
    try { state.profile = await api("/profile"); } catch (e) { state.profile = {}; }
    updateGreeting();
    refreshSidebarProfile();
    return state.profile;
  }

  // Fetch failures happen when the local app is restarting (e.g. during an
  // update) — say that instead of the browser's cryptic "Failed to fetch".
  function friendlyError(e) {
    return (e && e.message === "Failed to fetch")
      ? "Could not reach the local app (it may be restarting). Try again in a few seconds."
      : (e && e.message) || String(e);
  }

  // UX-8: one-click "Update available" above Billing. Polled once per app load;
  // the backend contacts GitHub at most once a day, only while the Settings
  // toggle is on, and sends nothing (see updates.py).
  async function checkUpdates() {
    try {
      var u = await api("/updates/status");
      var existing = document.getElementById("update-nav");
      if (!u.update_available) { if (existing) existing.remove(); return; }
      if (existing) return;
      var foot = document.getElementById("nav-foot");
      if (!foot) return;
      var b = document.createElement("button");
      b.className = "nav-item update";
      b.id = "update-nav";
      b.innerHTML = "<span class='nav-ico'><svg viewBox='0 0 24 24'><path d='M12 3v12'/>" +
        "<path d='m7 10 5 5 5-5'/><path d='M4 21h16'/></svg></span> Update available" +
        (u.latest ? " <span class='upd-ver'>" + esc(u.latest) + "</span>" : "");
      // v0.3.0: one click installs in place — download, verify signature, swap,
      // relaunch. Any failure leaves this version running and falls back to the
      // download page (updater.py).
      var installing = false;
      function setLabel(text) {
        b.innerHTML = "<span class='nav-ico'><svg viewBox='0 0 24 24'>" +
          "<path d='M12 3v12'/><path d='m7 10 5 5 5-5'/><path d='M4 21h16'/>" +
          "</svg></span> " + text;
      }
      async function pollInstall() {
        try {
          var s = (await api("/updates/install/status")) || {};
          if (s.state === "downloading") setLabel("Downloading… " + (s.pct || 0) + "%");
          else if (s.state === "verifying") setLabel("Verifying…");
          else if (s.state === "installing") setLabel("Installing…");
          else if (s.state === "restarting") { setLabel("Restarting…"); return; }
          else if (s.state === "error") {
            installing = false;
            setLabel("Update available" + (u.latest ? " <span class='upd-ver'>" +
              esc(u.latest) + "</span>" : ""));
            b.title = s.detail || "update failed — opening the download page";
            window.open(u.download_page || "https://docuchat.app", "_blank");
            return;
          }
          setTimeout(pollInstall, 1000);
        } catch (e) { /* server restarting mid-swap is expected */ }
      }
      b.addEventListener("click", async function () {
        if (installing) return;
        installing = true;
        try {
          await api("/updates/install", { method: "POST" });
          pollInstall();
        } catch (e) {
          installing = false;
          window.open(u.download_page || "https://docuchat.app", "_blank");
        }
      });
      foot.insertBefore(b, foot.firstChild);
    } catch (e) { /* silent — updates are never a nag */ }
  }

  // Sidebar profile block (UX-6): the user's avatar + first name once known, the
  // app identity until then. There is deliberately NO sign-out — no account exists.
  function refreshSidebarProfile() {
    var nameEl = document.getElementById("side-name");
    var av = document.getElementById("side-avatar");
    if (!nameEl || !av) return;
    var name = ((state.profile && state.profile.name) || "").trim();
    nameEl.textContent = name || "Legal Document Chat";
    if (state.profile && state.profile.has_photo) {
      av.innerHTML = "<img src='/profile/photo?v=" + photoVer + "' alt=''>";
    } else if (name) {
      av.textContent = name[0].toUpperCase();
    } else {
      av.textContent = "§";
    }
  }

  function updateGreeting() {
    var el = document.getElementById("chat-greet-title");
    if (!el) return;
    var name = ((state.profile && state.profile.name) || "").trim().split(/\s+/)[0];
    if (!name) { el.textContent = "What would you like to ask?"; return; }
    var h = new Date().getHours();
    var tod = h < 12 ? "Good morning" : (h < 18 ? "Good afternoon" : "Good evening");
    el.textContent = tod + ", " + name + ".";
  }

  // Practice-tailored prompt templates (generic document questions, honest: they do
  // not presume specific content — the user can edit before sending).
  var PRACTICE_PROMPTS = {
    "Business & Contracts": [
      "List every termination right in these documents",
      "What are the indemnification obligations?",
      "Find every payment obligation and its deadline"],
    "Litigation": [
      "Build a timeline of the key events in these documents",
      "What deadlines appear in these documents?",
      "Find every mention of the disputed incident"],
    "Employment": [
      "What do these documents say about non-compete restrictions?",
      "Find every reference to termination or severance",
      "What notice periods apply?"],
    "Estate & Probate": [
      "Who are the named beneficiaries and what does each receive?",
      "What powers does the trustee have?",
      "Find every reference to amendments or restatements"],
    "Real Estate": [
      "What are the closing conditions and deadlines?",
      "Find every easement or encumbrance mentioned",
      "What are the maintenance obligations?"],
    "Family": [
      "What do these documents say about custody and visitation?",
      "Find every support obligation and its amount",
      "What conditions trigger a modification?"],
    "Criminal Defense": [
      "Build a timeline of events from these documents",
      "Summarize what each witness statement says",
      "Find every mention of the evidence collected"],
    "Immigration": [
      "What deadlines and filing dates appear in these documents?",
      "Summarize the applicant's history from these documents",
      "Find every reference to prior applications"],
    "Personal Injury": [
      "Summarize the injuries described in these records",
      "Build a timeline from the incident to the last treatment",
      "Find every reference to lost wages or damages"],
    "IP & Technology": [
      "What does the license grant cover and exclude?",
      "Find every assignment of intellectual property",
      "What are the confidentiality obligations?"],
  };

  function practicePrompts() {
    var areas = (state.profile && state.profile.practice_areas) || [];
    var out = [], i = 0, added = true;
    while (out.length < 3 && added) {
      added = false;
      for (var j = 0; j < areas.length && out.length < 3; j++) {
        var list = PRACTICE_PROMPTS[areas[j]] || [];
        if (i < list.length) { out.push(list[i]); added = true; }
      }
      i++;
    }
    return out;
  }

  // Shared practice-area chip set (onboarding + Settings).
  function renderAreaChips(container, selected) {
    var areas = (state.profile && state.profile.available_practice_areas) || [];
    container.innerHTML = areas.map(function (a) {
      var on = (selected || []).indexOf(a) >= 0;
      return "<button type='button' class='chip" + (on ? " on" : "") + "' data-area='" +
        esc(a) + "'>" + esc(a) + "</button>";
    }).join("");
    container.querySelectorAll(".chip").forEach(function (b) {
      b.addEventListener("click", function () { b.classList.toggle("on"); });
    });
  }

  function chipValues(container) {
    return Array.prototype.slice.call(container.querySelectorAll(".chip.on"))
      .map(function (b) { return b.dataset.area; });
  }

  async function saveProfile(vals) {
    state.profile = await api("/profile", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(vals),
    });
    updateGreeting();
    refreshSidebarProfile();
    if (document.getElementById("chat-guide")) renderChatGuide();
  }

  // First-run onboarding: three skippable screens, under a minute. Screen 1 is the
  // privacy promise (the differentiator, not a chore), screen 2 captures the two
  // fields the product actually uses, screen 3 sets the verification expectation.
  function maybeShowOnboarding() {
    if (state.profile && state.profile.onboarded) return;
    if (document.getElementById("onboard-overlay")) return;
    var ov = document.createElement("div");
    ov.id = "onboard-overlay";
    function dots(n) {
      return "<div class='step-dots'>" + [1, 2, 3].map(function (i) {
        return "<span class='dot" + (i === n ? " on" : "") + "'></span>";
      }).join("") + "</div>";
    }
    ov.innerHTML =
      "<div class='onboard-card'>" +
      "<div class='onboard-step' data-step='1'>" + dots(1) +
      "<h2>Everything stays on this machine.</h2>" +
      "<p>docuchat runs entirely on your computer. Your documents never leave it. " +
      "No cloud, no account, no telemetry.</p>" +
      "<p class='muted'>It works with Wi-Fi off. You can check.</p>" +
      "<div class='onboard-actions'><button class='btn' data-next='2'>Set up in 30 seconds</button>" +
      "<a href='#' class='onboard-skip'>Skip</a></div>" +
      "</div>" +
      "<div class='onboard-step' data-step='2' style='display:none'>" + dots(2) +
      "<h2>A few basics</h2>" +
      "<label class='field-label'>What should we call you? (optional)</label>" +
      "<input type='text' id='onboard-name' placeholder='First name' style='margin-top:6px'>" +
      "<label class='field-label' style='margin-top:16px;display:block'>Your practice areas</label>" +
      "<div id='onboard-areas' class='chip-set'></div>" +
      "<p class='muted' style='font-size:12px;margin-top:12px'>Stored only in a local file on this " +
      "computer. Change anytime in Settings.</p>" +
      "<div class='onboard-actions'><button class='btn' data-next='3'>Continue</button>" +
      "<a href='#' class='onboard-back' data-back='1'>Back</a>" +
      "<a href='#' class='onboard-skip'>Skip</a></div>" +
      "</div>" +
      "<div class='onboard-step' data-step='3' style='display:none'>" + dots(3) +
      "<h2>How to trust the answers</h2>" +
      "<p>docuchat answers only from your documents. Every claim is cited to the exact page " +
      "and passage, and each citation is mechanically checked against the source text before " +
      "it reaches you. If the documents do not support an answer, it says so.</p>" +
      "<p><b>AI can still misread context.</b> Verify citations before you rely on them. " +
      "This is a research assistant, not legal advice.</p>" +
      "<div class='onboard-actions'><button class='btn' id='onboard-done'>Start</button>" +
      "<a href='#' class='onboard-back' data-back='2'>Back</a></div>" +
      "</div></div>";
    document.body.appendChild(ov);
    renderAreaChips(document.getElementById("onboard-areas"),
                    (state.profile && state.profile.practice_areas) || []);

    function goStep(n) {
      ov.querySelectorAll(".onboard-step").forEach(function (s) {
        s.style.display = s.dataset.step === String(n) ? "" : "none";
      });
      if (String(n) === "2") {
        var nameInput = document.getElementById("onboard-name");
        if (nameInput) setTimeout(function () { nameInput.focus(); }, 0);
      }
    }
    ov.querySelectorAll("[data-next]").forEach(function (b) {
      b.addEventListener("click", function () { goStep(b.dataset.next); });
    });
    ov.querySelectorAll("[data-back]").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); goStep(a.dataset.back); });
    });
    document.getElementById("onboard-name").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); goStep(3); }
    });
    ov.querySelectorAll(".onboard-skip").forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        saveProfile({ onboarded: true }).catch(function () {});
        ov.remove();
      });
    });
    document.getElementById("onboard-done").addEventListener("click", function () {
      saveProfile({
        name: document.getElementById("onboard-name").value,
        practice_areas: chipValues(document.getElementById("onboard-areas")),
        onboarded: true,
      }).catch(function () {});
      ov.remove();
    });
  }

  // --- Document Hub (UX-7, owner-directed): the filing cabinet -----------------
  // Upload ANYTHING here (documents, transcripts, emails); new files land in
  // "Unfiled". Below, the matters are folder cards: drag a document onto a matter
  // to file it (a per-row "Move to" select is the no-drag fallback). Clicking a
  // matter opens its drawer (documents, conversations, tools, retention actions).
  // The home skeleton builds ONCE (UX-3): find results and pickers survive
  // navigation; only tables/cards/status refresh.
  var mattersState = { open: null, builtFor: null, timer: null };
  var UNFILED_NAME = "Unfiled";
  var UNFILED_SLUG = "unfiled";

  function buildHub(inner) {
    inner.innerHTML =
      "<div id='hub-home'>" +
      "<h1>Document Hub</h1>" +
      "<p class='muted'>Your filing cabinet. Upload anything here, then file it into a matter. " +
      "Everything stays on this computer.</p>" +
      "<div class='panel'>" +
      "<div style='display:flex;gap:10px;align-items:center;margin-bottom:12px'>" +
      "<span class='field-label'>Add to</span>" +
      "<select id='hub-dest' style='max-width:280px'></select></div>" +
      "<div id='hub-dropzone' style='border:2px dashed var(--border);border-radius:12px;text-align:center;padding:28px;cursor:pointer'>" +
      "Drag &amp; drop files or a whole folder here, or click to choose. " +
      "<span class='muted'>(.pdf .docx .txt .md .eml .html .vtt .srt .csv .json)</span>" +
      "<input type='file' id='hub-file-input' multiple style='display:none'>" +
      "<input type='file' id='hub-folder-input' webkitdirectory style='display:none'></div>" +
      "<div style='display:flex;align-items:center;gap:14px;margin:8px 0 0'>" +
      "<a href='#' id='hub-pick-folder' style='font-size:13px;color:#6e5220;font-weight:600'>" +
      "Upload an entire folder…</a>" +
      "<span id='hub-upload-note' class='muted' style='font-size:13px'></span></div>" +
      "<label class='muted' style='display:block;font-size:13px;margin:6px 0 0'>" +
      "<input type='checkbox' id='hub-upload-transcript'> These are deposition/hearing transcripts " +
      "(numbered lines — answers get page:line citations)</label>" +
      "<div id='hub-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='hub-ingest-status' class='muted' style='font-size:13px'></div>" +
      "</div>" +
      "<div class='panel'><b>Unfiled</b> <span class='muted' style='font-size:13px'>— drag a document " +
      "onto a matter below to file it</span>" +
      "<table style='margin-top:8px'><thead><tr><th>Document</th><th>Size</th><th>Status</th><th></th></tr></thead>" +
      "<tbody id='unfiled-rows'></tbody></table></div>" +
      "<div class='panel'><b>Matters</b>" +
      "<div style='display:flex;gap:8px;margin:10px 0 4px;max-width:480px'>" +
      "<input id='new-matter-name' type='text' placeholder='New matter name (e.g. Pemberton Logistics)'>" +
      "<button class='btn' id='new-matter-btn'>Create</button></div>" +
      "<div id='new-matter-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='matter-cards' class='matter-cards'></div></div>" +
      "<div class='panel'><b>Find in documents</b>" +
      "<p class='muted' style='font-size:13px;margin:4px 0 10px'>Every mention, exhaustively — the full " +
      "list of matching passages in the chosen matter, not a top-5. No AI answering here, just your documents.</p>" +
      "<div style='display:flex;gap:8px;align-items:center'>" +
      "<select class='matter-picker' id='search-matter' style='max-width:240px'></select>" +
      "<input id='search-input' type='text' placeholder='A name, amount, defined term, case number…' style='flex:1'>" +
      "<select id='search-mode' style='max-width:170px'>" +
      "<option value='mentions'>Every mention</option><option value='fts'>Best match</option></select>" +
      "<button class='btn' id='search-go'>Find</button></div>" +
      "<div id='search-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='search-results'></div></div>" +
      "</div>" +
      "<div id='matter-detail' style='display:none'></div>";

    var dz = document.getElementById("hub-dropzone");
    var fi = document.getElementById("hub-file-input");
    var fdi = document.getElementById("hub-folder-input");
    dz.addEventListener("click", function () { fi.click(); });
    fi.addEventListener("change", function () { uploadToDest(fi.files); });
    fdi.addEventListener("change", function () { uploadToDest(fdi.files); });
    document.getElementById("hub-pick-folder").addEventListener("click", function (e) {
      e.preventDefault(); fdi.click();
    });
    dz.addEventListener("dragover", function (e) {
      // a file drag from the OS, not a row drag
      if (e.dataTransfer.types.indexOf("Files") !== -1) { e.preventDefault(); dz.style.background = "#eef3ff"; }
    });
    dz.addEventListener("dragleave", function () { dz.style.background = ""; });
    dz.addEventListener("drop", async function (e) {
      e.preventDefault(); dz.style.background = "";
      var files = await filesFromDataTransfer(e.dataTransfer);   // folders traversed
      if (files.length) uploadToDest(files);
    });
    document.getElementById("new-matter-btn").addEventListener("click", async function () {
      var name = document.getElementById("new-matter-name").value;
      var err = document.getElementById("new-matter-err");
      err.textContent = "";
      try {
        await api("/matters", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: name }),
        });
        document.getElementById("new-matter-name").value = "";
        await fillMatterPickers();
        refreshHubHome();
      } catch (e) { err.textContent = e.message; }
    });
    document.getElementById("search-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("search-go").addEventListener("click", function () { runSearch(true); });
    document.getElementById("search-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); runSearch(true); }
    });
  }

  function refreshHubView() {
    var home = document.getElementById("hub-home");
    var detail = document.getElementById("matter-detail");
    if (!home || !detail) return;
    var open = !!mattersState.open;
    home.style.display = open ? "none" : "";
    detail.style.display = open ? "" : "none";
    if (open) showMatterDetail(mattersState.open);
    else refreshHubHome();
  }

  async function refreshHubHome() {
    try { var d = await api("/matters"); state.matters = (d && d.matters) || []; }
    catch (e) {}
    fillHubDest();
    refreshUnfiled();
    renderMatterCards();
    refreshIngestStatus();
  }

  function fillHubDest() {
    var sel = document.getElementById("hub-dest");
    if (!sel) return;
    var prev = sel.value;
    var opts = "<option value='" + UNFILED_SLUG + "'>" + UNFILED_NAME + "</option>" +
      state.matters.filter(function (m) { return m.slug !== UNFILED_SLUG; })
        .map(function (m) {
          return "<option value='" + esc(m.slug) + "'>" + esc(m.display_name) + "</option>";
        }).join("");
    sel.innerHTML = opts;
    if (prev) sel.value = prev;
    if (!sel.value) sel.value = UNFILED_SLUG;
  }

  // The Unfiled tray is a real matter (created lazily on first use) so unfiled
  // documents are still fully chattable/searchable like everything else.
  async function ensureUnfiled() {
    if (state.matters.some(function (m) { return m.slug === UNFILED_SLUG; })) return;
    try {
      await api("/matters", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: UNFILED_NAME }),
      });
    } catch (e) { /* already exists */ }
    await fillMatterPickers();
  }

  var UPLOAD_TYPES = [".pdf", ".docx", ".txt", ".md", ".eml",
                      ".html", ".htm", ".vtt", ".srt", ".csv", ".json"];   // UX-11

  function isSupportedFile(name) {
    var dot = name.lastIndexOf(".");
    return dot > 0 && UPLOAD_TYPES.indexOf(name.slice(dot).toLowerCase()) !== -1;
  }

  // Folder upload (UX-9): a dropped folder is walked recursively via the entries
  // API; a picked folder (webkitdirectory input) arrives pre-flattened. Entries
  // must be captured synchronously during the drop event.
  function filesFromDataTransfer(dt) {
    var items = Array.prototype.slice.call(dt.items || []);
    var entries = items.map(function (i) {
      return i.webkitGetAsEntry ? i.webkitGetAsEntry() : null;
    }).filter(Boolean);
    if (!entries.length) return Promise.resolve(Array.prototype.slice.call(dt.files));
    var out = [];
    function walk(entry) {
      return new Promise(function (resolve) {
        if (entry.isFile) {
          entry.file(function (f) { out.push(f); resolve(); }, function () { resolve(); });
        } else if (entry.isDirectory) {
          var reader = entry.createReader();
          (function readBatch() {
            reader.readEntries(function (batch) {
              if (!batch.length) return resolve();
              Promise.all(Array.prototype.map.call(batch, walk)).then(readBatch);
            }, function () { resolve(); });
          })();
        } else resolve();
      });
    }
    return Promise.all(entries.map(walk)).then(function () { return out; });
  }

  async function uploadToDest(files) {
    var err = document.getElementById("hub-err");
    var note = document.getElementById("hub-upload-note");
    if (err) err.textContent = "";
    if (note) note.textContent = "";
    var dest = (document.getElementById("hub-dest") || {}).value || UNFILED_SLUG;
    if (dest === UNFILED_SLUG) await ensureUnfiled();
    var isTranscript = !!(document.getElementById("hub-upload-transcript") || {}).checked;
    // Unsupported/hidden files are counted and skipped, never errors — a real
    // client folder always has strays (.DS_Store, images, spreadsheets) in it.
    var added = 0, skipped = 0;
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      if (f.name.charAt(0) === "." || !isSupportedFile(f.name)) { skipped++; continue; }
      try {
        // Send the bytes, NOT the File object: WKWebView (the macOS app's web
        // view) throws "The string did not match the expected pattern" on a
        // File/Blob fetch body, though Chromium accepts it. ArrayBuffer works in both.
        await fetch("/kb/upload?matter=" + encodeURIComponent(dest) +
                    "&filename=" + encodeURIComponent(f.name) +
                    (isTranscript ? "&doc_type=transcript" : ""),
                    { method: "POST", body: await f.arrayBuffer() })
          .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail); }); });
        added++;
      } catch (e) { if (err) err.textContent = friendlyError(e); }
      if (note && files.length > 3) note.textContent = "Adding " + added + " of " + files.length + "…";
    }
    if (note) note.textContent = added
      ? ("Added " + added + " document" + (added === 1 ? "" : "s") +
         (skipped ? " (" + skipped + " unsupported skipped)" : "") + ".")
      : (skipped ? "Nothing added — " + skipped + " unsupported file" + (skipped === 1 ? "" : "s") + " skipped." : "");
    refreshHubHome();
  }

  async function moveDoc(docId, matter) {
    try {
      await api("/kb/documents/move", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_id: parseInt(docId, 10), matter: matter }),
      });
    } catch (e) { alert(e.message); }
    if (mattersState.open) refreshMatterDocs();
    else refreshHubHome();
  }

  function moveSelectHtml(d) {
    var opts = "<option value=''>Move to…</option>" +
      state.matters.filter(function (m) { return m.slug !== d.matter_slug; })
        .map(function (m) {
          return "<option value='" + esc(m.slug) + "'>" + esc(m.display_name) + "</option>";
        }).join("");
    return "<select class='move-doc' data-doc='" + d.id + "' style='width:auto;max-width:150px;" +
      "padding:5px 8px;font-size:12.5px'>" + opts + "</select>";
  }

  function wireDocRowActions(scope) {
    scope.querySelectorAll("[data-view-doc]").forEach(function (b) {
      b.onclick = function () { window.open("/kb/source/" + b.dataset.viewDoc, "_blank"); };
    });
    scope.querySelectorAll("[data-del-doc]").forEach(function (b) {
      b.onclick = async function () {
        if (!confirm("Remove this document from the knowledge base?")) return;
        try { await api("/kb/documents/" + b.dataset.delDoc, { method: "DELETE" }); }
        catch (e) { alert(e.message); }
        if (mattersState.open) refreshMatterDocs(); else refreshHubHome();
      };
    });
    scope.querySelectorAll("[data-digest-doc]").forEach(function (b) {
      b.onclick = function () { runDigest(b.dataset.digestDoc); };
    });
    scope.querySelectorAll(".move-doc").forEach(function (sel) {
      sel.addEventListener("change", function () {
        if (sel.value) moveDoc(sel.dataset.doc, sel.value);
      });
    });
    scope.querySelectorAll("tr[draggable]").forEach(function (tr) {
      tr.addEventListener("dragstart", function (e) {
        e.dataTransfer.setData("text/plain", tr.dataset.doc);
        e.dataTransfer.effectAllowed = "move";
      });
    });
  }

  async function refreshUnfiled() {
    var tbody = document.getElementById("unfiled-rows");
    if (!tbody) return;
    var hasUnfiled = state.matters.some(function (m) { return m.slug === UNFILED_SLUG; });
    var docs = [];
    if (hasUnfiled) {
      try { docs = (await api("/kb/documents?matter=" + UNFILED_SLUG)).documents || []; }
      catch (e) { docs = []; }
    }
    tbody.innerHTML = docs.length ? docs.map(function (d) {
      var size = d.size_bytes != null ? Math.max(1, Math.round(d.size_bytes / 1024)) + " KB" : "—";
      var kind = d.doc_type === "transcript" ? " <span class='muted'>(transcript)</span>" : "";
      return "<tr draggable='true' data-doc='" + d.id + "' class='doc-row'><td>" + esc(d.filename) + kind +
        "</td><td>" + size + "</td><td><span class='status " + esc(d.status) + "'>" + esc(d.status) +
        "</span></td><td>" + moveSelectHtml(d) + " " +
        "<button class='btn secondary' data-view-doc='" + d.id + "'>view</button> " +
        "<button class='btn secondary' data-del-doc='" + d.id + "'>delete</button></td></tr>";
    }).join("") : "<tr><td colspan='4' class='muted'>Nothing unfiled — uploads without a matter land here.</td></tr>";
    wireDocRowActions(tbody);
  }

  function renderMatterCards() {
    var box = document.getElementById("matter-cards");
    if (!box) return;
    var matters = state.matters.filter(function (m) { return m.slug !== UNFILED_SLUG; });
    box.innerHTML = matters.length ? matters.map(function (m) {
      return "<div class='matter-card' data-slug='" + esc(m.slug) + "'>" +
        "<span class='mc-name'>" + esc(m.display_name) + "</span>" +
        "<span class='mc-meta'>" + m.doc_count + " document" + (m.doc_count === 1 ? "" : "s") +
        (m.sample ? " · sample" : "") + "</span></div>";
    }).join("") : "<p class='muted' style='font-size:13px'>No matters yet — create one above, " +
                  "then drag unfiled documents onto it.</p>";
    box.querySelectorAll(".matter-card").forEach(function (card) {
      card.addEventListener("click", function () { openMatter(card.dataset.slug); });
      card.addEventListener("dragover", function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        card.classList.add("drop-target");
      });
      card.addEventListener("dragleave", function () { card.classList.remove("drop-target"); });
      card.addEventListener("drop", function (e) {
        e.preventDefault();
        card.classList.remove("drop-target");
        var id = e.dataTransfer.getData("text/plain");
        if (id) moveDoc(id, card.dataset.slug);
      });
    });
  }

  function openMatter(slug) {
    mattersState.open = slug;
    var m = null;
    state.matters.forEach(function (x) { if (x.slug === slug) m = x; });
    setActiveMatter(slug, m ? m.display_name : slug);
    showView("hub");   // the hook renders the drawer (matter detail)
  }
  window.openMatter = openMatter;

  function closeMatter() {
    mattersState.open = null;
    mattersState.builtFor = null;
    refreshHubView();
  }

  function showMatterDetail(slug) {
    var detail = document.getElementById("matter-detail");
    if (mattersState.builtFor !== slug) {
      mattersState.builtFor = slug;
      var m = null;
      state.matters.forEach(function (x) { if (x.slug === slug) m = x; });
      var name = m ? m.display_name : slug;
      detail.innerHTML =
        "<a href='#' class='back-link' id='matter-back'>&larr; Document Hub</a>" +
        "<h1>" + esc(name) + "</h1>" +
        "<div class='tool-row'>" +
        "<button class='btn' data-tool='chat'>Ask about this matter</button>" +
        "<button class='btn secondary' data-tool='clauses'>Contract review</button>" +
        "<button class='btn secondary' data-tool='grid'>Compare documents</button>" +
        "<span style='flex:1'></span>" +
        "<button class='btn secondary' id='matter-hold'>hold</button>" +
        "<button class='btn secondary' id='matter-export'>export</button>" +
        "<button class='btn secondary' id='matter-dispose'>dispose</button>" +
        "</div>" +
        "<div id='matter-overview'></div>" +
        "<div id='matter-dropzone' class='panel' style='border:2px dashed var(--border);text-align:center;padding:28px;cursor:pointer'>" +
        "Drag &amp; drop files here, or click to choose. <span class='muted'>(.pdf .docx .txt .md .eml .html .vtt .srt .csv .json)</span>" +
        "<input type='file' id='matter-file-input' multiple style='display:none'></div>" +
        "<label class='muted' style='display:block;font-size:13px;margin:2px 0 8px'>" +
        "<input type='checkbox' id='upload-transcript'> These are deposition/hearing transcripts " +
        "(numbered lines — answers get page:line citations)</label>" +
        "<div id='matter-upload-err' style='color:var(--err);font-size:13px'></div>" +
        "<div id='matter-ingest-status' class='muted' style='font-size:13px'></div>" +
        "<div class='panel'><table><thead><tr><th>Document</th><th>Size</th>" +
        "<th>Status</th><th>Updated</th><th></th></tr></thead><tbody id='matter-doc-rows'></tbody></table></div>" +
        "<div class='panel'><b>Conversations in this matter</b><div id='matter-threads' style='margin-top:8px'></div></div>" +
        "<div id='matter-digest'></div>";

      document.getElementById("matter-back").addEventListener("click", function (e) {
        e.preventDefault(); closeMatter();
      });
      detail.querySelectorAll("[data-tool]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (b.dataset.tool === "chat") showView("chat");
          else openReviewTab(b.dataset.tool);
        });
      });
      // Retention actions (Move 4, D-72): hold toggles (with reasons), export
      // downloads the complete matter file, dispose double-confirms and downloads
      // the honest Certificate of Disposition. Holds block dispose + deletes (409s).
      document.getElementById("matter-hold").addEventListener("click", async function () {
        var st = await api("/retention/" + slug + "/status");
        if (st.hold) {
          var why = prompt("Active hold: " + st.hold.reason + "\nRelease reason (cancel to keep the hold):");
          if (why) await api("/retention/" + slug + "/release", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: why }) });
        } else {
          var reason = prompt("Place a legal hold. Reason:");
          if (reason) await api("/retention/" + slug + "/hold", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: reason }) });
        }
      });
      document.getElementById("matter-export").addEventListener("click", function () {
        window.open("/retention/" + slug + "/export", "_blank");
      });
      document.getElementById("matter-dispose").addEventListener("click", async function () {
        if (!confirm("Dispose of this matter? Export the complete file FIRST if you have not. " +
                     "This removes its documents, index, and chat history from this computer.")) return;
        if (!confirm("Final confirmation: dispose of '" + slug + "' now?")) return;
        try {
          var cert = await api("/retention/" + slug + "/dispose?confirm=true", { method: "POST" });
          var blob = new Blob([JSON.stringify(cert, null, 2)], { type: "application/json" });
          var url = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = url; a.download = "certificate-of-disposition-" + slug + ".json";
          document.body.appendChild(a); a.click(); a.remove();
          URL.revokeObjectURL(url);
          alert("Disposed. Certificate downloaded. Method: " + cert.method);
        } catch (e) { alert(e.message); }
        closeMatter();
        fillMatterPickers();
      });
      var dz = document.getElementById("matter-dropzone");
      var fi = document.getElementById("matter-file-input");
      dz.addEventListener("click", function () { fi.click(); });
      fi.addEventListener("change", function () { uploadFiles(fi.files); });
      dz.addEventListener("dragover", function (e) { e.preventDefault(); dz.style.background = "#eef3ff"; });
      dz.addEventListener("dragleave", function () { dz.style.background = ""; });
      dz.addEventListener("drop", function (e) {
        e.preventDefault(); dz.style.background = "";
        uploadFiles(e.dataTransfer.files);
      });
    }
    refreshMatterDocs();
    refreshMatterThreads();
    renderMatterOverview(slug);
  }

  // Ingest progress line (Move 0c): queue depth + in-flight stage, from the worker.
  // Painted into whichever status slots exist (hub home + matter detail).
  async function refreshIngestStatus() {
    var els = [document.getElementById("hub-ingest-status"),
               document.getElementById("matter-ingest-status")].filter(Boolean);
    if (!els.length) return;
    var text = "";
    try {
      var s = await api("/kb/ingest/status");
      if (s.queue_depth > 0 || s.current) {
        var cur = s.current ? ("processing #" + esc(s.current.doc_id) + " (" +
          esc(s.current.stage) + ")") : "starting next";
        text = "Ingest: " + s.queue_depth + " waiting, " + cur + ".";
      }
    } catch (e) { text = ""; }
    els.forEach(function (el) { el.textContent = text; });
  }

  async function refreshMatterDocs() {
    refreshIngestStatus();
    var tbody = document.getElementById("matter-doc-rows");
    if (!tbody || !mattersState.open) return;
    var docs = [];
    try { docs = (await api("/kb/documents?matter=" + encodeURIComponent(mattersState.open))).documents || []; }
    catch (e) { docs = []; }
    tbody.innerHTML = docs.length ? docs.map(function (d) {
      var size = d.size_bytes != null ? Math.max(1, Math.round(d.size_bytes / 1024)) + " KB" : "—";
      var digestBtn = (d.doc_type === "transcript" && d.status === "ready")
        ? "<button class='btn secondary' data-digest-doc='" + d.id + "'>digest</button> " : "";
      var kind = d.doc_type === "transcript" ? " <span class='muted'>(transcript)</span>" : "";
      return "<tr><td>" + esc(d.filename) + kind + "</td><td>" + size +
        "</td><td><span class='status " + esc(d.status) + "'>" +
        esc(d.status) + "</span></td><td class='muted'>" + esc((d.updated || "").replace("T", " ")) +
        "</td><td>" + moveSelectHtml(d) + " " +
        "<button class='btn secondary' data-view-doc='" + d.id + "'>view</button> " +
        digestBtn +
        "<button class='btn secondary' data-del-doc='" + d.id + "'>delete</button></td></tr>";
    }).join("") : "<tr><td colspan='5' class='muted'>No documents yet — drop files above.</td></tr>";
    wireDocRowActions(tbody);
    var dz = document.getElementById("matter-dropzone");
    if (dz) dz.classList.toggle("slim", docs.length > 0);
    renderMatterOverview(mattersState.open);
  }

  async function refreshMatterThreads() {
    var box = document.getElementById("matter-threads");
    if (!box || !mattersState.open) return;
    var threads = [];
    try { threads = (await api("/chat/threads")).threads || []; } catch (e) { threads = []; }
    threads = threads.filter(function (t) { return t.matter_slug === mattersState.open; });
    box.innerHTML = threads.length
      ? threads.slice(0, 12).map(function (t) {
          return "<a href='#' class='matter-thread' data-thread='" + t.id + "'>" + esc(t.title) +
            " <span class='muted'>" + esc((t.updated || "").replace("T", " ")) + "</span></a>";
        }).join("")
      : "<span class='muted'>No conversations yet. Use “Ask about this matter” above.</span>";
    box.querySelectorAll(".matter-thread").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); openThread(a.dataset.thread); });
    });
  }

  // M-2 matter overview: pure display of mechanically verified fact rows. Deadline
  // dates are the attorney's — the UI shows source language and takes THEIR date;
  // it never computes one. Every row cites verbatim source with a highlight link.
  var overviewPoll = null;
  // Keyed by slug so switching matters always re-renders (a stale key from another
  // matter never matches); guards against the ~2s hub poll wiping an in-progress
  // attorney edit (F2) by skipping a re-render that would change nothing, or that
  // would land while focus is inside the overview box.
  var overviewLastPayload = null;
  async function renderMatterOverview(slug) {
    var box = document.getElementById("matter-overview");
    if (!box) return;
    var data, payloadKey;
    try {
      data = await api("/matters/" + encodeURIComponent(slug) + "/overview");
      payloadKey = slug + "|" + JSON.stringify(data);
    } catch (e) {
      if (!box.innerHTML)
        box.innerHTML = "<div class='panel muted'>Couldn't load the matter overview.</div>";
      return;   // never clobber existing content on a failed refresh
    }

    if (overviewPoll) { clearTimeout(overviewPoll); overviewPoll = null; }
    var building = data.building.total > 0 && data.building.done < data.building.total;
    if (building) overviewPoll = setTimeout(function () { renderMatterOverview(slug); }, 5000);

    if (box.contains(document.activeElement)) return;   // attorney is mid-interaction
    if (payloadKey === overviewLastPayload && box.innerHTML) return;   // nothing changed
    overviewLastPayload = payloadKey;

    function ovHref(i) {
      return highlightUrl({ doc_id: i.doc_id, page: i.page, span: i.span })
        .replace(/'/g, "%27"); // encodeURIComponent leaves ' raw; it would end the href='...'
    }

    function calHref(i) {
      return ("/matters/" + encodeURIComponent(slug) + "/facts/" +
        encodeURIComponent(i.fact_key) + "/calendar.ics").replace(/'/g, "%27");
    }

    function srcLine(i) {
      return "<div class='ov-src'>“" + esc(i.span) + "” — <a class='ov-cite' " +
        "href='" + ovHref(i) + "' target='_blank'>" + esc(i.filename) + " p." + esc(String(i.page)) + "</a></div>";
    }

    function deadlineRow(i) {
      var v = i.value, r = i.review, eff = (r && r.confirmed_date) || v.date_iso;
      var html = "<div class='ov-row' data-key='" + esc(i.fact_key) + "'><div class='ov-top'>";
      html += "<span class='ov-due" + (r && r.status === "confirmed" ? " ok" : eff ? "" : " none") +
        "'>" + (eff ? esc(eff) : "No date yet") + "</span>";
      html += "<span class='ov-label'>" + esc(v.label || "") + "</span>";
      if (r && r.status === "confirmed")
        html += "<span class='ov-chip ok'>confirmed by you</span>";
      else if (v.date_iso) html += "<span class='ov-chip'>date as written — confirm?</span>";
      else html += "<span class='ov-chip'>needs your date</span>";
      html += "</div>" + srcLine(i);
      if (v.anchor && !eff)
        html += "<div class='ov-note muted'>counts from: " + esc(v.anchor) + "</div>";
      html += "<div class='ov-actions'>";
      if (r && r.status === "confirmed") {
        html += "<a class='btn secondary' href='" + calHref(i) + "'>Add to calendar</a>";
        html += "<button class='btn secondary ov-act' data-act='undo'>Unconfirm</button>";
      }
      else {
        html += "<input type='date' class='ov-date' value='" + esc(v.date_iso || "") + "'>";
        html += "<button class='btn ov-act' data-act='confirm'>Confirm</button>";
        html += "<button class='btn secondary ov-act' data-act='dismiss'>Dismiss</button>";
      }
      return html + "</div></div>";
    }

    function tlRow(i) {
      var v = i.value;
      return "<div class='ov-tl'><span class='ov-tld'>" + esc(v.date_iso || v.date_text || "") +
        "</span><span>" + esc(v.label || "") + "</span> <a class='ov-cite' href='" + ovHref(i) +
        "' target='_blank'>p." + esc(String(i.page)) + "</a></div>";
    }

    function groupBy(items, keyFn) {
      var m = {};
      items.forEach(function (i) { var k = keyFn(i); (m[k] = m[k] || []).push(i); });
      return m;
    }

    var html = "";
    if (building)
      html += "<div class='muted' style='font-size:13px;margin-bottom:6px'>Building matter digest — " +
        data.building.done + " of " + data.building.total + " documents…</div>";

    if (data.deadlines.length) {
      html += "<div class='panel'><div class='ov-title'>Deadlines";
      var unconf = data.deadlines.filter(function (i) {
        return !(i.review && i.review.status === "confirmed"); }).length;
      if (unconf) html += " <span class='muted'>· " + unconf + " need your confirmation</span>";
      html += "</div>" + data.deadlines.map(deadlineRow).join("");
      html += "<div class='ov-disclaimer muted'>" +
        "Extracted from your documents - verify against the source. Not a complete docket.</div></div>";
    }

    if (data.timeline.length || data.parties.length || data.amounts.length) {
      html += "<div class='panel'><div class='ov-title'>Timeline · Parties · Amounts</div>";
      html += data.timeline.map(tlRow).join("");
      var parties = groupBy(data.parties, function (i) {
        return (i.value.name || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); });
      var pbits = Object.keys(parties).map(function (k) {
        var first = parties[k][0], v = first.value;
        return esc(v.name) + (v.role ? " <span class='muted'>(" + esc(v.role) + ")</span>" : "") +
          " <a class='ov-cite' href='" + ovHref(first) + "' target='_blank'>p." +
          esc(String(first.page)) + "</a>";
      });
      var abits = data.amounts.map(function (i) {
        return esc(i.value.value || "") + (i.value.purpose ? " <span class='muted'>" +
          esc(i.value.purpose) + "</span>" : "") +
          " <a class='ov-cite' href='" + ovHref(i) + "' target='_blank'>p." +
          esc(String(i.page)) + "</a>";
      });
      if (pbits.length || abits.length)
        html += "<div class='ov-tl'><span>" + pbits.concat(abits).join(" · ") + "</span></div>";
      html += "</div>";
    }

    if (data.terms.length || data.refs.length) {
      html += "<details class='panel ov-terms'><summary class='ov-title'>Key terms &amp; references (" +
        (data.terms.length + data.refs.length) + ")</summary>";
      html += data.terms.map(function (i) {
        return "<div class='ov-tl'><span>" + esc(i.value.term || "") + "</span>" + srcLine(i) + "</div>";
      }).join("");
      html += data.refs.map(function (i) {
        return "<div class='ov-tl'><span>" + esc(i.value.ref_type || "") + " " +
          esc(i.value.ref_value || "") + "</span>" + srcLine(i) + "</div>";
      }).join("");
      html += "</details>";
    }

    if (data.dismissed_count)
      html += "<div class='muted' style='font-size:12px'>dismissed (" + data.dismissed_count + ")</div>";
    if (!html && !building)
      html = "<div class='panel muted'>No extractable facts yet — the digest builds " +
        "automatically when documents are added.</div>";
    box.innerHTML = html;

    box.querySelectorAll(".ov-act").forEach(function (b) {
      b.addEventListener("click", async function () {
        var row = b.closest(".ov-row"), key = row.dataset.key, body;
        if (b.dataset.act === "dismiss") body = { status: "dismissed" };
        else if (b.dataset.act === "undo") body = { status: null };
        else {
          var d = row.querySelector(".ov-date").value;
          if (!d) { row.querySelector(".ov-date").focus(); return; }
          body = { status: "confirmed", confirmed_date: d };
        }
        await api("/matters/" + encodeURIComponent(slug) + "/facts/" +
          encodeURIComponent(key) + "/review",
          { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body) });
        if (document.activeElement && box.contains(document.activeElement)) document.activeElement.blur();
        renderMatterOverview(slug);
      });
    });
  }

  // Deposition digest (Move 2d): every bullet shown was mechanically verified against
  // the transcript; unverified bullets are counted and dropped, never displayed.
  async function runDigest(docId) {
    var out = document.getElementById("matter-digest");
    if (!out) return;
    out.innerHTML = "<div class='panel'><b>Deposition digest</b> <span class='muted' id='digest-status'>starting…</span><div id='digest-body'></div></div>";
    var status = document.getElementById("digest-status");
    var bodyEl = document.getElementById("digest-body");
    try {
      var resp = await fetch("/transcripts/" + docId + "/digest", { method: "POST" });
      if (!resp.ok) {
        var d = null; try { d = await resp.json(); } catch (e) {}
        throw new Error((d && d.detail) || ("HTTP " + resp.status));
      }
      var reader = resp.body.getReader(), dec = new TextDecoder(), buf = "", done = null, meta = null;
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += dec.decode(chunk.value, { stream: true });
        var parts = buf.split("\n\n"); buf = parts.pop();
        parts.forEach(function (blk) {
          var msg = parseSseBlock(blk);
          if (!msg) return;
          if (msg.event === "meta") { meta = msg.data; status.textContent = meta.pages + " pages, " + meta.batches + " passes…"; }
          else if (msg.event === "batch") status.textContent = "pass " + msg.data.batch + " of " + msg.data.of + (msg.data.verified != null ? " — " + msg.data.verified + " verified" : "");
          else if (msg.event === "done") done = msg.data;
        });
      }
      if (!done) throw new Error("digest stream ended unexpectedly");
      status.textContent = done.coverage + " · " + done.stats.bullets_verified +
        " verified quotes" + (done.stats.bullets_rejected_unverified
          ? " · " + done.stats.bullets_rejected_unverified + " unverified dropped" : "");
      var html = done.topics.map(function (t) {
        return "<h3 style='margin:10px 0 4px'>" + esc(t.topic) + "</h3><ul>" +
          t.bullets.map(function (bl) {
            var cite = esc(bl.filename) + " p." + esc(bl.page) + (bl.lines ? ":" + esc(bl.lines) : "");
            return "<li>" + esc(bl.text) + " <span class='src-chip'>" + cite + "</span></li>";
          }).join("") + "</ul>";
      }).join("");
      html += "<button class='btn' id='digest-docx' style='margin-top:10px'>Download Word digest</button>";
      bodyEl.innerHTML = html;
      document.getElementById("digest-docx").onclick = async function () {
        var r = await fetch("/transcripts/digest.docx", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(done),
        });
        var blob = await r.blob();
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url; a.download = "digest-" + (done.filename || "transcript") + ".docx";
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      };
    } catch (e) { bodyEl.innerHTML = "<span style='color:var(--err)'>" + esc(e.message) + "</span>"; }
  }

  async function uploadFiles(files) {
    var err = document.getElementById("matter-upload-err");
    if (err) err.textContent = "";
    var slug = mattersState.open || state.matter;
    if (!slug) { if (err) err.textContent = "Open a matter first, then upload."; return; }
    var isTranscript = !!(document.getElementById("upload-transcript") || {}).checked;
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      try {
        await fetch("/kb/upload?matter=" + encodeURIComponent(slug) +
                    "&filename=" + encodeURIComponent(f.name) +
                    (isTranscript ? "&doc_type=transcript" : ""),
                    { method: "POST", body: await f.arrayBuffer() })  // ArrayBuffer, not File (WKWebView)
          .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail); }); });
      } catch (e) { if (err) err.textContent = friendlyError(e); }
    }
    refreshMatterDocs();
  }

  function hubHook() {
    ensureBuilt("hub", buildHub);
    refreshHubView();
    if (mattersState.timer) clearInterval(mattersState.timer);
    mattersState.timer = setInterval(function () {
      var active = document.getElementById("view-hub").classList.contains("active");
      if (!active) { clearInterval(mattersState.timer); mattersState.timer = null; return; }
      if (mattersState.open) { refreshMatterDocs(); refreshIngestStatus(); }
      else { refreshUnfiled(); refreshIngestStatus(); }
    }, 2000);
  }
  window.viewHooks.hub = hubHook;

  // --- Chat view ---------------------------------------------------------------
  // renderAnswerHtml(body) -> HTML string for an assistant turn. Always escapes model
  // text first. Per verified citation, a card showing the cited PAGE with the exact
  // span highlighted — /kb/highlight/<doc_id>?page=&span= is chunk-derived page+span,
  // never model-asserted. Non-PDF docs 404 -> the <img> hides itself (onerror).
  function citationThumb(c) {
    if (c.doc_id == null) return "";
    var url = "/kb/highlight/" + encodeURIComponent(c.doc_id) +
      "?page=" + encodeURIComponent(c.page) + "&span=" + encodeURIComponent(c.span || "");
    return "<a href='" + url + "' target='_blank' title='Open " + esc(c.filename) +
      " p." + esc(c.page) + " with the cited span highlighted'>" +
      "<img class='thumb' src='" + url + "' alt='cited page' onerror=\"this.style.display='none'\"></a>";
  }

  // Minimal LOCAL markdown (no CDN lib). Operates on already-escaped text, so injected
  // chip/format HTML is the only markup that reaches innerHTML (XSS guard).
  function mdInline(s) { return s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>"); }
  function md(text) {
    var out = [], list = null, para = [];
    function flushPara() { if (para.length) { out.push("<p>" + mdInline(para.join(" ")) + "</p>"); para = []; } }
    function closeList() { if (list) { out.push("</" + list + ">"); list = null; } }
    text.split("\n").forEach(function (ln) {
      var t = ln.trim();
      if (/^###\s+/.test(t)) { flushPara(); closeList(); out.push("<h4>" + mdInline(t.replace(/^###\s+/, "")) + "</h4>"); }
      else if (/^##\s+/.test(t)) { flushPara(); closeList(); out.push("<h3>" + mdInline(t.replace(/^##\s+/, "")) + "</h3>"); }
      else if (/^[-*]\s+/.test(t)) { flushPara(); if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; } out.push("<li>" + mdInline(t.replace(/^[-*]\s+/, "")) + "</li>"); }
      else if (/^\d+\.\s+/.test(t)) { flushPara(); if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; } out.push("<li>" + mdInline(t.replace(/^\d+\.\s+/, "")) + "</li>"); }
      else if (t === "") { flushPara(); closeList(); }
      else { closeList(); para.push(t); }
    });
    flushPara(); closeList();
    return out.join("");
  }

  function highlightUrl(c) {
    return "/kb/highlight/" + encodeURIComponent(c.doc_id) +
      "?page=" + encodeURIComponent(c.page) + "&span=" + encodeURIComponent(c.span || "");
  }

  // Replace the model's verbose inline [document: X, page: N, ...] tags with compact
  // clickable source chips wired to the verified citation's highlight. Unmatched tags
  // (no verified citation) are dropped — we never surface a model-asserted page.
  function injectChips(escapedText, cites) {
    return escapedText.replace(/\[document:[^\]]*\]/g, function (tag) {
      var m = tag.match(/document:\s*([^,]+?)\s*,\s*page:\s*(\d+)/i);
      if (!m) return "";
      var fn = m[1].trim(), pg = m[2];
      for (var i = 0; i < cites.length; i++) {
        if (cites[i].filename === fn && String(cites[i].page) === pg) {
          var c = cites[i];
          var tip = esc(fn) + " p." + esc(pg) + (c.lines ? ":" + esc(c.lines) : "");
          if (c.doc_id == null) return " <span class='src-chip'>[" + (i + 1) + "]</span>";
          return " <a class='src-chip' target='_blank' href='" + highlightUrl(c) +
            "' title='" + tip + "'>[" + (i + 1) + "]</a>";
        }
      }
      return "";
    });
  }

  window.renderAnswerHtml = function (body) {
    var cites = body.citations || [];
    var safe = injectChips(esc(body.answer_text || ""), cites);
    var thumbs = cites.map(citationThumb).join("");
    var sources = cites.map(function (c, i) {
      // c.lines (transcripts, D-70): derived from VERIFIED span offsets via the line
      // map — court-citation format p.45:12-18. Absent = page-only citation.
      var pageLabel = "p." + esc(c.page) + (c.lines ? ":" + esc(c.lines) : "");
      var label = "[" + (i + 1) + "] " + esc(c.filename) + " — " + pageLabel;
      return c.doc_id != null
        ? "<li><a class='src-chip' target='_blank' href='" + highlightUrl(c) + "'>" + label + "</a></li>"
        : "<li>" + label + "</li>";
    }).join("");
    // B4: non-gating confidence pill (display only — never affects which citations show).
    var conf = "";
    if (typeof body.confidence === "number") {
      var pct = Math.round(body.confidence * 100);
      var lvl = pct >= 70 ? "ok" : (pct >= 40 ? "warn" : "low");
      conf = "<span class='conf-pill " + lvl + "' title='Model self-confidence " +
        "(display only — does not affect citations)'>confidence " + pct + "%</span>";
    }
    return "<div class='answer'>" + md(safe) + "</div>" + conf +
      (thumbs ? "<div class='thumb-row'>" + thumbs + "</div>" : "") +
      (sources ? "<div class='sources'><b>Sources</b><ul>" + sources + "</ul></div>" : "");
  };
  window.citationThumb = citationThumb;

  function appendMsg(role, html) {
    var box = document.getElementById("chat-messages");
    if (!box) return;
    var div = document.createElement("div");
    div.className = "msg " + role;
    div.innerHTML = html;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  // Retrieved passages shown while the model reads them — candidates only, deliberately
  // NOT clickable/thumbnailed so they can't be mistaken for the verified citations that
  // replace them on 'done' (never-false-accept: verified citations are the only things
  // ever presented as citations).
  function renderReadingSources(sources) {
    if (!sources.length) return "";
    var items = sources.map(function (s) {
      return "<li><span class='src-chip'>" + esc(s.filename) + " — p." + esc(s.page) +
        "</span> <span class='muted'>" + esc((s.snippet || "").slice(0, 140)) + "…</span></li>";
    }).join("");
    return "<div class='sources reading'><b>Reading these passages…</b><ul>" + items + "</ul></div>";
  }

  // Streaming display: hide a trailing half-typed citation tag, compact complete tags
  // to a placeholder chip (the final render swaps in real verified chips on 'done').
  function renderStreamingText(text) {
    var shown = esc(text.replace(/\[document:[^\]]*$/i, ""))
      .replace(/\[document:[^\]]*\]/gi, " <span class='src-chip'>…</span>");
    return "<div class='answer'>" + md(shown) + "</div>";
  }

  // First-run guidance under the greeting (P1.4): a 3-step path when no matters exist,
  // an "add documents" nudge for an empty matter, and one-click suggested questions for
  // the seeded sample matter. Never a bare dead-end.
  function renderChatGuide() {
    var box = document.getElementById("chat-guide");
    if (!box) return;
    var active = null;
    state.matters.forEach(function (m) { if (m.slug === state.matter) active = m; });
    if (!state.matters.length) {
      box.innerHTML =
        "<div class='panel guide'><b>Get to your first cited answer</b><ol>" +
        "<li><a href='#' data-goto='hub'>Open the Document Hub</a> and drop a document in</li>" +
        "<li>Wait for it to show Ready (file it into a matter if you like)</li>" +
        "<li>Come back here and ask a question about it</li></ol>" +
        "<p class='muted'>A sample matter with synthetic documents is being prepared in the " +
        "background and will appear here when ready.</p></div>";
    } else if (active && active.doc_count === 0) {
      box.innerHTML =
        "<div class='panel guide'><b>" + esc(active.display_name) + "</b> has no documents yet. " +
        "<a href='#' data-goto='hub' data-open-matter='" + esc(active.slug) + "'>Add documents</a>, " +
        "wait for Ready, then ask.</div>";
    } else if (active && active.sample && (active.suggested_questions || []).length) {
      box.innerHTML =
        "<div class='guide-chips'><span class='muted'>Try a question against the sample documents:</span> " +
        active.suggested_questions.map(function (q) {
          return "<button class='btn secondary guide-q' data-q='" + esc(q) + "'>" + esc(q) + "</button>";
        }).join(" ") + "</div>";
    } else if (active && active.doc_count > 0 && practicePrompts().length) {
      // UX-5: prompts tailored to the attorney's practice areas. They FILL the
      // composer (editable templates), never auto-send — the user stays in control.
      box.innerHTML =
        "<div class='guide-chips'><span class='muted'>Ideas for this matter:</span> " +
        practicePrompts().map(function (q) {
          return "<button class='btn secondary guide-fill' data-q='" + esc(q) + "'>" + esc(q) + "</button>";
        }).join(" ") + "</div>";
    } else {
      box.innerHTML = "";
    }
    box.querySelectorAll(".guide-fill").forEach(function (b) {
      b.addEventListener("click", function () {
        var input = document.getElementById("chat-input");
        input.value = b.dataset.q;
        input.focus();
      });
    });
    box.querySelectorAll("[data-goto]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        if (a.dataset.openMatter) openMatter(a.dataset.openMatter);
        else showView(a.dataset.goto);
      });
    });
    box.querySelectorAll(".guide-q").forEach(function (b) {
      b.addEventListener("click", function () {
        var input = document.getElementById("chat-input");
        input.value = b.dataset.q;
        sendChat();
      });
    });
  }

  async function sendChat() {
    var input = document.getElementById("chat-input");
    var q = input.value.trim();
    if (!q) return;
    if (!state.matter) {
      appendMsg("system", "<i>Add a document first — open the <a href='#' " +
        "onclick=\"showView('hub');return false\">Document Hub</a> to upload one.</i>");
      return;
    }
    input.value = "";
    appendMsg("user", esc(q));
    appendMsg("assistant", "<i class='muted'>Working…</i>");
    var box = document.getElementById("chat-messages");
    var pending = box.lastChild;
    var sourcesHtml = "", streamed = "";
    function paint() {
      pending.innerHTML = sourcesHtml +
        (streamed ? renderStreamingText(streamed)
                  : "<i class='muted'>Drafting the cited answer…</i>");
      box.scrollTop = box.scrollHeight;
    }
    try {
      var resp = await fetch("/chat/stream", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, matter: state.matter, thread_id: state.threadId || null }),
      });
      if (!resp.ok) {
        var d = null;
        try { d = await resp.json(); } catch (e) { d = null; }
        throw new Error((d && d.detail) || ("HTTP " + resp.status));
      }
      var reader = resp.body.getReader(), dec = new TextDecoder(), buf = "", done = null;
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += dec.decode(chunk.value, { stream: true });
        var parts = buf.split("\n\n"); buf = parts.pop();
        parts.forEach(function (b) {
          var msg = parseSseBlock(b);
          if (!msg) return;
          if (msg.event === "sources") { sourcesHtml = renderReadingSources(msg.data.sources || []); paint(); }
          else if (msg.event === "token") { streamed += msg.data.text; paint(); }
          else if (msg.event === "second_pass") {
            streamed = "";
            sourcesHtml = "<p class='muted'><i>Not found in the closest passages — searching the matter more broadly…</i></p>";
            paint();
          }
          else if (msg.event === "done") done = msg.data;
        });
      }
      if (!done) throw new Error("stream ended unexpectedly");
      state.threadId = done.thread_id;
      var isRefusal = (done.citations || []).length === 0 &&
        /could not find this in the documents/i.test(done.answer_text || "");
      if (isRefusal && sourcesHtml && sourcesHtml.indexOf("sources reading") !== -1) {
        // Near-miss leads (1b): a refusal keeps the retrieved passages visible as
        // explicitly-unverified leads instead of a dead end. Never styled as citations.
        pending.innerHTML = window.renderAnswerHtml(done) +
          sourcesHtml.replace("Reading these passages…",
                              "Closest passages (not verified support — leads only):");
      } else {
        pending.innerHTML = window.renderAnswerHtml(done);
      }
      box.scrollTop = box.scrollHeight;
    } catch (e) { pending.innerHTML = "<span style='color:var(--err)'>" + esc(e.message) + "</span>"; }
  }
  window.sendChat = sendChat;

  async function openThread(id) {
    var msgs = (await api("/chat/threads/" + id)).messages || [];
    state.threadId = id;
    showView("chat");
    var box = document.getElementById("chat-messages");
    box.innerHTML = "";
    msgs.forEach(function (m) {
      if (m.role === "user") appendMsg("user", esc(m.content));
      else appendMsg("assistant", window.renderAnswerHtml({
        answer_text: m.content, citations: m.citations_json ? JSON.parse(m.citations_json) : [],
      }));
    });
  }
  window.openThread = openThread;

  function newChat() {
    state.threadId = null;
    var box = document.getElementById("chat-messages");
    if (box) box.innerHTML = "";
    renderChatGuide();
  }

  // UX-7 (owner-directed): a single conversation pane — history is its own nav tab.
  function buildChat(inner) {
    inner.innerHTML =
      "<div class='chat-head'>" +
      "<span class='field-label'>Matter</span>" +
      "<select class='matter-picker' id='chat-matter'></select>" +
      "<button class='btn secondary' id='chat-new'>＋ New chat</button>" +
      "</div>" +
      "<div id='chat-messages' class='chat-messages'></div>" +
      "<div class='chat-composer-wrap'>" +
      "<div class='chat-greeting'><h1 id='chat-greet-title'>What would you like to ask?</h1>" +
      "<p class='greet-sub'>Answers are grounded in the selected matter&#39;s documents and cited to the exact page and span.</p></div>" +
      "<div id='chat-guide'></div>" +
      "<div class='chat-composer'>" +
      "<textarea id='chat-input' rows='1' placeholder='Ask anything about this matter&#39;s documents…'></textarea>" +
      "<button class='btn' id='chat-send'>Ask&nbsp;→</button>" +
      "</div></div>";
    document.getElementById("chat-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("chat-new").addEventListener("click", newChat);
    document.getElementById("chat-send").addEventListener("click", sendChat);
    document.getElementById("chat-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
  }

  function chatHook() {
    ensureBuilt("chat", buildChat);
    updateGreeting();
    fillMatterPickers().then(renderChatGuide).catch(function () {});
  }
  window.viewHooks.chat = chatHook;

  // --- Chat History view (UX-7, owner-directed: its own nav tab) ---------------
  async function renderHistory() {
    var inner = document.querySelector("#view-history .view-inner");
    var threads = [];
    try { threads = (await api("/chat/threads")).threads || []; } catch (e) { threads = []; }
    inner.innerHTML = "<h1>Chat History</h1>" + (threads.length
      ? "<div class='panel'><table><thead><tr><th>Conversation</th><th>Matter</th><th>Updated</th></tr></thead><tbody>" +
        threads.map(function (t) {
          return "<tr style='cursor:pointer' data-thread='" + t.id + "'><td>" + esc(t.title) +
            "</td><td class='muted'>" + esc(t.matter_slug) + "</td><td class='muted'>" +
            esc((t.updated || "").replace("T", " ")) + "</td></tr>";
        }).join("") + "</tbody></table></div>"
      : "<p class='muted'>No conversations yet — ask something in Chat.</p>");
    inner.querySelectorAll("[data-thread]").forEach(function (tr) {
      tr.addEventListener("click", function () { openThread(tr.dataset.thread); });
    });
  }
  window.viewHooks.history = renderHistory;

  // --- Search view (Move 1c) ---------------------------------------------------
  // Retrieval-only: every result is a real chunk with filename + page. "Every mention"
  // is exhaustive and paginated with the TRUE total - truncation is always labeled.
  var searchState = { offset: 0, lastQ: "" };

  async function runSearch(reset) {
    var q = document.getElementById("search-input").value.trim();
    var out = document.getElementById("search-results");
    var err = document.getElementById("search-err");
    if (err) err.textContent = "";
    if (!q) return;
    if (!state.matter) { if (err) err.textContent = "Create a matter first (Matters view)."; return; }
    if (reset) { searchState.offset = 0; searchState.lastQ = q; out.innerHTML = "<p class='muted'>Searching…</p>"; }
    try {
      var mode = document.getElementById("search-mode").value;
      var body = await api("/search?q=" + encodeURIComponent(q) +
        "&matter=" + encodeURIComponent(state.matter) + "&mode=" + mode +
        "&limit=25&offset=" + searchState.offset);
      var rows = (body.results || []).map(function (r) {
        var loc = esc(r.source_filename) + " — p." + esc(r.page_number) +
          (r.section ? " · " + esc(r.section) : "");
        var open = r.doc_id != null
          ? "<a class='src-chip' target='_blank' href='/kb/highlight/" + r.doc_id +
            "?page=" + r.page_number + "&span=" + encodeURIComponent((r.snippet || "").slice(0, 80)) +
            "'>" + loc + "</a>"
          : "<span class='src-chip'>" + loc + "</span>";
        return "<div class='panel search-hit'>" + open +
          "<div class='muted' style='margin-top:6px;font-size:13px'>…" + esc(r.snippet) + "…</div></div>";
      }).join("");
      var head = body.total != null
        ? ("<p class='muted'>" + body.total + " mention" + (body.total === 1 ? "" : "s") +
           (body.truncated ? " — showing " + (searchState.offset + body.results.length) + " so far" : "") + "</p>")
        : "<p class='muted'>Ranked matches (best first).</p>";
      var more = body.truncated
        ? "<button class='btn secondary' id='search-more'>Show more</button>" : "";
      if (reset) out.innerHTML = head + rows + more;
      else {
        var btn = document.getElementById("search-more");
        if (btn) btn.remove();
        out.insertAdjacentHTML("beforeend", rows + more);
      }
      var moreBtn = document.getElementById("search-more");
      if (moreBtn) moreBtn.onclick = function () { searchState.offset += 25; runSearch(false); };
    } catch (e) { out.innerHTML = "<span style='color:var(--err)'>" + esc(e.message) + "</span>"; }
  }

  // (The Search view was folded into the Document Hub's "Find in documents" panel
  // per owner direction — runSearch/searchState above are driven from there.)

  // --- Settings view (UX-6): Profile | Connectors | Memory | System -----------
  var settingsState = { tab: "profile" };

  function buildSettings(inner) {
    inner.innerHTML =
      "<h1>Settings</h1>" +
      "<div class='tab-row' id='settings-tabs'>" +
      "<button class='tab active' data-stab='profile'>Profile</button>" +
      "<button class='tab' data-stab='connectors'>Connectors</button>" +
      "<button class='tab' data-stab='memory'>Memory</button>" +
      "<button class='tab' data-stab='system'>System</button>" +
      "</div>" +
      "<div id='spane-profile'></div>" +
      "<div id='spane-connectors' style='display:none'></div>" +
      "<div id='spane-memory' style='display:none'></div>" +
      "<div id='spane-system' style='display:none'></div>";
    inner.querySelectorAll("#settings-tabs .tab").forEach(function (b) {
      b.addEventListener("click", function () { setSettingsTab(b.dataset.stab); });
    });
  }

  function setSettingsTab(tab) {
    settingsState.tab = tab;
    var view = document.getElementById("view-settings");
    if (!view) return;
    view.querySelectorAll("#settings-tabs .tab").forEach(function (b) {
      b.classList.toggle("active", b.dataset.stab === tab);
    });
    ["profile", "connectors", "memory", "system"].forEach(function (t) {
      var pane = document.getElementById("spane-" + t);
      if (pane) pane.style.display = t === tab ? "" : "none";
    });
  }

  function openSettingsTab(tab) {
    showView("settings");
    setSettingsTab(tab);
  }
  window.openSettingsTab = openSettingsTab;

  function renderProfilePane() {
    var pane = document.getElementById("spane-profile");
    if (!pane) return;
    var p = state.profile || {};
    var avatarInner = p.has_photo
      ? "<img src='/profile/photo?v=" + photoVer + "' alt=''>"
      : esc(((p.name || "").trim()[0] || "§").toUpperCase());
    pane.innerHTML =
      "<div class='panel'>" +
      "<div class='profile-photo-row'>" +
      "<span class='avatar avatar-lg' id='profile-avatar'>" + avatarInner + "</span>" +
      "<div><button class='btn secondary' id='photo-upload'>Upload photo</button> " +
      (p.has_photo ? "<button class='btn secondary' id='photo-remove'>Remove</button>" : "") +
      "<input type='file' id='photo-file' accept='image/png,image/jpeg' style='display:none'>" +
      "<p class='muted' style='font-size:12px;margin:8px 0 0'>PNG or JPEG. Stored only on this computer.</p>" +
      "</div></div>" +
      "<table class='settings-form' style='margin-top:16px'>" +
      "<tr><th>Name</th><td><input type='text' id='profile-name' placeholder='First name' value='" +
      esc(p.name || "") + "'></td></tr>" +
      "<tr><th>Role</th><td><input type='text' id='profile-role' placeholder='e.g. Solo attorney, Managing partner' value='" +
      esc(p.role || "") + "'></td></tr>" +
      "<tr><th>Firm</th><td><input type='text' id='profile-firm' placeholder='Firm or practice name' value='" +
      esc(p.firm || "") + "'></td></tr>" +
      "<tr><th>Practice areas</th><td><div id='profile-areas' class='chip-set'></div></td></tr>" +
      "</table>" +
      "<div style='margin-top:14px'><button class='btn' id='profile-save'>Save profile</button> " +
      "<span id='profile-saved' class='muted' style='font-size:13px'></span></div>" +
      "<p class='muted' style='font-size:12px'>Used to greet you and tailor suggested prompts. " +
      "Stored only on this computer. It never enters a cited answer.</p>" +
      "</div>" +
      "<div class='danger-zone'>" +
      "<h3>Erase all data</h3>" +
      "<p class='muted' style='font-size:13px;margin:0 0 12px'>The local equivalent of deleting an " +
      "account: disposes of every matter (documents, index, chats — crypto-shredded where encryption " +
      "is active) and clears your profile. Matters under a legal hold block this until the hold is " +
      "released. This cannot be undone.</p>" +
      "<button class='btn danger' id='erase-all'>Erase all data…</button>" +
      "</div>";
    renderAreaChips(document.getElementById("profile-areas"), p.practice_areas || []);

    var fileInput = document.getElementById("photo-file");
    document.getElementById("photo-upload").addEventListener("click", function () { fileInput.click(); });
    fileInput.addEventListener("change", async function () {
      var f = fileInput.files[0];
      if (!f) return;
      try {
        // ArrayBuffer, not the File: WKWebView throws "The string did not match
        // the expected pattern" on a File/Blob fetch body (works in Chromium).
        var r = await fetch("/profile/photo", { method: "POST", body: await f.arrayBuffer() });
        if (!r.ok) throw new Error((await r.json()).detail || "upload failed");
        photoVer++;
        await loadProfile();
        renderProfilePane();
      } catch (e) { alert(e.message); }
    });
    var rm = document.getElementById("photo-remove");
    if (rm) rm.addEventListener("click", async function () {
      await api("/profile/photo/delete", { method: "POST" });
      await loadProfile();
      renderProfilePane();
    });

    document.getElementById("profile-save").addEventListener("click", async function () {
      var saved = document.getElementById("profile-saved");
      saved.textContent = "";
      try {
        await saveProfile({
          name: document.getElementById("profile-name").value,
          role: document.getElementById("profile-role").value,
          firm: document.getElementById("profile-firm").value,
          practice_areas: chipValues(document.getElementById("profile-areas")),
        });
        saved.textContent = "Saved.";
      } catch (e) { saved.textContent = e.message; }
    });

    document.getElementById("erase-all").addEventListener("click", async function () {
      var typed = prompt('This erases every matter, document, chat, and your profile ' +
                         'from this computer. Type ERASE EVERYTHING to confirm:');
      if (typed === null) return;
      try {
        var out = await api("/data/erase", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm: typed }),
        });
        alert("Erased " + out.matters_disposed.length + " matter(s). The app will reload.");
        location.reload();
      } catch (e) { alert(e.message); }
    });
  }

  // --- Integration catalog (v0.3.0, D-81) -------------------------------------
  // Every row was verified against the vendor's CURRENT API docs (2026-07-10
  // research pass; see DECISIONS.md D-81). Rows are either LIVE (the user can
  // create a credential in the vendor's own UI, paste it here, and documents
  // flow into the Document Hub) or PLANNED (a real pull path exists but needs
  // a docuchat-registered developer app — coming; synced folders cover cloud
  // drives today). Vendors with NO user-reachable pull path were REMOVED —
  // we never list a connector a user would discover they cannot connect.
  // Row shape: [name, slug, credentialKind, description, live]
  var CONNECTOR_CATALOG = [
    { cat: "AI Meeting Notetakers", items: [
      ["Fathom", "fathom", "API key", "Call transcripts and meeting summaries", true],
      ["Fireflies.ai", "fireflies", "API key", "Transcripts and meeting summaries", true],
      ["Granola", "granola", "API key", "Meeting notes and transcripts", true],
      ["tl;dv", "tldv", "API key", "Meeting transcripts and notes", true],
      ["MeetGeek", "meetgeek", "API key", "Meeting summaries and transcripts", true],
      ["Avoma", "avoma", "API key", "Conversation notes and transcripts", true],
      ["Grain", "grain", "Access token", "Call transcripts and highlights", true],
      ["Jiminny", "jiminny", "API key", "Conversation transcripts", true],
      ["Rev AI", "revai", "Access token", "Speech-to-text transcripts (API jobs)", true],
      ["Sonix", "sonix", "API key", "Automated transcripts", true],
      ["Trint", "trint", "API key", "Transcripts and captions", true],
      ["Happy Scribe", "happyscribe", "API key", "Transcripts and subtitles", true],
      ["Read AI", "readai", "Coming", "Meeting notes, transcripts, and summaries", false],
      ["Rev", "rev", "Coming", "Human transcription orders and results", false],
      ["Circleback", "circleback", "Coming", "Meeting notes and action items", false],
    ]},
    { cat: "Meeting Platforms", items: [
      ["Zoom", "zoom", "Your Zoom app", "Cloud-recording transcripts", true],
      ["Cisco Webex", "webex", "Access token", "Meeting recordings and transcripts", true],
      ["Microsoft Teams", "msteams", "Coming", "Meeting recordings and transcripts", false],
      ["Google Meet", "googlemeet", "Coming", "Meeting recordings and transcripts", false],
    ]},
    { cat: "Notes & Knowledge", items: [
      ["Notion", "notion", "Integration token", "Pages and databases as documents", true],
      ["Confluence Cloud", "confluence", "API token", "Spaces and pages", true],
      ["Airtable", "airtable", "Personal token", "Tables exported as documents", true],
      ["Coda", "coda", "API token", "Docs exported as Markdown", true],
      ["ClickUp", "clickup", "API token", "Docs and pages", true],
      ["monday.com", "monday", "API token", "Workdocs from your boards", true],
      ["Asana", "asana", "Personal token", "Project files and attachments", true],
      ["Google Docs", "googledocs", "Coming", "Docs pulled into their matter", false],
      ["Microsoft OneNote", "onenote", "Coming", "Notebooks and sections", false],
      ["Microsoft Word", "msword", "Coming", "Word files from Microsoft 365", false],
      ["Dropbox Paper", "dropboxpaper", "Coming", "Paper docs via the Dropbox API", false],
    ]},
    { cat: "Email & Communications", items: [
      ["Gmail", "gmail", "App password", "Mail and attachments by label", true],
      ["Slack", "slack", "Your Slack app", "Files shared in your channels", true],
      ["Microsoft Outlook", "outlook", "Coming", "Mail and attachments by matter", false],
    ]},
    { cat: "Cloud File Storage", items: [
      ["Nextcloud", "nextcloud", "App password", "Self-hosted files over WebDAV", true],
      ["ShareFile", "sharefile", "API key", "Client-shared files", true],
      ["Microsoft OneDrive", "onedrive", "Coming", "Folders synced into matters", false],
      ["Microsoft SharePoint", "sharepoint", "Coming", "Document libraries", false],
      ["Google Drive", "googledrive", "Coming", "Folders synced into matters", false],
      ["Dropbox", "dropbox", "Coming", "Folders synced into matters", false],
      ["Box", "box", "Coming", "Folders synced into matters", false],
    ]},
    { cat: "Legal Practice & Case Management", items: [
      ["Clio Manage", "clio", "Coming", "Matters, documents, and contacts", false],
      ["MyCase", "mycase", "Coming", "Cases and documents", false],
      ["Lawmatics", "lawmatics", "Coming", "Intake files and CRM records", false],
      ["Actionstep", "actionstep", "Coming", "Matters and documents", false],
      ["LEAP", "leap", "Coming", "Matters and documents", false],
      ["Litify", "litify", "Coming", "Matters via the Salesforce platform", false],
    ]},
    { cat: "Legal Document Management", items: [
      ["NetDocuments", "netdocuments", "Coming", "Cabinets and documents", false],
    ]},
    { cat: "CRM & Intake", items: [
      ["HubSpot", "hubspot", "Private app token", "Notes and file attachments", true],
      ["Zoho CRM", "zoho", "Self Client", "Records and attachments", true],
      ["Pipedrive", "pipedrive", "API token", "Notes and files from your deals", true],
      ["Salesforce", "salesforce", "Coming", "Records and files", false],
    ]},
  ];

  // Logos are bundled local files (air-gap — no runtime fetch). Every catalog
  // brand ships a real mark (D-81: no letter tiles); _PNG_LOGOS lists the ones
  // whose official asset is a PNG. The tile remains only as a safety net.
  var _PNG_LOGOS = {actionstep:1, avoma:1, circleback:1, clio:1, fireflies:1,
    grain:1, happyscribe:1, jiminny:1, lawmatics:1, litify:1, meetgeek:1,
    monday:1, mycase:1, pipedrive:1, readai:1, rev:1, revai:1, sharefile:1,
    trint:1};

  function connectorLogo(name, slug) {
    var ext = _PNG_LOGOS[slug] ? ".png" : ".svg";
    return "<img class='conn-logo' src='/static/logos/" + slug + ext + "' alt='' " +
      "onerror=\"this.outerHTML='<span class=conn-tile>" + esc(name[0]) +
      "</span>'\">";
  }

  // Live-connection state for the pane: services metadata (key steps, credential
  // fields) from /connections/services, the user's connections, open drawer slug.
  var connState = { services: {}, connections: [], open: null, pollTimer: null };

  function connectionFor(slug) {
    for (var i = 0; i < connState.connections.length; i++)
      if (connState.connections[i].service === slug) return connState.connections[i];
    return null;
  }

  function connectorRowHtml(it) {
    var name = it[0], slug = it[1], kind = it[2], desc = it[3], live = it[4];
    var svc = connState.services[slug];
    var right;
    if (live && svc) {
      var existing = connectionFor(slug);
      right = existing
        ? "<span class='conn-status live'>Connected</span>"
        : "<span class='conn-access'>" + esc(kind) + "</span>" +
          "<button class='btn secondary conn-connect' data-connect='" + slug +
          "'>Connect</button>";
    } else if (live) {
      // adapter registered as live in the catalog but missing from the backend
      // registry — never show a Connect button that cannot work
      right = "<span class='conn-status'>Unavailable</span>";
    } else {
      right = "<span class='conn-access'>" + esc(kind === "Coming" ? "Connection" : kind) +
        "</span><span class='conn-status'>Coming</span>";
    }
    var open = connState.open === slug && live && svc;
    return "<div class='conn-row" + (open ? " open" : "") + "' data-row='" + slug + "'>" +
      connectorLogo(name, slug) +
      "<div class='conn-text'><span class='conn-name'>" + esc(name) + "</span>" +
      "<span class='conn-desc'>" + esc(desc) + "</span></div>" + right + "</div>" +
      (open ? connectDrawerHtml(svc) : "");
  }

  function connectDrawerHtml(svc) {
    var steps = (svc.key_steps || []).map(function (s) {
      return "<li>" + esc(s) + "</li>";
    }).join("");
    var fields = (svc.fields || []).map(function (f) {
      return "<label class='conn-field'>" + esc(f.label) +
        "<input type='" + (f.secret ? "password" : "text") + "' data-cred='" +
        esc(f.key) + "' autocomplete='off' spellcheck='false'" +
        (f.placeholder ? " placeholder='" + esc(f.placeholder) + "'" : "") + "></label>";
    }).join("");
    return "<div class='conn-drawer'>" +
      "<div class='conn-drawer-cols'><div class='conn-steps'>" +
      "<b>Where to get it</b><ol>" + steps + "</ol>" +
      (svc.plan_note ? "<p class='muted' style='font-size:12.5px'>" +
        esc(svc.plan_note) + "</p>" : "") +
      "<a href='" + esc(svc.docs_url) + "' target='_blank' rel='noreferrer' " +
      "style='font-size:12.5px'>API documentation</a></div>" +
      "<div class='conn-form'>" + fields +
      "<label class='conn-field'>Import into" +
      "<select class='matter-picker' id='conn-matter'></select></label>" +
      "<label style='display:flex;gap:8px;align-items:center;font-size:13px'>" +
      "<input type='checkbox' id='conn-sync'> Keep in sync (checks every 30 minutes)</label>" +
      "<div style='display:flex;gap:8px;align-items:center'>" +
      "<button class='btn' id='conn-save' data-service='" + esc(svc.slug) + "'>" +
      "Test &amp; connect</button>" +
      "<span class='muted' id='conn-busy' style='font-size:12.5px;display:none'>" +
      "testing the key…</span></div>" +
      "<div id='conn-err' style='color:var(--err);font-size:13px'></div>" +
      "<p class='muted' style='font-size:12px'>The key is tested first, then stored " +
      "encrypted on this Mac (never in a file, never sent anywhere but " +
      esc(svc.name) + "). Disconnect deletes it.</p></div></div></div>";
  }

  function jobLabel(c) {
    var j = c.job || {};
    if (j.state === "listing") return "checking " + esc(c.service_name) + "…";
    if (j.state === "importing")
      return "importing " + (j.done || 0) + (j.total ? " of " + j.total : "") + "…";
    if (j.state === "error" || c.last_error)
      return "<span style='color:var(--err)'>" + esc(j.error || c.last_error) + "</span>";
    if (j.state === "done")
      return "imported " + (j.imported || 0) +
        (j.skipped ? " (" + j.skipped + " unsupported skipped)" : "");
    if (c.last_sync) return "last import " + esc(c.last_sync.replace("T", " ").slice(0, 16));
    return "not imported yet";
  }

  function connectedHtml() {
    if (!connState.connections.length) return "";
    var rows = connState.connections.map(function (c) {
      var busy = c.job && (c.job.state === "listing" || c.job.state === "importing");
      return "<div class='conn-row'>" + connectorLogo(c.service_name, c.service) +
        "<div class='conn-text'><span class='conn-name'>" + esc(c.service_name) +
        (c.label ? " <span class='muted' style='font-weight:400'>· " + esc(c.label) +
          "</span>" : "") + "</span>" +
        "<span class='conn-desc'>into " +
        esc((c.config && c.config.matter) || "unfiled") +
        (c.config && c.config.sync ? " · syncing" : "") + " · " + jobLabel(c) +
        "</span></div>" +
        "<span style='display:flex;gap:8px;flex:0 0 auto'>" +
        "<button class='btn secondary' data-import='" + c.id + "'" +
        (busy ? " disabled" : "") + ">" + (busy ? "Importing…" : "Import now") +
        "</button>" +
        "<button class='btn secondary' data-disconnect='" + c.id +
        "'>Disconnect</button></span></div>";
    }).join("");
    return "<div class='panel conn-group'><b>Connected</b>" + rows + "</div>";
  }

  function connectorCatalogHtml() {
    return CONNECTOR_CATALOG.map(function (group) {
      var rows = group.items.map(connectorRowHtml).join("");
      return "<div class='panel conn-group'><b>" + esc(group.cat) + "</b>" + rows + "</div>";
    }).join("");
  }

  async function renderConnectorsPane() {
    var pane = document.getElementById("spane-connectors");
    if (!pane) return;
    var data = null;
    try { data = await api("/connectors/folders"); } catch (e) { data = { folders: [] }; }
    try {
      var svc = await api("/connections/services");
      connState.services = {};
      (svc.services || []).forEach(function (s) { connState.services[s.slug] = s; });
      connState.connections = (await api("/connections")).connections || [];
    } catch (e) { /* pane still renders; live rows show Unavailable */ }
    var rows = (data.folders || []).map(function (f) {
      return "<tr><td style='word-break:break-all'>" + esc(f.path) + "</td><td class='muted'>" +
        esc(f.matter_slug) + "</td><td><span class='folder-status " +
        (f.exists ? "ok'>watching" : "missing'>missing") + "</span></td>" +
        "<td><button class='btn secondary' data-rm-folder='" + f.id + "'>remove</button></td></tr>";
    }).join("");
    pane.innerHTML =
      "<div class='panel'>" +
      "<b>Watched folders</b>" +
      "<p class='muted' style='font-size:13.5px'>docuchat is 100% local, so anything that reaches " +
      "your disk can flow in automatically. New files dropped into a watched folder are added to " +
      "its matter (checked every " + (data.poll_seconds || 15) + " seconds; originals are never " +
      "moved or changed). Point one at a scanner's output folder, or at a Dropbox / Google Drive / " +
      "OneDrive synced folder: the sync app moves the bytes, docuchat never touches the network.</p>" +
      "<div style='display:flex;gap:8px;align-items:center;margin:12px 0'>" +
      "<select class='matter-picker' id='folder-matter' style='max-width:240px'></select>" +
      "<input type='text' id='folder-path' placeholder='/Users/you/Scans or a synced folder' style='flex:1'>" +
      "<button class='btn' id='folder-add'>Watch folder</button></div>" +
      "<div id='folder-err' style='color:var(--err);font-size:13px'></div>" +
      (rows ? "<table style='margin-top:8px'><thead><tr><th>Folder</th><th>Matter</th><th>Status</th><th></th></tr></thead><tbody>" +
              rows + "</tbody></table>"
            : "<p class='muted' style='font-size:13px'>No watched folders yet.</p>") +
      "</div>" +
      "<div class='panel'>" +
      "<b>What can come in</b>" +
      "<p class='muted' style='font-size:13.5px'>PDF (born-digital and scanned), Word (.docx), " +
      "text and Markdown, email files (.eml), web pages (.html), meeting and caption " +
      "transcripts (.vtt/.srt — the format Zoom, Teams, and Meet export, with timestamps and " +
      "speakers kept), spreadsheets as CSV, and JSON. Deposition and hearing transcripts get " +
      "page:line citations when marked as transcripts at upload.</p>" +
      "<p class='muted' style='font-size:13px'>Coming formats: Outlook .msg, .mbox mailboxes, " +
      "RTF, XLSX, and audio/video with local transcription.</p>" +
      "</div>" +
      connectedHtml() +
      "<h2 class='conn-catalog-head'>Integration catalog</h2>" +
      "<p class='muted' style='font-size:13.5px;max-width:72ch'>Every connection pulls documents " +
      "IN to this computer; nothing about your documents goes out. You create the key in the " +
      "service's own settings and paste it here — it is tested first, stored encrypted on this " +
      "Mac, and deleted the moment you disconnect. Every imported item keeps its source, author, " +
      "and dates. Rows marked Coming need a docuchat-registered app with that vendor and are on " +
      "the way; for cloud drives, a synced folder above covers the gap today.</p>" +
      connectorCatalogHtml();
    fillMatterPickers().catch(function () {});
    wireConnectionEvents(pane);
    document.getElementById("folder-add").addEventListener("click", async function () {
      var err = document.getElementById("folder-err");
      err.textContent = "";
      var matter = document.getElementById("folder-matter").value;
      var path = document.getElementById("folder-path").value.trim();
      if (!matter || !path) { err.textContent = "Choose a matter and enter a folder path."; return; }
      try {
        await api("/connectors/folders", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ matter: matter, path: path }),
        });
        renderConnectorsPane();
      } catch (e) { err.textContent = e.message; }
    });
    pane.querySelectorAll("[data-rm-folder]").forEach(function (b) {
      b.addEventListener("click", async function () {
        await api("/connectors/folders/remove", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: parseInt(b.dataset.rmFolder, 10) }),
        });
        renderConnectorsPane();
      });
    });
  }

  function wireConnectionEvents(pane) {
    pane.querySelectorAll("[data-connect]").forEach(function (b) {
      b.addEventListener("click", function () {
        connState.open = connState.open === b.dataset.connect ? null : b.dataset.connect;
        renderConnectorsPane();
      });
    });
    var save = document.getElementById("conn-save");
    if (save) save.addEventListener("click", async function () {
      var err = document.getElementById("conn-err");
      var busy = document.getElementById("conn-busy");
      err.textContent = "";
      var creds = {};
      var missing = false;
      pane.querySelectorAll("[data-cred]").forEach(function (i) {
        if (!i.value.trim()) missing = true;
        creds[i.dataset.cred] = i.value.trim();
      });
      if (missing) { err.textContent = "Fill in every field first."; return; }
      save.disabled = true;
      busy.style.display = "";
      try {
        var row = await api("/connections", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            service: save.dataset.service, credentials: creds,
            matter: document.getElementById("conn-matter").value || "unfiled",
            sync: document.getElementById("conn-sync").checked,
          }),
        });
        connState.open = null;
        await api("/connections/import", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: row.id }),
        });
        renderConnectorsPane();
      } catch (e) {
        save.disabled = false;
        busy.style.display = "none";
        err.textContent = friendlyError(e);
      }
    });
    pane.querySelectorAll("[data-import]").forEach(function (b) {
      b.addEventListener("click", async function () {
        await api("/connections/import", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: parseInt(b.dataset.import, 10) }),
        });
        renderConnectorsPane();
      });
    });
    pane.querySelectorAll("[data-disconnect]").forEach(function (b) {
      b.addEventListener("click", async function () {
        if (b.dataset.armed !== "1") {          // two-click confirm, no browser dialog
          b.dataset.armed = "1";
          b.textContent = "Delete key?";
          setTimeout(function () { b.dataset.armed = ""; b.textContent = "Disconnect"; },
                     4000);
          return;
        }
        await api("/connections/remove", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: parseInt(b.dataset.disconnect, 10) }),
        });
        renderConnectorsPane();
      });
    });
    // live progress: refresh while any import is running (and the pane is visible)
    var busyNow = connState.connections.some(function (c) {
      return c.job && (c.job.state === "listing" || c.job.state === "importing");
    });
    if (connState.pollTimer) clearTimeout(connState.pollTimer);
    if (busyNow) connState.pollTimer = setTimeout(function () {
      if (document.getElementById("spane-connectors")) renderConnectorsPane();
    }, 2000);
  }

  function renderMemoryPane() {
    var pane = document.getElementById("spane-memory");
    if (!pane) return;
    var p = state.profile || {};
    var notes = p.memory_notes || [];
    var noteRows = notes.map(function (n, i) {
      return "<div class='memory-note'><span>" + esc(n) + "</span>" +
        "<button class='note-x' data-note-i='" + i + "' title='Forget this'>✕</button></div>";
    }).join("");
    var known = [];
    if (p.name) known.push("your name (" + esc(p.name) + ")");
    if (p.role) known.push("your role (" + esc(p.role) + ")");
    if (p.firm) known.push("your firm (" + esc(p.firm) + ")");
    if ((p.practice_areas || []).length) known.push("your practice areas (" + esc(p.practice_areas.join(", ")) + ")");
    pane.innerHTML =
      "<div class='panel'>" +
      "<b>What docuchat knows about you</b>" +
      "<p class='muted' style='font-size:13.5px'>Memory here is teachable, not scraped: you write " +
      "it, you can see all of it, and you can delete any of it. It shapes greetings and suggested " +
      "prompts only — it NEVER enters a cited answer, so a remembered note can never contaminate " +
      "the record or cross between matters.</p>" +
      "<p class='muted' style='font-size:13px'>From your profile: " +
      (known.length ? known.join("; ") + "." : "nothing yet — fill in <a href='#' id='mem-to-profile'>Profile</a>.") +
      "</p>" +
      "<div style='margin-top:10px'><b style='font-size:14px'>Notes you've taught it</b></div>" +
      (noteRows || "<p class='muted' style='font-size:13px'>None yet.</p>") +
      "<div style='display:flex;gap:8px;margin-top:12px'>" +
      "<input type='text' id='memory-new' placeholder='e.g. I prefer short answers. Call me Jake, not Jacob.' style='flex:1'>" +
      "<button class='btn' id='memory-add'>Remember</button></div>" +
      "</div>";
    var toProfile = document.getElementById("mem-to-profile");
    if (toProfile) toProfile.addEventListener("click", function (e) {
      e.preventDefault(); setSettingsTab("profile"); renderProfilePane();
    });
    pane.querySelectorAll("[data-note-i]").forEach(function (b) {
      b.addEventListener("click", async function () {
        var next = notes.slice();
        next.splice(parseInt(b.dataset.noteI, 10), 1);
        await saveProfile({ memory_notes: next });
        renderMemoryPane();
      });
    });
    function addNote() {
      var input = document.getElementById("memory-new");
      var v = input.value.trim();
      if (!v) return;
      saveProfile({ memory_notes: notes.concat([v]) }).then(renderMemoryPane);
    }
    document.getElementById("memory-add").addEventListener("click", addNote);
    document.getElementById("memory-new").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); addNote(); }
    });
  }

  async function renderSystemPane() {
    var pane = document.getElementById("spane-system");
    if (!pane) return;
    var s = null;
    try { s = await api("/settings/status"); } catch (e) { s = null; }
    if (!s) { pane.innerHTML = "<p class='muted'>Status unavailable.</p>"; return; }
    var local = s.egress === "loopback-only" && s.bind === "127.0.0.1";
    pane.innerHTML =
      "<div class='panel' style='display:flex;align-items:center;gap:14px'>" +
      "<div class='privacy-badge " + (local ? "ok" : "warn") + "'>" +
      (local ? "100% local · 0 outbound" : "⚠ posture: " + esc(s.egress)) + "</div>" +
      "<div class='muted'>Bind " + esc(s.bind) + " · Ollama " + esc(s.ollama) +
      " · egress " + esc(s.egress) + "</div></div>" +
      "<div class='panel'><table>" +
      "<tr><th>Chat model</th><td>" + esc(s.models.chat) + "</td></tr>" +
      "<tr><th>Embedding model</th><td>" + esc(s.models.embed) + "</td></tr>" +
      "<tr><th>Ollama</th><td>" + esc(s.ollama) + " (loopback)</td></tr>" +
      "<tr><th>Bind</th><td>" + esc(s.bind) + "</td></tr>" +
      "<tr><th>KB documents</th><td>" + s.stores.kb_docs + "</td></tr>" +
      "<tr><th>KB chunks</th><td>" + s.stores.kb_chunks + "</td></tr>" +
      "<tr><th>Egress</th><td>" + esc(s.egress) + "</td></tr>" +
      (s.hardening ? (
        "<tr><th>Web-page attack guard</th><td>" +
        (s.hardening.trusted_host && s.hardening.origin_guard
          ? "on (host + origin checks)" : "partial") + "</td></tr>" +
        "<tr><th>Backup exclusions</th><td>" +
        esc(Object.values(s.hardening.backup_exclusions || {}).join("; ") || "n/a") +
        "</td></tr>") : "") +
      "</table></div>" +
      "<div class='panel'><b>Updates</b>" +
      "<label style='display:flex;align-items:center;gap:8px;margin-top:10px;font-size:13.5px'>" +
      "<input type='checkbox' id='update-check-toggle'" +
      ((state.profile && state.profile.update_check === false) ? "" : " checked") +
      "> Check for updates automatically</label>" +
      "<p class='muted' style='font-size:12.5px;margin:8px 0 0'>The one thing docuchat ever asks " +
      "the internet: the latest version number, from github.com, at most once a day. Nothing " +
      "about you or your documents is sent. Turn it off and docuchat makes zero outside calls.</p>" +
      "</div>" +
      "<p class='muted'>Synthetic/public documents only. Backup/restore via deploy/restore.sh (SC-7).</p>";
    document.getElementById("update-check-toggle").addEventListener("change", async function (e) {
      await saveProfile({ update_check: e.target.checked });
      checkUpdates();
    });
    var badge = document.getElementById("brand-badge");
    if (badge) badge.textContent = local ? "100% local" : "review";
  }

  function settingsHook() {
    ensureBuilt("settings", buildSettings);
    renderProfilePane();
    renderConnectorsPane();
    renderMemoryPane();
    renderSystemPane();
    setSettingsTab(settingsState.tab);
  }
  window.viewHooks.settings = settingsHook;

  // --- Review & Compare view ---------------------------------------------------
  // One workspace, two tabs (UX-2): Contract Review (the clause checklist) and
  // Compare Documents (the document × clause matrix) are tools over a matter's
  // documents, so they live together and are also launchable from inside a matter.
  var reviewState = { tab: "clauses", docsFor: null };

  // One checklist row. A "found" row shows the located value with inline source chips
  // + a citation thumbnail wired to the EXISTING /kb/highlight surface (chunk-derived
  // page + cited-span highlight — never a new fuzzy highlighter). A "potentially_missing"
  // row shows a clearly-distinct advisory badge and NO citation (never fabricate a
  // citation for an absence). A "not_confirmed" row shows the prose muted with NO
  // citation (the verifier rejected its spans — never shown as found). All model-supplied
  // strings pass through esc() before render (D-48 XSS guard).
  var CLAUSE_STATUS = {
    found: { label: "Found", cls: "found" },
    potentially_missing: { label: "Potentially missing", cls: "missing" },
    not_confirmed: { label: "Not confirmed", cls: "unconfirmed" },
  };

  function renderClauseRow(r) {
    var meta = CLAUSE_STATUS[r.status] || { label: esc(r.status), cls: "unconfirmed" };
    var head =
      "<div class='clause-head'><div><span class='clause-name'>" + esc(r.name) +
      "</span> <span class='clause-cat'>" + esc(r.category) + "</span></div>" +
      "<span class='clause-badge " + meta.cls + "'>" + esc(meta.label) + "</span></div>";

    var bodyHtml;
    if (r.status === "found") {
      var cites = r.citations || [];
      var value = md(injectChips(esc(r.value || ""), cites));
      var thumbs = cites.map(citationThumb).join("");
      bodyHtml = "<div class='answer'>" + value + "</div>" +
        (thumbs ? "<div class='thumb-row'>" + thumbs + "</div>" : "");
    } else if (r.status === "potentially_missing") {
      // advisory only — NOT legal advice, NOT a citation
      bodyHtml = "<p class='clause-advisory muted'>" + esc(r.value ||
        "Not located in the documents.") + "</p>";
    } else { // not_confirmed
      bodyHtml = "<div class='answer muted'>" + md(injectChips(esc(r.value || ""), [])) +
        "</div><p class='clause-advisory muted'>No span-verified citation — not shown as found.</p>";
    }
    return "<div class='clause-row " + meta.cls + "'>" + head + bodyHtml + "</div>";
  }

  async function runClauseReview() {
    var out = document.getElementById("clause-results");
    var err = document.getElementById("clause-err");
    if (err) err.textContent = "";
    if (!state.matter) { if (err) err.textContent = "Create a matter first (Matters view), then run the review."; return; }
    out.innerHTML = "<p class='muted'>Running the clause checklist over " +
      esc(state.matter) + " … this can take a moment.</p>";
    try {
      var body = await api("/clauses/review", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter: state.matter }),
      });
      var s = body.summary || {};
      var summary = "<div class='clause-summary'>" +
        "<span class='clause-badge found'>" + (s.found || 0) + " found</span>" +
        "<span class='clause-badge missing'>" + (s.potentially_missing || 0) + " potentially missing</span>" +
        "<span class='clause-badge unconfirmed'>" + (s.not_confirmed || 0) + " not confirmed</span>" +
        "</div>";
      var rows = (body.results || []).map(renderClauseRow).join("");
      out.innerHTML = summary + rows +
        "<p class='muted clause-foot'>Locate &amp; summarize only — verify each item against the cited source. This is not legal advice.</p>";
    } catch (e) {
      out.innerHTML = "<span style='color:var(--err)'>" + esc(e.message) + "</span>";
    }
  }

  // The comparison matrix streamed live over SSE (POST /grid). Each cell is a
  // span-verified finding ("found" + citation chip -> /kb/highlight), an advisory
  // "potentially missing", or "not confirmed" — reusing the SAME verifier as the rest of
  // the app (never a fuzzy highlight). Cells render as skeletons until their SSE event
  // arrives. All model-supplied text passes through esc() before render (D-48 XSS guard).
  var GRID_BADGE = { found: "found", potentially_missing: "missing", not_confirmed: "unconf" };
  var gridData = { columns: [], docs: [], cells: {} };

  function gridCellId(docId, colId) { return "gc-" + docId + "-" + colId; }

  function buildGridSkeleton(meta) {
    gridData = { columns: meta.columns || [], docs: meta.docs || [], cells: {} };
    var head = "<th class='grid-corner'>Document</th>" +
      gridData.columns.map(function (c) {
        return "<th class='grid-col' title='" + esc(c.question) + "'>" + esc(c.name || c.id) + "</th>";
      }).join("");
    var body = gridData.docs.map(function (d) {
      var cells = gridData.columns.map(function (c) {
        return "<td class='grid-cell skeleton' id='" + gridCellId(d.doc_id, c.id) + "'>…</td>";
      }).join("");
      return "<tr><th class='grid-rowhead' title='" + esc(d.filename) + "'>" + esc(d.filename) +
        "</th>" + cells + "</tr>";
    }).join("");
    var out = document.getElementById("grid-results");
    out.innerHTML = "<div class='grid-scroll'><table class='grid-table'><thead><tr>" +
      head + "</tr></thead><tbody>" + body + "</tbody></table></div>";
  }

  function fillGridCell(cell) {
    gridData.cells[gridCellId(cell.doc_id, cell.column_id)] = cell;
    var td = document.getElementById(gridCellId(cell.doc_id, cell.column_id));
    if (!td) return;
    var badge = GRID_BADGE[cell.status] || "unconf";
    var inner = "<span class='clause-badge " + badge + "'>" + esc(badge) + "</span>";
    if (cell.status === "found") {
      var c = (cell.citations || [])[0];
      var snippet = (cell.value || "").replace(/\s+/g, " ").slice(0, 90);
      inner += " <span class='grid-val'>" + esc(snippet) + "</span>";
      if (c && c.doc_id != null) {
        inner += " <a class='src-chip' target='_blank' href='" + highlightUrl(c) +
          "' title='" + esc(c.filename) + " p." + esc(c.page) + "'>p." + esc(c.page) + "</a>";
      }
    } else if (cell.status === "potentially_missing") {
      inner += " <span class='muted'>not located</span>";
    } else {
      inner += " <span class='muted'>unverified</span>";
    }
    td.className = "grid-cell " + badge;
    td.innerHTML = inner;
  }

  function gridToCsv() {
    var rows = [["Document", "Clause", "Status", "Value", "Citation"]];
    gridData.docs.forEach(function (d) {
      gridData.columns.forEach(function (col) {
        var cell = gridData.cells[gridCellId(d.doc_id, col.id)] || {};
        var c = (cell.citations || [])[0];
        rows.push([d.filename, col.name || col.id, cell.status || "",
          (cell.value || "").replace(/\s+/g, " "),
          c ? (c.filename + " p." + c.page) : ""]);
      });
    });
    return rows.map(function (r) {
      return r.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(",");
    }).join("\n");
  }

  function downloadCsv() {
    var blob = new Blob([gridToCsv()], { type: "text/csv" });  // local, no network
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = "review-grid.csv";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }
  window.gridToCsv = gridToCsv;

  // Explicit document picker (UX-4): the user chooses WHICH documents to compare.
  // Checkboxes default to all; a subset posts doc_ids, all-checked posts null (all).
  async function refreshGridDocs() {
    var box = document.getElementById("grid-docs");
    if (!box) return;
    if (!state.matter) { box.innerHTML = "<span class='muted'>Choose a matter first.</span>"; reviewState.docsFor = null; return; }
    // Always refetch (new uploads must appear) but preserve the user's selection by
    // doc id when the matter is unchanged; unseen docs default to checked.
    var prev = null;
    if (reviewState.docsFor === state.matter) {
      prev = {};
      box.querySelectorAll(".grid-doc").forEach(function (c) { prev[c.value] = c.checked; });
    }
    var docs = [];
    try { docs = (await api("/kb/documents?matter=" + encodeURIComponent(state.matter))).documents || []; }
    catch (e) { docs = []; }
    reviewState.docsFor = state.matter;
    if (!docs.length) { box.innerHTML = "<span class='muted'>No documents in this matter yet — add them in Matters.</span>"; return; }
    function isChecked(d) {
      return (prev && String(d.id) in prev) ? prev[String(d.id)] : true;
    }
    var allChecked = docs.every(isChecked);
    box.innerHTML =
      "<label><input type='checkbox' id='grid-docs-all'" + (allChecked ? " checked" : "") +
      "> <b>All documents</b></label>" +
      docs.map(function (d) {
        return "<label><input type='checkbox' class='grid-doc' value='" + d.id + "'" +
          (isChecked(d) ? " checked" : "") + "> " +
          esc(d.filename) + " <span class='status " + esc(d.status) + "'>" + esc(d.status) + "</span></label>";
      }).join("");
    var all = document.getElementById("grid-docs-all");
    all.addEventListener("change", function () {
      box.querySelectorAll(".grid-doc").forEach(function (c) { c.checked = all.checked; });
    });
    box.querySelectorAll(".grid-doc").forEach(function (c) {
      c.addEventListener("change", function () {
        var boxes = Array.prototype.slice.call(box.querySelectorAll(".grid-doc"));
        all.checked = boxes.every(function (x) { return x.checked; });
      });
    });
  }

  async function runGrid() {
    var err = document.getElementById("grid-err");
    if (err) err.textContent = "";
    if (!state.matter) { if (err) err.textContent = "Create a matter first (Matters view), then run the comparison."; return; }
    var boxes = Array.prototype.slice.call(document.querySelectorAll("#grid-docs .grid-doc"));
    var picked = boxes.filter(function (c) { return c.checked; })
                      .map(function (c) { return parseInt(c.value, 10); });
    if (boxes.length && !picked.length) { if (err) err.textContent = "Select at least one document to compare."; return; }
    var docIds = (picked.length && picked.length < boxes.length) ? picked : null;   // null = all
    document.getElementById("grid-csv").disabled = true;
    document.getElementById("grid-results").innerHTML =
      "<p class='muted'>Evaluating the matrix over " + esc(state.matter) + " — cells stream in live…</p>";
    try {
      var resp = await fetch("/grid", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter: state.matter, doc_ids: docIds }),
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      var reader = resp.body.getReader(), dec = new TextDecoder(), buf = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += dec.decode(chunk.value, { stream: true });
        var parts = buf.split("\n\n"); buf = parts.pop();
        parts.forEach(function (b) {
          var msg = parseSseBlock(b);
          if (!msg) return;
          if (msg.event === "meta") buildGridSkeleton(msg.data);
          else if (msg.event === "cell") fillGridCell(msg.data);
          else if (msg.event === "done") document.getElementById("grid-csv").disabled = false;
        });
      }
    } catch (e) {
      document.getElementById("grid-results").innerHTML =
        "<span style='color:var(--err)'>" + esc(e.message) + "</span>";
    }
  }

  function setReviewTab(tab) {
    reviewState.tab = tab;
    var view = document.getElementById("view-review");
    if (!view) return;
    view.querySelectorAll(".tab").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === tab);
    });
    var pc = document.getElementById("pane-clauses");
    var pg = document.getElementById("pane-grid");
    if (pc) pc.style.display = tab === "clauses" ? "" : "none";
    if (pg) pg.style.display = tab === "grid" ? "" : "none";
  }

  function openReviewTab(tab) {
    showView("review");
    setReviewTab(tab);
  }
  window.openReviewTab = openReviewTab;

  function buildReview(inner) {
    inner.innerHTML =
      "<h1>Review &amp; Compare</h1>" +
      "<p class='muted'>Tools over one matter&#39;s documents: a standard clause checklist, or a side-by-side " +
      "document comparison. Every finding is span-verified or honestly flagged — locate &amp; summarize only.</p>" +
      "<div class='tab-row'>" +
      "<button class='tab active' data-tab='clauses'>Contract Review</button>" +
      "<button class='tab' data-tab='grid'>Compare Documents</button>" +
      "</div>" +
      "<div id='pane-clauses'>" +
      "<div class='panel' style='display:flex;gap:8px;align-items:center'>" +
      "<label class='muted'>Matter:</label>" +
      "<select class='matter-picker' id='clause-matter' style='max-width:340px'></select>" +
      "<button class='btn' id='clause-run'>Run review</button></div>" +
      "<div id='clause-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='clause-results'></div>" +
      "</div>" +
      "<div id='pane-grid' style='display:none'>" +
      "<div class='panel'>" +
      "<div style='display:flex;gap:8px;align-items:center'>" +
      "<label class='muted'>Matter:</label>" +
      "<select class='matter-picker' id='grid-matter' style='max-width:340px'></select>" +
      "<button class='btn' id='grid-run'>Run comparison</button>" +
      "<button class='btn secondary' id='grid-csv' disabled>Export CSV</button></div>" +
      "<div id='grid-docs' class='doc-picker'></div>" +
      "</div>" +
      "<div id='grid-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='grid-results'></div>" +
      "</div>";
    inner.querySelectorAll(".tab").forEach(function (b) {
      b.addEventListener("click", function () { setReviewTab(b.dataset.tab); });
    });
    document.getElementById("clause-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("grid-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("clause-run").addEventListener("click", runClauseReview);
    document.getElementById("grid-run").addEventListener("click", runGrid);
    document.getElementById("grid-csv").addEventListener("click", downloadCsv);
  }

  function reviewHook() {
    ensureBuilt("review", buildReview);
    fillMatterPickers().catch(function () {});
    refreshGridDocs();
    setReviewTab(reviewState.tab);
  }
  window.viewHooks.review = reviewHook;
  // Back-compat aliases: the clause checklist and comparison grid live in the
  // review view now (viewHooks.clauses / viewHooks.grid callers land there).
  window.viewHooks.clauses = function () { openReviewTab("clauses"); };
  window.viewHooks.grid = function () { openReviewTab("grid"); };

  // --- Billing view (UX-7) -----------------------------------------------------
  // Honest by construction: there is no payment system yet, so this page reports
  // the real plan (free pilot) and reserves the slot where licensing will live.
  // No fake Upgrade buttons, ever.
  function buildBilling(inner) {
    inner.innerHTML =
      "<h1>Billing</h1>" +
      "<p class='muted'>Active plan</p>" +
      "<div class='panel plan-card'>" +
      "<div><span class='plan-name'>Pilot</span> <span class='plan-badge'>Free</span>" +
      "<p class='muted' style='margin:8px 0 0;max-width:52ch'>You are on the pilot build. " +
      "Everything runs on your own computer, so there is nothing to meter and nothing to bill. " +
      "Every feature is included: cited answers, transcripts, contract review, comparison, " +
      "watched folders, encryption at rest.</p></div>" +
      "</div>" +
      "<div class='panel'><b>What happens later</b>" +
      "<p class='muted' style='font-size:13.5px'>docuchat will be licensed like professional desktop " +
      "software: buy once on the website, paste a license key here, and it works offline. No " +
      "subscription meter is running on this machine. When licensing ships, this page holds your " +
      "key and your receipt. Pricing is being finalized.</p></div>";
  }
  window.viewHooks.billing = function () { ensureBuilt("billing", buildBilling); };

  // --- Referrals view (UX-7) -----------------------------------------------------
  function buildReferrals(inner) {
    var link = "https://docuchat.app";
    inner.innerHTML =
      "<h1>Referrals</h1>" +
      "<div class='panel'>" +
      "<h2 style='font-family:var(--serif);font-weight:500;font-size:22px;margin:0 0 8px'>" +
      "Know another attorney drowning in documents?</h2>" +
      "<p class='muted' style='margin:0 0 14px'>Send them docuchat. It is private by construction: " +
      "their client files never leave their computer.</p>" +
      "<div style='display:flex;gap:8px;max-width:520px'>" +
      "<input type='text' id='ref-link' value='" + link + "' readonly>" +
      "<button class='btn' id='ref-copy'>Copy link</button></div>" +
      "<span id='ref-copied' class='muted' style='font-size:12.5px'></span>" +
      "</div>" +
      "<div class='panel'><b>Referral rewards</b>" +
      "<p class='muted' style='font-size:13.5px'>A referral program with rewards arrives together " +
      "with licensing on the website. Shares from this page count from day one; nothing about " +
      "you or your machine is transmitted by copying the link.</p></div>";
    document.getElementById("ref-copy").addEventListener("click", async function () {
      var input = document.getElementById("ref-link");
      input.select();
      try { await navigator.clipboard.writeText(input.value); }
      catch (e) { document.execCommand("copy"); }
      document.getElementById("ref-copied").textContent = "Copied.";
    });
  }
  window.viewHooks.referrals = function () { ensureBuilt("referrals", buildReferrals); };

  // --- router ----------------------------------------------------------------
  function showView(name) {
    if (VIEWS.indexOf(name) === -1) return;
    VIEWS.forEach(function (v) {
      var el = document.getElementById("view-" + v);
      if (el) el.classList.toggle("active", v === name);
    });
    document.querySelectorAll(".nav-item").forEach(function (b) {
      b.classList.toggle("active", b.dataset.view === name);
    });
    var hook = window.viewHooks[name];
    if (typeof hook === "function") hook();
  }
  window.showView = showView;

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".nav-item").forEach(function (b) {
      b.addEventListener("click", function () { showView(b.dataset.view); });
    });
    var pb = document.getElementById("profile-block");
    if (pb) pb.addEventListener("click", function () { openSettingsTab("profile"); });
    fillMatterPickers().catch(function () {});
    showView("chat");
    loadProfile().then(maybeShowOnboarding).then(checkUpdates).catch(function () {});
  });
})();
