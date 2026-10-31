# Math Exercise Agent

A command-line tool that reads a chapter of a Greek secondary-school math textbook (online HTML or PDF) and uses an LLM (Claude) to generate **new, original exercises with step-by-step solutions in Greek**, exported as a ready-to-print PDF.

Built for teachers who need fresh practice material that follows the official textbook's content, terminology and notation.

## Features

- **Flexible input:** a textbook URL (HTML or PDF) or a local file
- **Targeting:** select by chapter, section (e.g. `3.7`) or page range, with an `--offset` option when printed page numbers differ from PDF page numbers
- **Difficulty levels:** `easy`, `medium`, `hard` or `mixed` (progressive difficulty)
- **Structured output:** the model returns exercises through a tool-use JSON schema (title, difficulty, statement, solution steps, final answer, optional tip), so the PDF layout is consistent
- **Batching and retries:** exercises are requested in small batches with earlier titles passed in to avoid duplicates, plus automatic retries if a batch comes back empty
- **PDF export (ReportLab):** Greek-capable fonts, exercises followed by solutions (`separate`) or solution under each exercise (`inline`)

## Installation

```bash
pip install requests pypdf beautifulsoup4 anthropic reportlab matplotlib
```

Set your API key as an environment variable (never commit it):

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="your-key"
# Windows
set ANTHROPIC_API_KEY=your-key
```

## Usage

```bash
python math_agent.py \
  --url "https://ebooks.edu.gr/ebooks/v/html/8547/2692/Geometria_A-Lykeiou_html-empl/index3.html" \
  --chapter 3 --difficulty medium --count 8 \
  --grade "Α΄ Λυκείου" --out askiseis.pdf
```

For a PDF textbook, select pages instead:

```bash
python math_agent.py --url https://example.com/algebra.pdf \
  --pages 45-52 --offset 6 --difficulty hard --count 6
```

| Option | Description |
|---|---|
| `--url` / `--file` | Textbook URL, or a local PDF/HTML file |
| `--chapter`, `--section`, `--pages` | What part of the book to use (at least one required) |
| `--offset` | PDF page = book page + offset |
| `--difficulty` | `easy`, `medium`, `hard`, `mixed` |
| `--count` | Number of exercises (default 6) |
| `--grade` | Grade level, e.g. `"Β΄ Λυκείου"` |
| `--layout` | `separate` (exercises, then solutions) or `inline` |
| `--model` | Claude model to use |
| `--font` | Path to a `.ttf` with Greek support (optional) |
| `--out` | Output PDF path |

## How it works

1. **Fetch and extract:** download the book and extract the relevant text (`pypdf` for PDFs, `BeautifulSoup` for HTML), locating the chapter or section heading with regular expressions
2. **Generate:** send the excerpt with a system prompt (Greek teacher persona, rules for notation and originality) and a forced tool call that returns structured JSON
3. **Render:** build the PDF with ReportLab, converting plain-text notation such as `x^(2)` into proper superscripts

## Limitations

- **Solutions are LLM-generated and not machine-verified.** Review them before giving them to students.
- The excerpt sent to the model is capped at 14,000 characters.
- Scanned PDFs need OCR first (the tool tells you when no text is found).
- Figures cannot be drawn; exercises that need a diagram describe it in words.

## Tech stack

Python · Anthropic API (tool use, streaming) · ReportLab · pypdf · BeautifulSoup · requests

## License

MIT (add a LICENSE file before publishing)
