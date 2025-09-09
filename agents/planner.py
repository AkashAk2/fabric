import json, time
from agno.agent import Agent
from . import fast_model
from services.guidelines import load_guideline_profile
from models.contracts import Plan
from models.json_utils import extract_json_string

GL = load_guideline_profile(None)

PlannerAgent = Agent(
    model=fast_model(),
    instructions=f"""
You are PlannerAgent.
STRICTLY follow GUIDELINES JSON: {json.dumps(GL, separators=(',',':'))}
OUTPUT: ONLY JSON Plan(topic, slides[Slide{{title, purpose in {GL['content_rules']['slide_types']}, bullets[Bullet{{text,note?}}], required_assets[]}}]).
ENFORCE:
- Slides: {GL['content_rules']['slide_count_min']}-{GL['content_rules']['slide_count_max']}
- Bullets per slide: {GL['content_rules']['bullets_per_slide_min']}-{GL['content_rules']['bullets_per_slide_max']} and each bullet <= {GL['content_rules']['bullet_char_limit']} chars
- One message per slide; tone "{GL['content_rules']['tone']}"
- Use structures {GL['content_rules']['structures']['preferred']} and sequence {GL['content_rules']['structures']['sequence']}
- Add specific slide types where applicable: Executive Summary, Case Studies, Action Plan, Appendix
- For key concepts (Business Transformation, Digital Core, Change Mgmt, Data Architecture, Cloud Transformation, Security/Governance, Industry-specific): ensure slides include the protocol: definition, business_analogy, technical_sidebar, diagram, case_study
- Avoid {GL['content_rules']['avoid']} and banned {GL['banned_phrases']}
- Mark visuals in required_assets, e.g. "image:concept:digital-core", "chart:bar"
JSON only.
""".strip()
)

async def make_plan(topic: str, context: str | None, sse_queue=None):
    payload = {"topic": topic, "context": context or ""}
    last_err = None
    for attempt in range(3):
        t0 = time.time()
        if sse_queue:
            try:
                await sse_queue.put({
                    "type": "agent", "role": "planner", "event": "attempt_start", "attempt": attempt+1,
                    "message": f"Planning attempt {attempt+1}: Creating slides for '{payload['topic']}'",
                    "input": {"topic": payload["topic"], "context_provided": bool(payload.get("context"))}
                })
            except Exception:
                pass
        out = await PlannerAgent.arun(json.dumps(payload))
        try:
            plan_json = extract_json_string(out.content)
            plan = Plan.model_validate_json(plan_json)
            if sse_queue:
                try:
                    slide_titles = [slide.title for slide in plan.slides[:5]]  # First 5 slide titles
                    slide_purposes = {}
                    for slide in plan.slides:
                        slide_purposes[slide.purpose] = slide_purposes.get(slide.purpose, 0) + 1
                        
                    await sse_queue.put({
                        "type": "agent", "role": "planner", "event": "attempt_success", "attempt": attempt+1,
                        "message": f"Created {len(plan.slides)} slides: {', '.join(slide_titles)}{'...' if len(plan.slides) > 5 else ''}",
                        "ms": int((time.time()-t0)*1000), 
                        "slides_total": len(plan.slides),
                        "slide_titles": slide_titles,
                        "slide_purposes": slide_purposes,
                        "output_sample": {"topic": plan.topic, "slide0": {"title": plan.slides[0].title if plan.slides else None}}
                    })
                except Exception:
                    pass
            return plan
        except Exception as e:
            last_err = e
            # Tighten instructions for subsequent attempts
            payload["__retry_note"] = "Return VALID JSON only. No code fences, no comments, start with { and end with }. Keep bullets as array."
            if sse_queue:
                try:
                    await sse_queue.put({
                        "type": "agent", "role": "planner", "event": "attempt_error", "attempt": attempt+1,
                        "message": f"Planning attempt {attempt+1} failed: {str(e)[:100]}...",
                        "error": str(e)
                    })
                except Exception:
                    pass
    raise ValueError(f"Planner produced invalid JSON after retries: {last_err}")
