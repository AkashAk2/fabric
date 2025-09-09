import json, time
from agno.agent import Agent
from . import strong_model
from services.guidelines import load_guideline_profile
from models.contracts import QCItem
from models.json_utils import extract_json_string

GL = load_guideline_profile(None)

CriticAgent = Agent(
    model=strong_model(),
    instructions=f"""
You are CriticAgent. Evaluate the generated PPT against ALL guidelines {json.dumps(GL, separators=(',',':'))}
INPUT: {{plan, ppt_facts, guidelines}}
OUTPUT: ONLY list[QCItem{{criterion, result in ["PASS","FAIL"], reason, severity in ["BLOCKER","MAJOR","MINOR"]}}]

CRITICAL: Every QCItem MUST have:
- result: exactly "PASS" or "FAIL" (no other values)
- severity: exactly "BLOCKER", "MAJOR", or "MINOR" (no other values, never "PASS")

CHECK (soft, but comprehensive):
- Tone "{GL['content_rules']['tone']}", avoid {GL['content_rules']['avoid']}, banned {GL['banned_phrases']}
- Structure adherence: {GL['storytelling_framework']}, sequence {GL['content_rules']['structures']['sequence']}
- Audience elements (Exec Takeaway / Technical Deep Dive) present when appropriate; split slides for mixed audiences
- Key concepts follow protocol: {GL['key_concepts_protocol']}
- Data standards: sources credible, visualized, labeled; citations format {GL['data_evidence']['citation_format']}
- Visual rhythm: avoid ≥3 heavy-text slides; images relevant; alt text present

Return JSON array only. Example format:
[{{"criterion": "Tone consistency", "result": "PASS", "reason": "Professional tone maintained", "severity": "MINOR"}}]
""".strip()
)

async def critique(plan_dict: dict, ppt_facts: dict, guideline: dict, sse_queue=None) -> list[QCItem]:
    payload = {"plan": plan_dict, "ppt_facts": ppt_facts, "guidelines": guideline}
    last_err = None
    for _ in range(3):
        t0 = time.time()
        if sse_queue:
            try:
                await sse_queue.put({"type": "agent", "role": "critic", "event": "attempt_start"})
            except Exception:
                pass
        out = await CriticAgent.arun(json.dumps(payload))
        try:
            json_str = extract_json_string(out.content)
            data = json.loads(json_str)
            # Sanitize each item to ensure valid enum values
            sanitized_items = []
            for item in data:
                if isinstance(item, dict):
                    # Ensure result is valid
                    result = item.get("result", "FAIL")
                    if result not in ["PASS", "FAIL"]:
                        result = "FAIL"
                    
                    # Ensure severity is valid (never use "PASS" as severity)
                    severity = item.get("severity", "MINOR")
                    if severity not in ["BLOCKER", "MAJOR", "MINOR"]:
                        severity = "MINOR"
                    
                    sanitized_items.append({
                        "criterion": str(item.get("criterion", "Unknown")),
                        "result": result,
                        "reason": str(item.get("reason", "No reason provided")),
                        "severity": severity
                    })
            
            items = [QCItem(**x) for x in sanitized_items]
            if sse_queue:
                try:
                    fails = [it for it in items if it.result == "FAIL"]
                    summary = f"QC: {len(items)-len(fails)} PASS, {len(fails)} FAIL"
                    fail_examples = [f"{it.criterion}: {it.reason}" for it in fails[:3]]
                    await sse_queue.put({
                        "type": "agent", "role": "critic", "event": "attempt_success",
                        "message": f"Quality review complete: {summary}",
                        "ms": int((time.time()-t0)*1000), 
                        "count": len(items), 
                        "summary": summary,
                        "fail_examples": fail_examples
                    })
                except Exception:
                    pass
            return items
        except Exception as e:
            last_err = e
            payload["__retry_note"] = "Return VALID JSON array of QCItem only. No code fences."
            if sse_queue:
                try:
                    await sse_queue.put({
                        "type": "agent", "role": "critic", "event": "attempt_error",
                        "message": f"Quality review failed: {str(e)[:100]}...",
                        "error": str(e)
                    })
                except Exception:
                    pass
    raise ValueError(f"CriticAgent produced invalid JSON after retries: {last_err}")
