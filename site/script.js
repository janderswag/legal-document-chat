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
      document.querySelectorAll(".hero .reveal, .seal.reveal").forEach(function (el) {
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
})();
