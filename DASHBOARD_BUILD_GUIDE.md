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
- **ALWAYS run JS through a parser before pushing.** Use Node:
  ```bash
  node -e "const html=require('fs').readFileSync('template.html','utf-8'); const m=html.match(/<script>([\\s\\S]*?)<\\/script>/g); m.forEach(b=>{const js=b.replace(/<\\/?script>/g,'').replace(/\\/\\*INJECT_\\w+\\*\\/null/g,'null'); try{new Function(js); console.log('OK')}catch(e){console.log('ERR:',e.message)}});"
  ```
  No exceptions. Don't push if anything fails to parse.

---

## 3. Data Pipeline Rules

- **ALWAYS pull from a fixed start date to today** (e.g., `2026-01-01` to today) — never a rolling window. Rolling windows lose history when the calendar advances.
- **ALWAYS exclude test/known-bad records** in the pipeline, not the UI. Maintain an `EXCLUDED` set at the top of the pipeline file. Filter once, in one place, before processing. Never let the UI try to filter test data — the user shouldn't have to know what's a test.
- **ALWAYS set HTTP timeouts on API calls.** 30–60 seconds. Without them, a hung connection halts the whole pipeline. Wrap external API fetches in `try/except` with retry logic — 3 attempts with backoff.
- **ALWAYS cache raw API responses to disk** (e.g., `ctm_calls_raw.json`). Build a `refresh_cached.py` companion that builds from cache without re-fetching. This makes iteration fast (seconds) instead of slow (5+ minutes per pull).
- **NEVER commit CTM auth strings, OpenAI keys, or GitHub tokens to the repo.** Store as GitHub Actions secrets and read via `os.environ`. The committed Python file should reference `os.environ['CTM_AUTH']`, never a literal value.
- **GitHub Contents API returns empty for files >1MB.** Use the Git Blob API (`/git/blobs/{sha}`) instead. Most dashboards exceed 1MB once data is injected — plan for this from day one.
- **ALWAYS verify the live URL after pushing.** Don't assume deployment worked. Wait 90 seconds for Pages to deploy, then fetch the URL and grep for new feature markers. Build size and feature presence checks both matter.

---

## 4. The Rogue Process Lesson

**Bug we hit:** Multiple machines/processes had access to the same `GH_TOKEN`, all running their own copy of `refresh_dashboard.py` against their own (sometimes stale) local copy of `dashboard_template_v2.html`. Every hour or so, a "rogue" process pushed an old build that overwrote our changes.

**Sustaining rule:** Treat GitHub Personal Access Tokens like database passwords.

- **Rotate tokens periodically.** When a token has been used by multiple sessions or shared with anyone, rotate it. Old token must be revoked at https://github.com/settings/tokens, not just replaced.
- **Author identity on commits is the diagnostic.** When changes mysteriously disappear, look at the commit author of the overwriting commit. If it's authored by your GitHub username (not `github-actions[bot]`), there's a process running somewhere with your token. If it's authored by `github-actions[bot]`, the legitimate scheduled workflow is running and you need to fix that workflow's source files.
- **Document where the token is used.** Every machine, GitHub Actions secret, scheduled task, or third-party automation that holds the token needs to be listed. When you rotate, update each one.

---

## 5. Cache Prevention (Mobile-Specifically)

**Bug we hit:** New build deployed, browser kept showing old data. Mobile browsers especially aggressive about caching `text/html`.

**Sustaining rule:** Every dashboard template must include from day one:

```html
<head>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate, max-age=0">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
```

Plus a Refresh button that does `window.location.replace(url + '?_v=' + Date.now())` — not just a UI animation. Plus a periodic check (every 5 min) that compares `BUILD_INFO.refreshed_at` to current time and warns the user with an amber timestamp if data is older than 90 minutes.

This is a one-time setup that prevents an entire class of "the data isn't fresh" tickets.

---

## 6. UI/UX Standards (Strive Brand)

For Provident Healthcare Consulting dashboards, these are non-negotiable:

