"""PDF export — builds review HTML and prints it via QTextDocument + QPrinter."""
from pathlib import Path

from PyQt5.QtGui import QFont, QTextDocument
from PyQt5.QtPrintSupport import QPrinter


def _build_pdf_html(title, subtitle_line, questions, answers, results):
    """Build HTML for PDF export. Used by both AssessmentPage and PerformanceTab."""
    auto_graded = [r for r in results.values() if r in ("correct", "incorrect", "unanswered")]
    auto_correct = sum(1 for r in auto_graded if r == "correct")
    score_line = (
        f" &nbsp;|&nbsp; Score: <b>{auto_correct}/{len(auto_graded)}</b>"
        if auto_graded else ""
    )

    parts = [
        "<html><body style='font-family: Arial, sans-serif; font-size: 12pt; color: #333;'>",
        f"<h1 style='color: #1a2744; margin-bottom:4px;'>{title}</h1>",
        f"<p style='color: #888; font-size:10pt;'>{subtitle_line}{score_line}</p>",
        "<hr>",
    ]

    q_map = {q["id"]: q for q in questions}
    for i, q in enumerate(questions, 1):
        q_id = q.get("id", "")
        q_type = q.get("type", "")
        result = results.get(q_id, "unknown")
        answer = (answers or {}).get(q_id, {})

        if result == "correct":
            badge = "<span style='color:#1a7a3a; font-weight:700;'>&#10003; Correct</span>"
            border_color, bg_color = "#2a9e50", "#edfaf2"
        elif result == "incorrect":
            badge = "<span style='color:#b02020; font-weight:700;'>&#10007; Incorrect</span>"
            border_color, bg_color = "#c23b3b", "#fdf0f0"
        elif result == "unanswered":
            badge = "<span style='color:#b08a00; font-weight:700;'>&#8212; Unanswered</span>"
            border_color, bg_color = "#d0a020", "#fdf8e8"
        else:
            badge, border_color, bg_color = "", "#cccccc", "#ffffff"

        parts.append(
            f"<div style='border-left:4px solid {border_color}; background:{bg_color};"
            f" padding:10px 14px; margin-bottom:14px; border-radius:3px;'>"
        )
        parts.append(
            f"<p style='margin:0 0 4px 0;'><b>Q{i}. {q.get('title', '')}</b>"
            + (f" &nbsp;{badge}" if badge else "") + "</p>"
        )

        if q_type == "mc":
            options = q.get("options", [])
            correct_letter = q.get("correct_answer", "").upper()
            selected = answer.get("selected_letter", "").upper() if isinstance(answer, dict) else ""
            for j, opt in enumerate(options):
                letter = chr(ord("A") + j)
                if letter == correct_letter and letter == selected:
                    mark, color = "&#10003;", "#1a7a3a"
                elif letter == selected:
                    mark, color = "&#10007;", "#b02020"
                elif letter == correct_letter:
                    mark, color = "&#8594;", "#1a7a3a"
                else:
                    mark, color = "", "#555"
                parts.append(
                    f"<p style='margin:2px 0 2px 12px; color:{color};'>"
                    f"{mark} {letter}) {opt}</p>"
                )
        elif q_type == "open":
            student_text = (answer.get("text", "") or answer.get("value", "")) if isinstance(answer, dict) else str(answer)
            parts.append(
                f"<p style='margin:4px 0;'><b>Your answer:</b> "
                f"{student_text if student_text else '<i>No answer provided</i>'}</p>"
            )
            suggested = q.get("suggested_answer", "")
            if suggested:
                parts.append(
                    f"<p style='margin:4px 0; color:#1a6e38;'>"
                    f"<b>Suggested answer:</b> {suggested}</p>"
                )
        elif q_type == "fill_blank":
            selected_texts = answer.get("selected_texts", []) if isinstance(answer, dict) else []
            correct_answers = q.get("correct_answers", [])
            blanks = q.get("blanks", [])
            for b_idx, sel in enumerate(selected_texts):
                ci = correct_answers[b_idx] if b_idx < len(correct_answers) else -1
                correct_text = blanks[b_idx][ci] if b_idx < len(blanks) and 0 <= ci < len(blanks[b_idx]) else "?"
                if sel == correct_text:
                    mark = "&#10003;"
                    color = "#1a7a3a"
                else:
                    mark = f"&#10007; (correct: {correct_text})"
                    color = "#b02020"
                parts.append(
                    f"<p style='margin:2px 0 2px 12px; color:{color};'>"
                    f"Blank {b_idx + 1}: <code>{sel}</code> {mark}</p>"
                )
        elif answer is None:
            parts.append("<p style='color:#999; margin:4px 0;'><i>No answer provided.</i></p>")
        elif isinstance(answer, str):
            text = answer if answer else "<i>No answer provided.</i>"
            parts.append(f"<p style='margin:4px 0;'>{text}</p>")
        elif isinstance(answer, dict):
            if "selected_letters" in answer:
                letters = ", ".join(answer["selected_letters"])
                parts.append(f"<p style='margin:4px 0;'>Selected: <b>{letters}</b></p>")
                for txt in answer.get("selected_texts", []):
                    parts.append(f"<p style='margin:2px 0 2px 12px; color:#555;'>— {txt}</p>")
            elif "selected_letter" in answer:
                parts.append(
                    f"<p style='margin:4px 0;'>Selected: <b>{answer['selected_letter']}</b>"
                    f" — {answer['selected_text']}</p>"
                )

        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def _render_pdf(html, output_path):
    doc = QTextDocument()
    doc.setHtml(html)
    doc.setDefaultFont(QFont("Arial", 11))
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(Path(output_path).resolve()))
    printer.setPageMargins(20, 20, 20, 20, QPrinter.Millimeter)
    doc.print_(printer)
