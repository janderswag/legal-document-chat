"""D-61 — docuchat.app rebrand + launch-batch contract (static checks; no network).

Asserts the public marketing site (``site/``) matches the D-61 brand/launch contract and that
the launcher's process-handling has a Windows branch. These are pure file/string checks: they
NEVER touch the pipeline, the verifier, or any LanceDB store, so they cannot move a baseline.

Contract checked here:
  * CNAME is exactly ``docuchat.app``.
  * No em-dashes anywhere in ``site/*.html`` (owner standing preference).
  * The old editorial palette tokens (``--oxblood*``, ``--brass``) are gone from styles.css;
    the new navy + gold tokens are present.
  * Both the Mac and Windows download buttons exist.
  * The Cal.com booking URL, the Product Hunt post URL, and the mailto: contact are present.
  * The owner's phone number never appears anywhere under ``site/``.
  * A Content-Security-Policy meta tag is present on index.html and demo.html.
  * No ``http://`` asset URLs in any ``site/*.html`` (no mixed content).
  * Every external ``target="_blank"`` link carries ``rel`` with noopener.
  * ``pages.yml`` is valid YAML and deploys ``site/`` on push.
  * The launcher selects a Windows (taskkill) process-kill branch when ``os.name == 'nt'``.
"""

import glob
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SITE = REPO_ROOT / "site"
HTML_FILES = sorted(glob.glob(str(SITE / "*.html")))

# The owner's phone number must never be published (D-61 owner directive). Match the digit
# runs regardless of separators so "(614) 208-1423", "614-208-1423", "614.208.1423" all trip.
PHONE_DIGITS = re.compile(r"614\D{0,3}208\D{0,3}1423")

CAL_URL = "https://cal.com/hawkify/janderswag"
PH_URL = ("https://www.producthunt.com/p/"
          "legal-document-chat-for-attorneys-open/legal-document-chat-for-attorneys-open")
CONTACT_EMAIL = "jacob.mm.anderson@gmail.com"


def _read(p):
    return Path(p).read_text(encoding="utf-8")


