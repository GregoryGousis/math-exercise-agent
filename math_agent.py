#!/usr/bin/env python3
"""
Πράκτορας Ασκήσεων Μαθηματικών (Math Exercise Agent)
====================================================
Παίρνει ένα URL με βιβλίο Μαθηματικών (HTML ή PDF), ένα κεφάλαιο/σελίδες και
ένα επίπεδο δυσκολίας, και παράγει ένα PDF με ασκήσεις + αναλυτικές λύσεις
βήμα-βήμα, στα Ελληνικά.

Παραδείγματα:
  python math_agent.py --url https://ebooks.edu.gr/.../algebra.pdf \
      --chapter 2 --pages 45-52 --difficulty medium --count 8 --out ασκήσεις.pdf

  # Αν η αρίθμηση σελίδων του βιβλίου διαφέρει από αυτή του PDF (π.χ. εξώφυλλο,
  # πρόλογος), δώστε --offset (σελίδα PDF = σελίδα βιβλίου + offset):
  python math_agent.py --url ... --pages 45-52 --offset 6 --difficulty hard

Απαιτεί τη μεταβλητή περιβάλλοντος ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from pathlib import Path

import requests

# --------------------------------------------------------------------------- #
# 1. Λήψη και εξαγωγή κειμένου από το βιβλίο
# --------------------------------------------------------------------------- #
HEADERS = {"User-Agent": "Mozilla/5.0 (MathExerciseAgent/1.0)"}
MAX_SOURCE_CHARS = 14000  # όριο κειμένου που στέλνεται στο μοντέλο


def parse_pages(spec: str | None) -> list[int]:
    """'45-52' -> [45..52],  '3,5,9-10' -> [3,5,9,10]"""
    if not spec:
        return []
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    return pages


def download(url: str) -> tuple[bytes, str]:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "").lower()


def load_source(src: str) -> tuple[bytes, str]:
    """Επιστρέφει (bytes, content-type) είτε από τοπικό αρχείο είτε από URL."""
    src = src.strip().strip('"').strip("'")
    if not re.match(r"^https?://", src, re.I):
        path = Path(src).expanduser()
        if not path.is_file():
            sys.exit(f"Δεν βρέθηκε το αρχείο: {path}")
        data = path.read_bytes()
        ctype = "application/pdf" if data[:4] == b"%PDF" else "text/html"
        return data, ctype
    return download(src)


def extract_from_pdf(data: bytes, pages: list[int], chapter: str | None, offset: int,
                     section: str | None = None) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    texts: list[str] = []

    if pages:
        for p in pages:
            idx = p + offset - 1  # 0-based
            if 0 <= idx < total:
                t = reader.pages[idx].extract_text() or ""
                texts.append(f"--- Σελίδα {p} ---\n{t}")
            else:
                print(f"[!] Η σελίδα {p} (PDF σελ. {p + offset}) είναι εκτός ορίων ({total} σελίδες).",
                      file=sys.stderr)
    elif chapter or section:
        # Αναζήτηση της πρώτης σελίδας με την ενότητα (π.χ. «3.7 Κύκλος») ή «Κεφάλαιο N»
        if section:
            pattern = re.compile(rf"(?<!§){re.escape(section)}\s+[Α-Ωα-ωΆ-ώ]")
        else:
            pattern = re.compile(rf"(ΚΕΦΑΛΑΙΟ|Κεφάλαιο|Chapter)\s*{re.escape(chapter)}\b", re.I)
        start = next((i for i, pg in enumerate(reader.pages)
                      if pattern.search(pg.extract_text() or "")), None)
        if start is None:
            sys.exit("Δεν βρέθηκε το κεφάλαιο/η ενότητα που ζητήσατε. Δώστε --pages.")
        for i in range(start, min(start + 8, total)):
            texts.append(f"--- Σελίδα PDF {i + 1} ---\n{reader.pages[i].extract_text() or ''}")
    else:
        sys.exit("Για PDF δώστε --pages ή --chapter.")

    return "\n".join(texts)


def extract_from_html(data: bytes, chapter: str | None, section: str | None = None) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))

    if section:
        m = re.search(rf"(?<!§){re.escape(section)}\s+[Α-Ωα-ωΆ-ώ]", text)
        if m:
            return text[m.start():]
        print(f"[!] Δεν βρέθηκε η ενότητα {section}· χρησιμοποιείται όλη η σελίδα.", file=sys.stderr)
    if chapter:
        m = re.search(rf"(ΚΕΦΑΛΑΙΟ|Κεφάλαιο|Chapter)\s*{re.escape(chapter)}\b", text, re.I)
        if m:
            text = text[m.start():]
        else:
            print(f"[!] Δεν βρέθηκε επικεφαλίδα για το Κεφάλαιο {chapter}· χρησιμοποιείται όλη η σελίδα.",
                  file=sys.stderr)
    return text


def get_source_text(url: str, chapter: str | None, pages: list[int], offset: int,
                    section: str | None = None) -> str:
    data, ctype = load_source(url)
    is_pdf = "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf") or data[:4] == b"%PDF"
    text = (extract_from_pdf(data, pages, chapter, offset, section) if is_pdf
            else extract_from_html(data, chapter, section))
    text = text.strip()
    if len(text) < 200:
        sys.exit("Εξήχθη ελάχιστο κείμενο. Αν το PDF είναι σκαναρισμένο, χρειάζεται OCR "
                 "(pytesseract + pdf2image, γλώσσα 'ell').")
    return text[:MAX_SOURCE_CHARS]


# --------------------------------------------------------------------------- #
# 2. Δημιουργία ασκήσεων με το Claude
# --------------------------------------------------------------------------- #
DIFFICULTY_EL = {"easy": "Εύκολο", "medium": "Μέτριο", "hard": "Δύσκολο", "mixed": "Μικτό"}

DIFFICULTY_GUIDE = {
    "easy": "Άμεση εφαρμογή ορισμών και τύπων, 1-2 βήματα, απλοί αριθμοί.",
    "medium": "Συνδυασμός 2-3 εννοιών, 3-5 βήματα, απαιτείται αιτιολόγηση.",
    "hard": "Πολυβηματικά προβλήματα, απόδειξη ή παράμετρος, συνδυασμός κεφαλαίων, "
            "στυλ εξετάσεων / θεμάτων Γ-Δ.",
    "mixed": "Ισορροπημένος συνδυασμός: περίπου 1/3 εύκολες, 1/3 μέτριες, 1/3 δύσκολες, "
             "σε αύξουσα σειρά δυσκολίας.",
}

SYSTEM_PROMPT = """Είσαι έμπειρος καθηγητής Μαθηματικών Δευτεροβάθμιας Εκπαίδευσης (Γυμνάσιο/Λύκειο) στην Ελλάδα.
Δημιουργείς πρωτότυπες ασκήσεις βασισμένες ΑΠΟΚΛΕΙΣΤΙΚΑ στην ύλη του αποσπάσματος του βιβλίου που σου δίνεται,
με ορολογία και συμβολισμό όπως στα σχολικά βιβλία του Υπουργείου Παιδείας.

