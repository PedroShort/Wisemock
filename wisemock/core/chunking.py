"""Pure text-handling helpers used by the AI workers."""
import json
import re


def chunk_text(text: str, max_chars: int = 6000) -> list:
    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text[:max_chars]]


def _strip_markdown_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def _parse_json_lenient(raw: str):
    """Parse the LLM response as JSON, tolerating common LLM failure modes.

    Strategy (in order):
      1. Plain json.loads — works for clean responses.
      2. Strip prose before the first '[' or '{' and after the last ']' or '}'.
         Catches "Here is the JSON:\n[...]" or trailing "Hope this helps!".
      3. If response was truncated (no closing bracket), try to recover the
         partial JSON array by trimming to the last complete object and
         appending ']'. Better to keep N-1 questions than fail entirely.

    Raises json.JSONDecodeError if all strategies fail.
    """
    raw = (raw or "").strip()
    if not raw:
        raise json.JSONDecodeError("empty response", raw, 0)

    # Strategy 1: as-is.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: trim to the outermost [...] or {...}.
    start_array = raw.find("[")
    start_object = raw.find("{")
    if start_array >= 0 and (start_object < 0 or start_array < start_object):
        start = start_array
        end_char = "]"
    elif start_object >= 0:
        start = start_object
        end_char = "}"
    else:
        raise json.JSONDecodeError("no JSON delimiter found", raw, 0)

    end = raw.rfind(end_char)
    if end > start:
        candidate = raw[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 3: truncated array recovery. Walk objects from the start and
    # keep the last complete one. Only applies to arrays of objects (the
    # generator's output format).
    if end_char == "]":
        # Find the last completed `}` (closes a question object).
        last_obj_close = raw.rfind("}")
        if last_obj_close > start:
            repaired = raw[start:last_obj_close + 1] + "]"
            try:
                parsed = json.loads(repaired)
                if isinstance(parsed, list) and parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

    raise json.JSONDecodeError("could not repair JSON", raw, 0)
