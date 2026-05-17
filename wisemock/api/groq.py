"""Groq Chat Completions client.

Single entry point: `groq_request(api_key, messages, ...)`.

Resilience model:
  1. Model waterfall: try a routing-mode-ordered list of models. On a
     rate-limit / 413 / transient error, advance to the next model instead
     of failing. Non-last models get ONE attempt (no long sleep — switching
     is cheaper than waiting). Only the LAST model does patient retry.
  2. Per-model TPM tracker: each model has its own Groq token bucket, so the
     8B running out must not block the 70B/Scout. Headers are cached per
     model and used to skip a saturated non-last model instantly.
"""
import json
import random
import re
import threading
import time
import urllib.error
import urllib.request

from wisemock.config import (
    GROQ_API_URL, ROUTING_MODES, QUALITY_FIRST, LOW_QUALITY_MODELS,
)


# Per-model TPM tracker. Groq enforces token-per-minute limits PER MODEL, so
# one global counter would be wrong the moment we switch models. Keyed by
# model name → {"remaining_tokens": int|None, "reset_at": float}.
_tpm_lock = threading.Lock()
_tpm_state = {}


def _tpm_get(model):
    """Return (creating if needed) the tracker entry for `model`. Caller must
    hold _tpm_lock."""
    entry = _tpm_state.get(model)
    if entry is None:
        entry = {"remaining_tokens": None, "reset_at": 0.0}
        _tpm_state[model] = entry
    return entry


def _parse_reset_duration(value):
    """Groq returns reset windows like '7.2s', '1m20s', '500ms', or a bare
    number-of-seconds. Returns seconds as float, or None if unparseable."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    # Bare number → seconds.
    try:
        return float(s)
    except ValueError:
        pass
    total = 0.0
    matched = False
    for num, unit in re.findall(r"([\d.]+)\s*(ms|s|m|h)", s):
        try:
            n = float(num)
        except ValueError:
            continue
        matched = True
        if unit == "ms":
            total += n / 1000
        elif unit == "s":
            total += n
        elif unit == "m":
            total += n * 60
        elif unit == "h":
            total += n * 3600
    return total if matched else None


def _record_rate_headers(model, headers):
    """Update `model`'s TPM tracker from a response's headers (200 or 429)."""
    if not headers:
        return
    remaining = headers.get("x-ratelimit-remaining-tokens")
    reset = headers.get("x-ratelimit-reset-tokens")
    if remaining is None and reset is None:
        return
    with _tpm_lock:
        entry = _tpm_get(model)
        if remaining is not None:
            try:
                entry["remaining_tokens"] = int(float(remaining))
            except (TypeError, ValueError):
                pass
        reset_secs = _parse_reset_duration(reset)
        if reset_secs is not None:
            entry["reset_at"] = time.time() + reset_secs


def _model_budget_ok(model, estimated_tokens):
    """Cheap, non-blocking check: can `model` likely cover this call right
    now? Cold cache (no header data yet) → True (attempt, don't skip).
    Used to skip a saturated NON-last model instantly instead of waiting."""
    with _tpm_lock:
        entry = _tpm_get(model)
        remaining = entry["remaining_tokens"]
        reset_at = entry["reset_at"]
    if remaining is None:
        return True  # no data — give it a shot
    if remaining >= estimated_tokens:
        return True
    # Budget exhausted but the window may have already rolled over.
    return (reset_at - time.time()) <= 0


def _wait_for_budget(model, estimated_tokens):
    """Patient wait for `model`'s window to reset — ONLY used for the last
    model in the waterfall. Capped at 65s: this is intentional so a daily
    quota (which resets at midnight UTC, not in 65s) fails fast instead of
    hanging the UI for hours."""
    with _tpm_lock:
        entry = _tpm_get(model)
        remaining = entry["remaining_tokens"]
        reset_at = entry["reset_at"]
    if remaining is None or remaining >= estimated_tokens:
        return
    wait = max(0.0, reset_at - time.time())
    if wait <= 0:
        return
    time.sleep(min(wait + 0.5, 65))


def _estimate_input_tokens(messages):
    """Rough heuristic: ~4 chars per token. Good enough for budget checks."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        total_chars += len(content)
    return total_chars // 4


def _parse_retry_after(http_error, body_text):
    """Prefer the Retry-After header; fall back to the 'try again in 7.2s'
    hint Groq embeds in the 429 body. Returns seconds (float) or None.
    """
    header = http_error.headers.get("retry-after") if http_error.headers else None
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    m = re.search(r"try again in\s+([\d.]+)\s*(ms|s)", body_text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        return val / 1000 if m.group(2).lower() == "ms" else val
    return None


def _build_request(api_key, model, messages, max_tokens, temperature):
    return urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "WiseMock/1.0 (compatible; Python urllib)",
        },
        method="POST",
    )


def _is_rate_limit(http_error, body_text):
    """413 (request too large for this model's TPM) and 429 both mean: try a
    model with a bigger bucket. Some tiers phrase it in the body instead."""
    if http_error.code in (429, 413):
        return True
    return bool(re.search(r"tokens per minute|rate limit",
                          body_text or "", re.IGNORECASE))


def _extract_text(resp):
    body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()


