import re
import markdown

ANKICRAFT_BASIC_MODEL_NAME = "AnkiCraft Pro (Basic)"
ANKICRAFT_CLOZE_MODEL_NAME = "AnkiCraft Pro (Cloze)"

BASIC_MODEL_FIELDS = ["Breadcrumb", "Front", "Back", "Extra"]
CLOZE_MODEL_FIELDS = ["Breadcrumb", "Text", "Back Extra", "Extra"]

BASIC_CARD_FRONT = """<div class="ankicraft-container">
  {{#Breadcrumb}}
  <div class="ankicraft-breadcrumb">📍 {{Breadcrumb}}</div>
  {{/Breadcrumb}}
  <div class="ankicraft-content ankicraft-front">
    {{Front}}
  </div>
</div>"""

BASIC_CARD_BACK = """<div class="ankicraft-container">
  {{#Breadcrumb}}
  <div class="ankicraft-breadcrumb">📍 {{Breadcrumb}}</div>
  {{/Breadcrumb}}
  <div class="ankicraft-content ankicraft-front ankicraft-dimmed">
    {{Front}}
  </div>
  <hr class="ankicraft-divider">
  <div class="ankicraft-content ankicraft-back">
    {{Back}}
  </div>
  {{#Extra}}
  <div class="ankicraft-extra-box">
    <div class="ankicraft-extra-header">💡 Síntesis Visual</div>
    <div class="ankicraft-extra-content">{{Extra}}</div>
  </div>
  {{/Extra}}
</div>"""

CLOZE_CARD_FRONT = """<div class="ankicraft-container">
  {{#Breadcrumb}}
  <div class="ankicraft-breadcrumb">📍 {{Breadcrumb}}</div>
  {{/Breadcrumb}}
  <div class="ankicraft-content">
    {{cloze:Text}}
  </div>
</div>"""

CLOZE_CARD_BACK = """<div class="ankicraft-container">
  {{#Breadcrumb}}
  <div class="ankicraft-breadcrumb">📍 {{Breadcrumb}}</div>
  {{/Breadcrumb}}
  <div class="ankicraft-content">
    {{cloze:Text}}
  </div>
  {{#Back Extra}}
  <hr class="ankicraft-divider">
  <div class="ankicraft-content ankicraft-back">
    {{Back Extra}}
  </div>
  {{/Back Extra}}
  {{#Extra}}
  <div class="ankicraft-extra-box">
    <div class="ankicraft-extra-header">💡 Síntesis Visual</div>
    <div class="ankicraft-extra-content">{{Extra}}</div>
  </div>
  {{/Extra}}
</div>"""

ANKICRAFT_CARD_CSS = """
/* AnkiCraft Pro - Visual Rest & Cognitive Ergonomics Theme */
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", Helvetica, Arial, sans-serif;
  font-size: 19px;
  line-height: 1.6;
  text-align: left;
  color: #1e293b;
  background-color: #ffffff;
  padding: 24px;
  margin: 0 auto;
  max-width: 680px;
}

/* Dark Mode support (native Anki .nightMode and system prefers-color-scheme) */
.nightMode .card,
@media (prefers-color-scheme: dark) {
  .card {
    color: #e2e8f0;
    background-color: #0b0f19;
  }
}

.ankicraft-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Breadcrumbs Header */
.ankicraft-breadcrumb {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.2);
  margin-bottom: 6px;
}

.nightMode .ankicraft-breadcrumb {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  border-color: rgba(99, 102, 241, 0.3);
}

/* Content Area */
.ankicraft-content {
  font-size: 19px;
  font-weight: 400;
}

.ankicraft-front {
  font-weight: 600;
  color: #0f172a;
}

.nightMode .ankicraft-front {
  color: #f8fafc;
}

.ankicraft-dimmed {
  opacity: 0.65;
  font-weight: 400;
  font-size: 16px;
}

.ankicraft-back {
  font-weight: 500;
  color: #10b981;
}

.nightMode .ankicraft-back {
  color: #34d399;
}

/* Cloze Deletions */
.cloze {
  font-weight: 700;
  color: #4f46e5;
  background: rgba(99, 102, 241, 0.12);
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid rgba(99, 102, 241, 0.25);
}

.nightMode .cloze {
  color: #818cf8;
  background: rgba(99, 102, 241, 0.2);
  border-color: rgba(99, 102, 241, 0.4);
}

/* Dividers */
.ankicraft-divider {
  border: 0;
  height: 1px;
  background: linear-gradient(to right, rgba(99, 102, 241, 0), rgba(99, 102, 241, 0.5), rgba(99, 102, 241, 0));
  margin: 16px 0;
}

/* Tables (Markdown to HTML) */
table {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 10px;
  overflow: hidden;
  margin: 14px 0;
  font-size: 15px;
}

th {
  background: rgba(99, 102, 241, 0.1);
  color: #4338ca;
  font-weight: 600;
  padding: 10px 14px;
  text-align: left;
  border-bottom: 1px solid rgba(148, 163, 184, 0.25);
}

.nightMode th {
  background: rgba(99, 102, 241, 0.2);
  color: #c7d2fe;
  border-bottom-color: rgba(148, 163, 184, 0.2);
}

td {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

tr:last-child td {
  border-bottom: none;
}

tr:nth-child(even) {
  background: rgba(148, 163, 184, 0.05);
}

/* Extra Field: Passive Visual Synthesis */
.ankicraft-extra-box {
  margin-top: 18px;
  padding: 16px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.nightMode .ankicraft-extra-box {
  background: rgba(15, 23, 42, 0.6);
  border-color: rgba(99, 102, 241, 0.25);
}

.ankicraft-extra-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #d97706;
  margin-bottom: 8px;
}

.nightMode .ankicraft-extra-header {
  color: #fbbf24;
}

.ankicraft-extra-content {
  font-size: 14px;
  line-height: 1.5;
  color: #475569;
}

.nightMode .ankicraft-extra-content {
  color: #94a3b8;
}
"""


