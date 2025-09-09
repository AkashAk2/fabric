import json, time
from agno.agent import Agent
from . import fast_model
from models.contracts import Plan
from models.json_utils import extract_json_string

FixerAgent = Agent(
    model=fast_model(),
    instructions=(
        "You are FixerAgent.\n"
        "Input: {plan, failures:list[QCItem]}.\n"
        "Task: Return a revised Plan JSON ONLY that will PASS all BLOCKER/MAJOR failures on the next verification.\n"
        "Hard requirements you MUST enforce in the returned Plan: \n"
        "- Slide count stays within 8-20 and content sequence remains intact.\n"
        "- Every slide has a non-empty title and >=2 bullets, each bullet <=120 chars (trim gracefully with ellipsis, do not cut mid-word).\n"
        "- If any failure mentions 'image required', ensure that slide includes required_assets with an appropriate 'image:<tag>'.\n"
        "- If any failure mentions 'credible sources', replace non-approved sources with only these approved ones: 'Infosys Research', 'Gartner', 'Forrester', 'World Economic Forum'.\n"
        "- If any failure mentions 'citation format', ensure all citations use '[Source, Year]' format, not '(Source, Year)'.\n"
        "- Avoid merging title text with bullet points; keep one clear message per slide.\n"
        "- Use only allowed slide purposes and keep consistent tone.\n"
        "OUTPUT: JSON Plan only."
    )
)

async def fix_plan(plan: Plan, failures: list[dict], sse_queue=None) -> Plan:
    payload = {"plan": plan.dict(), "failures": failures}
    last_err = None
    for _ in range(3):
        t0 = time.time()
        if sse_queue:
            try:
                await sse_queue.put({
                    "type": "agent", "role": "fixer", "event": "attempt_start",
                    "message": f"Fixing {len(failures)} issues in presentation plan",
                    "failures": failures[:3]  # Show first 3 failures
                })
            except Exception:
                pass
        out = await FixerAgent.arun(json.dumps(payload))
        try:
            plan_json = extract_json_string(out.content)
            # Merge with original plan for missing fields before strict validation
            try:
                data = json.loads(plan_json)
            except Exception:
                data = {}
            if isinstance(data, dict) and "plan" in data and isinstance(data["plan"], dict):
                data = data["plan"]
            if not isinstance(data, dict):
                data = {}
            # preserve topic if missing/empty
            if not data.get("topic"):
                data["topic"] = plan.topic
            # preserve slides if missing/too short
            s = data.get("slides")
            if not isinstance(s, list) or len(s) < 8:
                data["slides"] = plan.dict()["slides"]
            new_plan = Plan.model_validate(data)
            if sse_queue:
                try:
                    await sse_queue.put({
                        "type": "agent", "role": "fixer", "event": "attempt_success",
                        "message": f"Successfully fixed plan: {len(new_plan.slides)} slides with revised content",
                        "ms": int((time.time()-t0)*1000)
                    })
                except Exception:
                    pass
            return new_plan
        except Exception as e:
            last_err = e
            payload["__retry_note"] = "Return VALID JSON Plan only. No code fences."
            if sse_queue:
                try:
                    await sse_queue.put({
                        "type": "agent", "role": "fixer", "event": "attempt_error",
                        "message": f"Fix attempt failed: {str(e)[:100]}...",
                        "error": str(e)
                    })
                except Exception:
                    pass
    raise ValueError(f"FixerAgent produced invalid JSON after retries: {last_err}")
