---
name: "northstar-report"
description: "Daily synthesis of Northstar pipeline activity into a deliverable report with gap-fill, meta-analysis, and Discord delivery."
---

# northstar-report

Daily synthesis and delivery of Project Northstar pipeline activity. This skill is triggered by a cron job once per day (8:30 AM ET). It reads the rolling `next_report.md` ledger, ensures total coverage (no job left unscored), performs strategic meta-analysis, and delivers a polished daily briefing to the user via Discord.

---

## Wiki Locations

All paths are relative to `/data/vault/obsidian/project-northstar-wiki/`.

| Resource | Path | Purpose |
|:---|:---|:---|
| **Schema** | `SCHEMA.md` | Master architecture, archetypes, scoring weights |
| **Next Report Ledger** | `next_report.md` | Rolling input from sweeps — consumed and reset by this skill |
| **Criteria Files** | `ops-wiki/criteria/*.md` | Scoring rubrics for gap-fill evaluations |
| **Niches** | `ops-wiki/niches/*.md` | Niche definitions and search strategies |
| **Claims** | `xp-wiki/claims/*.md` | Verified skill registry (for resume validation) |
| **Search Reports** | `ops-wiki/searches/*.md` | Job-ferret query output reports |
| **Job Listings** | `ops-wiki/jobs/<label>/*.md` | Individual scraped job pages |
| **Applications** | `ops-wiki/applications/*.md` | Promoted jobs with evaluations and resumes |
| **Resumes** | `ops-wiki/job-docs/resumes/` | Resume drafts |
| **Strategy** | `ops-wiki/strategy/` | Search experiment logs and niche notes |
| **Daily Reports** | `ops-wiki/reports/` | Archive of finalized daily reports |
| **Log** | `log.md` | Append-only chronological action log |
| **Index** | `index.md` | Root table of contents |

---

## Execution Stages

This skill runs in three sequential stages within a single cron-triggered session. Each stage must complete before the next begins.

---

### Stage 1: Coverage Audit & Gap-Fill (≈ 30 min)

**Objective:** Ensure every discovered job has been scored. No job should appear in the final report as "unscored."

**Procedure:**

1. Read `next_report.md` to understand what sweeps have logged since the last report.
2. **Full coverage scan:** List ALL job listing files across ALL subdirectories of `ops-wiki/jobs/`.
3. For each job file, check frontmatter:
   - Missing `first_pass: true`? → Score it now using the first-pass procedure from `northstar-sweep` (Priority 3).
   - Has `promoted: true` but missing `deep_eval: true`? → Run the deep evaluation procedure from `northstar-sweep` (Priority 2).
   - Has `deep_eval: true` with overall score ≥ 75 but missing `resume_drafted: true`? → Flag for urgent resume drafting (include in report as "Action Required").
4. Update each gap-filled job's frontmatter with the new scores.
5. Append gap-fill actions to `next_report.md` under a `## Gap-Fill` section.

**Coverage Guarantee:** After Stage 1, every job file in `ops-wiki/jobs/` must have `first_pass: true` in its frontmatter. If time constraints prevent completing all evaluations, the report must explicitly list the remaining unscored jobs with a count and plan.

---

### Stage 2: Report Synthesis (≈ 20 min)

**Objective:** Compile `next_report.md` and the full pipeline state into a polished daily briefing.

**Procedure:**

1. Read `next_report.md` in full.
2. Read the last 50 lines of `log.md` for additional context.
3. Compile the report with the following sections:

#### Report Structure

```markdown
# Northstar Daily Report — YYYY-MM-DD

## Executive Summary
<!-- 3-5 sentence overview: total jobs discovered, scored, promoted, resumes drafted, key findings -->

## Queries Run
<!-- Table: label, niche, search term, result count, date, notable finds -->
| Label | Niche | Search Term | Results | Date | Notes |
|:---|:---|:---|:---|:---|:---|

## Pipeline Status
<!-- Counts and status breakdown -->
- Total jobs in pipeline: X
- Unscored (first_pass missing): X
- First-pass scored: X
- Promoted to deep evaluation: X
- Deep evaluation complete: X
- Resumes drafted: X
- Red-flagged: X

## Noteworthy Jobs
<!-- Detailed cards for every job scoring ≥ 65 overall. Include: -->
For each noteworthy job:
- **Title** at **Company** — Overall: XX/100
- Archetype: TRADITIONAL_FIT / AGENCY_APPROACH / EQUITY_LEVERAGE
- Scores: trad X | agency X | leverage X | employer X | niche X
- Key strengths / concerns
- Resume status: drafted / pending / not yet
- Link: [[job-listing-filename]]

## Resumes Drafted
<!-- List of all resumes created since last report, with links -->

## Employer Intelligence
<!-- Any new or updated employer pages, key findings -->

## Red Flags & Rejections
<!-- Jobs flagged as suspicious, fake, or low-quality. Include reason. -->

## Niche Performance
<!-- For each active niche: -->
For each niche:
- **Niche Name** ([[niche-page]])
  - Queries run (last 7 days): X
  - Average score of results: XX
  - Best result: [[job-link]] (score XX)
  - Trend: improving / declining / stable
  - Recommended action: continue / refine / expand / retire

## Meta-Analysis
<!-- Strategic insights — see Stage 3 -->
```

