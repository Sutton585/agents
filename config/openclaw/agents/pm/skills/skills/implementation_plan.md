# Implementation Plan: Simplified Single-Agent Wiki Setup

This plan outlines a simplified approach to eliminate search pollution while maintaining a single agent (`pm-agent`) and a single, unified wiki (`project-northstar-wiki`). 

By leveraging QMD's behavior of ignoring hidden directories, we can prevent scraped job postings from showing up in semantic memory searches without the overhead of multiple agents or complex directory restructuring.

---

## 1. Directory Structure

We will maintain your single, unified wiki but store scraped job postings in a hidden directory.

### Unified Wiki Layout
**Path**: `/data/vault/project-northstar-wiki`

```text
/data/vault/project-northstar-wiki/
├── SCHEMA.md                # Conventions, schemas, tag taxonomy, and resume rules
├── index.md                 
├── log.md                   
├── raw/                     # Layer 1: Immutable Source Materials
│   ├── background/          # Raw career assets (resumes, CV drafts, spreadsheets)
│   ├── portfolio/           # Website transcripts and bio pages
│   ├── profiles/            # Verbose user-profile.md drafts
│   └── .scraped-jobs/       # Hidden folder for raw job listings. QMD will ignore this folder.
├── criteria/                # Layer 2: Detailed scoring rubrics for the 4 core dimensions
├── niches/                  # Layer 2: Domain-specific job targets
├── experience/              # Layer 2: Curated Roles (Employers & Titles)
├── education/               # Layer 2: Academic History
├── projects/                # Layer 2: Curated STAR Achievements
├── claims/                  # Layer 2: Verifiable Skill & Tech Registry
└── applications/            # Layer 2: Tailored resume outputs and evaluations
```

---

## 2. Agent Configuration (`openclaw.json`)

Since we are using a single agent and a single wiki, your `openclaw.json` configuration can remain simple. The `pm-agent` is pointed to the root of `project-northstar-wiki`.

```json
"memorySearch": {
  "qmd": {
    "extraCollections": [
      {
        "name": "project-northstar-wiki",
        "path": "data/vault/project-northstar-wiki",
        "pattern": "**/*.md"
      }
    ]
  }
}
```

---

## 3. Custom Skill Outlines

The `pm-agent` will be equipped with four core skills to orchestrate this workflow. Here are the templates for these skills:

### Skill 1: `scrape jobs`
* **Trigger/Purpose**: Executed manually or on a scheduled cron job to fetch new opportunities and perform a first-pass triage.
* **Workflow Steps**:
  1. Trigger your external scraping tool.
  2. Parse the output and save individual markdown files to `raw/.scraped-jobs/[Timestamp]-[JobTitle].md`.
  3. Load the general `criteria/` and target `niches/` files.
  4. Perform an **initial evaluation & scoring** of the scraped descriptions.
  5. Identify outliers:
     * **Eliminate**: Mark low-scoring/non-matching jobs as dismissed (tag them as `#status/dismissed` with the reason, e.g., `#reason/tech-mismatch`).
     * **Promote**: Mark high-scoring outliers as promoted (tag them as `#status/promoted-initial`).

### Skill 2: `evaluate jobs`
* **Trigger/Purpose**: Analyzes the initial promoted outliers to run a more rigorous check.
* **Workflow Steps**:
  1. Retrieve all jobs tagged with `#status/promoted-initial` in `raw/.scraped-jobs/`.
  2. Load detailed scoring rubrics from the `criteria/` and `niches/` folders.
  3. Perform a detailed, point-by-point evaluation of the job requirements against your qualifications.
  4. Assign updated detailed scores.
  5. Route the job:
     * **Promote Again**: For exceptionally high-scoring fits, upgrade the tag to `#status/promoted-final` (targets for resume generation).
     * **Keep as Potential**: For decent matches that don't warrant an immediate resume, tag them as `#status/potential` (included in reports but not drafted yet).
     * **Dismiss**: Down-grade to `#status/dismissed` if they fail detailed criteria.

### Skill 3: `draft resume`
* **Trigger/Purpose**: Automatically kicks off when a job is twice-promoted to generate a tailored application.
* **Workflow Steps**:
  1. Retrieve jobs tagged with `#status/promoted-final`.
  2. Read the job description file directly.
  3. Perform a QMD semantic query (`memory_search`) against `professional-exp-wiki` (curated files under `experience/`, `projects/`, and `claims/`) to find matching achievements.
  4. Draft a tailored resume aligned with the job requirements.
  5. Save the resume draft to `applications/[JobName]/resume_draft.md`.
  6. Update the job tag to `#status/resume-drafted`.

### Skill 4: `generate report`
* **Trigger/Purpose**: Compile a comprehensive status report of all activities since the last report.
* **Workflow Steps**:
  1. Gather all files in `raw/.scraped-jobs/` that have been added or updated since the last ledger timestamp.
  2. Group results by **Niche**.
  3. Order the report by importance/promotional status:
     * **Group 1 (Highest Priority)**: Jobs promoted to `#status/resume-drafted` or `#status/promoted-final` (resumes generated or queueing).
     * **Group 2 (Medium Priority)**: Jobs marked as `#status/potential` (matching well, awaiting review).
     * **Group 3 (Dismissed - Bottom)**: Briefly mention dismissed jobs at the bottom, grouped by **Niche** and **Reason for dismissal** (e.g., location, salary, technology).
  4. Write the report to `log.md` (or a dedicated report file) and present it to the user.

---

## 4. Workflow & Access Rules

Because QMD ignores folders starting with `.`, the agent interacts with files differently depending on their location:

### A. Semantic Recall (For Your Experience)
* The agent uses the standard `memory_search` tool (powered by QMD) to retrieve achievements, skills, and work history.
* Because `raw/.scraped-jobs/` is hidden, semantic searches for keywords like "Python" or "Kubernetes" will **only** return matches from your career history. Scraped jobs will not pollute these results.

### B. Direct File Access (For Scraped Jobs)
* When your scraping tool completes, it provides a direct path to the file (e.g., `raw/.scraped-jobs/job-xyz.md`).
* The agent reads the job description directly using standard file tools (`read_file`, `view_file`) instead of QMD.
* If the agent needs to browse recent jobs, it can list the files in `raw/.scraped-jobs/` directly.

---

## 5. Verification Plan

1. **Create Hidden Folder**: Move/configure your scraping tool to output files to `/data/vault/project-northstar-wiki/raw/.scraped-jobs/`.
2. **Verify Separation**:
   - Run a test `memory_search` query for a unique term that exists *only* in one of the scraped jobs.
   - Verify that QMD returns **zero** results (proving the hidden directory is correctly ignored).
   - Run a direct `view_file` on a file in the hidden directory to verify the agent can still read it without issues.
3. **Dry-Run Skills**:
   - Verify the agent can execute the logic of the custom skills in sequence on a mock job posting.
