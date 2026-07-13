// Website analytics (PostHog). PUBLIC MARKETING SITE ONLY.
//
// Hard boundary: this file must never be copied into the desktop app. The app promises
// "no cloud, no account, no telemetry" and makes no network calls beyond the optional
// GitHub version check (D-78). That promise is the product. This is the docuchat.app
// landing page, which already loads third-party fonts and a booking link, and is the
// only place we are allowed to measure anything.
//
// The project key below is PostHog's public, write-only client key: safe in a public app,
// safe to commit. It cannot read data back out.
(function () {
  var PH_KEY = "phc_vH7FV85zJmm6dheatWMZxcHFsWyvBAngEmq8h3ekQUB2";
  var PH_HOST = "https://us.i.posthog.com";

  // PostHog loader snippet.
  !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);

  posthog.init(PH_KEY, {
    api_host: PH_HOST,
    person_profiles: "always",
    capture_pageview: true,
    autocapture: true,
    // Privacy posture for a product that sells privacy: no replay, no keystrokes,
    // no input contents, and Do Not Track is honored.
    disable_session_recording: true,
    respect_dnt: true,
    mask_all_text: false,
    mask_all_element_attributes: false
  });

  function track(name, props) {
    if (window.posthog && posthog.capture) posthog.capture(name, props || {});
  }
  window.dcTrack = track;

  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a, .btn-win, .copy-mail");
    if (!a) return;
    var href = a.getAttribute ? a.getAttribute("href") || "" : "";

    // The one real conversion on this site.
    if (href.indexOf("releases/latest/download/docuchat.dmg") !== -1) {
      track("download_clicked", { platform: "macos", placement: a.className || "link" });
      return;
    }
    // Highest-intent action on the page.
    if (href.indexOf("cal.com") !== -1) {
      track("book_call_clicked", {});
      return;
    }
    // Free demand signal for a decision we are split on: who actually wants Windows?
    if (a.classList && a.classList.contains("btn-win")) {
      track("windows_wanted", {});
      return;
    }
    if (a.classList && a.classList.contains("copy-mail")) {
      track("email_copied", {});
      return;
    }
    if (href.indexOf("mailto:") === 0) {
      track("email_link_clicked", {});
      return;
    }
    if (href.indexOf("github.com") !== -1) {
      track("github_clicked", { target: href.indexOf("/releases") !== -1 ? "releases" : "repo" });
      return;
    }
    if (href.indexOf("security.html") !== -1) track("security_page_clicked", {});
    if (href.indexOf("verification.html") !== -1) track("verification_page_clicked", {});
    if (href.indexOf("demo.html") !== -1) track("demo_clicked", {});
  });
})();
