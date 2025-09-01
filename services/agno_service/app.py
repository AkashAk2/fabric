import os, json, re, uuid, asyncio
from dotenv import load_dotenv
from pptx import Presentation
from pptx.util import Pt
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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

# Initialize Google/Vertex client from API key if provided, otherwise rely on ADC
API_KEY = os.getenv("GOOGLE_API_KEY")
try:
    # for google-generativeai
    import google.generativeai as genai  # type: ignore
    if API_KEY:
        genai.configure(api_key=API_KEY)
except Exception:
    pass

try:
    # for google-genai (if used in the project)
    from google import genai as genai2  # type: ignore
    if API_KEY and genai2 is not None:
        # Some versions accept environment variable or client init; set env as fallback
        os.environ["GOOGLE_API_KEY"] = API_KEY
        # if creating client instances in your code, you may need to pass key there
except Exception:
    pass


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
    # Prepare plan summary and criteria string
    plan_summary = json.dumps(plan, indent=2)
    criteria_str = "\n".join(f"- {c}" for c in criteria_list)
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



# Simple in-memory run manager for SSE streaming and run state
run_queues: dict = {}
run_states: dict = {}  # run_id -> dict with keys: criteria_list, skipped_criteria


async def _sse_event_generator(run_id: str):
    q: asyncio.Queue = run_queues.get(run_id)
    if q is None:
        # immediate close
        yield b""
        return
    try:
        while True:
            item = await q.get()
            # item should be a dict; send as JSON string
            payload = json.dumps(item, default=str)
            yield f"data: {payload}\n\n".encode("utf-8")
            if item.get("type") == "done":
                break
    finally:
        # cleanup
        run_queues.pop(run_id, None)



async def _run_and_emit(run_id: str, req: GenerateRequest):
    q: asyncio.Queue = run_queues.get(run_id)
    if q is None:
        return
    await q.put({"type": "log", "message": "Run started"})
    max_attempts = 5
    plan = None
    ppt_file = None
    failed_criteria = []
    qc_results = []
    improvement_instructions = None
    # Parse criteria and skipped criteria from run_states
    state = run_states.get(run_id)
    if state is not None:
        criteria_list = state.get("criteria_list", [])
        skipped_criteria = set(state.get("skipped_criteria", []))
    else:
        if req.criteria_chunk:
            criteria_list = [c.strip() for c in req.criteria_chunk.split(",") if c.strip()]
        else:
            criteria_list = [
                "At least 6 slides",
                "Each slide has a title",
                "Each slide has at least 2 bullets",
                "No slide has more than 5 bullets",
            ]
        skipped_criteria = set()
        run_states[run_id] = {"criteria_list": criteria_list, "skipped_criteria": list(skipped_criteria)}
    for attempt in range(1, max_attempts + 1):
        try:
            await q.put({"type": "log", "message": f"Attempt {attempt}..."})
            # Plan
            await q.put({"type": "log", "message": "Planning slides..."})
            plan_json_text = await asyncio.to_thread(plan_ppt, req.topic, improvement_instructions, plan, req.agent_context)
            try:
                plan = json.loads(plan_json_text)
                await q.put({"type": "log", "message": f"Plan created: {len(plan)} slides"})
            except Exception as e:
                await q.put({"type": "log", "message": f"Planning failed: {e}"})
                continue
            ok, _ = verify_ppt(plan)
            if not ok:
                await q.put({"type": "log", "message": "Plan verification failed."})
                continue
            # Execute
            await q.put({"type": "log", "message": "Rendering PPTX..."})
            try:
                ppt_file = await asyncio.to_thread(execute_ppt, plan)
                await q.put({"type": "log", "message": f"PPT saved: {ppt_file}"})
            except Exception as e:
                await q.put({"type": "log", "message": f"PPT generation failed: {e}"})
                continue
            valid, _ = validate_ppt(ppt_file)
            if not valid:
                await q.put({"type": "log", "message": "PPT validation failed."})
                continue
            # Quality check
            await q.put({"type": "log", "message": "Running quality checks..."})
            # Only check criteria that are not skipped
            active_criteria = [c for c in criteria_list if c not in skipped_criteria]
            qc_results = await asyncio.to_thread(quality_check_agent, plan, ppt_file, active_criteria)
            for r in qc_results:
                await q.put({"type": "qc", "criterion": r.get("criterion"), "result": r.get("result"), "reason": r.get("reason")})
            failed = [r for r in qc_results if r.get("result", "").upper() != "PASS"]
            if not failed:
                await q.put({"type": "log", "message": "All quality checks passed."})
                await q.put({"type": "done", "success": True, "ppt_file": ppt_file, "qc_results": qc_results})
                run_states.pop(run_id, None)
                return
            else:
                await q.put({"type": "log", "message": f"Quality checks found {len(failed)} failures."})
                # Pass failed criteria and reasons to LLM as improvement_instructions
                improvement_instructions = "; ".join([f"{r['criterion']}: {r['reason']}" for r in failed])
        except Exception as e:
            await q.put({"type": "log", "message": f"Error in attempt {attempt}: {e}"})
            continue
    # If we reach here, all attempts failed
    failed = [r for r in qc_results if r.get("result", "").upper() != "PASS"]
    if failed:
        await q.put({
            "type": "user_input_needed",
            "message": "Some criteria could not be satisfied after all attempts.",
            "failed_criteria": [
                {"criterion": r.get("criterion"), "reason": r.get("reason")} for r in failed
            ],
            "qc_results": qc_results,
            "run_id": run_id
        })
    else:
        await q.put({"type": "done", "success": False, "qc_results": qc_results})
    # Do not remove run_states here; allow resume


# Endpoint to continue a run with user input (skip/retry for failed criteria)
from fastapi import Body
from fastapi.responses import JSONResponse

class ContinueRunRequest(BaseModel):
    run_id: str
    skip_criteria: Optional[List[str]] = None

@app.post("/continue-run")
async def continue_run(req: ContinueRunRequest):
    run_id = req.run_id
    skip_criteria = set(req.skip_criteria or [])
    state = run_states.get(run_id)
    if not state:
        return JSONResponse(status_code=404, content={"error": "run_id not found or already completed"})
    # Update skipped_criteria
    prev_skipped = set(state.get("skipped_criteria", []))
    new_skipped = prev_skipped.union(skip_criteria)
    state["skipped_criteria"] = list(new_skipped)
    run_states[run_id] = state
    # Resume the run
    req_obj = GenerateRequest(
        topic="",  # Not used in resume, but required by signature
        agent_context=None,
        criteria_chunk=None
    )
    asyncio.create_task(_run_and_emit(run_id, req_obj))
    return {"ok": True, "message": "Run resumed", "run_id": run_id}


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



@app.post("/generate-stream")
async def generate_ppt_stream(req: GenerateRequest):
    """Start an orchestrator run and return a run_id. Clients can connect to /runs/{run_id}/stream to receive SSE events."""
    run_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    run_queues[run_id] = q
    # start background task
    asyncio.create_task(_run_and_emit(run_id, req))
    return {"run_id": run_id, "stream_url": f"/agents/runs/{run_id}/stream"}


@app.get("/runs/{run_id}/stream")
def run_stream(run_id: str):
    if run_id not in run_queues:
        raise HTTPException(status_code=404, detail="run id not found")
    return StreamingResponse(_sse_event_generator(run_id), media_type='text/event-stream')

@app.get("/download")
def download_ppt():
    path = os.path.join(BASEDIR, "output.pptx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No PPT file found. Generate one first.")
    return FileResponse(path, media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation', filename='output.pptx')
