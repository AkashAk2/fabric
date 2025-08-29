import os, json, re
from dotenv import load_dotenv
from pptx import Presentation
from pptx.util import Pt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from fastapi.responses import FileResponse
from agno.agent import Agent
from agno.models.google import Gemini

BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASEDIR, ".env"))

def bool_env(name: str, default=False):
    val = os.environ.get(name, str(default)).strip().lower()
    return val in ("1", "true", "yes", "y")

def make_agent() -> Agent:
    model = Gemini(
        id=os.environ.get("DEFAULT_MODEL", "gemini-1.5-flash"),
        vertexai=bool_env("GOOGLE_GENAI_USE_VERTEXAI", False),
        project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    return Agent(model=model)

def extract_json(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    return m.group(1) if m else text

def plan_ppt(topic: str, improvement_instructions=None, prev_plan=None, agent_context=None):
    agent = make_agent()
    base_prompt = f"You are a presentation planner. Topic: \"{topic}\"."
    if agent_context:
        base_prompt += f"\nContext: {agent_context}"
    base_prompt += """
Return ONLY valid JSON (no prose). Schema:
[
  {"title": "Slide title 1", "bullets": ["point 1", "point 2", "point 3"]},
  {"title": "Slide title 2", "bullets": ["point 1", "point 2"]}
]
Constraints:
- 6–15 slides total.
- Each slide: 2–5 concise bullets.
- No code fences.
- No commentary.
"""
    if improvement_instructions:
        base_prompt += f"\n\nRevise the plan to address the following feedback or failed criteria: {improvement_instructions}"
    if prev_plan:
        base_prompt += f"\n\nHere is the previous plan (JSON):\n{json.dumps(prev_plan, indent=2)}"
    resp = agent.run(base_prompt)
    text = getattr(resp, "content", None) or str(resp)
    json_text = extract_json(text)
    return json_text

def execute_ppt(plan):
    prs = Presentation()
    for slide in plan:
        title = slide.get("title", "").strip() or "Untitled"
        bullets = slide.get("bullets", []) or []
        slide_layout = prs.slide_layouts[1]
        slide_obj = prs.slides.add_slide(slide_layout)
        slide_obj.shapes.title.text = title
        body = slide_obj.shapes.placeholders[1].text_frame
        body.clear()
        for i, bullet in enumerate(bullets):
            para = body.add_paragraph() if i > 0 else body.paragraphs[0]
            para.text = str(bullet)
            para.level = 0
            para.font.size = Pt(20)
    out = os.path.join(BASEDIR, "output.pptx")
    prs.save(out)
    return out

def verify_ppt(plan):
    if not isinstance(plan, list) or len(plan) < 3:
        return False, "Too few slides or invalid JSON structure."
    for s in plan:
        if not isinstance(s, dict) or "title" not in s or "bullets" not in s:
            return False, "Slide missing 'title' or 'bullets'."
        if not isinstance(s["bullets"], list) or len(s["bullets"]) < 2:
            return False, f"Slide '{s.get('title','Untitled')}' has too few bullets."
    return True, "Verification passed."

def validate_ppt(file_path):
    try:
        prs = Presentation(file_path)
        if len(prs.slides) < 3:
            return False, "PPT has too few slides."
        return True, "Validation passed."
    except Exception as e:
        return False, str(e)

def quality_check_agent(plan, ppt_file, criteria_list):
    agent = make_agent()
    plan_summary = "\n".join([f"Slide: {s['title']}\nBullets: {', '.join(s['bullets'])}" for s in plan])
    criteria_str = "\n".join([f"- {c}" for c in criteria_list])
    prompt = f"""
You are a quality check agent for PowerPoint presentations. Here is the plan:
{plan_summary}

Here is a checklist of quality criteria:
{criteria_str}

For each criterion, respond with PASS or FAIL and a short reason. Return a JSON list like:
[
  {{"criterion": "...", "result": "PASS"/"FAIL", "reason": "..."}},
  ...
]
"""
    resp = agent.run(prompt)
    text = getattr(resp, "content", None) or str(resp)
    json_text = extract_json(text)
    try:
        results = json.loads(json_text)
    except Exception:
        results = [{"criterion": c, "result": "FAIL", "reason": "Could not parse LLM response."} for c in criteria_list]
    return results

def orchestrate(topic, criteria_list, agent_context=None):
    max_attempts = 5
    plan = None
    ppt_file = None
    failed_criteria = criteria_list.copy()
    qc_results = []
    improvement_instructions = None
    for attempt in range(1, max_attempts + 1):
        if plan is None or any(k in c.lower() for c in failed_criteria for k in ("slide","structure","title","section")):
            improvement_instructions = "; ".join(failed_criteria) if failed_criteria else None
            plan_json_text = plan_ppt(topic, improvement_instructions=improvement_instructions, prev_plan=plan, agent_context=agent_context)
            try:
                plan = json.loads(plan_json_text)
            except Exception:
                continue
            ok, _ = verify_ppt(plan)
            if not ok:
                continue
        if ppt_file is None or any(k in c.lower() for c in failed_criteria for k in ("format","visual","graph","text","source")):
            ppt_file = execute_ppt(plan)
            valid, _ = validate_ppt(ppt_file)
            if not valid:
                continue
        qc_results = quality_check_agent(plan, ppt_file, failed_criteria)
        failed_criteria = [r['criterion'] for r in qc_results if r.get('result','FAIL').upper() != 'PASS']
        if not failed_criteria:
            full = quality_check_agent(plan, ppt_file, criteria_list)
            return ppt_file, full
    final_results = quality_check_agent(plan, ppt_file, criteria_list)
    return None, final_results

app = FastAPI(title="Multi-Agent PPT Playground")

class GenerateRequest(BaseModel):
    topic: str
    agent_context: Optional[str] = None
    criteria_chunk: Optional[str] = None

@app.post("/generate")
def generate_ppt(req: GenerateRequest):
    topic = req.topic
    agent_context = req.agent_context or ""
    criteria_chunk = (req.criteria_chunk or "").strip()
    if criteria_chunk:
        crit = criteria_chunk[:2000] + (" [TRUNCATED]" if len(criteria_chunk) > 2000 else "")
        safe_text = json.dumps(crit)
        agent = make_agent()
        parse_prompt = f"""You are a helpful assistant. Given the following text, extract and return a JSON list of individual quality criteria for a PowerPoint presentation. Only return the JSON list, no commentary.
Text: {safe_text}
"""
        resp = agent.run(parse_prompt)
        text = getattr(resp, "content", None) or str(resp)
        json_text = extract_json(text)
        try:
            criteria_list = json.loads(json_text)
        except Exception:
            criteria_list = [c.strip() for c in criteria_chunk.split(",") if c.strip()]
    else:
        criteria_list = [
            "At least 6 slides",
            "Each slide has a title",
            "Each slide has at least 2 bullets",
            "No slide has more than 5 bullets"
        ]
    ppt_file, qc_results = orchestrate(topic, criteria_list, agent_context=agent_context)
    if ppt_file:
        return {"success": True, "ppt_file": ppt_file, "qc_results": qc_results}
    else:
        raise HTTPException(status_code=500, detail={"success": False, "qc_results": qc_results})

@app.get("/download")
def download_ppt():
    path = os.path.join(BASEDIR, "output.pptx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No PPT file found. Generate one first.")
    return FileResponse(path, media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation', filename='output.pptx')
