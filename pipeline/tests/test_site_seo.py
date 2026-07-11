"""D-61 SEO/GEO/AEO foundation — machine-readable discovery + structured data guards.

Phase A (machine-only, pushed to prod): robots.txt, sitemap.xml, llms.txt / llms-full.txt,
canonical, and JSON-LD (Organization + SoftwareApplication).
Phase B (customer-facing, held for owner approval): Open Graph / Twitter cards + OG image,
the visible FAQ + its FAQPage JSON-LD (visible-content parity), the comparison table, and the
GEO stat in visible copy.

Pure file/string/JSON/XML checks — they never touch the pipeline, verifier, or any store.
"""

import html
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SITE = REPO_ROOT / "site"

APEX = "https://docuchat.app/"
LDJSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def _read(name):
    return (SITE / name).read_text(encoding="utf-8")


def _ldjson_blocks(html):
    """Every <script type=application/ld+json> block, parsed to a dict (raises on bad JSON)."""
    return [json.loads(m) for m in LDJSON_RE.findall(html)]


class TestPhaseAMachineFiles(unittest.TestCase):
    def test_robots_allows_and_points_at_sitemap(self):
        r = _read("robots.txt")
        self.assertRegex(r, r"User-agent:\s*\*")
        self.assertRegex(r, r"Allow:\s*/")
        self.assertIn("Sitemap: https://docuchat.app/sitemap.xml", r)

    def test_robots_welcomes_ai_crawlers(self):
        r = _read("robots.txt")
        for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"):
            self.assertIn(bot, r, f"robots.txt does not name {bot}")

    def test_sitemap_is_valid_xml_with_apex(self):
        root = ET.fromstring(_read("sitemap.xml"))
        self.assertTrue(root.tag.endswith("urlset"), "sitemap root is not <urlset>")
        locs = [e.text for e in root.iter() if e.tag.endswith("loc")]
        self.assertIn(APEX, locs, "sitemap.xml missing the apex URL")

    def test_llms_files_exist(self):
        self.assertTrue((SITE / "llms.txt").is_file(), "site/llms.txt missing")
        self.assertTrue((SITE / "llms-full.txt").is_file(), "site/llms-full.txt missing")
        self.assertTrue(_read("llms.txt").startswith("# docuchat"), "llms.txt missing H1")

    def test_canonical_present(self):
        self.assertIn('<link rel="canonical" href="https://docuchat.app/">', _read("index.html"))

    def test_org_and_softwareapplication_jsonld_present_and_valid(self):
        blocks = _ldjson_blocks(_read("index.html"))
        types = {b.get("@type") for b in blocks}
        self.assertIn("Organization", types, "Organization JSON-LD missing/invalid")
        self.assertIn("SoftwareApplication", types, "SoftwareApplication JSON-LD missing/invalid")
        app = next(b for b in blocks if b.get("@type") == "SoftwareApplication")
        # sanity: the offer is free; downloadUrl is the live DMG (a release artifact
        # shipped at v0.1.0 — the P2.6 pre-release rule flipped); the advertised
        # version must track the app's real version (appversion.py) forever.
        from appversion import APP_VERSION
        self.assertEqual(app["offers"]["price"], "0")
        self.assertIn("github.com/janderswag/docuchat.app/releases/latest/"
                      "download/docuchat.dmg", app["downloadUrl"])
        self.assertEqual(app.get("softwareVersion"), APP_VERSION,
                         "site softwareVersion out of sync with appversion.py")


def _visible_faq(html_text):
    """[(question, answer)] parsed from the visible <details class=faq-item> blocks."""
    pairs = re.findall(
        r'<details class="faq-item[^"]*">\s*<summary>(.*?)</summary>\s*<p>(.*?)</p>',
        html_text, re.DOTALL)
    return [(html.unescape(q).strip(), html.unescape(a).strip()) for q, a in pairs]


def _strip_scripts(html_text):
    """HTML with <script>...</script> blocks removed (approximate 'visible' text)."""
    return re.sub(r"<script.*?</script>", "", html_text, flags=re.DOTALL)


class TestPhaseBCustomerFacing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read("index.html")

    def test_open_graph_and_twitter_present(self):
        for tag in ('property="og:title"', 'property="og:description"', 'property="og:url"',
                    'property="og:type"', 'property="og:image"',
                    'name="twitter:card"', 'name="twitter:title"', 'name="twitter:image"'):
            self.assertIn(tag, self.html, f"missing meta {tag}")
        self.assertIn("assets/og-cover.png", self.html, "OG image not referenced")
        self.assertIn('content="summary_large_image"', self.html)

    def test_og_cover_is_1200x630(self):
        from PIL import Image
        p = SITE / "assets" / "og-cover.png"
        self.assertTrue(p.is_file(), "site/assets/og-cover.png missing")
        self.assertEqual(Image.open(p).size, (1200, 630), "OG image must be 1200x630")

    def test_visible_faq_has_enough_questions(self):
        faq = _visible_faq(self.html)
        self.assertGreaterEqual(len(faq), 8, f"expected >=8 FAQ pairs, got {len(faq)}")

    def test_faqpage_jsonld_matches_visible_faq(self):
        visible = _visible_faq(self.html)
        blocks = _ldjson_blocks(self.html)
        faqpage = next((b for b in blocks if b.get("@type") == "FAQPage"), None)
        self.assertIsNotNone(faqpage, "FAQPage JSON-LD missing")
        ld = [(q["name"].strip(), q["acceptedAnswer"]["text"].strip())
              for q in faqpage["mainEntity"]]
        # Google requires the structured Q&A to match the visible content exactly.
        self.assertEqual(ld, visible, "FAQPage JSON-LD does not match the visible FAQ text")

    def test_comparison_table_present(self):
        self.assertIn('class="compare-table"', self.html, "comparison table missing")
        low = self.html.lower()
        self.assertIn("loopback", low)
        self.assertIn("privilege", low)

    def test_citation_stat_in_visible_copy(self):
        self.assertIn("98.4%", _strip_scripts(self.html),
                      "the 98.4% citation stat must appear in visible on-page copy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
