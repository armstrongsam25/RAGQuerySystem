"""Brand-contract tests for the Nymbl UI polish (feature 004).

Three concerns are enforced here, all of them static-text scans rather
than rendered-DOM assertions:

1. The brand-token vocabulary is declared at ``:root`` in ``styles.css``
   with the brand-pinned hex / family values (`test_css_tokens_defined`).
2. The stylesheet contains zero forbidden raw values: no pure white,
   no pure black, no ``purple`` literal anywhere
   (`test_no_forbidden_strings_in_styles`).
3. The error partials carry ``role="alert"`` and emit no raw backend
   strings (``{{ cause }}`` / ``{{ message }}`` / ``{{ error.message }}``)
   (`test_error_partials_carry_role_alert`,
   `test_error_templates_dont_emit_raw_backend_strings`).
4. ``base.html`` carries the required ``aria-live="polite"`` regions
   (`test_aria_attributes_on_base_template`).

Tests deliberately operate on file contents (regex / substring) rather
than a CSS parser — keeps the suite under a second and surfaces only
the regressions the brand guide actually cares about.
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STYLES_PATH = _REPO_ROOT / "src" / "rag" / "ui" / "static" / "styles.css"
_TEMPLATES_DIR = _REPO_ROOT / "src" / "rag" / "ui" / "templates"


# ---- Brand tokens contract ------------------------------------------------

# (property, expected exact value as it appears in the declaration RHS).
# The test asserts each property is declared with the brand-pinned value.
# Case-insensitive on the hex literals; the property names must match
# exactly. Source: contracts/css-tokens.md.
_REQUIRED_TOKENS: list[tuple[str, str]] = [
    # Core ink/paper
    ("--ink-900", "#0A0A0F"),
    ("--ink-700", "#1F2028"),
    ("--paper-50", "#F5F1E8"),
    ("--paper-100", "#EDE7D9"),
    # Accents
    ("--signal-500", "#DAFE5D"),
    ("--signal-600", "#B8DE3A"),
    ("--ember-500", "#E85A4F"),
    # Stone
    ("--stone-50", "#F0ECE3"),
    ("--stone-100", "#E2DCCE"),
    ("--stone-200", "#CAC2B0"),
    ("--stone-300", "#A39B89"),
    ("--stone-500", "#6E6757"),
    ("--stone-700", "#403B30"),
    # Semantic
    ("--success", "#3F8F5C"),
    ("--warning", "#D89A2E"),
    ("--danger", "#C7372F"),
    ("--info", "#4A6FA5"),
]

# Font-family / surface-alias / motion tokens — match by property name
# (the RHS is a CSS expression, not a single hex value).
_REQUIRED_TOKEN_NAMES: list[str] = [
    "--font-display",
    "--font-sans",
    "--font-mono",
    "--text-display-2xl",
    "--text-display-xl",
    "--text-display-lg",
    "--text-heading-xl",
    "--text-heading-lg",
    "--text-heading-md",
    "--text-heading-sm",
    "--text-body-lg",
    "--text-body-md",
    "--text-body-sm",
    "--text-caption",
    "--text-mono-md",
    "--text-mono-sm",
    "--bg",
    "--fg",
    "--fg-muted",
    "--border",
    "--accent",
    "--accent-fg",
    "--motion-pulse-duration",
]


def _styles_text() -> str:
    return _STYLES_PATH.read_text(encoding="utf-8")


def test_css_tokens_defined() -> None:
    css = _styles_text()
    for prop, expected_value in _REQUIRED_TOKENS:
        pattern = rf"{re.escape(prop)}\s*:\s*{re.escape(expected_value)}\s*;"
        assert re.search(pattern, css, re.IGNORECASE), (
            f"Missing or mis-valued brand token: {prop} should be {expected_value}"
        )
    for name in _REQUIRED_TOKEN_NAMES:
        pattern = rf"{re.escape(name)}\s*:"
        assert re.search(pattern, css), f"Missing brand token declaration: {name}"


# ---- Forbidden strings ----------------------------------------------------


def test_no_forbidden_strings_in_styles() -> None:
    css = _styles_text()
    # Pure white / black raw hex (whole-token regex — won't catch hex
    # literals that merely *contain* fff or 000 as a substring like
    # #efff00 or #c00000).
    forbidden_hex_patterns = [
        r"#[fF]{6}\b",
        r"#[fF]{3}\b",
        r"#0{6}\b",
        r"#0{3}\b",
    ]
    for pat in forbidden_hex_patterns:
        m = re.search(pat, css)
        assert m is None, f"Forbidden raw hex literal in styles.css: {m.group(0)!r}"
    # rgb(255, 255, 255) / rgb(0, 0, 0) — whitespace-tolerant.
    forbidden_rgb_patterns = [
        r"rgb\(\s*255\s*,\s*255\s*,\s*255\s*\)",
        r"rgb\(\s*0\s*,\s*0\s*,\s*0\s*\)",
    ]
    for pat in forbidden_rgb_patterns:
        m = re.search(pat, css, re.IGNORECASE)
        assert m is None, f"Forbidden rgb() white/black in styles.css: {m.group(0)!r}"
    # Literal substring 'purple' (case-insensitive). No false positives:
    # no Nymbl token name contains 'purple'.
    assert re.search(r"purple", css, re.IGNORECASE) is None, (
        "Forbidden literal 'purple' present in styles.css"
    )


# ---- Template a11y attributes --------------------------------------------


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def test_error_partials_carry_role_alert() -> None:
    env = _jinja_env()
    # _error.html — render with the new ``category`` context.
    err_html = env.get_template("_error.html").render(category="server", trace_id="t-test")
    assert 'role="alert"' in err_html, '_error.html root must carry role="alert"'
    # _upload_error.html — same.
    upload_err_html = env.get_template("_upload_error.html").render(
        category="server", trace_id="t-test", prior_corpus_intact=True
    )
    assert 'role="alert"' in upload_err_html, '_upload_error.html root must carry role="alert"'


def test_error_templates_dont_emit_raw_backend_strings() -> None:
    # Grep template SOURCES (not rendered output) for the legacy
    # context-key interpolations. If any of these substrings is present,
    # a backend string can slip into the rendered UI.
    forbidden_substrings = [
        "{{ cause }}",
        "{{ message }}",
        "{{ error.message }}",
        "{{ error.error }}",
    ]
    for template_name in ("_error.html", "_upload_error.html"):
        src = (_TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
        for needle in forbidden_substrings:
            assert needle not in src, (
                f"{template_name} must not interpolate {needle!r} — "
                "the clarify decision restricts visible copy to fixed "
                "category strings (see contracts/error-rendering.md)."
            )


def test_aria_attributes_on_base_template() -> None:
    base_src = (_TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    # The chat-thread region MUST announce new turns politely.
    assert re.search(
        r'<section[^>]*id="chat-thread"[^>]*aria-live="polite"', base_src
    ) or re.search(
        r'<section[^>]*aria-live="polite"[^>]*id="chat-thread"', base_src
    ), '#chat-thread section must carry aria-live="polite"'
    # The #current-doc region also gets polite announcements after the
    # initial load swap so screen readers note doc state changes.
    assert re.search(r'id="current-doc"[^>]*aria-live="polite"', base_src) or re.search(
        r'aria-live="polite"[^>]*id="current-doc"', base_src
    ), '#current-doc element must carry aria-live="polite"'
    # The upload-in-progress partial root must carry aria-live="polite".
    upload_progress_src = (_TEMPLATES_DIR / "_upload_in_progress.html").read_text(encoding="utf-8")
    assert 'aria-live="polite"' in upload_progress_src, (
        '_upload_in_progress.html root must carry aria-live="polite"'
    )
