/* First-run setup wizard (D-58 v1; P1.5 doer) — detect Ollama + the pinned models; if
   everything is present, drop straight into /app. Missing models are installed IN-APP:
   the Download button streams POST /setup/pull (SSE) into a real progress bar — no
   terminal. Also shows Tesseract (OCR) + free-disk notices. Vanilla JS, no framework,
   no CDN. All injected text is escaped. */
(function () {
  "use strict";
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  var OLLAMA_SITE = "https://ollama.com/download";  // the only intended external link (setup-time)
  var pulling = null;                                // model id currently downloading

  function stepRow(done, title, body, cls) {
    return "<div class='setup-step " + (done ? "done" : "todo") + (cls ? " " + cls : "") + "'>" +
      "<span class='setup-dot'>" + (done ? "✓" : "•") + "</span>" +
      "<div style='flex:1'><div class='setup-step-title'>" + title + "</div>" +
      (body ? "<div class='setup-step-body'>" + body + "</div>" : "") + "</div></div>";
  }

  function sizeNote(s, m) {
    var gb = (s.model_sizes_gb || {})[m];
    return gb ? " (about " + gb + " GB)" : "";
  }

  function render(s) {
    var title = document.getElementById("setup-title");
    var sub = document.getElementById("setup-sub");
    var steps = document.getElementById("setup-steps");
    var enter = document.getElementById("setup-enter");

    if (s.ready) {
      title.textContent = "You're all set";
      sub.textContent = "Ollama and the required models are installed. Opening the app…";
      steps.innerHTML = stepRow(true, "Ollama is running", esc(s.ollama_url)) +
        stepRow(true, "Models installed", "qwen3:14b · bge-m3") +
        (s.tesseract ? stepRow(true, "Scanned-PDF text recognition available", "Tesseract found") : "");
      enter.style.display = "";
      setTimeout(function () { window.location.href = "/app"; }, 600);  // drop into the app
      return;
    }

    title.textContent = "A little setup first";
    sub.textContent = "The app runs locally with Ollama. Finish the steps below — no terminal needed.";
    enter.style.display = "none";

    var html = "";
    // Step 1 — Ollama
    if (!s.ollama_reachable) {
      html += stepRow(false, "Install &amp; start Ollama",
        "Download Ollama, open the installer, and leave it running. " +
        "<a href='" + OLLAMA_SITE + "' target='_blank' rel='noopener'>Get Ollama</a>. " +
        "Then press Re-check.");
    } else {
      html += stepRow(true, "Ollama is running", esc(s.ollama_url));
    }
    // Disk-space notice before big downloads
    if (s.missing.length && s.disk_free_gb != null && s.disk_free_gb < s.disk_needed_gb) {
      html += stepRow(false, "Free up disk space",
        "The models need about " + esc(s.disk_needed_gb) + " GB; this disk has " +
        esc(s.disk_free_gb) + " GB free.");
    }
    // Step 2 — each missing model gets an IN-APP Download button + progress bar
    Object.keys(s.models).forEach(function (m) {
      if (s.models[m]) {
        html += stepRow(true, "Model installed: " + esc(m), "");
      } else if (s.ollama_reachable) {
        html += stepRow(false, "Download model: " + esc(m),
          "<button class='btn setup-pull' data-model='" + esc(m) + "'>Download" +
          esc(sizeNote(s, m)) + "</button>" +
          "<div class='setup-progress' id='prog-" + esc(m).replace(/[^a-z0-9]/gi, "_") + "'></div>");
      } else {
        html += stepRow(false, "Then download model: " + esc(m),
          "Available here once Ollama is running." + esc(sizeNote(s, m)));
      }
    });
    // Tesseract advisory (optional — scanned PDFs only)
    if (!s.tesseract) {
      html += stepRow(false, "Optional: text recognition for scanned PDFs",
        "Typed PDFs work without it. To also read scanned/photographed documents, " +
        "install Tesseract (macOS: <code>brew install tesseract</code>), then Re-check.");
    }
    steps.innerHTML = html;
    bindPull();
  }

  function progId(model) { return "prog-" + model.replace(/[^a-z0-9]/gi, "_"); }

  function paintProgress(model, pct, note) {
    var box = document.getElementById(progId(model));
    if (!box) return;
    box.innerHTML =
      "<div class='setup-bar'><div class='setup-bar-fill' style='width:" +
      (pct == null ? 0 : pct) + "%'></div></div>" +
      "<span class='setup-bar-note'>" + esc(note || "") + "</span>";
  }

  async function pullModel(model) {
    if (pulling) return;
    pulling = model;
    document.querySelectorAll(".setup-pull").forEach(function (b) { b.disabled = true; });
    paintProgress(model, 0, "starting…");
    try {
      var resp = await fetch("/setup/pull", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: model }),
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      var reader = resp.body.getReader(), dec = new TextDecoder(), buf = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += dec.decode(chunk.value, { stream: true });
        var parts = buf.split("\n\n"); buf = parts.pop();
        for (var i = 0; i < parts.length; i++) {
          var ev = null, data = null;
          parts[i].split("\n").forEach(function (line) {
            if (line.indexOf("event:") === 0) ev = line.slice(6).trim();
            else if (line.indexOf("data:") === 0) { try { data = JSON.parse(line.slice(5).trim()); } catch (e) {} }
          });
          if (ev === "progress" && data) {
            var note = data.percent != null
              ? data.percent + "% · " + (data.status || "")
              : (data.status || "working…");
            paintProgress(model, data.percent, note);
          } else if (ev === "error" && data) {
            throw new Error(data.detail || "download failed");
          } else if (ev === "done") {
            paintProgress(model, 100, "done");
          }
        }
      }
      pulling = null;
      check();                                     // re-detect -> marks the model installed
    } catch (e) {
      pulling = null;
      paintProgress(model, null, "Failed: " + e.message + " — press Download to retry.");
      document.querySelectorAll(".setup-pull").forEach(function (b) { b.disabled = false; });
    }
  }

  function bindPull() {
    document.querySelectorAll(".setup-pull").forEach(function (b) {
      b.addEventListener("click", function () { pullModel(b.getAttribute("data-model")); });
    });
  }

  async function check() {
    var sub = document.getElementById("setup-sub");
    sub.textContent = "Checking…";
    try {
      var r = await fetch("/setup/status");
      render(await r.json());
    } catch (e) {
      document.getElementById("setup-steps").innerHTML =
        "<div class='setup-step todo'><span class='setup-dot'>!</span><div>" +
        "<div class='setup-step-title'>Could not reach the local app.</div></div></div>";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("setup-recheck").addEventListener("click", check);
    check();
  });
})();
