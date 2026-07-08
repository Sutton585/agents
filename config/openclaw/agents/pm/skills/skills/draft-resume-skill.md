---
name: draft-resume
description: Automatically drafts a tailored resume for double-promoted jobs by semantically querying the professional experience files.
---

# Draft Resume Skill

This skill takes jobs that have passed all evaluations and drafts an initial, highly-tailored resume. It utilizes the agent's semantic memory to retrieve the most relevant career achievements and skills.

## Instructions

1. **Find Finalists:** Search `raw/.scraped-jobs/` for all files tagged with `#status/promoted-final`.
2. **Read Job Context:** For each finalist job, read its markdown file completely to understand the required skills, keywords, and responsibilities.
3. **Query Experience (Semantic Search):**
   - Use the `memory_search` tool to query your professional experience.
   - Example queries: "Achievements related to [Key Technology from Job]", "Leadership experience matching [Job Requirement]".
   - Since `raw/.scraped-jobs/` is hidden, these queries will strictly return facts from `experience/`, `projects/`, and `claims/`.
4. **Draft Resume:**
   - Compile the retrieved facts into a structured, tailored resume.
   - Ensure the resume aligns with the formatting rules defined in `[[SCHEMA]]`.
5. **Output & Track:**
   - Save the finalized resume draft to a new markdown file in the `applications/` folder (e.g., `applications/Resume-[Company]-[JobTitle].md`).
   - Create an application tracking file in `applications/` (e.g., `applications/App-[Company]-[JobTitle].md`) that includes links to the resume draft and the original job listing.
   - Update the original job file's tag from `#status/promoted-final` to `#status/resume-drafted`.
