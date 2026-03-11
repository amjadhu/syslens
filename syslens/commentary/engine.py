import json
from syslens.commentary.knowledge_base import WINDOWS_EVENT_KB, HEURISTIC_KB

FALLBACK_COMMENTARY = {
    "explanation": "No static commentary available for this event.",
    "concern": "none",
    "action": "Search online for the Event ID and provider name for more context.",
    "source": "none",
}

SYSTEM_PROMPT = """\
You are a Windows and macOS system diagnostics expert. Analyze system log events and return practical, plain-English commentary for each one.

Rules:
- "explanation": 1-2 sentences. What happened and why it might matter. No jargon.
- "concern": exactly one of: "ignore", "monitor", "investigate", "fix_now"
  - ignore: informational, no action needed
  - monitor: watch for recurrence, not urgent
  - investigate: dig deeper, could be a real problem
  - fix_now: data loss or stability risk, act immediately
- "action": 1 sentence starting with a verb. The single most useful thing the user should do. Use "No action needed." if appropriate.
- "source": always the string "claude"

Return ONLY a valid JSON object mapping each "ref" key to a commentary dict. No prose, no markdown fences.\
""".strip()


def _lookup_static(event_id: int | None, provider: str = "") -> dict | None:
    if event_id is None:
        return None
    entry = WINDOWS_EVENT_KB.get(event_id)
    if entry:
        return {**entry, "source": "static"}
    return None


def _build_user_prompt(unknown_events: list[dict]) -> str:
    lines = ["Analyze these system log events and return commentary for each:\n"]
    for ev in unknown_events:
        lines.append(
            f'ref={ev["ref"]} | id={ev.get("id", "N/A")} | '
            f'provider={ev.get("provider", "N/A")} | '
            f'level={ev.get("level", "N/A")} | '
            f'message={ev.get("message", "")[:200]}'
        )
    lines.append(
        '\nRespond with a single JSON object mapping each "ref" key to a commentary dict '
        'with keys: explanation, concern, action, source.'
    )
    return "\n".join(lines)


def _call_claude(unknown_events: list[dict], api_key: str) -> dict[str, dict]:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is required for AI commentary. "
            "Install it with: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(unknown_events)}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if model added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _heuristic_key(finding: dict) -> str:
    return finding.get("heuristic_key", "")


def annotate(data: dict, api_key: str | None = None) -> dict:
    unknowns: list[dict] = []
    ai_note: str | None = None

    # ── Step 1: static KB pass over event findings ────────────────────────────
    for category, findings in data.get("events", {}).items():
        for i, f in enumerate(findings):
            commentary = _lookup_static(f.get("id"), f.get("provider", ""))
            if commentary:
                f["commentary"] = commentary
            else:
                ref = f"evt_{category}_{i}"
                f["_ref"] = ref
                unknowns.append({**f, "ref": ref})

    # ── Step 2: Claude API for unknowns ──────────────────────────────────────
    if unknowns:
        if api_key:
            try:
                results = _call_claude(unknowns, api_key)
                # Attach results back to original findings
                for category, findings in data.get("events", {}).items():
                    for f in findings:
                        ref = f.pop("_ref", None)
                        if ref and ref in results:
                            f["commentary"] = results[ref]
                            f["commentary"]["source"] = "claude"
                        elif ref:
                            f["commentary"] = {**FALLBACK_COMMENTARY}
            except Exception as e:
                # Clean up _ref fields on failure
                for findings in data.get("events", {}).values():
                    for f in findings:
                        ref = f.pop("_ref", None)
                        if ref:
                            f["commentary"] = {**FALLBACK_COMMENTARY}

                err_type = type(e).__name__
                if "AuthenticationError" in err_type or "auth" in str(e).lower():
                    ai_note = "AI commentary skipped: invalid API key."
                elif "RateLimitError" in err_type:
                    ai_note = "AI commentary skipped: API rate limit reached."
                elif "JSONDecodeError" in err_type or "json" in str(e).lower():
                    ai_note = "AI commentary skipped: could not parse API response."
                else:
                    ai_note = f"AI commentary skipped: {e}"
        else:
            # No API key — clean up _ref, set fallback, add note
            for findings in data.get("events", {}).values():
                for f in findings:
                    f.pop("_ref", None)
                    if "commentary" not in f:
                        f["commentary"] = {**FALLBACK_COMMENTARY}
            ai_note = (
                f"{len(unknowns)} event(s) have no built-in commentary. "
                "Set ANTHROPIC_API_KEY or use --api-key for AI-powered analysis."
            )
    else:
        # All events matched static KB — clean up any stray _ref
        for findings in data.get("events", {}).values():
            for f in findings:
                f.pop("_ref", None)

    # ── Step 3: heuristic commentary (always static) ─────────────────────────
    for h in data.get("heuristics", []):
        key = _heuristic_key(h)
        kb_entry = HEURISTIC_KB.get(key)
        if kb_entry:
            h["commentary"] = {**kb_entry}
        else:
            h["commentary"] = {
                "explanation": h.get("message", ""),
                "concern": h.get("severity", "monitor"),
                "action": "Review this finding and take appropriate action.",
                "source": "static",
            }

    data["commentary_note"] = ai_note
    return data
