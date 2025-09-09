import json
import re
from typing import Any, Optional


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\n|\n```$", re.MULTILINE)


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        # Remove leading ```lang and trailing ```
        s = _FENCE_RE.sub("", s)
    return s.strip()


def _extract_balanced(s: str, open_ch: str, close_ch: str) -> Optional[str]:
    """Extract the first balanced {...} or [...] JSON substring while respecting quotes/escapes."""
    start = s.find(open_ch)
    if start == -1:
        return None
    stack = []
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                stack.append(ch)
            elif ch == close_ch:
                if not stack:
                    # unmatched close
                    return None
                stack.pop()
                if not stack:
                    return s[start : i + 1]
    return None


def extract_json_string(text: str) -> str:
    """
    Given an LLM response string, return a canonical JSON string for the first valid
    top-level object or array. Handles Markdown code fences and surrounding prose.
    Raises ValueError if no valid JSON can be recovered.
    """
    if text is None:
        raise ValueError("Empty response")
    raw = _strip_fences(str(text))

    # First try: parse entire string
    try:
        obj = json.loads(raw)
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        pass

    # Second try: find first {...}
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        frag = _extract_balanced(raw, open_ch, close_ch)
        if frag:
            try:
                obj = json.loads(frag)
                return json.dumps(obj, ensure_ascii=False)
            except Exception:
                continue

    # Third try: remove any remaining backticks and try again
    raw2 = raw.replace("```", "").strip()
    try:
        obj = json.loads(raw2)
        return json.dumps(obj, ensure_ascii=False)
    except Exception as e:
        snippet = raw[:200].replace("\n", "\\n")
        raise ValueError(f"Invalid JSON from model. Snippet: {snippet}") from e
