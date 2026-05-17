# Sustaining Instructions for Building Dashboards in GitHub Pages

**Author:** Claude (working with Vadim Muchnik / Provident Healthcare Consulting)
**Context:** Lessons learned from building the Strive Recovery CTM Call Analytics dashboard at `ProvidentAnalytics/Strive`. These rules exist because we hit each one as a real bug or operational pain point.

---

## 1. Architecture: One Template, One Pipeline, One Output

Every dashboard follows the same three-file structure:

| File | Purpose | Edit it? |
|---|---|---|
| `dashboard_template_v2.html` | The HTML/CSS/JS source of truth. Contains placeholder tokens like `/*INJECT_DAILY*/null` where data goes. | **Yes — this is canonical.** |
| `refresh_dashboard.py` (or named pipeline) | Pulls data from source API → processes → injects into template → writes the output file → pushes to GitHub. Self-contained. | **Yes** — for pipeline logic only. |
| `<sub-folder>/index.html` | The generated, deployed output. Built by the pipeline. | **Never.** Generated artifact. Edits get clobbered. |

**The Golden Rule:** The template is the source of truth. The output is generated. Any change goes into the template, then rebuild.

---

## 2. JavaScript Inside Python: Hard-Won Bug Sources

These rules exist because violating them caused multiple production crashes during the Strive build.

- **NEVER put JS inside a Python f-string.** Brace escaping (`{{`, `}}`) introduces silent bugs. Keep JS as plain HTML in the template, inject only data via `html.replace('/*INJECT_KEY*/null', json_data, 1)`.
- **NEVER nest backtick template literals inside JS.** Use string concatenation instead.
- **NEVER use `onclick="func('value')"` inside template literals.** Use `document.createElement` and assign `.onclick = function() {...}` instead.
- **NEVER reuse `const` variable names across loops in the same function.** Use `let` or rename per iteration.
- **NEVER use `\u0027` in `str_replace` arguments.** Gets written as literal text. Use actual single quotes inside double-quoted strings.
- **ALWAYS run JS through a parser before pushing.** No exceptions. Don't push if anything fails to parse.

---

## 3. Data Pipeline Rules

- **ALWAYS pull from a fixed start date to today** (e.g., `2026-01-01` to today) — never a rolling window. Rolling windows lose history when the calendar advances.
- **ALWAYS exclude test/known-bad records** in the pipeline, not the UI. Maintain an `EXCLUDED` set at the top of the pipeline file. Filter once, in one place, before processing.
- **ALWAYS set HTTP timeouts on API calls.** 30–60 seconds. Wrap external API fetches in `try/except` with retry logic — 3 attempts with backoff.
- **ALWAYS cache raw API responses to disk** (e.g., `ctm_calls_raw.json`). Build a `refresh_cached.py` companion that builds from cache without re-fetching.
- **NEVER commit CTM auth strings, OpenAI keys, or GitHub tokens to the repo.** Store as GitHub Actions secrets and read via `os.environ`.
- **GitHub Contents API returns empty for files >1MB.** Use the Git Blob API (`/git/blobs/{sha}`) instead.
- **ALWAYS verify the live URL after pushing.** Wait 90 seconds for Pages to deploy, then fetch the URL and grep for new feature markers.

---

## 4. The Rogue Process Lesson

**Bug we hit:** Multiple machines/processes had access to the same `GH_TOKEN`, all running their own copy of `refresh_dashboard.py` against their own (sometimes stale) local copy of `dashboard_template_v2.html`. Every hour or so, a "rogue" process pushed an old build that overwrote our changes.

**Sustaining rule:** Treat GitHub Personal Access Tokens like database passwords.

- **Rotate tokens periodically.** Old token must be revoked at https://github.com/settings/tokens, not just replaced.
- **Author identity on commits is the diagnostic.** When changes mysteriously disappear, look at the commit author of the overwriting commit. If it's authored by your GitHub username (not `github-actions[bot]`), there's a process running somewhere with your token.
- **Document where the token is used.** Every machine, GitHub Actions secret, scheduled task, or third-party automation that holds the token needs to be listed.

---

## 5. Cache Prevention (Mobile-Specifically)

Every dashboard template must include from day one:

```html
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate, max-age=0">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
```

Plus a Refresh button that does `window.location.replace(url + '?_v=' + Date.now())`. Plus a periodic check (every 5 min) comparing `BUILD_INFO.refreshed_at` to current time, warning with an amber timestamp if data is older than 90 minutes.

---

## 6. UI/UX Standards (Strive Brand)

