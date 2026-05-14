"""Generate `data/sample.pdf` — a small public-domain PDF for smoke tests.

Run once after a fresh clone:

    uv run python scripts/make_sample_pdf.py

Output: writes `data/sample.pdf` (overwrites if present).

Content: short adapted excerpts of Arthur Conan Doyle's *Adventures of Sherlock
Holmes* (public domain, Project Gutenberg) plus one deliberately-knowable page
of made-up facts (clinical fasting requirements) so the demo / eval can ask a
factoid question and verify the citation.

`reportlab` is a dev-only dependency; this script is not on the runtime path.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "data" / "sample.pdf"


# ---- Content ---------------------------------------------------------------
# Page 1: introductory excerpt.
# Page 2: knowable-fact page with a numbered list — good citation target.
# Page 3: continuation; lets multi-page chunk-page-boundedness be exercised.

PAGE_1 = """
<b>A Scandal in Bohemia</b><br/><br/>

To Sherlock Holmes she is always <i>the</i> woman. I have seldom heard him
mention her under any other name. In his eyes she eclipses and predominates the
whole of her sex. It was not that he felt any emotion akin to love for Irene
Adler. All emotions, and that one particularly, were abhorrent to his cold,
precise but admirably balanced mind.<br/><br/>

He was, I take it, the most perfect reasoning and observing machine that the
world has seen, but as a lover he would have placed himself in a false
position. He never spoke of the softer passions, save with a gibe and a sneer.
They were admirable things for the observer&mdash;excellent for drawing the
veil from men's motives and actions.<br/><br/>

But for the trained reasoner to admit such intrusions into his own delicate and
finely adjusted temperament was to introduce a distracting factor which might
throw a doubt upon all his mental results.
"""

PAGE_2 = """
<b>Pre-Procedure Fasting Requirements (Clinical Reference)</b><br/><br/>

The following requirements apply to patients scheduled for outpatient
procedures requiring sedation. Compliance is mandatory.<br/><br/>

<b>1. Fasting from solids</b><br/>
Patients are required to fast from solid food for a minimum of <b>8 hours</b>
prior to the scheduled procedure time. This includes light meals, snacks, and
all dairy products.<br/><br/>

<b>2. Fasting from clear liquids</b><br/>
Clear liquids (water, plain tea, black coffee without milk) are permitted up to
<b>2 hours</b> before the procedure. Beverages containing pulp, dairy, or
alcohol are not considered clear liquids.<br/><br/>

<b>3. Medications</b><br/>
Routine prescription medications may be taken with a small sip of water on the
morning of the procedure unless explicitly contraindicated by the prescribing
clinician. Diabetic patients should consult the pre-procedure team regarding
insulin adjustment.<br/><br/>

<b>4. Documentation</b><br/>
The pre-procedure team will confirm fasting status verbally on arrival.
Patients who have not complied with the fasting requirement will have the
procedure rescheduled to a later date.
"""

PAGE_3 = """
<b>The Speckled Band &mdash; opening</b><br/><br/>

On glancing over my notes of the seventy odd cases in which I have during the
last eight years studied the methods of my friend Sherlock Holmes, I find many
tragic, some comic, a large number merely strange, but none commonplace; for,
working as he did rather for the love of his art than for the acquirement of
wealth, he refused to associate himself with any investigation which did not
tend towards the unusual, and even the fantastic.<br/><br/>

Of all these varied cases, however, I cannot recall any which presented more
singular features than that which was associated with the well-known Surrey
family of the Roylotts of Stoke Moran. The events in question occurred in the
early days of my association with Holmes, when we were sharing rooms as
bachelors in Baker Street.<br/><br/>

It is possible that I might have placed them upon record before, but a promise
of secrecy was made at the time, from which I have only been freed during the
last month by the untimely death of the lady to whom the pledge was given.
"""


def build_pdf(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=1.0 * inch,
        bottomMargin=1.0 * inch,
        leftMargin=1.0 * inch,
        rightMargin=1.0 * inch,
        title="RAG Demo Sample PDF",
        author="Nymbl RAG Assessment fixture",
    )
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontSize = 11
    body.leading = 16

    story: list = []
    for page in (PAGE_1, PAGE_2, PAGE_3):
        story.append(Paragraph(page.strip(), body))
        story.append(Spacer(1, 0.2 * inch))
        story.append(PageBreak())
    # drop the trailing PageBreak so we end on page 3, not a blank page 4
    if story and isinstance(story[-1], PageBreak):
        story.pop()

    doc.build(story)


if __name__ == "__main__":
    build_pdf(OUTPUT)
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"wrote {OUTPUT} ({size_kb:.1f} KB, 3 pages)")
