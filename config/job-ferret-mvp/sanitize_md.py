import unicodedata
import re
import html
import logging

logger = logging.getLogger("sanitize_md")
logger.setLevel(logging.INFO)

STANDARDIZE_BULLET_LISTS = True    # Converts * or + bullets to hyphen -
REMOVE_BOLD_FROM_LISTS = True      # Converts "- **Bold**" to "- Bold"
REMOVE_ITALIC_FROM_LISTS = True    # Converts "- *Italic*" to "- Italic"

# --- Header Detection Thresholds ---
# ALL CAPS lines shorter than MIN or longer than MAX won't be promoted to headers.
MIN_ALL_CAPS_HEADER_LEN = 5
MAX_ALL_CAPS_HEADER_LEN = 60
# Lines ending in punctuation shorter than this threshold get promoted to headers.
MAX_PUNCT_HEADER_LEN = 60
# Structural context: plain short lines flanked by long text are promoted.
MAX_STRUCTURAL_HEADER_LEN = 36
MIN_FLANKING_LINE_LEN = 70


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def is_all_caps(line: str) -> bool:
    stripped = line.strip()

    # Exclude if empty
    if not stripped:
        return False

    # Exclude if already formatted as markdown
    if stripped.startswith("#"):
        return False

    # Exclude if contains 'chapter' (case-insensitive)
    if "chapter" in stripped.lower():
        return False

    # Exclude if contains '|'
    if "|" in stripped:
        return False

    # Must be within length bounds to be considered a header
    if len(stripped) < MIN_ALL_CAPS_HEADER_LEN:
        return False
    if len(stripped) > MAX_ALL_CAPS_HEADER_LEN:
        return False

    # Must contain only uppercase letters or non-letter symbols
    return all(c.isupper() or not c.isalpha() for c in stripped)


def decode_unicode_escapes(text: str) -> str:
    def repl(match):
        try:
            return bytes(match.group(0), 'utf-8').decode('unicode_escape')
        except Exception:
            return match.group(0)  # Return as-is if decoding fails
    return re.sub(r'\\u[0-9a-fA-F]{4}', repl, text)


def _extract_code_blocks(text: str) -> tuple[str, list[str]]:
    """Extract markdown code blocks and replace them with placeholders."""
    code_blocks = []
    def replacer(match):
        code_blocks.append(match.group(0))
        return f"___CODE_BLOCK_{len(code_blocks)-1}___"
    
    text = re.sub(r'(?s)```.*?```', replacer, text)
    return text, code_blocks


def _restore_code_blocks(text: str, code_blocks: list[str]) -> str:
    """Restore extracted code blocks from placeholders."""
    for i, block in enumerate(code_blocks):
        text = text.replace(f"___CODE_BLOCK_{i}___", block)
    return text


def _strip_formatting(line: str) -> str:
    """Strip outer Markdown formatting (bold, italic, bold-italic) from a line.

    Examples:
        '**Requirements:**' -> 'Requirements:'
        '*Physical Requirements:*' -> 'Physical Requirements:'
        '***Important***' -> 'Important'
        '_Underline Title_' -> 'Underline Title'
    """
    s = line.strip()
    # Bold-italic (*** or ___) 
    m = re.match(r'^(\*{3}|_{3})(.+?)\1$', s)
    if m:
        return m.group(2).strip()
    # Bold (** or __)
    m = re.match(r'^(\*{2}|_{2})(.+?)\1$', s)
    if m:
        return m.group(2).strip()
    # Italic (* or _) — single marker
    m = re.match(r'^(\*|_)(.+?)\1$', s)
    if m:
        return m.group(2).strip()
    return s


def _is_list_item(line: str) -> bool:
    """Check if a line is a bullet or numbered list item."""
    return bool(re.match(r'^\s*([\-\*\+\•]|\d+\.)\s+', line))


