# Walkthrough: Simplified Single-Agent Wiki Setup & Skill Integration

This walkthrough details the changes made to structure your unified `Career` wiki and configure your agent workflows to eliminate search pollution.

## Changes Made

### 1. File & Folder Reorganization
We created a hidden folder under `raw/` and moved the existing job directories into it:
* **Created**: `raw/.scraped-jobs/`
* **Moved**: `raw/jobs/` $\rightarrow$ `raw/.scraped-jobs/jobs/`
* **Moved**: `raw/searches/` $\rightarrow$ `raw/.scraped-jobs/searches/`

This ensures QMD's indexing engine automatically ignores the scraped data.

### 2. Schema Documentation
We updated `SCHEMA.md` to reflect the new layout and added instructions on how the agent executes the custom skills:
* Updated the directory tree diagram and templates.
* Documented the new tag taxonomy (such as `#status/promoted-initial`, `#status/promoted-final`, `#status/potential`, `#status/dismissed`).
* Added the **Custom Skills Orchestration** reference section.

### 3. Custom Skill Drafts Created
We drafted the templates for the four core skills to automate the pipeline:
* **`scrape-jobs-skill.md`**: Triggers scrape via API call to `http://job-ferret:3333`, logs query in `next_report.md`, and does first-pass scoring inside the search report's frontmatter.
* **`evaluate-jobs-skill.md`**: Reviews individual job files in `jobs/` above the triage threshold against full criteria text, updating files with detailed scores and rationales.
* **`draft-resume-skill.md`**: Executes QMD semantic search against only your actual experience files to draft tailored resumes for `#status/promoted-final` jobs.
* **`generate-report-skill.md`**: References `next_report.md` to list newly queried niches, highlight finalists with active resume paths, list potential fits, and bury dismissed jobs at the bottom by reason.

---

## Verification Results

* **QMD Path Exclusion**: Verified that by placing raw scrapes under a hidden directory (`raw/.scraped-jobs/`), QMD's recursive indexing will ignore them. This preserves the agent's semantic memory boundaries.
* **Direct File Access**: Confirmed that the agent can read and write files directly within `raw/.scraped-jobs/` via direct paths, even though QMD ignores them.
* **Link Safety**: Moving folders in Obsidian preserves link integrity because filenames are unique and do not rely on absolute directory paths.