def _clean_api_key(api_key):
    """Normalize common paste artifacts before using the key in an HTTP header."""
    cleaned = str(api_key or "").strip()
    match = re.search(r"gsk_[A-Za-z0-9_-]+", cleaned)
    if match:
        cleaned = match.group(0)
    if not cleaned:
        raise ValueError("Enter your Groq API key before using AI features.")
    try:
        cleaned.encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError(
            "Invalid Groq API key. Paste only the key itself, starting with gsk_."
        )
    return cleaned


def _set_meta(meta, model):
    if meta is not None:
        meta["model"] = model
        meta["low_quality_fallback"] = model in LOW_QUALITY_MODELS


def groq_request(api_key, messages, max_tokens=4096, temperature=0.7, timeout=60,
                 max_retries=3, routing_mode="quality", allow_fallback=True,
                 meta=None):
    """Try models in `routing_mode` order, advancing on rate-limit / 413 /
    transient error. Non-last models get one quick attempt; only the last
    model waits and retries patiently. Returns the response text (signature
    unchanged for back-compat). `meta` (if a dict) gets {"model", \
    "low_quality_fallback"}."""
    api_key = _clean_api_key(api_key)
    models = ROUTING_MODES.get(routing_mode, QUALITY_FIRST)
    if not allow_fallback:
        models = models[:1]
    estimated = _estimate_input_tokens(messages) + max_tokens
    last_error = None

    for i, model in enumerate(models):
        is_last = i == len(models) - 1

        if not is_last:
            # Saturated non-last model → skip instantly (switching > waiting).
            if not _model_budget_ok(model, estimated):
                continue
            req = _build_request(api_key, model, messages, max_tokens, temperature)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    _record_rate_headers(model, resp.headers)
                    text = _extract_text(resp)
                    _set_meta(meta, model)
                    return text
            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                if e.code in (401, 400):
                    raise  # fatal: bad key / invalid prompt — no model fixes it
                if _is_rate_limit(e, body_text):
                    _record_rate_headers(model, e.headers)
                last_error = e
                continue  # rate-limit OR 5xx → next model
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = e
                continue  # transient / network → next model

        # Last model: patient — proactive wait + retry with capped backoff.
        _wait_for_budget(model, estimated)
        for attempt in range(max_retries + 1):
            req = _build_request(api_key, model, messages, max_tokens, temperature)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    _record_rate_headers(model, resp.headers)
                    text = _extract_text(resp)
                    _set_meta(meta, model)
                    return text
            except urllib.error.HTTPError as e:
                if e.code in (429, 413) and attempt < max_retries:
                    err_body = e.read().decode("utf-8", errors="replace")
                    _record_rate_headers(model, e.headers)
                    wait = _parse_retry_after(e, err_body)
                    if wait is None:
                        wait = 2 ** attempt + random.random()
                    # Cap is intentional: a daily-quota 429 resets at midnight
                    # UTC, not in seconds — fail fast instead of hanging.
                    wait = min(wait + 0.3, 30)
                    time.sleep(wait)
                    continue
                raise

    # Reached only if every model was budget-skipped without a real attempt.
    if last_error is not None:
        raise last_error
    raise RuntimeError(
        "All configured Groq models are currently rate-limited or unavailable."
    )


def _handle_worker_error(finished_err_signal, e):
    """Shared error handler for background workers that call Groq.

    `finished_err_signal` is any callable taking a single string (typically
    a Qt pyqtSignal's `.emit`).
    """
    if isinstance(e, urllib.error.HTTPError):
        err_body = e.read().decode("utf-8")
        try:
            err_msg = json.loads(err_body).get("error", {}).get("message", err_body)
        except Exception:
            err_msg = err_body
        if e.code == 401:
            finished_err_signal.emit("Invalid API key. Check your Groq key and try again.")
        elif e.code == 413:
            finished_err_signal.emit(
                "The request is too large for the available Groq model limit. "
                "Try a smaller custom exam size or a smaller study-material batch."
            )
        elif e.code == 429:
            if re.search(
                r"tokens per minute|requests per minute|try again in|rate limit",
                err_msg,
                re.IGNORECASE,
            ):
                finished_err_signal.emit(
                    "Groq rate limit reached. Wait about a minute and try again."
                )
            elif re.search(r"daily|monthly|quota|usage limit", err_msg, re.IGNORECASE):
                finished_err_signal.emit(
                    "Groq quota reached for this API key. Try again later or use another key."
                )
            else:
                finished_err_signal.emit(
                    "Groq rate limit reached. Wait about a minute and try again."
                )
        else:
            finished_err_signal.emit(f"API error {e.code}: {err_msg}")
    elif isinstance(e, json.JSONDecodeError):
        finished_err_signal.emit("AI returned invalid JSON. Try again.")
    elif isinstance(e, urllib.error.URLError):
        finished_err_signal.emit("Could not connect to Groq. Check your internet connection.")
    elif isinstance(e, TimeoutError):
        finished_err_signal.emit("Request timed out. Try again.")
    elif isinstance(e, ValueError):
        finished_err_signal.emit(str(e))
    else:
        finished_err_signal.emit(f"Unexpected error: {e}")
