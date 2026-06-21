/* SAM-style local UI — vanilla JS, no framework, no CDN. Client-side view router +
   per-view data fetches. Extended task-by-task (matters/hub/chat/history/settings). */
(function () {
  "use strict";
  var VIEWS = ["chat", "matters", "hub", "history", "settings"];
  var state = { matter: null };
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
    var el = document.getElementById("active-matter");
    if (el) el.textContent = label || slug || "none";
    document.querySelectorAll(".matter-picker").forEach(function (sel) {
      if (sel.value !== state.matter) sel.value = state.matter || "";
    });
    if (typeof window.onMatterChange === "function") window.onMatterChange();
  }
  window.setActiveMatter = setActiveMatter;

  // A shared <select> matter picker (reused by Chat + Document Hub).
  async function fillMatterPickers() {
    var data = await api("/matters");
    var matters = (data && data.matters) || [];
    document.querySelectorAll(".matter-picker").forEach(function (sel) {
      sel.innerHTML = '<option value="">— choose matter —</option>' +
        matters.map(function (m) {
          return '<option value="' + esc(m.slug) + '">' + esc(m.display_name) +
            " (" + m.doc_count + ")</option>";
        }).join("");
      if (state.matter) sel.value = state.matter;
    });
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

  async function refreshHubTable() {
    var tbody = document.getElementById("hub-rows");
    if (!tbody) return;
    if (!state.matter) {
      tbody.innerHTML = "<tr><td colspan='6' class='muted'>Choose a matter to see its documents.</td></tr>";
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
    if (!state.matter) { if (err) err.textContent = "Choose a matter first."; return; }
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