ΚΑΝΟΝΕΣ:
1. Όλο το κείμενο στα Ελληνικά.
2. Μην αντιγράφεις ασκήσεις του βιβλίου· φτιάξε νέες, με άλλους αριθμούς/πλαίσιο, ίδιου τύπου.
3. Κάθε άσκηση να έχει πλήρη, ΣΩΣΤΗ λύση βήμα-βήμα. Έλεγξε τους υπολογισμούς σου πριν απαντήσεις.
   Κάθε βήμα: τίτλος (τι κάνουμε) + εξήγηση/υπολογισμός.
4. Μαθηματικός συμβολισμός ΜΟΝΟ σε απλό Unicode κείμενο, ΟΧΙ LaTeX:
   - δυνάμεις: x^(2), 2^(n+1)   - δείκτες: a_(1), x_(0)
   - ρίζες: √, ³√   - κλάσματα: (α+β)/(γ-δ) ή 3/4
   - σύμβολα: ≤ ≥ ≠ ≈ ± · π Δ α β γ θ ∈ ∞ → ⇒ ⇔
   - χρησιμοποίησε το < και > κανονικά για ανισότητες.
5. Αν η άσκηση χρειάζεται σχήμα, περιέγραψέ το με λόγια (δεν μπορείς να σχεδιάσεις).
6. Μην βγάζεις τίποτα εκτός από την κλήση του εργαλείου."""

TOOL = {
    "name": "submit_exercises",
    "description": "Υποβολή των παραγόμενων ασκήσεων με τις λύσεις τους.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Τίτλος θεματικής ενότητας (Ελληνικά)"},
            "exercises": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Σύντομος τίτλος, π.χ. 'Δευτεροβάθμια εξίσωση'"},
                        "difficulty": {"type": "string", "enum": ["Εύκολο", "Μέτριο", "Δύσκολο"]},
                        "statement": {"type": "string", "description": "Εκφώνηση. Υποερωτήματα σε νέες γραμμές: α), β), γ)"},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "explanation": {"type": "string"},
                                },
                                "required": ["title", "explanation"],
                            },
                        },
                        "final_answer": {"type": "string"},
                        "tip": {"type": "string", "description": "Προαιρετική συμβουλή / συνηθισμένο λάθος"},
                    },
                    "required": ["title", "difficulty", "statement", "steps", "final_answer"],
                },
            },
        },
        "required": ["topic", "exercises"],
    },
}


def generate_exercises(source: str, args: argparse.Namespace) -> dict:
    """Ζητά τις ασκήσεις σε μικρές παρτίδες, ώστε η απάντηση να μην κόβεται."""
    import anthropic

    client = anthropic.Anthropic()  # διαβάζει ANTHROPIC_API_KEY
    BATCH = 4
    total = args.count

    def build_prompt(n: int, first: int, titles: list[str]) -> str:
        avoid = ("\nΜην επαναλάβεις ασκήσεις με αυτούς τους τίτλους: " + "; ".join(titles)) if titles else ""
        return (
            f"Τάξη: {args.grade or 'δεν δόθηκε (συμπέρανέ την από το κείμενο)'}\n"
            f"Κεφάλαιο: {args.chapter or '-'} | Ενότητα: {args.section or '-'} | Σελίδες: {args.pages or '-'}\n"
            f"Επίπεδο δυσκολίας: {DIFFICULTY_EL[args.difficulty]} — {DIFFICULTY_GUIDE[args.difficulty]}\n"
            f"Συνολικός αριθμός ασκήσεων: {total}\n\n"
            f"=== ΑΠΟΣΠΑΣΜΑ ΒΙΒΛΙΟΥ ===\n{source}\n=== ΤΕΛΟΣ ΑΠΟΣΠΑΣΜΑΤΟΣ ===\n\n"
            f"Δημιούργησε {n} ασκήσεις: τις υπ' αριθμόν {first} έως {first + n - 1} από τις {total}.{avoid}"
        )

    def call(prompt: str, force: bool):
        kwargs = dict(
            model=args.model,
            max_tokens=12000,
            system=SYSTEM_PROMPT,
            tools=[TOOL],
            messages=[{"role": "user", "content": prompt}],
            tool_choice={"type": "tool", "name": "submit_exercises"} if force else {"type": "auto"},
        )
        with client.messages.stream(**kwargs) as stream:
            return stream.get_final_message()

    def find_result(msg):
        for block in msg.content:
            if block.type == "tool_use" and block.name == "submit_exercises":
                return block.input
        return None

    state = {"force": True}  # γίνεται False αν το μοντέλο δεν υποστηρίζει forced tool_choice

    def get_batch(n: int, first: int, titles: list[str]) -> dict:
        prompt = build_prompt(n, first, titles)
        for attempt in range(1, 4):
            try:
                msg = call(prompt, state["force"])
            except anthropic.BadRequestError as e:
                # Ορισμένα μοντέλα δεν υποστηρίζουν εξαναγκασμένο tool_choice.
                if state["force"] and "tool_choice" in str(e):
                    state["force"] = False
                    msg = call(prompt, False)
                else:
                    raise
            res = find_result(msg)
            if res and res.get("exercises"):
                return res
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            print(f"[!] Προσπάθεια {attempt}: δεν ελήφθησαν ασκήσεις "
                  f"(stop_reason={msg.stop_reason}). {text[:300]}", file=sys.stderr)
            prompt += ("\n\nΧρησιμοποίησε ΥΠΟΧΡΕΩΤΙΚΑ το εργαλείο submit_exercises "
                       "και κράτα τις λύσεις συνοπτικές.")
        raise RuntimeError("Το μοντέλο δεν επέστρεψε ασκήσεις μετά από 3 προσπάθειες.")

    exercises: list[dict] = []
    topic = ""
    done = 0
    while done < total:
        n = min(BATCH, total - done)
        print(f"   … ασκήσεις {done + 1}-{done + n} από {total}")
        res = get_batch(n, done + 1, [e.get("title", "") for e in exercises])
        topic = topic or res.get("topic", "")
        exercises += res["exercises"]
        done += n
    return {"topic": topic, "exercises": exercises}


# --------------------------------------------------------------------------- #
# 3. Δημιουργία PDF (ReportLab, με ελληνική γραμματοσειρά)
# --------------------------------------------------------------------------- #
def find_fonts(custom: str | None) -> tuple[str, str]:
    """Επιστρέφει (κανονική, έντονη) γραμματοσειρά με υποστήριξη ελληνικών."""
    candidates: list[tuple[str, str]] = []
    if custom:
        candidates.append((custom, custom))
    try:
        import matplotlib
        d = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        candidates.append((str(d / "DejaVuSans.ttf"), str(d / "DejaVuSans-Bold.ttf")))
    except Exception:
        pass
    candidates += [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for reg, bold in candidates:
        if Path(reg).exists():
            return reg, (bold if Path(bold).exists() else reg)
    sys.exit("Δεν βρέθηκε γραμματοσειρά με ελληνικά. Εγκαταστήστε DejaVu Sans ή δώστε --font path/to/font.ttf")


def fmt(text: str) -> str:
    """Escape XML και μετατροπή x^(2) -> <super>, a_(1) -> <sub>, νέες γραμμές -> <br/>."""
    text = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\^\(([^()]*)\)", r"<super>\1</super>", text)
    text = re.sub(r"_\(([^()]*)\)", r"<sub>\1</sub>", text)
    # x^2 (μονό ψηφίο/γράμμα χωρίς παρένθεση) για ασφάλεια
    text = re.sub(r"\^([0-9nxyk])", r"<super>\1</super>", text)
    return text.replace("\n", "<br/>")


def build_pdf(data: dict, args: argparse.Namespace, out_path: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

    reg, bold = find_fonts(args.font)
    pdfmetrics.registerFont(TTFont("GR", reg))
    pdfmetrics.registerFont(TTFont("GR-B", bold))
    pdfmetrics.registerFontFamily("GR", normal="GR", bold="GR-B", italic="GR", boldItalic="GR-B")

    base = ParagraphStyle("base", fontName="GR", fontSize=10.5, leading=15)
    title = ParagraphStyle("title", parent=base, fontName="GR-B", fontSize=20, leading=26, alignment=TA_CENTER)
    sub = ParagraphStyle("sub", parent=base, fontSize=10, alignment=TA_CENTER, textColor=colors.grey)
    h1 = ParagraphStyle("h1", parent=base, fontName="GR-B", fontSize=15, leading=20,
                        textColor=colors.HexColor("#1F3A68"), spaceBefore=6, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=base, fontName="GR-B", fontSize=12, leading=16, spaceBefore=10, spaceAfter=4)
    step_t = ParagraphStyle("step_t", parent=base, fontName="GR-B", textColor=colors.HexColor("#1F3A68"))
    step_b = ParagraphStyle("step_b", parent=base, leftIndent=14)
    ans = ParagraphStyle("ans", parent=base, fontName="GR-B")
    tip = ParagraphStyle("tip", parent=base, fontSize=9.5, textColor=colors.HexColor("#7A5200"))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("GR", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(A4[0] / 2, 1.2 * cm, f"Σελίδα {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Ασκήσεις Μαθηματικών", author="Math Exercise Agent")
    story = []
    exercises = data.get("exercises", [])

    # Εξώφυλλο / κεφαλίδα
    story += [Paragraph("Ασκήσεις Μαθηματικών", title), Spacer(1, 4),
              Paragraph(fmt(data.get("topic", "")), sub), Spacer(1, 2)]
    meta = [f"Κεφάλαιο: {args.chapter or '-'}", f"Ενότητα/Σελίδες: {args.section or args.pages or '-'}",
            f"Δυσκολία: {DIFFICULTY_EL[args.difficulty]}", f"Ασκήσεις: {len(exercises)}"]
    story += [Paragraph(" &nbsp;|&nbsp; ".join(meta), sub), Spacer(1, 6),
              HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1F3A68")), Spacer(1, 10)]

    def exercise_block(i: int, ex: dict) -> list:
        head = Table([[Paragraph(f"Άσκηση {i}", ParagraphStyle("hd", parent=base, fontName="GR-B", textColor=colors.white)),
                       Paragraph(f"{fmt(ex.get('title', ''))} &nbsp;·&nbsp; {ex.get('difficulty', '')}",
                                 ParagraphStyle("hd2", parent=base, textColor=colors.white))]],
                     colWidths=[3 * cm, 14 * cm])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1F3A68")),
                                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return [head, Spacer(1, 4), Paragraph(fmt(ex["statement"]), base), Spacer(1, 8)]

    def solution_block(i: int, ex: dict) -> list:
        parts = [Paragraph(f"Λύση Άσκησης {i}", h2)]
        for n, st in enumerate(ex.get("steps", []), 1):
            parts.append(KeepTogether([
                Paragraph(f"Βήμα {n}: {fmt(st['title'])}", step_t),
                Paragraph(fmt(st["explanation"]), step_b), Spacer(1, 4)]))
        box = Table([[Paragraph(f"Απάντηση: {fmt(ex['final_answer'])}", ans)]], colWidths=[17 * cm])
        box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#2E7D32")),
                                 ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF5EA")),
                                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        parts += [Spacer(1, 2), box]
        if ex.get("tip"):
            parts += [Spacer(1, 4), Paragraph(f"Συμβουλή: {fmt(ex['tip'])}", tip)]
        parts.append(Spacer(1, 10))
        return parts

    if args.layout == "inline":
        for i, ex in enumerate(exercises, 1):
            story += exercise_block(i, ex) + solution_block(i, ex)
            story.append(HRFlowable(width="100%", thickness=0.4, color=colors.lightgrey))
            story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("Μέρος Α΄ — Ασκήσεις", h1))
        for i, ex in enumerate(exercises, 1):
            story += exercise_block(i, ex)
        story += [PageBreak(), Paragraph("Μέρος Β΄ — Αναλυτικές Λύσεις", h1)]
        for i, ex in enumerate(exercises, 1):
            story += solution_block(i, ex)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


# --------------------------------------------------------------------------- #
# 4. CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Πράκτορας ασκήσεων Μαθηματικών από online βιβλίο.")
    ap.add_argument("--url", help="URL του βιβλίου (HTML ή PDF)")
    ap.add_argument("--file", help="Τοπικό αρχείο PDF/HTML στον υπολογιστή σας")
    ap.add_argument("--chapter", help="Αριθμός κεφαλαίου, π.χ. 2")
    ap.add_argument("--pages", help="Σελίδες, π.χ. 45-52 ή 45,47,50-51 (μόνο για PDF)")
    ap.add_argument("--section", help="Ενότητα, π.χ. 3.7 (η ανάγνωση ξεκινά από εκεί)")
    ap.add_argument("--offset", type=int, default=0, help="σελίδα PDF = σελίδα βιβλίου + offset")
    ap.add_argument("--difficulty", choices=list(DIFFICULTY_EL), default="medium")
    ap.add_argument("--count", type=int, default=6, help="Πλήθος ασκήσεων")
    ap.add_argument("--grade", help="Τάξη, π.χ. 'Β΄ Λυκείου' (προαιρετικό)")
    ap.add_argument("--layout", choices=["separate", "inline"], default="separate",
                    help="separate: ασκήσεις και μετά λύσεις · inline: λύση κάτω από κάθε άσκηση")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--font", help="Διαδρομή .ttf με ελληνικά (προαιρετικό)")
    ap.add_argument("--out", default="askiseis.pdf")
    args = ap.parse_args()

    source_loc = args.file or args.url
    if not source_loc:
        ap.error("Δώστε --file (αρχείο στον υπολογιστή) ή --url.")
    if not (args.chapter or args.pages or args.section):
        ap.error("Δώστε --chapter, --section ή --pages.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Ορίστε τη μεταβλητή περιβάλλοντος ANTHROPIC_API_KEY.")

    pages = parse_pages(args.pages)
    print("⏬ Λήψη και ανάγνωση βιβλίου…")
    source = get_source_text(source_loc, args.chapter, pages, args.offset, args.section)
    print(f"✅ Εξήχθησαν {len(source)} χαρακτήρες. 🧠 Δημιουργία ασκήσεων…")
    data = generate_exercises(source, args)
    print(f"📝 Παρήχθησαν {len(data['exercises'])} ασκήσεις. 📄 Δημιουργία PDF…")
    build_pdf(data, args, args.out)
    print(f"🎉 Έτοιμο: {args.out}")


if __name__ == "__main__":
    main()
