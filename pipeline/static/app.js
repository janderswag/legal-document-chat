/* SAM-style local UI — vanilla JS, no framework, no CDN. Client-side view router +
   per-view data fetches. Extended task-by-task (matters/hub/chat/history/settings). */
(function () {
  "use strict";
  var VIEWS = ["chat", "matters", "hub", "clauses", "grid", "history", "settings"];
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

  // A shared <select> matter picker (reused by Chat + Document Hub). Also enforces the
  // P1.4 default: a stale stored matter is dropped, and when none is active the first
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

  // --- Matters view ----------------------------------------------------------
  async function renderMatters() {
    var inner = document.querySelector("#view-matters .view-inner");
    inner.innerHTML =
      "<h1>Matters</h1><p class='muted'>Each matter is the scope for search — answers never cross matters.</p>" +
      "<div class='panel'><div style='display:flex;gap:8px'>" +
      "<input id='new-matter-name' type='text' placeholder='New matter name (e.g. Pemberton Logistics)'>" +
      "<button class='btn' id='new-matter-btn'>Create</button></div>" +
      "<div id='new-matter-err' style='color:var(--err);font-size:13px;margin-top:8px'></div></div>" +
      "<div class='panel'><table><thead><tr><th>Matter</th><th>Slug</th><th>Docs</th></tr></thead>" +
      "<tbody id='matters-rows'></tbody></table></div>";

    var matters = [];
    try { var d = await api("/matters"); matters = (d && d.matters) || []; }
    catch (e) { matters = []; }
    document.getElementById("matters-rows").innerHTML = matters.length
      ? matters.map(function (m) {
          return "<tr><td><b>" + esc(m.display_name) + "</b></td><td class='muted'>" +
            esc(m.slug) + "</td><td>" + m.doc_count + "</td></tr>";
        }).join("")
      : "<tr><td colspan='3' class='muted'>No matters yet — create one above.</td></tr>";

    document.getElementById("new-matter-btn").addEventListener("click", async function () {
      var name = document.getElementById("new-matter-name").value;
      var err = document.getElementById("new-matter-err");
      err.textContent = "";
      try {
        await api("/matters", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_name: name }),
        });
        await renderMatters();
        await fillMatterPickers();
      } catch (e) { err.textContent = e.message; }
    });
  }
  window.viewHooks.matters = renderMatters;

  // --- Document Hub view -----------------------------------------------------
  var hubTimer = null;

  // Ingest progress line (Move 0c): queue depth + in-flight stage, from the worker.
  async function refreshIngestStatus() {
    var el = document.getElementById("hub-ingest-status");
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

  async function refreshHubTable() {
    refreshIngestStatus();
    var tbody = document.getElementById("hub-rows");
    if (!tbody) return;
    if (!state.matter) {
      tbody.innerHTML = "<tr><td colspan='6' class='muted'>Create a matter first (Matters view) — its documents will appear here.</td></tr>";
      return;
    }
    var docs = [];
    try { docs = (await api("/kb/documents?matter=" + encodeURIComponent(state.matter))).documents || []; }
    catch (e) { docs = []; }
    tbody.innerHTML = docs.length ? docs.map(function (d) {
      var size = d.size_bytes != null ? Math.max(1, Math.round(d.size_bytes / 1024)) + " KB" : "—";
      return "<tr><td>" + esc(d.filename) + "</td><td class='muted'>" + esc(d.matter_slug) +
        "</td><td>" + size + "</td><td><span class='status " + esc(d.status) + "'>" +
        esc(d.status) + "</span></td><td class='muted'>" + esc((d.updated || "").replace("T", " ")) +
        "</td><td><button class='btn secondary' data-view-doc='" + d.id + "'>view</button> " +
        "<button class='btn secondary' data-del-doc='" + d.id + "'>delete</button></td></tr>";
    }).join("") : "<tr><td colspan='6' class='muted'>No documents yet — drop files above.</td></tr>";

    tbody.querySelectorAll("[data-view-doc]").forEach(function (b) {
      b.onclick = function () { window.open("/kb/source/" + b.dataset.viewDoc, "_blank"); };
    });
    tbody.querySelectorAll("[data-del-doc]").forEach(function (b) {
      b.onclick = async function () {
        if (!confirm("Remove this document from the knowledge base?")) return;
        await api("/kb/documents/" + b.dataset.delDoc, { method: "DELETE" });
        refreshHubTable();
      };
    });
  }
  window.onMatterChange = function () { refreshHubTable(); };

  async function uploadFiles(files) {
    var err = document.getElementById("hub-err");
    if (err) err.textContent = "";
    if (!state.matter) { if (err) err.textContent = "Create a matter first (Matters view), then upload."; return; }
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      try {
        await fetch("/kb/upload?matter=" + encodeURIComponent(state.matter) +
                    "&filename=" + encodeURIComponent(f.name), { method: "POST", body: f })
          .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail); }); });
      } catch (e) { if (err) err.textContent = e.message; }
    }
    refreshHubTable();
  }

  function renderHub() {
    var inner = document.querySelector("#view-hub .view-inner");
    inner.innerHTML =
      "<h1>Document Hub</h1><p class='muted'>Upload synthetic documents for the active matter. Parsing → Ready.</p>" +
      "<div class='panel'><label class='muted'>Matter:</label> " +
      "<select class='matter-picker' id='hub-matter' style='max-width:340px;display:inline-block'></select></div>" +
      "<div id='dropzone' class='panel' style='border:2px dashed var(--border);text-align:center;padding:28px;cursor:pointer'>" +
      "Drag &amp; drop files here, or click to choose. <span class='muted'>(.pdf .docx .txt .md)</span>" +
      "<input type='file' id='file-input' multiple style='display:none'></div>" +
      "<div id='hub-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='hub-ingest-status' class='muted' style='font-size:13px'></div>" +
      "<div class='panel'><table><thead><tr><th>Name</th><th>Matter</th><th>Size</th>" +
      "<th>Status</th><th>Updated</th><th></th></tr></thead><tbody id='hub-rows'></tbody></table></div>";

    fillMatterPickers().catch(function () {});
    document.getElementById("hub-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });

    var dz = document.getElementById("dropzone");
    var fi = document.getElementById("file-input");
    dz.addEventListener("click", function () { fi.click(); });
    fi.addEventListener("change", function () { uploadFiles(fi.files); });
    dz.addEventListener("dragover", function (e) { e.preventDefault(); dz.style.background = "#eef3ff"; });
    dz.addEventListener("dragleave", function () { dz.style.background = ""; });
    dz.addEventListener("drop", function (e) {
      e.preventDefault(); dz.style.background = "";
      uploadFiles(e.dataTransfer.files);
    });

    refreshHubTable();
    if (hubTimer) clearInterval(hubTimer);
    hubTimer = setInterval(function () {
      if (document.getElementById("view-hub").classList.contains("active")) refreshHubTable();
      else { clearInterval(hubTimer); hubTimer = null; }
    }, 2000);
  }
  window.viewHooks.hub = renderHub;

  // --- Chat view -------------------------------------------------------------
  // renderAnswerHtml(body) -> HTML string for an assistant turn. Basic here; Task 6
  // upgrades it to markdown + inline source chips. Always escapes model text first.
  // Per verified citation, a card showing the cited PAGE with the exact span highlighted
  // (Task 5). The image is /kb/highlight/<doc_id>?page=&span= — chunk-derived page+span,
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
          if (c.doc_id == null) return " <span class='src-chip'>[" + (i + 1) + "]</span>";
          return " <a class='src-chip' target='_blank' href='" + highlightUrl(c) +
            "' title='" + esc(fn) + " p." + esc(pg) + "'>[" + (i + 1) + "]</a>";
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
      var label = "[" + (i + 1) + "] " + esc(c.filename) + " — p." + esc(c.page);
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

  // Default answer path = SSE streaming (/chat/stream): retrieved sources render first,
  // tokens stream over them, and the 'done' event (verifier ran on the COMPLETE text)
  // replaces everything with the standard verified-citation render.
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
        "<li><a href='#' data-goto='matters'>Create a matter</a> (the private scope for a client or case)</li>" +
        "<li><a href='#' data-goto='hub'>Add a document</a> and wait for it to show Ready</li>" +
        "<li>Come back here and ask a question about it</li></ol>" +
        "<p class='muted'>A sample matter with demo documents is being prepared in the " +
        "background and will appear here when ready.</p></div>";
    } else if (active && active.doc_count === 0) {
      box.innerHTML =
        "<div class='panel guide'><b>" + esc(active.display_name) + "</b> has no documents yet. " +
        "<a href='#' data-goto='hub'>Add a document</a>, wait for Ready, then ask.</div>";
    } else if (active && active.sample && (active.suggested_questions || []).length) {
      box.innerHTML =
        "<div class='guide-chips'><span class='muted'>Try a question against the sample documents:</span> " +
        active.suggested_questions.map(function (q) {
          return "<button class='btn secondary guide-q' data-q='" + esc(q) + "'>" + esc(q) + "</button>";
        }).join(" ") + "</div>";
    } else {
      box.innerHTML = "";
    }
    box.querySelectorAll("[data-goto]").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); showView(a.dataset.goto); });
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
    appendMsg("assistant", "<i class='muted'>Searching " + esc(state.matter) + " …</i>");
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
          else if (msg.event === "done") done = msg.data;
        });
      }
      if (!done) throw new Error("stream ended unexpectedly");
      state.threadId = done.thread_id;
      pending.innerHTML = window.renderAnswerHtml(done);
      box.scrollTop = box.scrollHeight;
    } catch (e) { pending.innerHTML = "<span style='color:var(--err)'>" + esc(e.message) + "</span>"; }
  }
  window.sendChat = sendChat;

  function renderChat() {
    var inner = document.querySelector("#view-chat .view-inner");
    inner.innerHTML =
      "<div class='chat-head'>" +
      "<span class='field-label'>Matter</span>" +
      "<select class='matter-picker' id='chat-matter'></select>" +
      "<button class='btn secondary' id='chat-new'>＋ New chat</button>" +
      "</div>" +
      "<div id='chat-messages' class='chat-messages'></div>" +
      "<div class='chat-composer-wrap'>" +
      "<div class='chat-greeting'><h1>What would you like to ask?</h1>" +
      "<p class='greet-sub'>Answers are grounded in the selected matter&#39;s documents and cited to the exact page and span.</p></div>" +
      "<div id='chat-guide'></div>" +
      "<div class='chat-composer'>" +
      "<textarea id='chat-input' rows='1' placeholder='Ask anything about this matter&#39;s documents…'></textarea>" +
      "<button class='btn' id='chat-send'>Ask&nbsp;→</button>" +
      "</div></div>";
    fillMatterPickers().then(renderChatGuide).catch(function () {});
    document.getElementById("chat-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("chat-new").addEventListener("click", function () {
      state.threadId = null; renderChat();
    });
    document.getElementById("chat-send").addEventListener("click", sendChat);
    document.getElementById("chat-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
  }
  window.viewHooks.chat = renderChat;

  // --- Chat History view -----------------------------------------------------
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
      : "<p class='muted'>No conversations yet.</p>");
    inner.querySelectorAll("[data-thread]").forEach(function (tr) {
      tr.addEventListener("click", function () { openThread(tr.dataset.thread); });
    });
  }
  window.viewHooks.history = renderHistory;

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
      "<tr><th>Egress</th><td>" + esc(s.egress) + "</td></tr></table></div>" +
      "<p class='muted'>Synthetic/public documents only. Backup/restore via deploy/restore.sh (SC-7).</p>";
    var badge = document.getElementById("brand-badge");
    if (badge) badge.textContent = local ? "100% local" : "review";
  }
  window.viewHooks.settings = renderSettings;

  // --- Contract Review view --------------------------------------------------
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

  function renderClauses() {
    var inner = document.querySelector("#view-clauses .view-inner");
    inner.innerHTML =
      "<h1>Contract Review</h1>" +
      "<p class='muted'>Run a standard clause checklist over the active matter's documents. " +
      "Each clause is located &amp; span-verified, or honestly flagged as potentially missing.</p>" +
      "<div class='panel' style='display:flex;gap:8px;align-items:center'>" +
      "<label class='muted'>Matter:</label>" +
      "<select class='matter-picker' id='clause-matter' style='max-width:340px'></select>" +
      "<button class='btn' id='clause-run'>Run review</button></div>" +
      "<div id='clause-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='clause-results'></div>";
    fillMatterPickers().catch(function () {});
    document.getElementById("clause-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("clause-run").addEventListener("click", runClauseReview);
  }
  window.viewHooks.clauses = renderClauses;

  // --- Compare Documents view ------------------------------------------------
  // A document x clause matrix streamed live over SSE (POST /grid). Each cell is a
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

  function parseSseBlock(block) {
    var ev = null, data = null;
    block.split("\n").forEach(function (line) {
      if (line.indexOf("event:") === 0) ev = line.slice(6).trim();
      else if (line.indexOf("data:") === 0) { try { data = JSON.parse(line.slice(5).trim()); } catch (e) {} }
    });
    return ev ? { event: ev, data: data } : null;
  }

  async function runGrid() {
    var err = document.getElementById("grid-err");
    if (err) err.textContent = "";
    if (!state.matter) { if (err) err.textContent = "Create a matter first (Matters view), then run the grid."; return; }
    document.getElementById("grid-csv").disabled = true;
    document.getElementById("grid-results").innerHTML =
      "<p class='muted'>Evaluating the matrix over " + esc(state.matter) + " — cells stream in live…</p>";
    try {
      var resp = await fetch("/grid", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter: state.matter }),
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

  function renderGrid() {
    var inner = document.querySelector("#view-grid .view-inner");
    inner.innerHTML =
      "<h1>Compare Documents</h1>" +
      "<p class='muted'>A document × clause matrix. Each cell is span-verified, advisory " +
      "(potentially missing), or unverified — locate &amp; summarize only.</p>" +
      "<div class='panel' style='display:flex;gap:8px;align-items:center'>" +
      "<label class='muted'>Matter:</label>" +
      "<select class='matter-picker' id='grid-matter' style='max-width:340px'></select>" +
      "<button class='btn' id='grid-run'>Run grid</button>" +
      "<button class='btn secondary' id='grid-csv' disabled>Export CSV</button></div>" +
      "<div id='grid-err' style='color:var(--err);font-size:13px'></div>" +
      "<div id='grid-results'></div>";
    fillMatterPickers().catch(function () {});
    document.getElementById("grid-matter").addEventListener("change", function (e) {
      var opt = e.target.selectedOptions[0];
      setActiveMatter(e.target.value, opt ? opt.textContent : null);
    });
    document.getElementById("grid-run").addEventListener("click", runGrid);
    document.getElementById("grid-csv").addEventListener("click", downloadCsv);
  }
  window.viewHooks.grid = renderGrid;

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
  });
})();
