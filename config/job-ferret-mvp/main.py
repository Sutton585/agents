"""
job-ferret-mvp: A lightweight FastAPI service that wraps python-jobspy,
persists query history and job records in SQLite, and generates
interlinked Markdown files (summary reports + individual listings).
"""

import csv
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "jobs.sqlite"
REPORTS_DIR = DATA_DIR / "reports"
LISTINGS_DIR = DATA_DIR / "listings"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("job-ferret")

# Preview section configuration (configurable via Env variables in docker-compose)
PREVIEW_DUTIES = int(os.getenv("PREVIEW_DUTIES", "1"))
PREVIEW_TECH = int(os.getenv("PREVIEW_TECH", "0"))
PREVIEW_EXP = int(os.getenv("PREVIEW_EXP", "2"))

PREVIEW_DUTIES_KEYWORDS = [
    "responsibilities", "key responsibilities", "essential duties", "duties", 
    "what you'll do", "what you will do", "role description", "the role", 
    "job description", "responsabilidade", "aufgaben"
]
PREVIEW_TECH_KEYWORDS = [
    "technologies", "tech stack", "technology", "tools", "languages", 
    "stack", "tecnologias", "architectur"
]
PREVIEW_EXP_KEYWORDS = [
    "qualifications", "experience", "what you bring", "education", 
    "requirements", "about you", "requisits", "anforderungen"
]

# Markdown Sanitization configuration
SANITIZE_MD = os.getenv("SANITIZE_MD", "false").lower() == "true"

# Report verbosity configuration
VERBOSE_REPORT = os.getenv("VERBOSE_REPORT", "false").lower() == "true"

def sanitize_description(text: str) -> str:
    """Default pass-through markdown sanitizer."""
    return text

if SANITIZE_MD:
    try:
        from sanitize_md import sanitize_description as custom_sanitize
        sanitize_description = custom_sanitize
        logger.info("Successfully imported custom sanitize_description from sanitize_md.py")
    except ImportError:
        logger.warning("SANITIZE_MD=true but sanitize_md.py or sanitize_description could not be imported. Using default pass-through.")

# ---------------------------------------------------------------------------
# Database Setup (SQLAlchemy + SQLite)
# ---------------------------------------------------------------------------

Base = declarative_base()


class QueryRun(Base):
    """Tracks every search query executed through the API."""

    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)
    label = Column(String, nullable=False, index=True)
    search_term = Column(String)
    location = Column(String)
    site_names = Column(String)  # Stored as comma-separated string
    results_wanted = Column(Integer)
    results_count = Column(Integer, default=0)
    raw_params = Column(Text)  # Full JSON of all params for auditability
    report_filename = Column(String)  # Relative path to the report markdown

    jobs = relationship("JobRecord", back_populates="query_run")


