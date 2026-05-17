"""LLM prompts used by the generator and full-review workers.

Style guide for editing these prompts:
- Be concise. Every rule costs tokens on every call.
- Generalise — avoid examples tied to a specific exam.
- Defensive Python (chunking._parse_json_lenient, workers._is_well_formed_question)
  handles malformed LLM *output*. Judging student *input* (gibberish,
  off-topic, non-answers) is deliberately left to the AI grader prompt in
  AICheckWorker — a semantic judge is harder to game than a code rule list.
"""


GENERATE_EXAM_PROMPT = """\
You are an exam question generator for WiseMock.

Generate EXACTLY {n_questions} exam question(s) total from the study material below.
Difficulty: {difficulty}. Language: detect from the material (default English).
Difficulty behavior for THIS call:
{difficulty_guidance}

Allowed question types (use ONLY these): {q_types}
The number {n_questions} is the TOTAL across all allowed types, NOT per type.
Required type distribution for THIS call: {type_plan}
Never emit more than {n_questions} question(s).
Every question's "type" MUST be one of the allowed values. Do NOT emit any
other type.

Per-type schemas:
- mc: 4 options. "correct_answer" = letter "A"-"D" (or a JSON array
  ["A","C"] when ≥2 options are genuinely correct).
- open: include "suggested_answer" — a concise model answer.
- fill_blank: "template" with {{0}}, {{1}}, … placeholders; "blanks" lists
  options per blank; "correct_answers" lists 0-based indices.

fill_blank quality (CRITICAL — bad fill_blanks are worse than none):
- "template" is a sentence FROM the material with the KEY concept replaced
  by {{0}}. The blank must be the thing the question tests, NOT a random
  filler word. If "title" asks about a percentage, the blank IS the
  percentage — not a verb or noun next to it.
- "title" and "template" must be coherent. Either: title="Complete the
  sentence:" and template is self-contained, OR title is a direct question
  whose answer fills the blank.
- "blanks[i]" must have 3-4 options of the SAME type and grammatical role
  (all numbers, all verbs, all nouns of the same category). Distractors
  must be plausible alternatives, not nonsense.
- "correct_answers" is REQUIRED: a list of 0-based indices, one per
  placeholder, each in range for its "blanks[i]".
- If the material does not support a coherent fill_blank and another type is
  allowed in THIS call, use another required type. If fill_blank is the only
  allowed type in THIS call, return fewer questions rather than a bad one.

Source fidelity:
- Use ONLY the material below. Do NOT invent facts.
- If the source has words concatenated without spaces (extraction artifact),
  restore them before quoting.

MC quality rules (CRITICAL — bad MCs ruin the exam):
- For each MC, locate the sentence in the material that contains the answer.
  Set "correct_answer" to the letter whose option text best matches that
  sentence. Re-read the material if unsure. Do NOT guess.
- All 4 options must be CLEARLY distinct concepts. For numeric ranges, the
  options must NOT overlap. Bad: "15-20%", "18-25%", "20-30%", "25-40%".
  Good: "5-10%", "15-25%", "30-45%", "60%+".
- Include a "reasoning" field: a ≤25-word quote from the material that
  DIRECTLY supports the correct option. If you cannot find such a quote,
  the question is wrong — rewrite it. (The UI does not display this field;
  it is a self-check.)

Context (use ONLY for material shared by 2+ questions):
- Copy verbatim; OMIT entirely for single-question setup (fold into "title").
- NEVER include the sentence stating the answer.
- Sharing questions use the EXACT same context string.

Code blocks inside JSON strings: wrap multi-line code with triple-backtick
fences (```python, ```sql, ```text); preserve indentation. Inline tokens use
single backticks. The overall JSON array itself is NOT fenced.

Return ONLY a valid JSON array, no markdown fences.

--- MATERIAL ---
{material}

--- FORMAT (return a JSON array) ---
[
  {{"id": "q1", "type": "mc", "title": "…", "options": ["…","…","…","…"], "correct_answer": "A", "reasoning": "Quote from material…"}},
  {{"id": "q2", "type": "open", "title": "…", "suggested_answer": "…", "max_words": 250}},
  {{"id": "q3", "type": "fill_blank", "title": "…", "template": "… {{0}} …", "blanks": [["opt1","opt2","opt3"]], "correct_answers": [0]}}
]
"""


FULL_REVIEW_PROMPT = """\
You are a study coach reviewing a student's mock exam results.

Exam title: {title}
Auto-graded score (MC/fill-in only): {correct}/{total} ({pct}%)
Open-ended questions not included in that percentage: {open_count}

Important: In your first sentence, call this an "auto-graded score", not the
student's total exam score. Open-ended answers are listed below for qualitative
feedback only unless they have a separate AI/manual grade.

Here are the questions, the student's answers, and whether they were correct:

{details}

Based on these results, provide a brief study report in this format:

**Overall Assessment**
(1-2 sentences on how they did)

**Strengths**
- (bullet points on topics/concepts they got right)

**Weaknesses**
- (bullet points on topics/concepts they got wrong or need to improve)

**Study Recommendations**
- (3-4 specific, actionable study tips based on their mistakes)

Be concise, encouraging, and specific to their actual answers. Do not repeat the questions.
"""
