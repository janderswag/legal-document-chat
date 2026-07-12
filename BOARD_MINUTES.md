# BOARD_MINUTES

Newest first.

---

## 2026-07-12 — "We shipped the council's fixes. Now what: connectors, referrals, startup speed, fine-tuning, or attorneys?"

**The question.** The founder asked the board to evaluate yesterday's releases (v0.5.1 + v0.6.0) and rank the next moves before the Fable 5 build window closes July 18: build the "Coming" connectors, improve the referral section, speed up app launch, and decide whether to fine-tune the open-source model. Standing goal: get real attorneys using the free product.

**Positions (one line each).**
- **Commander (Napoleon):** Yesterday was a model strike; the decisive point now is four attorneys using it, and 15 "Coming" connectors is Spain. One front. Deadline: first attorney session before July 18.
- **Engineer (Karpathy):** Fine-tuning is a no on the evidence (verifier-gated architecture, failures are retrieval, qwen3.5:9b swap scored 46/63, no GPU, custom weights break digest pinning); launch is already window-first, so profile before optimizing; the golden gate + verifier IS the moat.
- **Marketer (Hormozi):** Referral polish with zero users is optimizing a funnel nobody is in; the Core Four move is warm outreach to the four prospects this week; the mailto/sms share buttons are fine, they cost an hour, ship them and move on.
- **Analyst (Thiel):** The beachhead is solo/small-firm Mac attorneys with digital matters; the connector list and Windows serve the firm sale the 2026-07-11 council already called premature; distribution is the unanswered question of the seven, and no roadmap item answers it, only the founder can.
- **Guardian (Munger):** Invert: the ways this dies this month are (1) the firm-logo river implying endorsement by real law firms on a zero-user product whose moat is honesty, (2) "being packaged and signed now" Windows copy that overstates reality, (3) spending the window building surface instead of getting users. Fix the honesty gaps first; they are cheap and fatal.
- **Visionary (Jobs):** The product earned "insanely great" on the part that matters (verified citations, honest refusal); the experience gaps are the first hour (10GB download framing) and the last three feet (nobody is sitting next to an attorney yet). Three things only. Kill the rest of the list.

**The Decision.** Stop widening the product. Spend the Fable 5 window converting the four known prospects into live users, and ship only the short list that serves that first session: the honesty patch (logo river + Windows copy + first-run disclosure screen), the referral share buttons (tested in the packaged app), and a measured launch profile before touching startup code. Fine-tuning is rejected. New API connectors are deferred, with one exception: the founder does the 15-minute Microsoft Entra app registration now, because it is free, owner-gated, and unlocks the Outlook build (the queue's #1) if time remains. Synced Drive/Dropbox/OneDrive folders already work today via watched folders; say so in the UI and site instead of building APIs.

**Why.**
1. The evidence says the product is no longer the constraint; distribution is (Analyst, Commander). The council's three tipping blockers all shipped within a day; the golden gate held 63/63; there are zero real users and no pilot roster in the repo.
2. Fine-tuning attacks a component the architecture deliberately does not trust (Engineer). Both known eval failures were retrieval bugs, the smaller-model experiment failed the verifier 46/63, and custom weights would break the pinned-digest supply chain that makes the local install trustworthy.
3. The two cheapest fixes protect the only moat (Guardian). A trust-positioned product showing real firms' logos over "Built for the firms that live in documents," with zero users, risks the exact accusation the whole verifier exists to prevent.

**The Next 3 Moves (this week).**
1. Name the four prospects, contact them today, and book the first hand-held onboarding session (confirm Apple silicon + 16GB + digital matters first). First session held before July 18.
2. Ship the honesty patch: remove or reframe the firm-logo river, correct the Windows "signed now" copy to the truth, and build Sam's first-run disclosure screen (the one open council tipping item).
3. Ship the referral mailto:/sms: buttons with a pre-written message and verify them by clicking in the packaged .app (WKWebView external-scheme handoff is unverified); log a written decision rejecting fine-tuning and pointing quality work at retrieval recall; add a launch-time profile (icon-click to usable) before any startup optimization.

**The Dissent (Commander, joined in part by the Marketer).** The build capability expires July 18; recruiting attorneys does not. Most of the profession is on Windows and Outlook, so the window should also be spent on the Outlook OAuth build and unblocking Windows signing, with attorney outreach running in parallel rather than first. What would change the call: if any of the four prospects turns out to be Windows/Outlook-only, the beachhead itself demands that work, and the board reconvenes.

**Disclosure.** Directors are characters based on the public philosophy of real people (see the board repo's DISCLAIMER.md). This is a thinking tool, not professional advice.
