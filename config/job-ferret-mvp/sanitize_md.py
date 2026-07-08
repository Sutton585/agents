import unicodedata
import re
import html
import logging

logger = logging.getLogger("sanitize_md")
logger.setLevel(logging.INFO)

STANDARDIZE_BULLET_LISTS = True    # Converts * or + bullets to hyphen -
REMOVE_BOLD_FROM_LISTS = True      # Converts "- **Bold**" to "- Bold"
REMOVE_ITALIC_FROM_LISTS = True    # Converts "- *Italic*" to "- Italic"
BOLD_LINE_HEADER_LEVEL = "####"

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

    # Must be long enough and all uppercase
    if len(stripped) < 5:
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

def sanitize_description(text: str) -> str:
    if not text:
        return text
    
    original_length = len(text)
    logger.info(f"sanitize_description STARTED. Original length: {original_length}")

    # --- Step 0: Strip HTML/RTF Paste Artifacts ---
    if '\\u' in text:
        text = decode_unicode_escapes(text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Convert common HTML entities
    text = html.unescape(text)

    # Normalize line breaks from RTF
    text = text.replace('\u2028', '\n').replace('\u2029', '\n')

    # ---Step 1: Normalize Unicode & Fix Spacing---
    # Remove soft hyphen (U+00AD) and similar characters BEFORE normalization
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

    # Normalize line endings (soft/carriage returns → linefeeds)
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Normalize more soft return variants to hard returns
    for sr in ['\u2028', '\u2029', '\v', '\f']:
        text = text.replace(sr, '\n')

    text = re.sub(r'\n{3,}', '\n\n', text)  # Max two newlines in a row

    # --- Remove Markdown Horizontal Rules ---
    hr_pattern = re.compile(r'(?m)^\s*([-_*=])(?:\s*\1){2,}\s*$', re.MULTILINE)
    text, _ = hr_pattern.subn('', text)

    # --- Step 2: Replace Confusables ---
    CONFUSABLES = {
        'а': 'a', 'е': 'e', 'і': 'i', 'о': 'o', 'р': 'p',
        'с': 'c', 'у': 'y', 'х': 'x',
        'Α': 'A', 'Β': 'B', 'Ο': 'O',
        'Ｈ': 'H', 'ｅ': 'e', 'ｏ': 'o',
        'ⅰ': 'i', 'ⅱ': 'ii', 'ⅲ': 'iii',
    }
    text = ''.join(c if c not in CONFUSABLES else CONFUSABLES[c] for c in text)

    # --- Step 3: Replace Common Punctuation---
    REPLACEMENTS = {
        '“': '"', '”': '"',
        '‘': "'", '’': "'",
        '–': '-', '—': '-', '−': '-',
        '…': '...',
        '\u2010': '-', '\u2011': '-', '\u2212': '-',
        '\uFE63': '-', '\u2043': '-', '\uFF0D': '-',
    }
    for orig, repl in REPLACEMENTS.items():
        if orig in text:
            text = text.replace(orig, repl)

    # --- Step 4: Normalize Bullet-like Characters ---
    BULLETS = "•‣▪●◦·‒—–→►⁃∙⋅⦿☉⦾"
    pattern = f"[{re.escape(BULLETS)}][\u00A0\u2000-\u200B\\s]*"
    text, _ = re.subn(pattern, "- ", text)

    # --- Step 4.25: ALL CAPS Header Conversion (script1_smaller.py) ---
    lines = text.splitlines()
    modified_lines = lines.copy()
    for i, line in enumerate(lines):
        if is_all_caps(line):
            above_blank = i == 0 or lines[i-1].strip() == ""
            # A faux header shouldn't require a blank line below it; often it's directly above a list.
            if above_blank:
                modified_lines[i] = f"### {line}"
    text = "\n".join(modified_lines)

    # --- Step 4.5: Standardize Lists & Optional Un-Bolding/Un-Italicizing ---
    if STANDARDIZE_BULLET_LISTS:
        text, _ = re.subn(r'(?m)^[ \t]*[*+]\s+', '- ', text)

    list_marker_pattern = r'(?m)^(\s*(?:[-*+]|\d+\.)\s+)'
    if REMOVE_BOLD_FROM_LISTS:
        bold_pat = re.compile(list_marker_pattern + r'\*\*(.+?)\*\*(.*)')
        text, _ = bold_pat.subn(r'\1\2\3', text)

    if REMOVE_ITALIC_FROM_LISTS:
        italic_pat = re.compile(list_marker_pattern + r'[*_](?![*_])(.+?)(?<![*_])[*_](.*)')
        text, _ = italic_pat.subn(r'\1\2\3', text)

    # --- Step 5: Convert Bold Markdown Lines to Headers ---
    if BOLD_LINE_HEADER_LEVEL:
        bold_line_pattern = re.compile(
            r'^\s*\*\*(.+?)\*\*\s*[.?!\-–—]*\s*$', re.MULTILINE
        )
        text, _ = bold_line_pattern.subn(
            lambda m: f"{BOLD_LINE_HEADER_LEVEL} {m.group(1).strip()}", text
        )

    # --- Step 6: Remove Forbidden or Invisible Characters ---
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

    # --- Step 6.5 Extra Cleanup: Emoji, ZWJ, Formatting Marks ---
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

    # --- Step 7: Remove Combining Marks ---
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    # --- Step 8: Fix Whitespace and Normalize Line Endings ---
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text, _ = re.subn(r'[^\S\r\n\t]{2,}', ' ', text)
    text, _ = re.subn(r'\s+([.,;:!?)\]])', r'\1', text)
    text, _ = re.subn(r'([\(\[]) +', r'\1', text)

    # Force normalize remaining line breaks
    text = text.replace('\u2028', '\n').replace('\u2029', '\n')
    text = re.sub(r'[\v\f]+', '\n', text)

    result = text.strip()
    logger.info(f"sanitize_description FINISHED. Final length: {len(result)}. Difference: {len(result) - original_length}")
    
    return result
