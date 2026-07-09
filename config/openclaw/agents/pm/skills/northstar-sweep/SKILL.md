---
name: "northstar-sweep"
description: "Periodic patrol of the Northstar pipeline. Updated to use report frontmatter for rapid first-pass scoring and enforce niche aliases for query labels."
---

# northstar-sweep

Periodic patrol of the Project Northstar job pipeline. This skill is triggered by a cron job every ~5 hours. Each sweep picks up wherever the last one left off, working through a priority queue of tasks. Not every task runs every sweep—the agent selects the highest-priority incomplete work and processes as many items as time allows.

---

## Wiki Locations

All paths are relative to `/data/vault/obsidian/project-northstar-wiki/`.

| Resource | Path | Purpose |
|:---|:---|:---|
| **Schema** | `SCHEMA.md` | Master architecture, archetypes, tag taxonomy |
| **Criteria: Traditional Fit** | `professional-xp/criteria/trad_score.md` | Career alignment rubric |
| **Criteria: Agency Score** | `professional-xp/criteria/agency_score.md` | Stackability & automation rubric |
| **Criteria: Leverage Score** | `professional-xp/criteria/leverage_score.md` | Strategic career leverage rubric |
| **Criteria: Employer Score** | `professional-xp/criteria/employer_score.md` | Employer sanity & job integrity rubric |
| **Niches** | `professional-xp/niches/*.md` | Niche definitions, search strategies, niche-specific scoring criteria |
| **Claims** | `professional-xp/claims/*.md` | Verified skill & technology registry |
| **Experience** | `professional-xp/experience/*.md` | Curated role history |
| **Accomplishments** | `professional-xp/accomplishments/*.md` | STAR case studies |
| **Evidence** | `professional-xp/evidence/*.md` | Raw CSV/spreadsheet citation sources |
| **Search Reports** | `job-ops/searches/*.md` | Job-ferret query output reports |
| **Job Listings** | `job-ops/jobs/<label>/*.md` | Individual scraped job pages |
| **Applications** | `job-ops/applications/*.md` | Promoted jobs with full evaluations and tailored resumes |
| **Resumes** | `job-ops/resumes/` | Resume drafts and niche templates |
| **Strategy** | `job-ops/strategy/` | Search experiment logs and niche refinement notes |
| **Next Report** | `next_report.md` | Rolling ledger consumed by the daily report skill |
| **Log** | `log.md` | Append-only chronological action log |
| **Index** | `index.md` | Root table of contents |

---

## Orientation Sequence

Before executing any sweep task, the agent must:

1. Read `SCHEMA.md` to confirm current archetypes, scoring weights, and conventions.
2. Read `index.md` to understand the current page catalog.
3. Read the last 30 lines of `log.md` to understand recent operations.
4. Read `next_report.md` to understand what has already been logged for the current reporting cycle.

---

## Priority Queue

Each sweep works through these tasks in descending priority order. The agent picks up the highest-priority incomplete task and works through as many as time allows. After completing each task, append a summary to `next_report.md` and log the action in `log.md`.

### Priority 1: Draft Resumes for Promoted Jobs

**Trigger:** Any job in `job-ops/jobs/` whose frontmatter contains `promoted: true` AND does NOT contain `resume_drafted: true`.

**Procedure:**
1. Read the job's full listing file.
2. Read the relevant niche file from `professional-xp/niches/` (matched via the query label alias).
3. If the niche has a `template_resume` property, read that template from `job-ops/resumes/`.
4. Match the job's required skills against `professional-xp/claims/*.md` to retrieve pre-verified evidence.
5. Match the job's required accomplishments against `professional-xp/accomplishments/*.md` for STAR-formatted case studies.
6. Draft a tailored resume. Every claim or bullet must be cited using wikilink formatting: `[[claims/skill-name]]` or inline footnotes: `^[evidence/Accomplishments.csv#row-N]`.
7. Save the resume draft to `job-ops/resumes/<date>_<company>_<title>.md`.
8. Update the job listing's frontmatter: `resume_drafted: true`, `resume_file: "[[resume-filename]]"`.
9. Create or update the application file in `job-ops/applications/`.
10. Append to `next_report.md`: job title, company, scores, resume file link.

### Priority 2: Deep Evaluation of Promoted Jobs

**Trigger:** Any job in `job-ops/jobs/` whose frontmatter contains `promoted: true` AND does NOT contain `deep_eval: true`.

**Procedure:**
1. Read the individual job listing file and full description.
2. Read ALL four criteria files (`trad_score.md`, `agency_score.md`, `leverage_score.md`, `employer_score.md`).
3. Apply the scoring rubrics in detail, identifying specific modifiers triggered.
4. Apply the niche-specific scoring criteria from the relevant niche file.
5. Calculate the overall score using the weighting formula from `SCHEMA.md`:
   ```
   overall = (0.25 × trad) + (0.25 × agency) + (0.20 × leverage) + (0.15 × employer) + (0.15 × niche)
   ```
6. Determine the strategic archetype (`TRADITIONAL_FIT`, `AGENCY_APPROACH`, `EQUITY_LEVERAGE`, hybrid).
7. Calculate the viability score (1-10).
8. Update the job listing's frontmatter with all scores, rationale, archetype, and viability.
9. Set `deep_eval: true`.
10. Append detailed evaluation summary to `next_report.md`.