def _is_pseudo_header(line: str, above_blank: bool, lines: list, idx: int) -> bool:
    """Determine if a non-header line should be promoted to a header.

    Evaluates four rules against a formatting-stripped version of the line:
      Rule 1: ALL CAPS text (5-60 chars).
      Rule 2: Ends in ':' or '?' (< MAX_PUNCT_HEADER_LEN chars).
      Rule 3: Standalone formatting (entire line is bold, italic, or bold-italic).
      Rule 4: Structural context (short plain line flanked by long text or lists).

    The line must be preceded by a blank line or be at the start of the document
    (or follow the end of a list block) to qualify.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False

    # Standard list items are never pseudo-headers
    if _is_list_item(stripped):
        return False

    clean = _strip_formatting(stripped)

    # Must be preceded by a blank line, start of doc, or end of list/code block
    if not above_blank:
        # Also allow if previous non-blank line was a list item (list boundary)
        if idx > 0 and _is_list_item(lines[idx - 1]):
            pass  # list boundary counts
        elif idx > 0 and "___CODE_BLOCK_" in lines[idx - 1]:
            pass  # code block boundary counts
        else:
            return False

    # Rule 1: ALL CAPS
    if is_all_caps(clean):
        return True

    # Rule 2: Ending punctuation (: or ?) after stripping formatting
    if len(clean) < MAX_PUNCT_HEADER_LEN and not _is_list_item(stripped):
        if clean.endswith(':') or clean.endswith('?'):
            return True

    # Rule 3: Standalone formatting (entire line is bold, italic, or bold-italic)
    if re.match(r'^(\*{1,3}|_{1,3}).+?\1$', stripped) and len(clean) < MAX_PUNCT_HEADER_LEN:
        return True

    # Rule 4: Structural context — short plain line flanked by long text or list blocks
    if len(clean) < MAX_STRUCTURAL_HEADER_LEN:
        # Find next non-blank line
        next_len = 0
        for j in range(idx + 1, len(lines)):
            next_stripped = lines[j].strip()
            if next_stripped:
                if "___CODE_BLOCK_" in next_stripped:
                    next_len = 100  # Treat code blocks as large structural boundaries
                else:
                    next_len = len(next_stripped)
                break

        if next_len >= MIN_FLANKING_LINE_LEN or (idx + 1 < len(lines) and _is_list_item(lines[idx + 1])):
            return True

    return False


# ---------------------------------------------------------------------------
# Main Sanitization Pipeline
# ---------------------------------------------------------------------------

def sanitize_description(text: str) -> str:
    if not text:
        return text
    
    original_length = len(text)
    logger.info(f"sanitize_description STARTED. Original length: {original_length}")

    # ======================================================================
    # Phase 1: Encoding & Character-Level Normalization
    # ======================================================================
    # Normalize line endings first for predictable extraction
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Decode \uXXXX escapes
    if '\\u' in text:
        text = decode_unicode_escapes(text)

    # Protect code blocks before HTML/backslash stripping
    text, code_blocks = _extract_code_blocks(text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Convert common HTML entities
    text = html.unescape(text)

    # Normalize line breaks from RTF
    text = text.replace('\u2028', '\n').replace('\u2029', '\n')

    # Remove soft hyphen (U+00AD) BEFORE normalization
    text = text.replace('\u00AD', '')

    # Normalize to NFKC
    text = unicodedata.normalize('NFKC', text)

    # Replace all Unicode Zs ("space separator") category chars with standard space
    text = ''.join(' ' if unicodedata.category(c) == 'Zs' else c for c in text)

    # Replace other invisible/zero-width spacing characters with normal space
    invisible_to_space = {
        '\u200B', '\u200C', '\u200D', '\u2060', '\uFEFF',
        '\u2009', '\u200A', '\u202F', '\u205F',
    }
    text = ''.join(' ' if c in invisible_to_space else c for c in text)

    # Normalize line endings (soft/carriage returns -> linefeeds)
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Normalize more soft return variants to hard returns
    for sr in ['\u2028', '\u2029', '\v', '\f']:
        text = text.replace(sr, '\n')

    text = re.sub(r'\n{3,}', '\n\n', text)  # Max two newlines in a row

    # Remove Markdown Horizontal Rules
    hr_pattern = re.compile(r'(?m)^\s*([-_*=])(?:\s*\1){2,}\s*$', re.MULTILINE)
    text, _ = hr_pattern.subn('', text)

    # Replace Confusables (Cyrillic -> ASCII, fullwidth -> ASCII)
    CONFUSABLES = {
        'а': 'a', 'е': 'e', 'і': 'i', 'о': 'o', 'р': 'p',
        'с': 'c', 'у': 'y', 'х': 'x',
        'Α': 'A', 'Β': 'B', 'Ο': 'O',
        'Ｈ': 'H', 'ｅ': 'e', 'ｏ': 'o',
        'ⅰ': 'i', 'ⅱ': 'ii', 'ⅲ': 'iii',
    }
    text = ''.join(c if c not in CONFUSABLES else CONFUSABLES[c] for c in text)

    # Replace common smart punctuation
    REPLACEMENTS = {
        '\u201C': '"', '\u201D': '"',
        '\u2018': "'", '\u2019': "'",
        '\u2013': '-', '\u2014': '-', '\u2212': '-',
        '\u2026': '...',
        '\u2010': '-', '\u2011': '-',
        '\uFE63': '-', '\u2043': '-', '\uFF0D': '-',
    }
    for orig, repl in REPLACEMENTS.items():
        if orig in text:
            text = text.replace(orig, repl)

    # Strip Backslash Escapes (HTML-to-MD converter artifacts)
    text = re.sub(r'\\([\\`*_{}[\]()#+\-.!<>])', r'\1', text)

    # ======================================================================
    # Phase 2: Inline Structural Repair & Splitting
    # ======================================================================
    # Split jammed inline headers & bullets (e.g. `**Required Qualifications:** * 6+ years`)
    # Restrict to horizontal whitespace only ([^\S\n]) to prevent swallowing newlines.
    text = re.sub(r'(?m)^[^\S\n]*\*\*([^*:\n]+):\*\*[^\S\n]*[\*\-\+][^\S\n]+', r'\1:\n- ', text)

    # Split escaped asterisk jam (e.g. `What You'll Accomplish\* Lead, coach...`)
    text = re.sub(r'(?m)^([A-Za-z][A-Za-z0-9\s/\'?]{4,40}?)\*[^\S\n]+(.*)', r'\1:\n- \2', text)

    # Split bold paragraph jam (e.g. `Additional Information**Applicants must...`)
    # Strips the trailing bold marker if it matches at the end of the line.
    text = re.sub(r'(?m)^([A-Za-z][A-Za-z0-9\s/\']{4,40}?)\*\*(.*?)(?:\*\*)?[^\S\n]*$', r'\1:\n\2', text)

    # Normalize bullet-like characters (•, ►, ▪, etc. -> - )
    BULLETS = "•‣▪●◦·‒—–→►⁃∙⋅⦿☉⦾"
    pattern = f"[{re.escape(BULLETS)}][\u00A0\u2000-\u200B\\s]*"
    text, _ = re.subn(pattern, "- ", text)

    # ======================================================================
    # Phase 3: Comprehensive Pseudo-Header Detection & Dynamic Depth
    # ======================================================================
    # Unified single pass: detect pseudo-headers and assign header depth
    # relative to the last-seen real header level.
    lines = text.splitlines()
    modified_lines = lines.copy()
    current_header_level = 2  # Default: job descriptions live under H2

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Track existing Markdown headers to maintain depth context
        header_match = re.match(r'^(#{1,6})\s+', stripped)
        if header_match:
            current_header_level = len(header_match.group(1))
            continue

        above_blank = (i == 0) or (lines[i - 1].strip() == "")

        if _is_pseudo_header(line, above_blank, lines, i):
            clean = _strip_formatting(stripped)
            # Strip trailing colon from the title text (the header itself implies a section)
            if clean.endswith(':'):
                clean = clean[:-1].strip()
            # Assign depth: one level below the last-seen real header, capped at H4
            target_level = min(current_header_level + 1, 4)
            modified_lines[i] = f"{'#' * target_level} {clean}"

    text = "\n".join(modified_lines)

    # ======================================================================
    # Phase 4: List Marker & Content Normalization
    # ======================================================================
    if STANDARDIZE_BULLET_LISTS:
        text, _ = re.subn(r'(?m)^([ \t]*)[*+]\s+', r'\1- ', text)

    list_marker_pattern = r'(?m)^([ \t]*(?:[-*+]|\d+\.)\s+)'
    if REMOVE_BOLD_FROM_LISTS:
        bold_pat = re.compile(list_marker_pattern + r'\*\*(.+?)\*\*(.*)')
        text, _ = bold_pat.subn(r'\1\2\3', text)

    if REMOVE_ITALIC_FROM_LISTS:
        italic_pat = re.compile(list_marker_pattern + r'[*_](?![*_])(.+?)(?<![*_])[*_](.*)')
        text, _ = italic_pat.subn(r'\1\2\3', text)

    # ======================================================================
    # Phase 5: Header Hierarchy Re-Indexing
    # ======================================================================
    # Ensure headers form a valid, incrementally descending tree.
    # Walk through all headers and re-index any that skip levels.
    lines = text.splitlines()
    modified_lines = lines.copy()
    last_level = 0  # No header seen yet

    for i, line in enumerate(lines):
        m = re.match(r'^(#{1,6})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            if last_level == 0:
                # First header in document — accept as-is
                last_level = level
            elif level > last_level + 1:
                # Header skips levels (e.g. ## followed by ####) — pull it down
                level = last_level + 1
                modified_lines[i] = f"{'#' * level} {title}"
            last_level = level

    text = "\n".join(modified_lines)

    # Restore code blocks before final filtering passes
    text = _restore_code_blocks(text, code_blocks)

    # ======================================================================
    # Phase 6: Character Filtering & Emoji/Control Strip
    # ======================================================================
    ALLOWED_NON_ASCII = set("áéíóúüñçãõêâôûìÁÉÍÓÚÜÑÇÃÕÊÂÔÛÌ€£¥©®™")
    cleaned = []
    for c in text:
        cat = unicodedata.category(c)
        if c in ('\n', '\t'):
            cleaned.append(c)
        elif not c.isprintable():
            continue
        elif cat in ('Cf', 'Cc', 'Cs'):
            continue
        elif ord(c) <= 127:
            cleaned.append(c)
        elif c in ALLOWED_NON_ASCII:
            cleaned.append(c)
    text = ''.join(cleaned)

    # Extra Cleanup: Emoji, ZWJ, Formatting Marks
    emoji_pattern = re.compile(
        '['
        '\U0001F000-\U0001FAFF'
        '\U00002500-\U00002BEF'
        '\U00002702-\U000027B0'
        '\U0001F900-\U0001F9FF'
        '\U0001F300-\U0001F5FF'
        ']+',
        flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    text = re.sub(r'[\u200B-\u200D\uFEFF\u202A-\u202E\u2060-\u206F]', '', text)

    # Remove Combining Marks
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    # Fix Whitespace and Normalize Line Endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text, _ = re.subn(r'[^\S\r\n\t]{2,}', ' ', text)
    text, _ = re.subn(r'\s+([.,;:!?)\]])', r'\1', text)
    text, _ = re.subn(r'([\(\[]) +', r'\1', text)

    # Force normalize remaining line breaks
    text = text.replace('\u2028', '\n').replace('\u2029', '\n')
    text = re.sub(r'[\v\f]+', '\n', text)

    # ======================================================================
    # Phase 7: Standard GFM Formatting Pass (mdformat)
    # ======================================================================
    result = text
    import os
    if os.getenv("SANITIZE_MDFORMAT", "true").lower() == "true":
        try:
            import mdformat
            result = mdformat.text(text, extensions={"gfm"})
        except Exception as e:
            import traceback
            logger.warning(f"mdformat formatting skipped: {e}")
            try:
                with open("/app/data/mdformat_error.log", "a", encoding="utf-8") as err_f:
                    err_f.write(f"Error: {e}\n{traceback.format_exc()}\n")
            except Exception:
                pass
    else:
        logger.info("mdformat formatting skipped per SANITIZE_MDFORMAT setting.")

    result = result.strip()
    logger.info(f"sanitize_description FINISHED. Final length: {len(result)}. Difference: {len(result) - original_length}")
    
    return result