- **Light/white background only.** Never dark theme.
- **Brand colors:** Navy `#1B3A6B` (or deeper `#0a3d5c` for analytics dashboards), Sky Blue `#4BBDE8`, accent Teal `#3dffc0`, dark gray text `#2D2D2D`.
- **Fonts:** DM Sans for body, Space Mono for numbers/codes/timestamps.
- **Charts:** Chart.js 4.4.1 from CDN.
- **Filters live in a left side panel on desktop, sticky-top bar on mobile.** Breakpoint at 1024px.
- **Tab navigation must wrap onto two lines on narrow screens.** Use `flex-wrap: wrap`.
- **Reverse-chronological by default.** Newest data on the left of every trending chart, top of every log table.
- **Synced timestamp is full format:** derived from `BUILD_INFO.refreshed_at`, not from `new Date()` at page load.

---

## 7. Build Pipeline Workflow

1. **Pull data** — fetch from source APIs. Handle pagination, retries, timeouts. Save raw to disk.
2. **Process data** — filter exclusions, normalize fields, compute derived metrics.
3. **Score / enrich** — AI scoring or expensive operations. Cache results.
4. **Build dashboard** — read template HTML, replace each `/*INJECT_KEY*/null` placeholder with JSON-stringified data blob.
5. **Push to GitHub** — use Git Blob API for files >1MB.

---

## 8. Adding a New Dashboard to the Hub

1. **New folder** — e.g., `sunwave/`.
2. **New pipeline file** — e.g., `refresh_sunwave.py`.
3. **New template file** — e.g., `dashboard_template_sunwave.html`.
4. **New nightly workflow** — `.github/workflows/nightly-sunwave.yml`.
5. **Reuse hub** — `index.html` (root) is the landing page.
6. **Brand consistency** — same colors, fonts, layout primitives across all dashboards.

---

## 9. Verification Discipline

1. **Brace balance must be zero.** Run the Node parser check.
2. **Wait 90 seconds for Pages to deploy.**
3. **Fetch the live URL with cache-busting.**
4. **Grep for feature markers.**
5. **Check `last-modified` header.** Within the last 2 minutes of your push.
6. **For visual changes**, view on both desktop AND mobile.

---

## 10. The Iteration Pattern

- **Plan in dependency order.** Layout first, then state management, then individual features.
- **Build → verify JS → push → verify live → confirm.** Five steps, every time.
- **Layer changes into existing structure.** Don't rebuild a working tab to add a feature.
- **Use cached data for fast iteration.** Complete pull = 5+ min. Cached rebuild = 30 sec.
- **Trust the user's reports of "it's not working."** Investigate before arguing.

---

## 11. Documentation as You Go

- **`README.md`** — what it does, who uses it, where to find it
- **`PROJECT_BRIEFING.docx`** — same content but exportable
- **CSV/text dump of credentials** — stored in 1Password or SharePoint, NEVER in the repo
- **Comment block at top of pipeline file**

Build the docs WHILE building the dashboard, not after.

---

## 12. Tools & Defaults

**Always available, always preferred:**
- Chart.js 4.4.1, DM Sans + Space Mono, GitHub Actions (4x daily: `0 6,12,16,21 * * *` UTC), Git Blob API for files >1MB.

**Avoid unless justified:**
- React/Vue/Svelte, LocalStorage/SessionStorage, External CSS frameworks, Build tools.

---

## 13. Healthcare-Specific Considerations

- **Never log PHI** in console output, error messages, or webhook bodies.
- **Filtered test data must be auditable.**
- **Access controls live in GitHub.** Document and revisit annually.
- **Data refresh cadence matters operationally.** 4x-daily for staffing decisions.

---

## 14. The Soft Stuff That Saves Time

- **Communicate in stages.** Log all instructions, ask "ready?", then execute in dependency order.
- **Show the plan before the changes.**
- **Confirm assumptions in writing.**
- **The user is right about UX.**
- **Speed of iteration matters more than the perfect first pass.**

---

## Quick-Reference Pre-Push Checklist

Before pushing:
- [ ] JS parses cleanly
- [ ] No literal credentials
- [ ] No JS inside Python f-strings
- [ ] All `/*INJECT_*/null` placeholders matched
- [ ] Pipeline runs end-to-end on test data
- [ ] Light theme, brand colors, full-format synced timestamp
- [ ] Mobile viewport tested

After pushing:
- [ ] Wait 90 seconds for GitHub Pages
- [ ] Fetch live URL with cache-busting
- [ ] Grep for new feature strings
- [ ] Verify `last-modified` header is recent
- [ ] Confirm with user on mobile

---

This document should be saved to the project root as `DASHBOARD_BUILD_GUIDE.md` and referenced at the start of every new dashboard project. Update it whenever a new pattern proves useful or a new bug class emerges.