### Priority 3: First-Pass Scoring (Rapid Triage via Reports)

**Trigger:** Search reports in `job-ops/searches/` containing job entries in their `results` array that lack a `first_pass` score block.

**Crucial Workflow Note:** Do **not** read individual job listing files for first-pass scoring. Evaluate purely using the summary frontmatter (Duties, Exp, title, compensation) provided inside the search report YAML.

**Procedure:**
1. Read the most recent unscored search reports in `job-ops/searches/`.
2. For each job in the `results` array, estimate a rough score based *only* on the provided summary data:
   - **trad_score (1-10)**: Do the summarized duties/experience match Expert/Proficient claims?
   - **agency_score (1-10)**: Any remote indicators or vague scope? Any immediate red flags (e.g., "fast-paced", "standups")?
   - **leverage_score (1-10)**: Is the title strategic or operational?
   - **employer_score (1-10)**: Known bad employer? Missing compensation? Blank company name?
3. Calculate a preliminary overall score.
4. **Red Flag Detection** — Flag if:
   - Company is known fake/harvesting (Deloitte, Crossover, Revature).
   - "Entry level" title with 5+ years experience required in summary.
   - Company name is generic ("Confidential").
5. **Update the Report File:** Add a `scores` dictionary directly to the job object in the search report's `results` array, including `first_pass: true`, the preliminary sub-scores, the `overall` score, and any `red_flags`.
6. **Promotion Decision:** If `overall ≥ 75` AND no critical red flags, the job is promoted.
   - Open the *individual job listing file* in `job-ops/jobs/<label>/`.
   - Inject `promoted: true` and the preliminary scores into that individual file's frontmatter.
   - (The job now enters the Priority 2 queue for deep evaluation).
7. Unpromoted jobs require no further action. Most scraped jobs will never be opened individually.
8. Append summary to `next_report.md`: count of jobs triaged, count promoted.

### Priority 4: Run a Fresh Query for a Stale Niche

**Trigger:** A niche in `professional-xp/niches/` that has not been queried recently.

**Procedure:**
1. Check the `aliases` frontmatter property on niche files. This property dictates the query labels. (e.g., `aliases: ["figma-rochester", "figma-remote"]`).
2. If an alias hasn't been queried recently, craft an optimized Indeed Boolean query (`"exact phrases"`, `-exclusions`, `(term1 OR term2)`).
3. Call the job-ferret API:
   ```
   POST http://job-ferret-mvp:8000/search
   {
     "label": "<niche-alias-from-frontmatter>",
     "search_term": "<optimized-boolean-query>",
     "location": "Rochester, NY",
     "distance": 75,
     "site_name": ["indeed"],
     "results_wanted": 20,
     "country_indeed": "USA"
   }
   ```
4. Verify the report generated in `job-ops/searches/`.
5. Update the niche file's frontmatter with the latest query date.
6. Append query details to `next_report.md`.

### Priority 5: Re-run a Proven Query

**Trigger:** A query label (alias) that hasn't been run in 3+ days but previously returned high-scoring results.

**Procedure:**
1. Identify the query by reviewing past reports in `job-ops/searches/`.
2. Re-run via API. Log the re-run in `next_report.md`.

### Priority 6: Niche Health Check

**Trigger:** A niche whose recent reports show consistently low average scores (<50).

**Procedure:**
1. Analyze failures: terms too broad? wrong location?
2. Document findings in `job-ops/strategy/`.
3. Propose adding a new alias to the niche file to test a different query label/tactic.
4. Append analysis to `next_report.md`.

### Priority 7: Employer Research

**Trigger:** An employer name appearing in 3+ recent job summaries without a dedicated employer page.

**Procedure:**
1. Create/update page in `job-ops/employers/<company-name>.md`.
2. Research Glassdoor, LinkedIn headcount, corporate registry, funding.
3. Append summary to `next_report.md`.

---

## Coverage Guarantee

Each sweep begins by ensuring no high-value job stalls:
1. Scan `job-ops/searches/` for any report missing `first_pass` evaluations in its `results` array. (Add to Priority 3).
2. Scan individual files in `job-ops/jobs/*/` with `promoted: true` but missing `deep_eval`. (Add to Priority 2).
3. Scan individual files with `deep_eval: true` (score ≥ 75) missing `resume_drafted`. (Add to Priority 1).

---

## Frontmatter Mapping and Aliases

- **Niche Aliases = Query Labels:** The `label` property in a job-ferret search payload MUST exactly match an item in the `aliases` array of the target niche file (e.g., `aliases: ["ai-rochester"]` → API label `"ai-rochester"`). This ensures clicking the label link `[[ai-rochester]]` in Obsidian resolves directly to the niche page containing the strategy history.
- If you need a new query tactic, add a new alias string to the niche file first, then run the search with that label.

---

## Logging & Reporting

After every completed task:
1. **Append to `log.md`**: `## [YYYY-MM-DD] <action> | <subject>`
2. **Append to `next_report.md`**: Structured summary for the daily briefing skill.
3. **Update `index.md`**: If new wiki pages were created.
