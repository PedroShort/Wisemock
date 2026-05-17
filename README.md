# WiseMock

WiseMock is a desktop mock-exam application built for the Introduction to
Programming course at Nova SBE. It helps students turn study material into an
interactive timed exam, submit answers, review incorrect and historical
responses, and keep track of performance over time.

The active application is implemented in Python with PyQt5 and an embedded
HTML/WebEngine frontend. Legacy PyQt pages and widgets remain in the package as
a fallback path. WiseMock can run fully offline with a prepared JSON exam, and
it can also use Groq AI features to generate questions from study documents and
review open-ended answers.

## Highlights

- Load WiseMock exam files in `.json` or `.exam.json` format.
- Load one or more PDF, DOCX, or PPTX study files for AI generation.
- Generate new mock exams from study material.
- Support multiple-choice, fill-in-the-blank, and open-ended questions.
- Run timed exams with optional fullscreen mode, shuffled question order, and
  shuffled multiple-choice answer options.
- Grade multiple-choice and fill-in-the-blank answers locally.
- Review open-ended answers and produce study feedback with AI when a Groq API
  key is provided.
- Save performance history locally, export submitted answers, and export review
  material.
- Include a complete auto-graded sample exam so the app can be tested without
  AI access.

## Quick Start

From the project root:

```bash
pip install -r requirements.txt
python wiseflow.py
```

Alternative package entry point:

```bash
python -m wisemock
```

If you are using a virtual environment, create and activate it before installing
the requirements.

## Test Without a Groq API Key

WiseMock includes a loadable sample exam at:

```text
examples/sample_exam.json
```

After launching the app with the HTML/WebEngine frontend, click
`Try sample exam` on the setup screen, or load the file manually. This sample
contains 30 auto-graded programming questions across four sections: 23
multiple-choice questions and 7 fill-in-the-blank questions. It does not
require network access or a Groq API key.

This is the recommended reviewer path for quickly checking that the application
runs end to end for offline loading, timed exam flow, local grading, review,
history, and export. It does not exercise open-ended questions or AI review.

## Supported Inputs

| Input type | Purpose | Groq required |
| --- | --- | --- |
| `.json` | Load a prepared WiseMock exam file, including exams saved from WiseMock with the `.exam.json` suffix. | No |
| `.pdf` | Extract study material for exam generation | Yes for AI generation |
| `.docx` | Extract study material for exam generation | Yes for AI generation |
| `.pptx` | Extract slide material for exam generation | Yes for AI generation |

JSON exam files must be loaded alone. Multiple study documents can be loaded
together; their extracted text is combined with per-source headers before
generation. The loader enforces a 50 MB limit per file, a 100 MB combined limit
for multi-file imports, and at least 50 characters in each extracted study
document payload.

PDF extraction uses PyMuPDF, reconstructs text by page, and serializes detected
PDF tables as Markdown. DOCX extraction reads paragraphs, and PPTX extraction
reads text-frame content from slides. OCR for scanned or image-heavy PDF pages
is best-effort, runs only when the page looks like it needs OCR, and requires
both the Python OCR packages and the Tesseract system binary.

### WiseMock JSON Structure

You can create your own `.json` exam file and load it directly. Here is a tiny Portuguese survival exam:

```json
{
  "title": "Portuguese Survival Exam",
  "questions": [
    {"id": "q1", "type": "mc", "title": "What is the correct emergency move when someone offers you a pastel de Belem?", "options": ["Refuse politely", "Ask for a salad instead", "Eat it before it gets cold", "Start a spreadsheet about custard"], "correct_answer": "C"},
    {"id": "q2", "type": "fill_blank", "title": "Complete the sentence:", "template": "The capital of Portugal is {0}.", "blanks": [["Porto", "Lisbon", "Madrid", "Pastelaria"]], "correct_answers": [1]},
    {"id": "q3", "type": "open", "title": "Explain why coffee and a pastel de nata can be a valid study strategy before an exam.", "suggested_answer": "A strong answer mentions morale, energy, cultural wisdom, and not covering the keyboard in custard.", "max_words": 120}
  ],
  "sections": [
    {"name": "Section I", "questions": ["q1", "q2", "q3"]}
  ]
}
```