class JobRecord(Base):
    """Stores individual job postings returned by a query."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True)  # Deterministic hash of site + job_url
    query_id = Column(Integer, ForeignKey("queries.id"), nullable=False)
    site = Column(String)
    title = Column(String)
    company = Column(String)
    company_url = Column(String)
    location = Column(String)
    city = Column(String)
    state = Column(String)
    country = Column(String)
    job_url = Column(String)
    job_type = Column(String)
    is_remote = Column(String)
    description = Column(Text)
    date_posted = Column(String)
    min_amount = Column(String)
    max_amount = Column(String)
    currency = Column(String)
    interval = Column(String)
    scraped_at = Column(String, nullable=False)
    listing_filename = Column(String)  # Relative path to listing markdown

    query_run = relationship("QueryRun", back_populates="jobs")


def _enable_sqlite_fk(dbapi_connection, connection_record):
    """Enable foreign key enforcement for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> sessionmaker:
    """Create the SQLite database engine and return a session factory."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LISTINGS_DIR.mkdir(parents=True, exist_ok=True)

    db_url = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    engine = create_engine(db_url, echo=False)

    # Enable FK support for SQLite
    if "sqlite" in db_url:
        event.listen(engine, "connect", _enable_sqlite_fk)

    Base.metadata.create_all(engine)
    logger.info(f"Database initialized at {db_url}")
    return sessionmaker(bind=engine)


SessionFactory = init_db()

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Request body for the /search endpoint."""

    label: str = Field(
        default="default-scrape",
        description="Custom tag to categorize this query (e.g. 'python-linkedin-only-2026')",
    )
    site_name: Union[List[str], str] = Field(
        default=["indeed"],
        description="Job board(s) to scrape: indeed, linkedin, zip_recruiter, glassdoor, google, bayt, naukri",
    )
    search_term: str = Field(
        ...,
        description="Search keyword (e.g. 'python developer')",
    )
    location: Optional[str] = Field(default=None, description="Job location")
    distance: Optional[int] = Field(default=50, description="Distance in miles")
    results_wanted: Optional[int] = Field(
        default=20, description="Number of results per site"
    )
    hours_old: Optional[int] = Field(
        default=None, description="Filter by hours since posting"
    )
    job_type: Optional[str] = Field(
        default=None,
        description="fulltime, parttime, internship, contract",
    )
    is_remote: Optional[bool] = Field(default=None, description="Remote job filter")
    country_indeed: Optional[str] = Field(
        default="USA", description="Country filter for Indeed & Glassdoor"
    )
    google_search_term: Optional[str] = Field(
        default=None, description="Search term for Google jobs"
    )
    description_format: Optional[str] = Field(
        default="markdown", description="markdown or html"
    )
    linkedin_fetch_description: Optional[bool] = Field(
        default=False, description="Fetch full LinkedIn descriptions (slower)"
    )
    enforce_annual_salary: Optional[bool] = Field(
        default=False, description="Convert wages to annual salary"
    )
    easy_apply: Optional[bool] = Field(
        default=None,
        description="Filter for jobs that can be applied to directly on the platform (works reliably on Indeed only; LinkedIn easy apply filter is broken upstream)",
    )
    linkedin_company_ids: Optional[List[int]] = Field(
        default=None,
        description="List of numeric LinkedIn Company IDs to restrict results to specific employers (e.g. [162474, 1035] for Google and Microsoft)",
    )
    proxies: Optional[List[str]] = Field(
        default=None,
        description="List of proxy addresses in 'user:pass@host:port' or 'host:port' format. Scrapers round-robin through these. Essential for LinkedIn at scale.",
    )
    ca_cert: Optional[str] = Field(
        default=None,
        description="Path to a CA certificate file for proxy TLS verification",
    )
    offset: Optional[int] = Field(
        default=None,
        description="Start the search from this result offset (e.g. 25 skips the first 25 results)",
    )
    save_report: Optional[bool] = Field(
        default=True,
        description="Whether to generate the aggregated report markdown file in /app/data/reports",
    )
    save_listings: Optional[bool] = Field(
        default=True,
        description="Whether to generate individual job listing markdown files in /app/data/listings",
    )
    verbose_report: Optional[bool] = Field(
        default=None,
        description="Whether to include full job descriptions in the report body. Defaults to VERBOSE_REPORT environment variable.",
    )


class SearchResponse(BaseModel):
    """Response body for the /search endpoint."""

    query_id: int
    label: str
    timestamp: str
    count: int
    report_file: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SITES = {
    "indeed",
    "linkedin",
    "zip_recruiter",
    "glassdoor",
    "google",
    "bayt",
    "naukri",
    "bdjobs",
}


def _sanitize_filename(text: str) -> str:
    """Convert arbitrary text to a safe filename component."""
    if not text:
        return "unknown"
    text = re.sub(r"[^\w\s-]", "", str(text).strip())
    text = re.sub(r"[\s]+", "_", text)
    return text[:80].lower()


def _get_short_title(title: str) -> str:
    """Generate a clean, lowercase, underscore-separated title snippet (e.g. first 3 words or max 30 characters)."""
    if not title:
        return "unknown"
    title = re.sub(r"[^\w\s-]", "", str(title).strip())
    words = title.split()[:3]
    snippet = "_".join(words).lower()
    return snippet[:30]