def format_anki_field(text: str) -> str:
    """Transform markdown tables, LaTeX MathJax, and linebreaks into clean HTML for Anki."""
    if not text:
        return ""

    math_placeholders = []

    def _save_math(match):
        token = f"XMJXTOKEN{len(math_placeholders)}XMJX"
        math_placeholders.append(match.group(0))
        return token

    # 1. Convert $$block math$$ to \[block math\]
    processed = re.sub(r"\$\$(.+?)\$\$", lambda m: f"\\[{m.group(1)}\\]", text, flags=re.DOTALL)

    # 2. Convert $inline math$ to \(inline math\)
    processed = re.sub(r"(?<!\\)\$([^\$\n]+?)\$", lambda m: f"\\({m.group(1)}\\)", processed)

    # 3. Protect MathJax tokens from markdown parser
    processed = re.sub(r"\\\(.+?\\\)", _save_math, processed)
    processed = re.sub(r"\\\[.+?\\\]", _save_math, processed, flags=re.DOTALL)

    # 4. Ensure tables have a preceding blank line
    lines = processed.split("\n")
    cleaned_lines = []
    in_table = False
    for line in lines:
        is_table_row = line.strip().startswith("|") and line.strip().endswith("|")
        if is_table_row and not in_table:
            if cleaned_lines and cleaned_lines[-1].strip():
                cleaned_lines.append("")
            in_table = True
        elif not is_table_row:
            in_table = False
        cleaned_lines.append(line)

    normalized_text = "\n".join(cleaned_lines)

    # 5. Convert Markdown to HTML
    html = markdown.markdown(
        normalized_text,
        extensions=["tables", "fenced_code", "nl2br"],
        output_format="html5",
    )

    # 6. Restore MathJax
    for i, original_math in enumerate(math_placeholders):
        html = html.replace(f"XMJXTOKEN{i}XMJX", original_math)

    return html.strip()


def extract_breadcrumb_and_body(text: str):
    """Separate '[Macro > Sub > Cat]' breadcrumb from the card body."""
    match = re.match(r"^\[(.*?)\]\s*(.*)$", text.strip(), flags=re.DOTALL)
    if match:
        breadcrumb = match.group(1).strip()
        body = match.group(2).strip()
        if not body:
            # If text only contained brackets, treat it as body so front is not empty
            return "", breadcrumb
        return breadcrumb, body
    return "", text.strip()


def rewrite_media_urls_for_web(
    html: str,
    media_proxy_base: str = "http://127.0.0.1:8000/api/anki/media/",
) -> str:
    """Rewrite relative Anki <img src="filename.ext"> tags to proxy URLs for web browser preview."""
    if not html:
        return html

    def _replace_src(m):
        full_tag = m.group(0)
        src_val = m.group(1)
        if src_val.startswith("http://") or src_val.startswith("https://") or src_val.startswith("data:"):
            return full_tag
        new_src = f"{media_proxy_base.rstrip('/')}/{src_val.lstrip('/')}"
        return re.sub(r'src=["\'][^"\']+["\']', f'src="{new_src}"', full_tag)

    return re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', _replace_src, html)

