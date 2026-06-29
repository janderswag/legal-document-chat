/* First-run setup wizard (D-58 v1) — detect Ollama + the pinned models; if everything is
   present, drop straight into /app; otherwise show guided, copy-pasteable steps + a
   Re-check button. Vanilla JS, no framework, no CDN. All injected text is escaped. */
(function () {
  "use strict";
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  var OLLAMA_SITE = "https://ollama.com/download";  // the only intended external link (setup-time)

  function stepRow(done, title, body) {
    return "<div class='setup-step " + (done ? "done" : "todo") + "'>" +
      "<span class='setup-dot'>" + (done ? "✓" : "•") + "</span>" +
      "<div><div class='setup-step-title'>" + title + "</div>" +
      (body ? "<div class='setup-step-body'>" + body + "</div>" : "") + "</div></div>";
  }

  function cmd(text) {
    return "<code class='setup-cmd'>" + esc(text) +
      "<button class='setup-copy' data-cmd='" + esc(text) + "'>copy</button></code>";
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
        stepRow(true, "Models installed", "qwen3:14b · bge-m3");
      enter.style.display = "";
      setTimeout(function () { window.location.href = "/app"; }, 600);  // drop into the app
      return;
    }

    title.textContent = "A little setup first";
    sub.textContent = "The app runs locally with Ollama. Finish the steps below, then Re-check.";
    enter.style.display = "none";

    var html = "";
    // Step 1 — Ollama
    if (!s.ollama_reachable) {
      html += stepRow(false, "Install &amp; start Ollama",
        "Download Ollama, install it, and make sure it's running. " +
        "<a href='" + OLLAMA_SITE + "' target='_blank' rel='noopener'>Get Ollama</a>. " +
        "It listens on <code>" + esc(s.ollama_url) + "</code>.");
    } else {
      html += stepRow(true, "Ollama is running", esc(s.ollama_url));
    }
    // Step 2 — each missing model with its exact pull command
    var modelNames = Object.keys(s.models);
    modelNames.forEach(function (m) {
      if (s.models[m]) {
        html += stepRow(true, "Model installed: " + esc(m), "");
      } else if (s.ollama_reachable) {
        html += stepRow(false, "Install model: " + esc(m),
          "In a terminal, run: " + cmd("ollama pull " + m));
      } else {
        html += stepRow(false, "Then install model: " + esc(m),
          "After Ollama is running: " + cmd("ollama pull " + m));
      }
    });
    steps.innerHTML = html;
    bindCopy();
  }

  function bindCopy() {
    document.querySelectorAll(".setup-copy").forEach(function (b) {
      b.addEventListener("click", function () {
        var text = b.getAttribute("data-cmd");
        if (navigator.clipboard) navigator.clipboard.writeText(text).catch(function () {});
        b.textContent = "copied";
        setTimeout(function () { b.textContent = "copy"; }, 1200);
      });
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
