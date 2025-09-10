import json, time
from agno.agent import Agent
from . import fast_model
from services.guidelines import load_guideline_profile
from models.contracts import AssetManifest, Plan, StyleHints
from models.json_utils import extract_json_string

GL = load_guideline_profile(None)

ImageAgent = Agent(
    model=fast_model(),
    instructions=f"""
You are ImageAgent. Produce slide-specific prompts aligned with GUIDELINES {json.dumps(GL, separators=(',',':'))}
OUTPUT: ONLY AssetManifest{{images:[{{slide_index, prompt, alt_text}}]}}
RULES:
- Style: {GL['visual_rules']['image_style']}
- Subject alignment: {GL['imagery_policy']['subject_alignment']}
- Disallowed: {GL['imagery_policy']['disallowed']}
- Include composition cues; ensure prompts reflect the slide headline & bullets.
JSON only.
""".strip()
)

async def plan_images(plan: Plan, style: StyleHints, sse_queue=None) -> AssetManifest:
    payload = {"plan": plan.dict(), "style": style.dict()}
    last_err = None
    for _ in range(3):
        t0 = time.time()
        if sse_queue:
            try:
                await sse_queue.put({"type": "agent", "role": "image_agent", "event": "attempt_start"})
            except Exception:
                pass
        out = await ImageAgent.arun(json.dumps(payload))
        try:
            manifest_json = extract_json_string(out.content)
            manifest = AssetManifest.model_validate_json(manifest_json)
            # Ensure every image has alt_text; default to slide title
            for it in manifest.images:
                if not (it.alt_text and it.alt_text.strip()):
                    idx = it.slide_index if isinstance(it.slide_index, int) else -1
                    if 0 <= idx < len(plan.slides):
                        it.alt_text = plan.slides[idx].title
                    else:
                        it.alt_text = ""
            if sse_queue:
                try:
                    first = manifest.images[0] if manifest.images else None
                    image_details = []
                    for img in manifest.images[:3]:  # First 3 images
                        image_details.append({
                            "slide": img.slide_index + 1,
                            "prompt": img.prompt[:60] + "..." if len(img.prompt) > 60 else img.prompt
                        })
                    await sse_queue.put({
                        "type": "agent", "role": "image_agent", "event": "attempt_success", 
                        "message": f"Planned {len(manifest.images)} images for slides: {', '.join([f'slide {img.slide_index+1}' for img in manifest.images[:5]])}",
                        "ms": int((time.time()-t0)*1000), 
                        "images_total": len(manifest.images),
                        "image_details": image_details,
                        "output_sample": ({"slide_index": first.slide_index, "prompt": first.prompt} if first else None)
                    })
                except Exception:
                    pass
            return manifest
        except Exception as e:
            last_err = e
            payload["__retry_note"] = "Return VALID JSON only (AssetManifest). No code fences."
            if sse_queue:
                try:
                    await sse_queue.put({"type": "agent", "role": "image_agent", "event": "attempt_error", "error": str(e)})
                except Exception:
                    pass
    raise ValueError(f"ImageAgent produced invalid JSON after retries: {last_err}")