---

### Stage 3: Meta-Analysis & Strategy Review (≈ 15 min)

**Objective:** Step back and evaluate the effectiveness of the overall search strategy. This is the "detective" pass.

**Procedure:**

1. **Niche Evaluation:**
   - For each active niche, compare the last 7 days of query results against the previous period.
   - Are scores trending up or down? Are we finding more promotable jobs?
   - Should any niche be refined (tighter Boolean queries), expanded (broader terms), or retired (consistently low scores)?
   - Are there patterns in high-scoring jobs that suggest a NEW niche we haven't defined yet?

2. **Query Strategy Evaluation:**
   - Which Boolean search terms are producing the best results?
   - Are exclusion terms (e.g., `-Deloitte`) effectively filtering noise?
   - Is the `distance: 75` radius for Rochester-area searches working, or are we getting too many irrelevant distant results?
   - Should we try different job boards (LinkedIn with proxies, ZipRecruiter)?

3. **Scoring Calibration:**
   - Are the criteria rubrics producing scores that match user intuition? (Check against any user feedback in `next_report.md`.)
   - Are certain dimensions consistently too high or too low?
   - Flag any criteria files that may need updating: link to the specific `[[criteria/score-name]]` page.

4. **Skill Self-Audit:**
   - Is the `northstar-sweep` skill performing well? Any steps that consistently fail or produce poor results?
   - Is the `northstar-report` skill capturing everything? Any sections that are consistently empty?
   - Propose specific improvements to either skill (to be discussed with user before applying).

5. **New Niche Discovery:**
   - Scan the last 7 days of job listings for recurring patterns:
     - Job titles that appear frequently but don't match any existing niche.
     - Companies or industries that keep showing up with high scores.
     - Skills or technologies that are in demand but not well-represented in current niches.
   - Propose up to 3 new niche ideas with rationale.

6. Write the complete meta-analysis as the final section of the report under `## Meta-Analysis`.

---

## Delivery

After all three stages are complete:

1. **Finalize the report file:**
   - Save the completed report as `ops-wiki/reports/YYYY-MM-DD-northstar-report.md`.
2. **Update wiki infrastructure:**
   - Append to `log.md`: `## [YYYY-MM-DD] report | Daily Northstar Report generated and delivered`.
   - Update `index.md` if new pages were created during gap-fill.
3. **Deliver to Discord:**
   - Send the report to the user's Discord PM channel (channel ID: `1512206118372511934`).
   - Message format: A summary of the Executive Summary section, followed by highlights of the top 3 noteworthy jobs, followed by a note about the full report location.
   - If the report is too long for a single Discord message, send the Executive Summary and Noteworthy Jobs as the message body, and attach the full report file.
4. **Reset the ledger:**
   - Create a fresh `next_report.md` with the standard header:
     ```markdown
     # Next Report Ledger

     This file tracks job search activity between daily reports.
     The northstar-report skill reads this file to compile the daily briefing and resets it upon completion.

     ## Activity Log
     <!-- northstar-sweep will append entries below -->
     ```
5. **Archive check:**
   - If `ops-wiki/reports/` contains more than 30 reports, note in `log.md` that archiving may be needed (do not auto-delete).

---

## Error Handling

- **Empty `next_report.md`:** If no sweeps have run since the last report (ledger is empty), still run the coverage audit (Stage 1). If there are unscored jobs, score them and report. If everything is current, generate a brief "No new activity" report and note it in Discord.
- **Incomplete gap-fill:** If Stage 1 cannot complete all evaluations within a reasonable time, list the remaining unscored jobs explicitly in the report under a `## Incomplete Evaluations` section with count and job links.
- **Discord delivery failure:** If the Discord message fails, save the report to `ops-wiki/reports/` anyway and log the delivery failure in `log.md`. Retry on next report cycle.

---

## Relationship to northstar-sweep

This skill **reads** from the same wiki locations that `northstar-sweep` **writes** to. The two skills share state through:

1. **`next_report.md`**: Sweeps append; this skill reads, synthesizes, and resets.
2. **Job listing frontmatter**: Sweeps set `first_pass`, `promoted`, `deep_eval`, `resume_drafted`; this skill audits those flags for coverage.
3. **`log.md`**: Both skills append chronological entries.

The two skills should never run simultaneously. The cron schedule ensures separation:
- `northstar-sweep`: Every 5 hours (e.g., 1:00, 6:00, 11:00, 16:00, 21:00)
- `northstar-report`: Daily at 8:30 AM ET

If a sweep is running at 8:30 AM, the report should wait for it to complete before starting.