class TestSiteBrand(unittest.TestCase):
    def test_html_files_exist(self):
        self.assertTrue(HTML_FILES, "no site/*.html found")
        names = {Path(p).name for p in HTML_FILES}
        self.assertIn("index.html", names)
        self.assertIn("demo.html", names)

    def test_cname_is_docuchat_app(self):
        cname = SITE / "CNAME"
        self.assertTrue(cname.exists(), "site/CNAME missing")
        # exactly the apex domain, single line, no trailing content
        self.assertEqual(cname.read_text(encoding="utf-8").strip(), "docuchat.app")
        self.assertNotIn("\n", cname.read_text(encoding="utf-8").strip())

    def test_no_em_dashes_in_html(self):
        for p in HTML_FILES:
            t = _read(p)
            for needle in ("—", "&mdash;", "&#8212;"):
                self.assertFalse(needle in t, f"em-dash ({needle!r}) in {Path(p).name}")

    def test_old_palette_tokens_removed(self):
        css = _read(SITE / "styles.css")
        self.assertFalse("--oxblood" in css, "oxblood token still in styles.css")
        self.assertFalse("--brass" in css, "brass token still in styles.css")

    def test_navy_and_gold_tokens_present(self):
        css = _read(SITE / "styles.css")
        self.assertIn("--navy", css)
        self.assertIn("--gold", css)

    def test_mac_and_windows_buttons_present(self):
        idx = _read(SITE / "index.html").lower()
        self.assertIn("for mac", idx, "Mac download button missing")
        self.assertIn("windows", idx, "Windows download button missing")

    def test_contact_and_outbound_links_present(self):
        idx = _read(SITE / "index.html")
        self.assertIn(CAL_URL, idx, "Cal.com booking URL missing")
        self.assertIn(PH_URL, idx, "Product Hunt post URL missing")
        self.assertIn(f"mailto:{CONTACT_EMAIL}", idx, "mailto: contact missing")

    def test_no_phone_number_anywhere_under_site(self):
        for p in glob.glob(str(SITE / "**" / "*"), recursive=True):
            fp = Path(p)
            if not fp.is_file():
                continue
            try:
                t = fp.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue  # binary asset (png/etc.) — no phone string possible
            self.assertIsNone(PHONE_DIGITS.search(t),
                              f"phone number leaked in {fp.relative_to(REPO_ROOT)}")

    def test_csp_meta_present(self):
        for name in ("index.html", "demo.html"):
            t = _read(SITE / name).lower()
            self.assertIn('http-equiv="content-security-policy"', t,
                          f"CSP meta missing on {name}")
        self.assertIn('name="referrer"', _read(SITE / "index.html").lower(),
                      "referrer meta missing on index.html")

    def test_no_insecure_http_asset_urls(self):
        # Inline HTML5 SVG omits the xmlns namespace, so any http:// here would be a real
        # (mixed-content) asset reference. There should be none.
        for p in HTML_FILES:
            t = _read(p)
            self.assertFalse("http://" in t,
                             f"insecure http:// reference in {Path(p).name}")

    def test_external_blank_links_have_noopener(self):
        link_re = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
        for p in HTML_FILES:
            for tag in link_re.findall(_read(p)):
                if 'target="_blank"' in tag.lower():
                    self.assertIn("noopener", tag.lower(),
                                  f"target=_blank without noopener in {Path(p).name}: {tag}")

    def test_security_txt_present(self):
        sec = SITE / ".well-known" / "security.txt"
        self.assertTrue(sec.exists(), "site/.well-known/security.txt missing")
        body = _read(sec)
        self.assertIn(CONTACT_EMAIL, body, "security.txt missing Contact email")
        self.assertIn("Expires:", body, "security.txt missing Expires")

    def test_pages_workflow_valid_and_deploys_site(self):
        wf = REPO_ROOT / ".github" / "workflows" / "pages.yml"
        self.assertTrue(wf.exists(), "pages.yml missing")
        doc = yaml.safe_load(_read(wf))
        self.assertIsInstance(doc, dict)
        # PyYAML parses the bare `on:` key as boolean True — accept either form.
        triggers = doc.get("on", doc.get(True))
        self.assertIn("push", triggers, "pages.yml does not trigger on push")
        self.assertIn("site/**", triggers["push"]["paths"], "push not scoped to site/**")
        # permissions may be declared workflow-level or per-job — accept either.
        perms = doc.get("permissions") or next(iter(doc["jobs"].values())).get("permissions", {})
        self.assertEqual(perms.get("pages"), "write")
        self.assertEqual(perms.get("id-token"), "write")
        self.assertIn("deploy-pages", _read(wf), "workflow must run actions/deploy-pages")


# ---- launcher Windows branch ------------------------------------------------------------

sys.path.insert(0, str(REPO_ROOT / "desktop"))
import launcher  # noqa: E402  (module under test)


class TestLauncherWindowsBranch(unittest.TestCase):
    def test_is_windows_reflects_os_name(self):
        self.assertFalse(launcher._is_windows())  # this CI host is posix

    def test_kill_pid_uses_taskkill_under_nt(self):
        with mock.patch.object(launcher.os, "name", "nt"), \
             mock.patch.object(launcher.subprocess, "run") as run:
            self.assertTrue(launcher._is_windows(), "os.name=='nt' not detected")
            launcher._kill_pid(4321, hard=True)
        self.assertTrue(run.called, "Windows branch did not shell out")
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "taskkill", f"not the taskkill branch: {argv}")
        self.assertIn("4321", argv)
        self.assertIn("/F", argv)  # hard kill
        self.assertIn("/T", argv)  # whole tree

    def test_kill_pid_uses_signals_under_posix(self):
        with mock.patch.object(launcher.os, "kill") as oskill:
            launcher._kill_pid(4321, hard=False)
        oskill.assert_called_once()
        self.assertEqual(oskill.call_args[0][0], 4321)


if __name__ == "__main__":
    unittest.main(verbosity=2)
