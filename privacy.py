"""Local heuristic screening. No matches or source fragments are returned."""
import re

PATTERNS = {
    'email': re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I),
    'us_ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    'phone': re.compile(r'(?<!\w)(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}\b'),
    'sensitive_label': re.compile(r'\b(?:social security|passport|date of birth|dob|patient|medical record|bank account|credit card|pii|confidential personal)\b', re.I),
}


def screen(text):
    return sorted(name for name, pattern in PATTERNS.items() if pattern.search(text))


def inspect_inputs(adapter, instructions, text, project_path, files):
    kinds = set(screen(instructions + '\n' + text))
    for name in files or []:
        path = adapter.resolve_file(project_path, name)
        # Fail closed for files too large to screen, including log sampling.
        with path.open('rb') as f:
            raw = f.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Privacy screening limit exceeded. Split the file locally; do not send it to the cloud.')
        try: content = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError('Privacy screening requires UTF-8 text. Convert locally; do not send it to the cloud.') from None
        kinds.update(screen(content))
    return sorted(kinds)
