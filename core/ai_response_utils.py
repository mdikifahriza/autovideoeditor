"""Helpers for parsing model responses that are expected to be JSON."""

import json
import re


def _normalize_structured_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            pass
    if hasattr(value, "to_json_dict"):
        try:
            return value.to_json_dict()
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return dict(value.__dict__)
        except Exception:
            pass
    return None


def get_response_payload(response) -> tuple[str, object | None]:
    """Extract the richest usable payload from a GenAI response."""
    if response is None:
        return "", None

    parsed = _normalize_structured_value(getattr(response, "parsed", None))
    if isinstance(parsed, (dict, list)):
        try:
            return json.dumps(parsed, ensure_ascii=False), parsed
        except Exception:
            return "", parsed
    if isinstance(parsed, str) and parsed.strip():
        return parsed.strip(), parsed.strip()

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip(), None

    parts_text = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                parts_text.append(part_text.strip())
    if parts_text:
        joined = "\n".join(parts_text).strip()
        return joined, None

    return "", parsed


def clean_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_first_json_object(text: str) -> str | None:
    start = None
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start : i + 1]
    return None


def parse_json_object(raw_text: str) -> dict:
    cleaned = clean_json_text(raw_text)
    if not cleaned:
        raise json.JSONDecodeError("Respons model kosong", cleaned, 0)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    json_text = _extract_first_json_object(cleaned)
    if json_text:
        try:
            data = json.loads(json_text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            repaired = re.sub(r",\s*([}\]])", r"\1", json_text)
            try:
                data = json.loads(repaired)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

    raise json.JSONDecodeError("Gagal parse object JSON", cleaned, 0)


def parse_json_array(raw_text: str) -> list:
    cleaned = clean_json_text(raw_text)
    if not cleaned:
        raise json.JSONDecodeError("Respons model kosong", cleaned, 0)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            repaired = re.sub(r",\s*([}\]])", r"\1", match.group())
            data = json.loads(repaired)
            if isinstance(data, list):
                return data
    raise json.JSONDecodeError("Gagal parse array JSON", cleaned, 0)
