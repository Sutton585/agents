---
name: "draft-resume"
description: "Drafts a tailored, ATS-optimized resume for a fully evaluated job and packages it into an application file."
---

# draft-resume

---
name: "draft-resume"
description: "Drafts a tailored, ATS-optimized resume for a fully evaluated job and packages it into an application file."
status: proposal
version: "v2"
date: "2026-07-14"
agent: "pm-agent"
---

## Purpose

This skill is the culmination of the job pipeline. It matches verified claims from the `xp-wiki` to the ATS keywords identified during deep evaluation, and formats them into a targeted resume. The output is a complete application package containing the evaluation breakdown, ATS keyword coverage, and the tailored resume draft.

## Execution Trigger

- **Workboard dispatch**: Triggered when a job evaluation child card in Workboard is marked `review` (or user requests drafting).
- Agent: `pm-agent`

## Required Inputs

- `SCHEMA.md` — pipeline structure reference
- The evaluated job file in `pipeline/active/jobs/` (must have `ATS-keywords` and `condensed-JD` populated)
- The user's `xp-wiki/claims/` and `xp-wiki/accomplishments/`
- Resume templates in `/templates/`

## Procedure

### 1. Pre-Flight

1. Claim the Workboard job card via `workboard_claim`.
2. Read the target job listing file in `pipeline/active/jobs/`.
3. Extract the `ATS-keywords` and the `condensed-JD` from the frontmatter.
4. Verify the job has `status: evaluated` — do not draft for unevaluated jobs.

### 2. Template Acquisition

1. Review the available resume templates in `/templates/` and select the most appropriate base template for the job's strategic archetype (`TRADITIONAL_FIT`, `SHORT_TERM_PRIORITIES`, `LONG_TERM_GOALS`).
2. **Critical**: Extract the exact Markdown structure from the fenced code blocks in the template file. The template contains the precise heading levels, blockquote syntax, and section ordering that the downstream CSS/PDF renderer depends on.
   - Blockquote lines (`> `) are used for contact info and section subtitles — these are **not optional formatting**; they are parsed by the CSS stylesheet.
   - Heading levels (`#`, `##`, `###`) must match the template exactly. Do not promote or demote headings.
3. Use the extracted structure as a skeleton. Populate it with targeted content but preserve all structural formatting.

### 3. Resume Targeting (ATS Keyword Mapping)

1. Read the user's `xp-wiki/claims/` and `xp-wiki/accomplishments/`.
2. Perform an **ATS Keyword Mapping**: Attempt to map every required ATS keyword from the job to a verified claim in the `xp-wiki`.
3. Build a coverage table:
   | Required ATS Term | Status | Matching Wiki Claim |
   |---|---|---|
   | Figma | ✅ Covered | `claims/figma` |
   | Kubernetes | ❌ Gap | — |
4. If any ATS keywords remain unmapped (user lacks the verified claim), highlight them prominently.

### 4. Mandatory Consulting Block

If the user's work history contains freelance periods, contract gaps, or parallel engagements:

1. **Synthesize** all freelance/contract/gap work into a single unified "Consulting" block in the experience timeline.
2. Present it as a coherent professional narrative — not a list of disconnected gigs.
3. Frame the consulting period with a unifying theme that connects to the target role's requirements.
4. This block must appear in the correct chronological position in the experience section.

### 5. Enhanced Title Strategy

Maximize ATS keyword density in the resume title/header section:

1. The resume title line should not just be the user's current title — it should be a **keyword-optimized professional headline** that mirrors the target job's language.
2. Include the top 2-3 most critical ATS keywords from the job in the title/subtitle area.
3. Example: Instead of "UX Designer" → "Senior UX Designer | Design Systems & Accessibility Specialist"

### 6. Drafting

1. Generate the tailored resume draft using the template skeleton.
2. Every claim or bullet point **must** be cited using inline footnotes: `^[claims/<skill-name>]` or `^[accomplishments/<star-case>]`.
3. Prioritize bullet points that directly address the `condensed-JD` requirements.
4. Use `workboard_heartbeat` periodically during drafting.

### 7. Output Validation

1. **Wrap the final resume in a markdown fenced code block** (` ```markdown ... ``` `) in the application package. This prevents downstream renderers from interpreting the resume markdown as document structure.
2. Verify all heading levels match the source template.
3. Verify all blockquote lines are preserved.
4. Confirm the consulting block (if applicable) is present and chronologically placed.

### 8. Output Generation (The Application Package)

1. Create a new markdown file in `/applications/` (e.g., `applications/AcmeCorp-UXDesigner.md`).
2. Format this file to contain:
   - **Metadata** (Job link, date, archetype)
   - **Evaluation Breakdown** (scores and rationale from the evaluation step)
   - **ATS Keyword Coverage Table** (Required Term | Status | Matching Wiki Claim)
   - **Tailored Resume Draft** (wrapped in code block)
3. Save the raw markdown resume separately in `/job-docs/resumes/` if requested.
4. Move the source job file from `pipeline/active/jobs/` to `pipeline/archive/jobs/`.

### 9. Workboard State (The Ledger)

1. Complete the workboard card using `workboard_complete` with status `done`.

## Output Artifacts

| Artifact | Location |
|---|---|
| Application package | `/applications/<Company>-<Role>.md` |
| Raw resume (optional) | `/job-docs/resumes/<Company>-<Role>.md` |
| Archived job file | `pipeline/archive/jobs/<job>.md` (moved from `active/`) |
| Workboard card | Status: `done` |

## Error Handling

- If the job file lacks `ATS-keywords` or `condensed-JD`, use `workboard_block` with a message requesting evaluation completion first.
- If no matching template exists for the archetype, use the default/generic template and note the substitution.
- If `xp-wiki` is unavailable, use `workboard_block` — resume drafting requires claim verification.

## State Transitions

```
Job card: review → claimed (workboard_claim)
  → Job file read from pipeline/active/jobs/
  → Template selected and structure extracted
  → ATS keywords mapped to xp-wiki claims
  → Consulting block synthesized (if applicable)
  → Enhanced title constructed
  → Resume drafted with citations
  → Output validated (structure, code block wrapping)
  → Application package written to /applications/
  → Job file moved to pipeline/archive/jobs/
  → workboard_complete (card → done)
```