`sections[].questions` can contain question IDs, as shown above, when those IDs
refer to objects in the top-level `questions` list. Section entries can also
embed full question objects; that embedded-object form lets the loader rebuild
the top-level `questions` list if it is missing. WiseMock exports `.exam.json`
files with cleaned question objects and no runtime answer state. A top-level
`questions` list remains the recommended shape.

## Groq AI Features

A Groq API key unlocks the AI-assisted parts of the application:

- generating mock questions from study material;
- reviewing open-ended answers;
- generating study reports after submission.

The app uses Groq through direct HTTP requests, so there is no separate Groq pip
package in `requirements.txt`. Document text and answer content are sent to Groq
only when AI features are used.

### Model Selection and Resilience

WiseMock does not pin a single model. One Groq API key is used to route each
request through an ordered list of models, falling back automatically when a
model is rate-limited, returns `413 Request too large`, or is temporarily
unavailable:

- **Generation / study reports** prefer higher-quality models and
  only fall back to a smaller, faster model as a last resort. When the
  last-resort model is used during exam generation, the generation screen shows
  a notice to review the questions carefully.
- **Large documents** prefer the model with the highest tokens-per-minute
  budget first and use chunking/sampling to reduce request-size failures.
  A provider `413 Request too large` can still occur and is handled by the same
  fallback path.
- **Open-answer grading never falls back to the low-quality model.** An
  unreliable score shown as if it were trustworthy is worse than a grade
  being temporarily unavailable; if every quality model is exhausted or fails,
  the app surfaces the grading error instead of guessing with the low-quality
  model.

Per-model token-per-minute budgets are tracked separately, so one exhausted
model does not block the others. Request-per-minute and quota errors are handled
when Groq returns them. This keeps normal single-document generation practical
within Groq's free tier without manual model configuration.

Generation settings in the active HTML frontend use a difficulty slider from
1 to 10 and size presets of small 10, medium 20, large 30, or custom 1 to 200
questions. These are target budgets: malformed, duplicate, or unsupported
questions returned by the model are dropped, so the final generated exam can be
smaller than the target.

### Getting a Free API Key

1. Create a free account at https://console.groq.com/keys
2. Click "Create API Key" and copy the key (it starts with `gsk_`).
3. In WiseMock: paste the key in the API Key field on the setup screen,
   or after submitting an exam click `✨ Activate AI` to add it then.
4. The key lives only in memory for the current session — WiseMock never
   writes it to disk.

Without a key, the app still loads any pre-built JSON exam (including the
included sample) and grades multiple-choice and fill-in-the-blank answers
locally.

## Exam Data Model

WiseMock exams are represented as JSON. A typical exam includes:

- `title`: exam title shown in the UI;
- `questions`: recommended flat list used by summaries, grading, exports, and
  section resolution;
- `sections`: optional structured grouping used by the exam display. When
  sections are present, runtime preparation uses the section question order and
  shuffles within each section when shuffling is enabled.

Question types:

- `mc`: multiple-choice question with `options` and `correct_answer`. The
  common documented form is one correct letter such as `"C"`; runtime grading
  also accepts a list of letters for multi-answer MC questions, but PDF review
  export is oriented around single-answer MC questions;
- `fill_blank`: fill-in-the-blank question with `template`, `blanks`, and
  `correct_answers`;
- `open`: open-ended question with an optional suggested answer for AI review.
  Open-ended questions are not included in the auto-graded score.

See `examples/sample_exam.json` for a complete working exam file.

## Project Structure

```text
.
├── wiseflow.py                 # Compatibility launcher from the project root
├── .gitignore                  # Local runtime/build artifact exclusions
├── requirements.txt            # Python dependencies
├── examples/
│   ├── sample_exam.json        # Full auto-graded sample exam for offline testing
│   ├── submitted_answers.json  # Example JSON submission export
│   └── submitted_answers.pdf   # Example PDF submission export
├── tests/                      # unittest coverage for loaders, grading, prompts, UI text
└── wisemock/                   # Active application package
    ├── app.py                  # QApplication setup and main window selection
    ├── __main__.py             # Enables: python -m wisemock
    ├── config.py               # Paths, capability flags, optional dependency checks
    ├── api/                    # Groq API request helpers
    ├── assets/                 # HTML frontend, bundled fonts, icon assets
    ├── core/                   # Input loading, extraction, chunking, grading, history
    ├── export/                 # PDF and exam-file export helpers
    ├── pages/                  # Legacy/fallback PyQt pages
    ├── runtime/                # WebEngine window, JS/Python bridge, runtime exam state
    ├── widgets/                # Legacy/fallback PyQt widgets
    └── workers.py              # Background AI workers
```