def _get_job_id(native_id: str, site: str, job_url: str) -> str:
    """Return the platform-native job ID provided by jobspy.

    Most scrapers populate the `id` field with a prefixed native ID:
      indeed  -> in-{jk_param}     (e.g. in-f1512e968ecd1c02)
      linkedin -> li-{view_id}     (e.g. li-4296350537)
      ziprecruiter -> zr-{key}     glassdoor -> gd-{listing_id}
      google -> go-{internal}      naukri -> nk-{job_id}

    Bayt and BDJobs use Python's non-deterministic hash(), so we
    fall back to a stable SHA-256 of the URL when the native ID
    is missing or looks like a raw hash integer.
    """
    if native_id and not native_id.lstrip("-").isdigit():
        # Has a native ID with a site prefix — use it directly
        return native_id
    # Fallback: stable hash of site + url (covers Bayt, BDJobs, or missing IDs)
    raw = f"{site}|{job_url or ''}"
    return f"{site[:2]}-{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _safe_str(value: Any) -> str:
    """Convert a value to string, handling NaN/None gracefully."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _yaml_safe(value: Any) -> str:
    """Escape a value for YAML frontmatter by wrapping in double quotes and escaping special characters."""
    s = _safe_str(value)
    if not s:
        return '""'
    # Clean up internal line breaks and multiple spaces for safe single-line YAML values
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r'\s+', ' ', s)
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _obsidian_link_safe(text: str) -> str:
    """Normalize / \ : into _ for Obsidian links."""
    s = _safe_str(text)
    for char in ["/", "\\", ":"]:
        s = s.replace(char, "_")
    return s


def _yaml_obsidian_link(text: str) -> str:
    """Generate a YAML-safe Obsidian link wrapped in single quotes, escaping internal single quotes."""
    normalized = _obsidian_link_safe(text)
    # Clean up internal line breaks/multiple spaces just in case
    normalized = normalized.replace("\n", " ").replace("\r", " ")
    normalized = re.sub(r'\s+', ' ', normalized)
    link = f"[[{normalized}]]"
    escaped = link.replace("'", "''")
    return f"'{escaped}'"


# ---------------------------------------------------------------------------
# Markdown Generation
# ---------------------------------------------------------------------------


def _extract_section_preview(description: str, keywords: List[str], max_items: int) -> List[str]:
    """Extract a list of key bullet points or sentences from a specific section of the job description.
    
    Default logic: Looks for bulleted or numbered lists, finds the last non-blank line preceding
    the list, and checks if it contains any of our key words.
    """
    if max_items <= 0 or not description:
        return []
    
    lines = description.split("\n")
    
    # 1. Identify which lines are list items (start with standard list markers)
    is_list_item = []
    for line in lines:
        s = line.strip()
        # Match standard markdown list markers: "-", "*", "+", or digit followed by dot (e.g. "1.")
        # Must be followed by a space to avoid parsing things like "5+ years" as lists
        match = re.match(r'^([\-\*\+\•]|\d+\.)\s+', s)
        is_list_item.append(bool(match))
        
    # 2. Group consecutive list items into blocks
    list_blocks = []
    in_block = False
    current_block = []
    preceding_line_idx = -1
    
    for idx, is_item in enumerate(is_list_item):
        if is_item:
            if not in_block:
                in_block = True
                current_block = []
                # Find the nearest preceding markdown header
                preceding_line_idx = -1
                fallback_idx = -1
                for p_idx in range(idx - 1, -1, -1):
                    line_strip = lines[p_idx].strip()
                    if line_strip:
                        if fallback_idx == -1:
                            fallback_idx = p_idx  # Keep the first non-blank line as fallback
                        if line_strip.startswith("#"):
                            preceding_line_idx = p_idx
                            break
                            
                # If no header was found, fall back to the immediate preceding non-blank line
                if preceding_line_idx == -1:
                    preceding_line_idx = fallback_idx
            current_block.append(lines[idx])
        else:
            if in_block:
                if preceding_line_idx != -1:
                    list_blocks.append({
                        "preceding_line": lines[preceding_line_idx],
                        "items": current_block
                    })
                in_block = False
                
    # Grab the last block if we hit the end of the text
    if in_block and preceding_line_idx != -1:
        list_blocks.append({
            "preceding_line": lines[preceding_line_idx],
            "items": current_block
        })
        
    # 3. Check preceding lines for keywords
    for block in list_blocks:
        preceding_clean = re.sub(r'[^a-z0-9\s]', '', block["preceding_line"].lower())
        
        matched = False
        for kw in keywords:
            kw_clean = re.sub(r'[^a-z0-9\s]', '', kw.lower())
            if kw_clean in preceding_clean:
                matched = True
                break
                
        if matched:
            extracted = []
            for item in block["items"]:
                item_clean = item.strip()
                # Strip bullet point prefix
                bullet_match = re.match(r'^([\-\*\+\•]|\d+\.)\s+', item_clean)
                if bullet_match:
                    item_clean = item_clean[len(bullet_match.group(0)):]
                # Clean markdown formatting characters
                item_clean = re.sub(r'[\#\*\_`\-\+\[\]\(\)]', ' ', item_clean)
                item_clean = re.sub(r'\s+', ' ', item_clean).strip()
                if item_clean and len(item_clean) > 10:
                    extracted.append(item_clean)
                    
            if extracted:
                final_items = []
                for it in extracted[:max_items]:
                    if len(it) > 200:
                        it = it[:197] + "..."
                    final_items.append(it)
                return final_items
                
    return []


def _make_timestamps(now: datetime) -> dict:
    """Derive all timestamp variants from a single datetime object.

    Returns a dict with:
      display  - human-readable for frontmatter: "2026-07-07 20:34"
      file_date - compact date for filenames: "20260707"
    """
    return {
        "display": now.strftime("%Y-%m-%d %H:%M"),
        "file_date": now.strftime("%Y%m%d"),
    }


def write_listing_file(
    job: Dict[str, str],
    label: str,
    report_filename: str,
    ts: dict,
) -> str:
    """Write an individual job listing markdown file.

    Filename format: {date}_{safe_title}_{job_id}.md
    Returns just the filename (Obsidian resolves it without a path).
    """
    job_id = job["id"]
    label_dir = LISTINGS_DIR / _sanitize_filename(label)
    label_dir.mkdir(parents=True, exist_ok=True)

    safe_employer = _sanitize_filename(job.get("company", "unknown"))
    safe_title = _get_short_title(job.get("title", "untitled"))
    filename = f"{job_id}_{safe_employer}_{safe_title}.md"
    filepath = label_dir / filename

    title = _safe_str(job.get("title", "Untitled"))
    company = _safe_str(job.get("company", "Unknown"))
    site = _safe_str(job.get("site", ""))
    job_url = _safe_str(job.get("job_url", ""))
    date_posted = _safe_str(job.get("date_posted", ""))
    is_remote = _safe_str(job.get("is_remote", ""))
    city = _safe_str(job.get("city", ""))
    state = _safe_str(job.get("state", ""))
    country = _safe_str(job.get("country", ""))
    min_amount = _safe_str(job.get("min_amount", ""))
    max_amount = _safe_str(job.get("max_amount", ""))
    currency = _safe_str(job.get("currency", ""))
    interval = _safe_str(job.get("interval", ""))
    company_url = _safe_str(job.get("company_url", ""))
    description = _safe_str(job.get("description", "No description available."))

    # Generate flat YAML frontmatter
    yaml_lines = [
        "---",
        "type: job-listing",
        f'scraped_at: "{ts["display"]}"',
        f'label: {_yaml_obsidian_link(label)}',
        "query_report:",
        f'  - {_yaml_obsidian_link(report_filename[:-3] if report_filename.endswith(".md") else report_filename)}',
        f'job_id: {_yaml_safe(job_id)}',
        f'title: {_yaml_safe(title)}',
        f'employer: {_yaml_obsidian_link(company)}',
        f'employer_url: {_yaml_safe(company_url)}',
        f'job_url: {_yaml_safe(job_url)}',
        f'date_posted: {_yaml_safe(date_posted)}',
        f'source: {_yaml_safe(site)}',
        f'is_remote: {_yaml_safe(is_remote)}',
        f'city: {_yaml_safe(city)}',
        f'state: {_yaml_safe(state)}',
        f'country: {_yaml_safe(country)}',
        f'min_amount: {_yaml_safe(min_amount)}',
        f'max_amount: {_yaml_safe(max_amount)}',
        f'currency: {_yaml_safe(currency)}',
        f'interval: {_yaml_safe(interval)}',
        "---",
        "## Description",
        "",
        description,
    ]
    content = "\n".join(yaml_lines) + "\n"
    
    filepath.write_text(content, encoding="utf-8")
    logger.debug(f"Wrote listing: {filepath}")
    # Return only the filename — Obsidian resolves wikilinks by name, not path
    return filename


def write_report_file(
    params: Dict[str, Any],
    jobs_list: List[Dict[str, str]],
    label: str,
    ts: dict,
    query_id: int,
    save_listings: bool,
    verbose: bool = False,
) -> str:
    """Write the aggregated query report markdown file.

    Filename format: {date}_{safe_label}_{query_id}.md
    Returns the filename.
    """
    safe_label = _sanitize_filename(label)
    filename = f"{ts['file_date']}_{safe_label}_{query_id}.md"
    filepath = REPORTS_DIR / filename

    # Sites as wikilink list
    site_names_raw = params.get("site_name", [])
    if isinstance(site_names_raw, str):
        site_names_raw = [s.strip() for s in site_names_raw.split(",") if s.strip()]
    sites_yaml = "\n".join([f'  - {_yaml_obsidian_link(s)}' for s in site_names_raw])

    # Search term(s) as wikilink list
    search_term = _safe_str(params.get("search_term", ""))
    search_terms_yaml = f'  - {_yaml_obsidian_link(search_term)}'

    # Results as structured YAML list
    results_yaml_lines = []
    for job in jobs_list:
        lf = job.get("listing_filename")
        if save_listings and lf:
            lf_no_ext = lf[:-3] if lf.endswith(".md") else lf
            results_yaml_lines.append(f"  - {_yaml_obsidian_link(lf_no_ext)}")
        else:
            results_yaml_lines.append(f"  - {_yaml_obsidian_link(job.get('id', ''))}")
    results_yaml = "\n".join(results_yaml_lines) if results_yaml_lines else "  []"

    # Optional fields (only include if present)
    optional_lines = []
    if params.get("location"):
        optional_lines.append(f'location: {_yaml_safe(params["location"])}')
    if params.get("distance") is not None:
        optional_lines.append(f'distance: {params["distance"]}')
    if params.get("results_wanted") is not None:
        optional_lines.append(f'results_wanted: {params["results_wanted"]}')
    if params.get("country_indeed"):
        optional_lines.append(f'country_indeed: {_yaml_safe(params["country_indeed"])}')
    if params.get("hours_old") is not None:
        optional_lines.append(f'hours_old: {params["hours_old"]}')
    if params.get("job_type"):
        optional_lines.append(f'job_type: {_yaml_safe(params["job_type"])}')
    if params.get("is_remote") is not None:
        optional_lines.append(f'is_remote: {params["is_remote"]}')
    if params.get("linkedin_fetch_description"):
        optional_lines.append(f'linkedin_fetch_description: {params["linkedin_fetch_description"]}')
    if params.get("enforce_annual_salary"):
        optional_lines.append(f'enforce_annual_salary: {params["enforce_annual_salary"]}')

    # Build condensed results section
    condensed_results = ["# Condensed Results\n"]
    for job in jobs_list:
        title = _safe_str(job.get("title", "Untitled"))
        company = _safe_str(job.get("company", "Unknown"))
        location = _safe_str(job.get("location", ""))
        job_url = _safe_str(job.get("job_url", ""))
        
        # Build compensation display
        min_amount = job.get("min_amount", "")
        max_amount = job.get("max_amount", "")
        currency = job.get("currency", "")
        interval = job.get("interval", "")
        comp_parts = []
        if min_amount and max_amount:
            comp_parts.append(f"{min_amount} - {max_amount}")
        elif min_amount:
            comp_parts.append(f"From {min_amount}")
        elif max_amount:
            comp_parts.append(f"Up to {max_amount}")
        if currency:
            comp_parts.append(currency)
        if interval:
            comp_parts.append(interval)
        comp_display = " ".join(comp_parts) if comp_parts else "Not specified"
        
        # Extract section previews
        duties_list = _extract_section_preview(job.get("description", ""), PREVIEW_DUTIES_KEYWORDS, PREVIEW_DUTIES)
        tech_list = _extract_section_preview(job.get("description", ""), PREVIEW_TECH_KEYWORDS, PREVIEW_TECH)
        exp_list = _extract_section_preview(job.get("description", ""), PREVIEW_EXP_KEYWORDS, PREVIEW_EXP)

        # Header for this job (e.g. ## [Job Title](listing_filename_without_extension))
        lf = job.get("listing_filename")
        if save_listings and lf:
            lf_no_ext = lf[:-3] if lf.endswith(".md") else lf
            condensed_results.append(f"## [{title}]({lf_no_ext})")
        else:
            condensed_results.append(f"## {title}")
            
        # Apply link blockquote
        if job_url:
            condensed_results.append(f"> [Link]({job_url})")
            
        # Metadata fields
        condensed_results.append(f"Employer: [[{_obsidian_link_safe(company)}]]")
        if location:
            condensed_results.append(f"Location: {location}")
        if comp_display and comp_display != "Not specified":
            condensed_results.append(f"Compensation: {comp_display}")
            
        # Preview lists
        if duties_list:
            condensed_results.append("Duties:")
            for item in duties_list:
                condensed_results.append(f'- "{item}"')
        if tech_list:
            condensed_results.append("Tech:")
            for item in tech_list:
                condensed_results.append(f'- "{item}"')
        if exp_list:
            condensed_results.append("Exp:")
            for item in exp_list:
                condensed_results.append(f'- "{item}"')
                
        # Empty line separating jobs
        condensed_results.append("")

    condensed_body = "\n".join(condensed_results)

    # Build detailed descriptions section if verbose
    if verbose:
        descriptions = []
        for i, job in enumerate(jobs_list, 1):
            title = _safe_str(job.get("title", "Untitled"))
            company = _safe_str(job.get("company", "Unknown"))
            jid = job.get("id", "")
            job_url = _safe_str(job.get("job_url", ""))
            desc = _safe_str(job.get("description", "No description available."))
            descriptions.append(
                f"## {jid}\n"
                f"### {title} at {company}\n\n"
                f"**Apply**: [{job_url}]({job_url})\n\n"
                f"{desc}\n"
            )
        descriptions_body = "\n---\n\n".join(descriptions) if descriptions else "No results."
        detailed_section = f"\n# Full Results\n\n{descriptions_body}\n"
    else:
        detailed_section = ""

    # Assemble query report YAML (flat structure)
    yaml_lines = [
        "---",
        "type: query_report",
        f'date: "{ts["display"]}"',
        f'label: {_yaml_obsidian_link(label)}',
        f'query_id: {query_id}',
        "sites:",
        sites_yaml,
        "search_term:",
        search_terms_yaml,
    ]
    if optional_lines:
        yaml_lines.extend(optional_lines)
    yaml_lines.extend([
        "results:",
        results_yaml,
        "---",
        "",
        condensed_body.strip(),
    ])
    content = "\n".join(yaml_lines) + "\n"

    if verbose and detailed_section:
        content += f"\n{detailed_section.strip()}\n"
        
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Wrote report: {filepath}")
    return filename


# ---------------------------------------------------------------------------
# Database Persistence
# ---------------------------------------------------------------------------


def persist_results(
    session: Session,
    params: Dict[str, Any],
    jobs_df: pd.DataFrame,
    label: str,
    ts: dict,
    save_report: bool,
    save_listings: bool,
    verbose_report: bool,
) -> tuple:
    """Save the query run and job records to SQLite. Generate Markdown files.

    Returns (query_id, jobs_list_with_filenames, report_filename).
    """
    # Normalize site_name for storage
    site_names_raw = params.get("site_name", [])
    if isinstance(site_names_raw, list):
        site_names_str = ",".join(site_names_raw)
    else:
        site_names_str = str(site_names_raw)

    # Create query run record and flush to get the auto-incremented ID
    # We need the ID upfront to build the report filename before writing listings.
    query_run = QueryRun(
        timestamp=ts["display"],
        label=label,
        search_term=params.get("search_term"),
        location=params.get("location"),
        site_names=site_names_str,
        results_wanted=params.get("results_wanted"),
        results_count=len(jobs_df),
        raw_params=json.dumps(params, default=str),
        report_filename="",  # Filled in after file is written
    )
    session.add(query_run)
    session.flush()  # Assigns query_run.id

    # Now we can compute the report filename deterministically
    safe_label = _sanitize_filename(label)
    report_filename = f"{ts['file_date']}_{safe_label}_{query_run.id}.md"

    # Process each job: build dicts, write listing files, insert DB records
    jobs_list = []
    for _, row in jobs_df.iterrows():
        site = _safe_str(row.get("site", ""))
        job_url = _safe_str(row.get("job_url", ""))
        title = _safe_str(row.get("title", ""))
        native_id = _safe_str(row.get("id", ""))
        job_id = _get_job_id(native_id, site, job_url)

        # Retrieve description and apply markdown header sanitization first (if enabled)
        raw_description = _safe_str(row.get("description", ""))
        sanitized_description = sanitize_description(raw_description)

        job_dict = {
            "id": job_id,
            "site": site,
            "title": title,
            "company": _safe_str(row.get("company", "")),
            "company_url": _safe_str(row.get("company_url", "")),
            "location": _safe_str(row.get("location", "")),
            "city": _safe_str(row.get("city", "")),
            "state": _safe_str(row.get("state", "")),
            "country": _safe_str(row.get("country", "")),
            "job_url": job_url,
            "job_type": _safe_str(row.get("job_type", "")),
            "is_remote": _safe_str(row.get("is_remote", "")),
            "description": sanitized_description,
            "date_posted": _safe_str(row.get("date_posted", "")),
            "min_amount": _safe_str(row.get("min_amount", "")),
            "max_amount": _safe_str(row.get("max_amount", "")),
            "currency": _safe_str(row.get("currency", "")),
            "interval": _safe_str(row.get("interval", "")),
        }

        # Write individual listing file — pass the already-known report filename
        if save_listings:
            listing_filename = write_listing_file(job_dict, label, report_filename, ts)
        else:
            listing_filename = ""
        job_dict["listing_filename"] = listing_filename

        # Insert or update job record in SQLite
        existing = session.get(JobRecord, job_id)
        if existing:
            existing.query_id = query_run.id
            existing.scraped_at = ts["display"]
            existing.listing_filename = listing_filename
        else:
            job_record = JobRecord(
                id=job_id,
                query_id=query_run.id,
                site=job_dict["site"],
                title=job_dict["title"],
                company=job_dict["company"],
                company_url=job_dict["company_url"],
                location=job_dict["location"],
                city=job_dict["city"],
                state=job_dict["state"],
                country=job_dict["country"],
                job_url=job_dict["job_url"],
                job_type=job_dict["job_type"],
                is_remote=job_dict["is_remote"],
                description=job_dict["description"],
                date_posted=job_dict["date_posted"],
                min_amount=job_dict["min_amount"],
                max_amount=job_dict["max_amount"],
                currency=job_dict["currency"],
                interval=job_dict["interval"],
                scraped_at=ts["display"],
                listing_filename=listing_filename,
            )
            session.add(job_record)

        jobs_list.append(job_dict)

    # Write the aggregated report now that all listing filenames are known
    if save_report:
        actual_report_filename = write_report_file(
            params, jobs_list, label, ts, query_run.id, save_listings, verbose_report
        )
    else:
        actual_report_filename = ""
        
    query_run.report_filename = actual_report_filename

    session.commit()
    logger.info(
        f"Persisted query #{query_run.id} with {len(jobs_list)} jobs (label={label})"
    )
    return query_run.id, jobs_list, actual_report_filename


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Job Ferret MVP",
    description="A lightweight job scraping API that persists results to SQLite and generates interlinked Markdown files.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "job-ferret-mvp"}


@app.get("/")
def root():
    """Welcome endpoint with basic API info."""
    return {
        "service": "job-ferret-mvp",
        "version": "0.1.0",
        "endpoints": {
            "POST /search": "Run a job search query",
            "GET /queries": "List past query runs",
            "GET /health": "Health check",
        },
    }


@app.get("/queries")
def list_queries(limit: int = 20):
    """List recent query runs stored in the database."""
    session = SessionFactory()
    try:
        runs = (
            session.query(QueryRun)
            .order_by(QueryRun.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "count": len(runs),
            "queries": [
                {
                    "id": r.id,
                    "timestamp": r.timestamp,
                    "label": r.label,
                    "search_term": r.search_term,
                    "location": r.location,
                    "site_names": r.site_names,
                    "results_count": r.results_count,
                    "report_filename": r.report_filename,
                }
                for r in runs
            ],
        }
    finally:
        session.close()


@app.post("/search", response_model=SearchResponse)
def search_jobs(req: SearchRequest):
    """Execute a job search, persist results to SQLite, and generate Markdown files."""
    from jobspy import scrape_jobs

    # Use local time — respects TZ environment variable set in docker-compose
    now = datetime.now()
    ts = _make_timestamps(now)

    # Normalize site_name to a list
    site_names = req.site_name if isinstance(req.site_name, list) else [req.site_name]
    invalid = [s for s in site_names if s not in VALID_SITES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid site name(s)",
                "invalid": invalid,
                "valid_sites": sorted(VALID_SITES),
            },
        )

    # Build the scraper parameters dict (only pass non-None values)
    scraper_params: Dict[str, Any] = {
        "site_name": site_names,
        "search_term": req.search_term,
        "description_format": "markdown",  # Always markdown
    }
    if req.location is not None:
        scraper_params["location"] = req.location
    if req.distance is not None:
        scraper_params["distance"] = req.distance
    if req.results_wanted is not None:
        scraper_params["results_wanted"] = req.results_wanted
    if req.hours_old is not None:
        scraper_params["hours_old"] = req.hours_old
    if req.job_type is not None:
        scraper_params["job_type"] = req.job_type
    if req.is_remote is not None:
        scraper_params["is_remote"] = req.is_remote
    if req.country_indeed is not None:
        scraper_params["country_indeed"] = req.country_indeed
    if req.google_search_term is not None:
        scraper_params["google_search_term"] = req.google_search_term
    if req.linkedin_fetch_description is not None:
        scraper_params["linkedin_fetch_description"] = req.linkedin_fetch_description
    if req.enforce_annual_salary is not None:
        scraper_params["enforce_annual_salary"] = req.enforce_annual_salary
    if req.easy_apply is not None:
        scraper_params["easy_apply"] = req.easy_apply
    if req.linkedin_company_ids is not None:
        scraper_params["linkedin_company_ids"] = req.linkedin_company_ids
    if req.proxies is not None:
        scraper_params["proxies"] = req.proxies
    if req.ca_cert is not None:
        scraper_params["ca_cert"] = req.ca_cert
    if req.offset is not None:
        scraper_params["offset"] = req.offset

    logger.info(f"Starting search: label={req.label}, params={scraper_params}")

    try:
        jobs_df = scrape_jobs(**scraper_params)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Scraping failed",
                "message": str(e),
                "suggestion": "Try fewer sites, simpler queries, or adding proxies.",
            },
        )

    logger.info(f"Scrape returned {len(jobs_df)} jobs")

    # Persist to SQLite and generate Markdown
    session = SessionFactory()
    try:
        # Keep site_name as a list in params (write_report_file handles both)
        full_params = {**scraper_params, "label": req.label}

        verbose = req.verbose_report if req.verbose_report is not None else VERBOSE_REPORT
        query_id, jobs_list, report_filename = persist_results(
            session, full_params, jobs_df, req.label, ts, req.save_report, req.save_listings, verbose
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Persistence failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to save results", "message": str(e)},
        )
    finally:
        session.close()

    return SearchResponse(
        query_id=query_id,
        label=req.label,
        timestamp=ts["display"],
        count=len(jobs_list),
        report_file=f"reports/{report_filename}" if req.save_report else "",
    )
