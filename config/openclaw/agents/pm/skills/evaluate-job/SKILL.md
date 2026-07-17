---
name: "evaluate-job"
description: "Evaluates job, condenses JD, extracts keywords, scores against pillars, and updates niche tracking."
---

# evaluate-job

---
name: "evaluate-job"
description: "Evaluates job, condenses JD, extracts keywords, scores against pillars, and updates niche tracking."
status: proposal
version: "v2"
date: "2026-07-14"
agent: "analyst-agent"
---

## Purpose

This skill performs a full, rigorous evaluation of a job listing. It reads the raw Job Description text to identify ATS keywords, assigns a strict 1-100 quantitative score, generates qualitative rationale, flags missing professional claims, and feeds learnings back into the niche experiment system.

## Execution Trigger

- **Workboard dispatch**: Triggered when a job evaluation child card in Workboard becomes `todo` or `ready` (after parent report triage completes).
- Agent: `analyst-agent`

## Required Inputs

- `SCHEMA.md` — pipeline structure reference
- The job listing file in `pipeline/active/jobs/`
- The `query_label` from the job's frontmatter
- The parent Niche file (discovered by following the `label` link)
- Full text of all criteria files:
  - `strategy/criteria/criteria-traditional-fit.md`
  - `strategy/criteria/criteria-short-term-priorities.md`
  - `strategy/criteria/criteria-long-term-goals.md`
  - `strategy/criteria/criteria-employer-evaluation.md`
- The user's `xp-wiki` (to check for missing claims)

## Procedure

### 1. Pre-Flight

1. Claim the Workboard job card via `workboard_claim`.
2. Open the job listing file in `pipeline/active/jobs/`.
3. Extract the `query_label` from the frontmatter. Find the parent Niche file matching that label alias.

### 2. Condense JD & ATS Extraction

1. Read the full text of the Job Description.
2. **ATS Keyword Extraction**: Identify required hard skills, tools, and methodologies. Populate the `ATS-keywords` YAML list in the job's frontmatter.
3. **Line-by-Line Condensation**: Convert every requirement sentence into a concise bullet point under the frontmatter key `condensed-JD`. Do not abbreviate keywords — they must remain ATS-scannable.

### 3. Deep Evaluation (Three Pillars)

1. Read the full text of the four criteria files.
2. Score the job **1-100** based on detailed analysis of the full Job Description against the rubrics:
   - **Traditional Fit** — baseline alignment with technical background and compensation
   - **Agency Development (Short-Term Priorities)** — stackable arbitrage potential, remote/async viability
   - **Long-Term Value & Equity** — ownership path, Trojan Horse potential
3. Determine the **Strategic Archetype**: `TRADITIONAL_FIT`, `SHORT_TERM_PRIORITIES`, or `LONG_TERM_GOALS`.
4. Update the job's frontmatter with detailed scores, qualitative rationale, and the chosen archetype.

### 4. Verification & Gap Checking

1. Compare the `ATS-keywords` against the user's `xp-wiki/claims/`.
2. If a required claim is missing:
   - Formulate a targeted interview question for the user to generate that claim.
   - **MUST** call `workboard_block` on this card and provide the question as the block comment so the user can answer it.
3. Use `workboard_heartbeat` periodically during long evaluations.

### 5. Niche Iteration & Feedback Loop (The Scientific Method)

This is the critical learning loop. Every evaluation feeds intelligence back into the niche experiment.

1. Read the parent Niche file.
2. Trace query lineage: the job's `query_label` maps to an alias in the niche's frontmatter. Understand which specific experiment/query produced this result.
3. If the evaluation uncovered recurring employers, interesting titles, or common disqualifiers, update the `## Learning Log` section inside the Niche file.
4. Check the `failure_threshold` in the niche frontmatter. If the niche is failing based on recent activity (e.g., too many low scores, repeated disqualifiers), flag it for the user by creating a `niche_alert` workboard card or noting it when blocking the card.

#### Learning Log Format

Use structured entries in the niche's `## Learning Log`:

**Discoveries** — new patterns, recurring employers, unexpected role types:
```markdown
- **[YYYY-MM-DD] Discovery**: <Company> keeps posting <role type> — potential agency target.
  Query: `<label>` | Job: `<job-id>` | Score: <N>/100
```

**Health / Pivots** — niche health signals, pivot recommendations:
```markdown
- **[YYYY-MM-DD] Health**: Niche producing <N>% sub-40 scores over last <M> runs.
  Recommendation: Tighten query to exclude <pattern> OR pause experiment.
```

**Ideas** — new query ideas spawned by evaluation:
```markdown
- **[YYYY-MM-DD] Idea**: Seeing demand for <skill> at <company type>.
  Proposed query: `"<new search term>"` | Proposed label: `<new-label>`
```

### 6. Workboard State (The Ledger)

1. Update the job frontmatter to `status: evaluated`. The file remains in `pipeline/active/jobs/`.
2. If no questions or missing claims block the job, use `workboard_complete` to advance the card to `review` or `done` so the resume drafting step can begin.
3. If blocked (missing claims), the card stays in `blocked` status until the user provides answers.

## Output Artifacts

| Artifact | Location |
|---|---|
| Updated job file (scores, ATS keywords, condensed JD) | `pipeline/active/jobs/<job>.md` |
| Updated niche Learning Log | `niches/<niche>.md` |
| Workboard card status | `review`/`done` (or `blocked` if gaps found) |
| Niche alert card (if threshold hit) | Workboard (type: `niche_alert`) |

## Error Handling

- If the job listing file is missing from `pipeline/active/jobs/`, use `workboard_block` with descriptive error.
- If the parent niche file cannot be resolved from the label, proceed with evaluation using only the four criteria files. Note the missing niche in the job's frontmatter.
- If `xp-wiki` claims directory is unavailable, skip gap checking and note it in the evaluation rationale. Do not block the card for infrastructure issues.

## State Transitions

```
Job card: todo/ready → claimed (workboard_claim)
  → Job file read from pipeline/active/jobs/
  → JD condensed, ATS keywords extracted
  → Scored 1-100 against Three Pillars criteria
  → xp-wiki claims checked for gaps
  → IF gaps found: workboard_block (card stays blocked)
  → IF no gaps: workboard_complete (card → review/done)
  → Niche Learning Log updated
  → Job frontmatter updated to status: evaluated
```
