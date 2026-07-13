/* Landing page — load/scroll reveals + copy-to-clipboard. Vanilla, no deps. */
(function () {
  "use strict";

  // Staggered reveal on load + as sections scroll in.
  var items = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  if (!("IntersectionObserver" in window)) {
    items.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    items.forEach(function (el) { io.observe(el); });
    // hero items are above the fold — reveal immediately
    requestAnimationFrame(function () {
      document.querySelectorAll(".hero .reveal").forEach(function (el) {
        el.classList.add("in");
      });
    });
  }

  // Copy buttons (commands).
  document.querySelectorAll(".copy").forEach(function (b) {
    b.addEventListener("click", function () {
      var text = (b.getAttribute("data-cmd") || "").replace(/&#10;/g, "\n");
      if (navigator.clipboard) navigator.clipboard.writeText(text).catch(function () {});
      var prev = b.textContent;
      b.textContent = "copied ✓";
      setTimeout(function () { b.textContent = prev; }, 1300);
    });
  });

  // Copy the contact address.
  document.querySelectorAll(".copy-mail").forEach(function (b) {
    b.addEventListener("click", function () {
      var mail = b.getAttribute("data-mail") || "";
      if (navigator.clipboard) navigator.clipboard.writeText(mail).catch(function () {});
      var prev = b.textContent;
      b.textContent = "copied ✓";
      setTimeout(function () { b.textContent = prev; }, 1300);
    });
  });

  // Contact form. Web3Forms relays the submission to the owner's inbox; the access key is a
  // public client-side identifier, not a secret. Falls back to the visitor's own mail app if
  // the request cannot be made, so the form is never a dead end.
  var W3F_KEY = "cc03675e-977f-4cd4-9f96-0210e64842d0";
  var cform = document.getElementById("contact-form");
  if (cform) {
    cform.addEventListener("submit", function (e) {
      e.preventDefault();
      var status = document.getElementById("contact-status");
      var btn = cform.querySelector("button[type=submit]");
      var name = (cform.name.value || "").trim();
      var email = (cform.email.value || "").trim();
      var firm = (cform.firm.value || "").trim();
      var msg = (cform.message.value || "").trim();
      var subject = "docuchat: " + (name || "hello") + (firm ? " (" + firm + ")" : "");

      btn.disabled = true;
      status.className = "contact-status small muted";
      status.textContent = "Sending…";

      fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          access_key: W3F_KEY,
          subject: subject,
          from_name: "docuchat.app",
          name: name,
          email: email,
          firm: firm || "(not given)",
          message: msg,
          botcheck: cform.botcheck.checked
        })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.success) throw new Error(data.message || "send failed");
          cform.reset();
          status.className = "contact-status small ok";
          status.textContent = "Sent. I'll write back to " + email + ".";
          // Never send the visitor's message or address to analytics; just that it worked.
          if (window.dcTrack) window.dcTrack("contact_submitted", { has_firm: !!firm });
        })
        .catch(function () {
          status.className = "contact-status small err";
          status.innerHTML = 'That did not go through. Please email '
            + '<a href="mailto:jacob.mm.anderson@gmail.com">jacob.mm.anderson@gmail.com</a> directly.';
          if (window.dcTrack) window.dcTrack("contact_failed", {});
        })
        .finally(function () { btn.disabled = false; });
    });
  }
})();