- **Light/white background only.** Never dark theme. Sticky in `userMemories`.
- **Brand colors:** Navy `#1B3A6B` (or deeper `#0a3d5c` for analytics dashboards), Sky Blue `#4BBDE8`, accent Teal `#3dffc0`, dark gray text `#2D2D2D`.
- **Fonts:** DM Sans for body and labels, Space Mono for numbers/codes/timestamps.
- **Charts:** Chart.js 4.4.1 from CDN. Don't pull in heavier libraries unless there's a specific need.
- **Filters live in a left side panel on desktop, sticky-top bar on mobile.** Breakpoint at 1024px. Users should never have to scroll up to change a filter.
- **Tab navigation must wrap onto two lines on narrow screens.** Use `flex-wrap: wrap` — never let the user need horizontal scrolling for tabs.
- **Reverse-chronological by default.** Newest data on the left of every trending chart, top of every log table. People read left-to-right, top-to-bottom; today is the most relevant.
- **Synced timestamp is full format:** "Synced: Monday, May 4, 2026 · 12:38 PM" — derived from `BUILD_INFO.refreshed_at`, not from `new Date()` at page load.

---

## 7. Build Pipeline Workflow

The repeatable, proven sequence:

1. **Pull data** — fetch from source APIs (CTM, Sunwave, etc.). Handle pagination, retries, timeouts. Save raw response to disk for cache.
2. **Process data** — filter exclusions, normalize fields, compute derived metrics. One function per output blob (daily aggregates, log records, recordings, etc.).
3. **Score / enrich** — if AI scoring or other expensive operations apply, do them here. Cache results so re-scoring is incremental, not full-batch.
4. **Build dashboard** — read the template HTML, replace each `/*INJECT_KEY*/null` placeholder with the JSON-stringified data blob. One injection per data domain.
5. **Push to GitHub** — use Git Blob API for files >1MB. Commit message format: `Auto-refresh: {timestamp} ({calls_count} calls, {scored_count} scored)`. Use `committer.name = "github-actions[bot]"` if running from Actions, your name otherwise.

For a new dashboard, follow this exact sequence. Don't try to do step 4 inline with step 1.

---

## 8. Adding a New Dashboard to the Hub

When building a second dashboard (e.g., Sunwave):

1. **New folder** — e.g., `sunwave/`. Generated output goes in `sunwave/index.html`. Never share folders between dashboards.
2. **New pipeline file** — e.g., `pull_sunwave.py`, `refresh_sunwave.py`. Don't bolt onto the existing pipeline.
3. **New template file** — e.g., `dashboard_template_sunwave.html`. The CTM template is for CTM. Each dashboard owns its template.
4. **New nightly workflow** — `.github/workflows/nightly-sunwave.yml`. Each dashboard has its own scheduled refresh. Don't chain them in one workflow.
5. **Reuse hub** — `index.html` (root) is the landing page with cards linking to each dashboard. Add a card when a new dashboard ships.
6. **Brand consistency** — same colors, fonts, layout primitives across all dashboards. Users should feel the family resemblance immediately.

---

## 9. Verification Discipline

After every push, before declaring a feature "live":

1. **Brace balance must be zero.** Run the Node parser check from Section 2.
2. **Wait 90 seconds for Pages to deploy.** GitHub doesn't deploy instantly.
3. **Fetch the live URL with cache-busting.** Use `?nocache={timestamp}` and a `Cache-Control: no-cache` header.
4. **Grep for feature markers.** Test for the presence of new code (function names, CSS class names, specific strings). Don't trust that a successful push means a successful deploy.
5. **Check `last-modified` header.** It should be within the last 2 minutes of your push.
6. **For visual changes**, view on both desktop AND mobile. Mobile is the primary review device for this team — design failures show up there first.

---

## 10. The Iteration Pattern

For complex artifacts like dashboards:

- **Plan in dependency order.** Layout first (defines skeleton), then state management (filters), then individual features. Don't jump between layers.
- **Build → verify JS → push → verify live → confirm.** Five steps, every time. Skipping verification creates compounding bugs that are hard to trace.
- **Layer changes into existing structure.** Don't rebuild a working tab to add a feature. Insert into the existing pattern. Document consistency matters more than aesthetic perfection.
- **Use cached data for fast iteration.** A complete CTM pull takes 5+ minutes. A cached rebuild takes 30 seconds. Always have both pipelines available.
- **Trust the user's reports of "it's not working."** When the user says they don't see a change, don't argue — investigate. Start with: live URL fetch + grep for feature markers + `last-modified` header. Diagnose before re-pushing.

