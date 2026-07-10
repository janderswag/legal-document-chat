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
  var VIEWS = ["matters", "chat", "search", "review", "settings"];
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
    var el = document.getElementById("active-matter");
    if (el) el.textContent = label || slug || "none";
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

  async function loadProfile() {
    try { state.profile = await api("/profile"); } catch (e) { state.profile = {}; }
    updateGreeting();
    return state.profile;
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
    ov.innerHTML =
      "<div class='onboard-card'>" +
      "<div class='onboard-step' data-step='1'>" +
      "<h2>Everything stays on this machine.</h2>" +
      "<p>docuchat runs entirely on your computer. Your documents never leave it. " +
      "No cloud, no account, no telemetry.</p>" +
      "<p class='muted'>It works with Wi-Fi off. You can check.</p>" +
      "<div class='onboard-actions'><button class='btn' data-next='2'>Set up in 30 seconds</button>" +
      "<a href='#' class='onboard-skip'>Skip</a></div>" +
      "</div>" +
      "<div class='onboard-step' data-step='2' style='display:none'>" +
      "<h2>A few basics</h2>" +
      "<label class='field-label'>What should we call you? (optional)</label>" +
      "<input type='text' id='onboard-name' placeholder='First name' style='margin-top:6px'>" +
      "<label class='field-label' style='margin-top:16px;display:block'>Your practice areas</label>" +
      "<div id='onboard-areas' class='chip-set'></div>" +
      "<p class='muted' style='font-size:12px;margin-top:12px'>Stored only in a local file on this " +
      "computer. Change anytime in Settings.</p>" +
      "<div class='onboard-actions'><button class='btn' data-next='3'>Continue</button>" +
      "<a href='#' class='onboard-skip'>Skip</a></div>" +
      "</div>" +
      "<div class='onboard-step' data-step='3' style='display:none'>" +
      "<h2>How to trust the answers</h2>" +
      "<p>docuchat answers only from your documents. Every claim is cited to the exact page " +
      "and passage, and each citation is mechanically checked against the source text before " +
      "it reaches you. If the documents do not support an answer, it says so.</p>" +
      "<p><b>AI can still misread context.</b> Verify citations before you rely on them. " +
      "This is a research assistant, not legal advice.</p>" +
      "<div class='onboard-actions'><button class='btn' id='onboard-done'>Start</button></div>" +
      "</div></div>";
    document.body.appendChild(ov);
    renderAreaChips(document.getElementById("onboard-areas"),
                    (state.profile && state.profile.practice_areas) || []);

    function goStep(n) {
      ov.querySelectorAll(".onboard-step").forEach(function (s) {
        s.style.display = s.dataset.step === String(n) ? "" : "none";
      });
    }
    ov.querySelectorAll("[data-next]").forEach(function (b) {
      b.addEventListener("click", function () { goStep(b.dataset.next); });
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

  // --- Matters view (the case file: list + detail) ----------------------------
  // A matter holds its documents (upload lives HERE), its conversations, and its
  // tools. The old global "Document Hub" is absorbed: documents always belong to a
  // matter, the way a filing belongs to a case file.
  var mattersState = { open: null, builtFor: null, timer: null };

  function buildMatters(inner) {
    inner.innerHTML = "<div id='matters-list'></div>" +
      "<div id='matter-detail' style='display:none'></div>";
  }

  function refreshMattersView() {
    var list = document.getElementById("matters-list");
    var detail = document.getElementById("matter-detail");
    if (!list || !detail) return;
    var open = !!mattersState.open;
    list.style.display = open ? "none" : "";
    detail.style.display = open ? "" : "none";
    if (open) showMatterDetail(mattersState.open);
    else renderMattersList();
  }

  async function renderMattersList() {
    var list = document.getElementById("matters-list");
    list.innerHTML =
      "<h1>Matters</h1><p class='muted'>A matter is the case file: its documents, chats, and reviews " +
      "live inside it. Answers never cross matters.</p>" +
      "<div class='panel'><div style='display:flex;gap:8px'>" +
      "<input id='new-matter-name' type='text' placeholder='New matter name (e.g. Pemberton Logistics)'>" +
      "<button class='btn' id='new-matter-btn'>Create</button></div>" +
      "<div id='new-matter-err' style='color:var(--err);font-size:13px;margin-top:8px'></div></div>" +
      "<div class='panel'><table><thead><tr><th>Matter</th><th>Docs</th><th>Retention</th></tr></thead>" +
      "<tbody id='matters-rows'></tbody></table></div>";

    var matters = [];
    try { var d = await api("/matters"); matters = (d && d.matters) || []; }
    catch (e) { matters = []; }
    state.matters = matters;
    document.getElementById("matters-rows").innerHTML = matters.length
      ? matters.map(function (m) {
          return "<tr><td><a href='#' class='matter-open' data-open='" + esc(m.slug) + "'><b>" +
            esc(m.display_name) + "</b></a>" +
            (m.sample ? " <span class='muted'>(sample)</span>" : "") + "</td><td>" +
            m.doc_count + "</td><td>" +
            "<button class='btn secondary' data-hold='" + esc(m.slug) + "'>hold</button> " +
            "<button class='btn secondary' data-export='" + esc(m.slug) + "'>export</button> " +
            "<button class='btn secondary' data-dispose='" + esc(m.slug) + "'>dispose</button>" +
            "</td></tr>";
        }).join("")
      : "<tr><td colspan='3' class='muted'>No matters yet — create one above.</td></tr>";

    list.querySelectorAll(".matter-open").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); openMatter(a.dataset.open); });
    });

    // Retention actions (Move 4, D-72): hold toggles (with reasons), export downloads
    // the complete matter file, dispose double-confirms and downloads the honest
    // Certificate of Disposition. Holds block dispose and document deletes (409s).
    list.querySelectorAll("[data-hold]").forEach(function (b) {
      b.onclick = async function () {
        var st = await api("/retention/" + b.dataset.hold + "/status");
        if (st.hold) {
          var why = prompt("Active hold: " + st.hold.reason + "\nRelease reason (cancel to keep the hold):");
          if (why) { await api("/retention/" + b.dataset.hold + "/release", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: why }) }); renderMattersList(); }
        } else {
          var reason = prompt("Place a legal hold. Reason:");
          if (reason) { await api("/retention/" + b.dataset.hold + "/hold", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: reason }) }); renderMattersList(); }
        }
      };
    });
    list.querySelectorAll("[data-export]").forEach(function (b) {
      b.onclick = function () { window.open("/retention/" + b.dataset.export + "/export", "_blank"); };
    });
    list.querySelectorAll("[data-dispose]").forEach(function (b) {
      b.onclick = async function () {
        var slug = b.dataset.dispose;
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
        renderMattersList(); fillMatterPickers();
      };
    });

    document.getElementById("new-matter-btn").addEventListener("click", async function () {
      var name = document.getElementById("new-matter-name").value;
      var err = document.getElementById("new-matter-err");
      err.textContent = "";
      try {
        var m = await api("/matters", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: name }),
        });
        await fillMatterPickers();
        openMatter(m.slug);   // straight into the new case file — upload is right there
      } catch (e) { err.textContent = e.message; }
    });
  }

  function openMatter(slug) {
    mattersState.open = slug;
    var m = null;
    state.matters.forEach(function (x) { if (x.slug === slug) m = x; });
    setActiveMatter(slug, m ? m.display_name : slug);
    showView("matters");   // the hook renders the detail
  }
  window.openMatter = openMatter;

  function closeMatter() {
    mattersState.open = null;
    mattersState.builtFor = null;
    refreshMattersView();
  }

  function showMatterDetail(slug) {
    var detail = document.getElementById("matter-detail");
    if (mattersState.builtFor !== slug) {
      mattersState.builtFor = slug;
      var m = null;
      state.matters.forEach(function (x) { if (x.slug === slug) m = x; });
      var name = m ? m.display_name : slug;
      detail.innerHTML =
        "<a href='#' class='back-link' id='matter-back'>&larr; All matters</a>" +
        "<h1>" + esc(name) + "</h1>" +
        "<div class='tool-row'>" +
        "<button class='btn' data-tool='chat'>Ask about this matter</button>" +
        "<button class='btn secondary' data-tool='clauses'>Contract review</button>" +
        "<button class='btn secondary' data-tool='grid'>Compare documents</button>" +
        "</div>" +
        "<div id='matter-dropzone' class='panel' style='border:2px dashed var(--border);text-align:center;padding:28px;cursor:pointer'>" +
        "Drag &amp; drop files here, or click to choose. <span class='muted'>(.pdf .docx .txt .md)</span>" +
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
  }

  // Ingest progress line (Move 0c): queue depth + in-flight stage, from the worker.
  async function refreshIngestStatus() {
    var el = document.getElementById("matter-ingest-status");
    if (!el) return;
    try {
      var s = await api("/kb/ingest/status");
      if (s.queue_depth > 0 || s.current) {
        var cur = s.current ? ("processing #" + esc(s.current.doc_id) + " (" +
          esc(s.current.stage) + ")") : "starting next";
        el.textContent = "Ingest: " + s.queue_depth + " waiting, " + cur + ".";
      } else {
        el.textContent = "";
      }
    } catch (e) { el.textContent = ""; }
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
        "</td><td><button class='btn secondary' data-view-doc='" + d.id + "'>view</button> " +
        digestBtn +
        "<button class='btn secondary' data-del-doc='" + d.id + "'>delete</button></td></tr>";
    }).join("") : "<tr><td colspan='5' class='muted'>No documents yet — drop files above.</td></tr>";

    tbody.querySelectorAll("[data-view-doc]").forEach(function (b) {
      b.onclick = function () { window.open("/kb/source/" + b.dataset.viewDoc, "_blank"); };
    });
    tbody.querySelectorAll("[data-del-doc]").forEach(function (b) {
      b.onclick = async function () {
        if (!confirm("Remove this document from the knowledge base?")) return;
        await api("/kb/documents/" + b.dataset.delDoc, { method: "DELETE" });
        refreshMatterDocs();
      };
    });
    tbody.querySelectorAll("[data-digest-doc]").forEach(function (b) {
      b.onclick = function () { runDigest(b.dataset.digestDoc); };
    });
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
                    (isTranscript ? "&doc_type=transcript" : ""), { method: "POST", body: f })
          .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail); }); });
      } catch (e) { if (err) err.textContent = e.message; }
    }
    refreshMatterDocs();
  }

  function mattersHook() {
    ensureBuilt("matters", buildMatters);
    refreshMattersView();
    if (mattersState.timer) clearInterval(mattersState.timer);
    mattersState.timer = setInterval(function () {
      var active = document.getElementById("view-matters").classList.contains("active");
      if (active && mattersState.open) refreshMatterDocs();
      else if (!active) { clearInterval(mattersState.timer); mattersState.timer = null; }
    }, 2000);
  }
  window.viewHooks.matters = mattersHook;

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
        "<li><a href='#' data-goto='matters'>Create a matter</a> (the private case file for a client or case)</li>" +
        "<li>Drop its documents into the matter and wait for Ready</li>" +
        "<li>Come back here and ask a question about them</li></ol>" +
        "<p class='muted'>A sample matter with synthetic documents is being prepared in the " +
        "background and will appear here when ready.</p></div>";
    } else if (active && active.doc_count === 0) {
      box.innerHTML =
        "<div class='panel guide'><b>" + esc(active.display_name) + "</b> has no documents yet. " +
        "<a href='#' data-goto='matters' data-open-matter='" + esc(active.slug) + "'>Add documents</a>, " +
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
      appendMsg("system", "<i>Create a matter first — open <a href='#' " +
        "onclick=\"showView('matters');return false\">Matters</a> to add one.</i>");
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
      refreshThreadRail();
    } catch (e) { pending.innerHTML = "<span style='color:var(--err)'>" + esc(e.message) + "</span>"; }
  }
  window.sendChat = sendChat;

  // Past conversations rail (UX-2): history lives NEXT TO the chat, not two nav items
  // away. Click any past conversation to reopen it and build on it.
  async function refreshThreadRail() {
    var listEl = document.getElementById("thread-list");
    if (!listEl) return;
    var threads = [];
    try { threads = (await api("/chat/threads")).threads || []; } catch (e) { threads = []; }
    listEl.innerHTML = threads.length
      ? threads.slice(0, 30).map(function (t) {
          var cls = "thread-item" + (String(t.id) === String(state.threadId) ? " active" : "");
          return "<button class='" + cls + "' data-thread='" + t.id + "'>" +
            "<span class='t-title'>" + esc(t.title) + "</span>" +
            "<span class='t-meta'>" + esc(t.matter_slug) + " · " +
            esc((t.updated || "").replace("T", " ").slice(0, 16)) + "</span></button>";
        }).join("")
      : "<span class='muted' style='font-size:12px'>No conversations yet.</span>";
    listEl.querySelectorAll("[data-thread]").forEach(function (b) {
      b.addEventListener("click", function () { openThread(b.dataset.thread); });
    });
  }

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
    refreshThreadRail();
  }
  window.openThread = openThread;

  function newChat() {
    state.threadId = null;
    var box = document.getElementById("chat-messages");
    if (box) box.innerHTML = "";
    renderChatGuide();
    refreshThreadRail();
  }

  function buildChat(inner) {
    inner.innerHTML =
      "<div class='chat-layout'>" +
      "<aside class='chat-rail'>" +
      "<button class='btn secondary' id='chat-new'>＋ New chat</button>" +
      "<span class='rail-label'>Past conversations</span>" +
      "<div id='thread-list' class='thread-list'></div>" +
      "</aside>" +
      "<div class='chat-main'>" +
      "<div class='chat-head'>" +
      "<span class='field-label'>Matter</span>" +
      "<select class='matter-picker' id='chat-matter'></select>" +
      "</div>" +
      "<div id='chat-messages' class='chat-messages'></div>" +
      "<div class='chat-composer-wrap'>" +
      "<div class='chat-greeting'><h1 id='chat-greet-title'>What would you like to ask?</h1>" +
      "<p class='greet-sub'>Answers are grounded in the selected matter&#39;s documents and cited to the exact page and span.</p></div>" +
      "<div id='chat-guide'></div>" +
      "<div class='chat-composer'>" +
      "<textarea id='chat-input' rows='1' placeholder='Ask anything about this matter&#39;s documents…'></textarea>" +
      "<button class='btn' id='chat-send'>Ask&nbsp;→</button>" +
      "</div></div></div>";
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
    refreshThreadRail();
  }
  window.viewHooks.chat = chatHook;

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

  function buildSearch(inner) {
    inner.innerHTML =
      "<h1>Search</h1>" +
      "<p class='muted'>Every mention is exhaustive: the full list of matching passages in the active matter, " +
      "not a top-5. No AI answering here — just your documents.</p>" +
      "<div class='panel' style='display:flex;gap:8px;align-items:center'>" +
      "<select class='matter-picker' id='search-matter' style='max-width:280px'></select>" +
      "<input id='search-input' type='text' placeholder='A name, amount, defined term, case number…' style='flex:1'>" +
      "<select id='search-mode' style='max-width:170px'>" +
      "<option value='mentions'>Every mention</option><option value='fts'>Best match</option></select>" +
      "<button class='btn' id='search-go'>Search</button></div>" +
      "<div id='search-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='search-results'></div>";
    document.getElementById("search-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("search-go").addEventListener("click", function () { runSearch(true); });
    document.getElementById("search-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); runSearch(true); }
    });
  }

  function searchHook() {
    ensureBuilt("search", buildSearch);
    fillMatterPickers().catch(function () {});
  }
  window.viewHooks.search = searchHook;

  // --- Settings view ---------------------------------------------------------
  async function renderSettings() {
    var inner = document.querySelector("#view-settings .view-inner");
    var s = null;
    try { s = await api("/settings/status"); } catch (e) { s = null; }
    if (!s) { inner.innerHTML = "<h1>Settings</h1><p class='muted'>Status unavailable.</p>"; return; }
    var local = s.egress === "loopback-only" && s.bind === "127.0.0.1";
    inner.innerHTML =
      "<h1>Settings</h1>" +
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
      "<div class='panel'><b>Profile</b>" +
      "<table style='margin-top:8px'>" +
      "<tr><th>Name</th><td><input type='text' id='profile-name' placeholder='First name' " +
      "style='max-width:280px' value='" + esc((state.profile && state.profile.name) || "") + "'></td></tr>" +
      "<tr><th>Practice areas</th><td><div id='profile-areas' class='chip-set'></div></td></tr>" +
      "</table>" +
      "<div style='margin-top:12px'><button class='btn' id='profile-save'>Save profile</button> " +
      "<span id='profile-saved' class='muted' style='font-size:13px'></span></div>" +
      "<p class='muted' style='font-size:12px'>Used to greet you and tailor suggested prompts. " +
      "Stored only on this computer.</p></div>" +
      "<p class='muted'>Synthetic/public documents only. Backup/restore via deploy/restore.sh (SC-7).</p>";
    renderAreaChips(document.getElementById("profile-areas"),
                    (state.profile && state.profile.practice_areas) || []);
    document.getElementById("profile-save").addEventListener("click", async function () {
      var saved = document.getElementById("profile-saved");
      saved.textContent = "";
      try {
        await saveProfile({
          name: document.getElementById("profile-name").value,
          practice_areas: chipValues(document.getElementById("profile-areas")),
        });
        saved.textContent = "Saved.";
      } catch (e) { saved.textContent = e.message; }
    });
    var badge = document.getElementById("brand-badge");
    if (badge) badge.textContent = local ? "100% local" : "review";
  }
  window.viewHooks.settings = renderSettings;

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
    if (reviewState.docsFor === state.matter) return;   // keep the user's selection
    var docs = [];
    try { docs = (await api("/kb/documents?matter=" + encodeURIComponent(state.matter))).documents || []; }
    catch (e) { docs = []; }
    reviewState.docsFor = state.matter;
    if (!docs.length) { box.innerHTML = "<span class='muted'>No documents in this matter yet — add them in Matters.</span>"; return; }
    box.innerHTML =
      "<label><input type='checkbox' id='grid-docs-all' checked> <b>All documents</b></label>" +
      docs.map(function (d) {
        return "<label><input type='checkbox' class='grid-doc' value='" + d.id + "' checked> " +
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
    fillMatterPickers().catch(function () {});
    showView("chat");
    loadProfile().then(maybeShowOnboarding).catch(function () {});
  });
})();
