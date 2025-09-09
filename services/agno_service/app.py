import os, json, uuid, asyncio, sys, pathlib
# Ensure project root is on sys.path for imports like models.* when executed directly
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from fastapi.responses import FileResponse
from models.contracts import OrchestratorState
from orchestrator import run_pipeline

BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASEDIR, ".env"))

app = FastAPI(title="Agno Multi-Agent PPT")

class GenerateRequest(BaseModel):
    topic: str
    agent_context: Optional[str] = None
    guideline_profile_id: Optional[str] = None



# Simple in-memory run manager for SSE streaming and run state
run_queues: dict = {}


KEEPALIVE_SECS = 15


async def _sse_event_generator(run_id: str):
    q: asyncio.Queue = run_queues.get(run_id)
    if q is None:
        # immediate close
        yield b""
        return
    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_SECS)
                # item should be a dict; send as JSON string
                payload = json.dumps(item, default=str)
                yield f"data: {payload}\n\n".encode("utf-8")
                if item.get("type") == "done":
                    break
            except asyncio.TimeoutError:
                # Heartbeat comment to keep proxies and clients alive
                yield b": keepalive\n\n"
    finally:
        # cleanup
        run_queues.pop(run_id, None)



async def _run_and_emit(run_id: str, req: GenerateRequest):
    q: asyncio.Queue = run_queues.get(run_id)
    if q is None:
        return
    await q.put({"type": "log", "message": "Run started"})
    # New pipeline with stages and SSE logs
    try:
        await q.put({"type": "agent", "role": "orchestrator", "stage": "start", "status": "RUNNING", "topic": req.topic})
        state = OrchestratorState(topic=req.topic, context=req.agent_context, guideline_profile_id=req.guideline_profile_id)
        final_state = await run_pipeline(state, sse_queue=q)
        await q.put({"type": "agent", "role": "orchestrator", "stage": "complete", "status": "PASS", "findings": {
            "qc_hard": [f.dict() for f in final_state.hard_findings],
            "qc_soft": [f.dict() for f in final_state.soft_findings]
        }})
        await q.put({"type": "done", "success": True, "ppt_file": final_state.ppt_path})
    except Exception as e:
        await q.put({"type": "error", "message": str(e)})
        await q.put({"type": "done", "success": False, "error": str(e)})


# Endpoint to continue a run with user input (skip/retry for failed criteria)
# legacy compatibility imports removed

class ContinueRunRequest(BaseModel):
    run_id: str
    dummy: Optional[bool] = None

@app.post("/continue-run")
async def continue_run(req: ContinueRunRequest):
    # With new orchestrator, runs are atomic; this endpoint is kept for compatibility
    return {"ok": False, "message": "Resume not supported in new pipeline."}


@app.post("/generate")
async def generate(req: GenerateRequest):
    state = OrchestratorState(topic=req.topic, context=req.agent_context, guideline_profile_id=req.guideline_profile_id)
    try:
        final_state = await run_pipeline(state)
        return {
            "success": True,
            "ppt_file": final_state.ppt_path,
            "qc_hard": [f.dict() for f in final_state.hard_findings],
            "qc_soft": [f.dict() for f in final_state.soft_findings],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/generate-stream")
async def generate_ppt_stream(req: GenerateRequest):
    """Start an orchestrator run and return a run_id. Clients can connect to /runs/{run_id}/stream to receive SSE events."""
    run_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    run_queues[run_id] = q
    # start background task
    asyncio.create_task(_run_and_emit(run_id, req))
    return {"run_id": run_id, "stream_url": f"/runs/{run_id}/stream"}


@app.get("/runs/{run_id}/stream")
def run_stream(run_id: str):
    if run_id not in run_queues:
        raise HTTPException(status_code=404, detail="run id not found")
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        _sse_event_generator(run_id),
        media_type='text/event-stream',
        headers=headers,
    )

@app.get("/download")
def download_ppt():
    path = os.path.join(BASEDIR, "output.pptx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No PPT file found. Generate one first.")
    return FileResponse(path, media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation', filename='output.pptx')