---

## 11. Documentation as You Go

Every dashboard repo should contain, by the time it's "complete":

- **`README.md`** — what it does, who uses it, where to find it
- **`PROJECT_BRIEFING.docx`** — same content but exportable for stakeholders (the analytics briefing pattern from the Strive build)
- **CSV/text dump of credentials and access** — stored in 1Password or SharePoint, NEVER in the repo
- **Comment block at top of pipeline file** — describing data sources, refresh schedule, known limitations

Build the docs WHILE building the dashboard, not after. After never happens.

---

## 12. Tools & Defaults

**Always available, always preferred:**
- **Chart.js 4.4.1** for visualizations
- **DM Sans + Space Mono** for typography
- **GitHub Actions** for scheduled refreshes (4x daily is the proven cadence: `0 6,12,16,21 * * *` UTC)
- **Git Blob API** for files >1MB

**Avoid unless justified:**
- React/Vue/Svelte for these dashboards. Plain HTML+JS is faster to iterate, easier to debug, and the rendered output is immediately readable.
- LocalStorage/SessionStorage for state. Use URL query params or in-memory state. Storage adds complexity and persistence bugs across browser tabs.
- External CSS frameworks (Bootstrap, Tailwind). Custom CSS is ~5 KB, framework imports are 100+ KB.
- Build tools (webpack, vite). Add complexity for no value at this scale.

---

## 13. Healthcare-Specific Considerations

This is operational tooling for HIPAA-regulated environments:

- **Never log PHI** in console output, error messages, or webhook bodies. If transcripts contain caller names/phones, redact in logs even if they're shown in the UI.
- **Filtered test data must be auditable.** Maintain a list of excluded numbers in code (with comments explaining why each is excluded).
- **Access controls live in GitHub.** Repository visibility (private vs public), Pages visibility, who has push access. Document these decisions and revisit annually.
- **Data refresh cadence matters operationally.** A 4x-daily refresh is the right cadence for staffing decisions. A 1x-daily refresh is wrong for a call center because morning decisions need afternoon data.

---

## 14. The Soft Stuff That Saves Time

- **Communicate in stages.** When the user says "do A, B, C, D, E, F" — log all of them, ask "ready?", then execute in dependency order. Don't auto-execute at the first instruction.
- **Show the plan before the changes.** For non-trivial work, summarize the diff in plain language before writing it. The user catches mistakes faster than the code does.
- **Confirm assumptions in writing.** When unclear ("does this also affect outbound calls?"), ask in a single targeted question. Don't make undocumented decisions.
- **The user is right about UX.** When they say "the filter should be on the left," that's a real workflow constraint. Don't argue with the form factor — fix it.
- **Speed of iteration matters more than the perfect first pass.** A working v1 that the user can react to beats a thought-through v2 that takes 3x as long.

---

## Quick-Reference Pre-Push Checklist

Before pushing any dashboard change to `main`:

- [ ] JS parses cleanly (Node `new Function()` test passes)
- [ ] No literal credentials in committed files
- [ ] No JS inside Python f-strings
- [ ] All `/*INJECT_*/null` placeholders are matched in the pipeline's `data_blobs` dict
- [ ] Pipeline runs end-to-end against a test data subset without errors
- [ ] Generated output file size is reasonable (single-digit to mid-double-digit MB)
- [ ] Light theme, brand colors, full-format synced timestamp present
- [ ] Mobile viewport tested (or at least viewport meta tag and responsive CSS in place)

After pushing:

- [ ] Wait 90 seconds for GitHub Pages
- [ ] Fetch live URL with cache-busting
- [ ] Grep for new feature strings
- [ ] Verify `last-modified` header is recent
- [ ] Confirm with user on their preferred device (mobile first)

---

This document should be saved to the project root as `DASHBOARD_BUILD_GUIDE.md` and referenced at the start of every new dashboard project. Update it whenever a new pattern proves useful or a new bug class emerges.