`wiseflow.py` remains at the root as a convenient launcher and compatibility
facade. New code should generally import from the `wisemock` package directly.

## Reviewer Guide

For a quick code review, start with these files:

- `wiseflow.py` - root launcher and compatibility layer.
- `wisemock/app.py` - application startup.
- `wisemock/runtime/bridge.py` - connection between the HTML frontend and
  Python logic.
- `wisemock/runtime/prepare.py` - runtime exam preparation, shuffling, and
  answer normalization.
- `wisemock/core/input_loading.py` - JSON/document import pipeline and limits.
- `wisemock/core/grading.py` - local grading logic.
- `wisemock/core/extract.py` - PDF/DOCX/PPTX extraction, PDF table extraction,
  and optional OCR text extraction.
- `wisemock/workers.py` - background Groq workers for generation and review.
- `wisemock/assets/wisemock_frontend.html` - main user interface.

Automated checks:

```bash
python -m unittest discover -s tests
```

Suggested manual review flow:

1. Install dependencies with `pip install -r requirements.txt`.
2. Start the app with `python wiseflow.py`.
3. Click `Try sample exam`.
4. Start the exam, answer a few questions, submit, and open the review.
5. Optionally add a Groq API key and use study documents or a custom exam with
   open-ended questions to test AI generation and feedback.

## Dependencies

`requirements.txt` installs the required GUI packages plus the Python-side
document/OCR packages used by optional extraction features. The app still checks
capabilities at runtime so missing extraction modules or missing Tesseract can
be reported gracefully.

Required for the main HTML/WebEngine UI:

- `PyQt5`
- `PyQtWebEngine`

Document/OCR support packages and tools:

- `pymupdf` for PDF extraction;
- `python-docx` for DOCX extraction;
- `python-pptx` for PPTX extraction;
- `pytesseract` and `Pillow` for OCR image handling;
- the Tesseract system binary for OCR.

On macOS, Tesseract can be installed with:

```bash
brew install tesseract
```

## Runtime Data

Performance history is stored outside the package at:

```text
~/.wiseflow/history.json
```

This keeps the source tree separate from local user data.

When an exam is submitted, the active HTML flow also writes
`submitted_answers.json` and, when Qt PDF support is available,
`submitted_answers.pdf` next to the loaded exam or source document. The JSON
export includes submitted answers and answer-key material for each question.
The PDF export is a rendered review document for submitted answers; it is
oriented around single-answer multiple-choice review and does not expose every
answer-key case that the JSON does. Neither export includes the Groq API key.
The checked-in `examples/submitted_answers.*` files are reference exports from
the sample exam; running the sample flow again can overwrite those tracked
files in place. History records can include date, title, score, time,
questions, answers, results, section names, and question IDs per section. The
Groq API key is kept in memory for the current session and is not written to
history or submission exports.

## Notes and Limitations

- The included sample exam works without AI or internet access and is the
  simplest way to test the offline app flow, but it contains no open-ended
  questions.
- Groq-powered generation, answer review, and study reports can make mistakes,
  so AI-generated exams and feedback should be reviewed before being used for
  real study or assessment.
- Groq features require a valid API key and network access. Provider rate
  limits still apply, but the model-fallback waterfall (see *Model Selection
  and Resilience*) handles many rate-limit and request-size errors
  automatically; under quota exhaustion, network failure, or heavy simultaneous
  load some AI features may still be temporarily unavailable.
- Very large, scanned, image-heavy, or poorly formatted documents may take
  longer to extract and may require OCR or manual cleanup.
- OCR is best-effort and depends on both Python packages and the system
  Tesseract installation.
- WiseMock is a practice/review tool, not a secure proctored exam environment;
  the local frontend receives answer-key data needed for grading and review.
- The legacy PyQt fallback pages and widgets do not mirror every workflow in
  the active HTML/WebEngine frontend. In particular, some newer JSON shapes and
  review/export paths are only complete in the active HTML runtime.
