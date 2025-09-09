import json, time
from agno.agent import Agent
from . import fast_model
from services.guidelines import load_guideline_profile
from models.contracts import StyleHints, Plan
from models.json_utils import extract_json_string

GL = load_guideline_profile(None)

DesignAgent = Agent(
    model=fast_model(),
    instructions=f"""
You are DesignAgent.
STRICT: Use GUIDELINES {json.dumps(GL, separators=(',',':'))}
OUTPUT: ONLY JSON StyleHints{{palette, fonts, master_layout, slide_layouts, image_style, spacing_rules}}
ENFORCE:
- Palette EXACT: {GL['brand']['palette']} (off-brand allowed? {GL['visual_rules']['allow_off_brand_colors']})
- Fonts: title={GL['brand']['fonts']['title_family']} (>= {GL['brand']['fonts']['title_min_pt']}pt), body={GL['brand']['fonts']['body_family']} (>= {GL['brand']['fonts']['body_min_pt']}pt)
- 16:9 {GL['visual_rules']['canvas_px']}, margins >= {GL['visual_rules']['margins_min_px']}px, whitespace >= {GL['visual_rules']['white_space_min_pct']}%
- Use templates: {GL['visual_rules']['templates']}; map each slide index to an existing layout name in slide_layouts
- image_style = "{GL['visual_rules']['image_style']}"
- Respect logo rules {GL['brand']['logo_rules']} and WCAG {GL['visual_rules']['wcag_contrast']}
JSON only.
""".strip()
)

async def design_style(plan: Plan, guideline: dict, sse_queue=None) -> StyleHints:
    payload = {"plan": plan.dict(), "guidelines": guideline}
    last_err = None
    for _ in range(3):
        t0 = time.time()
        if sse_queue:
            try:
                await sse_queue.put({"type": "agent", "role": "designer", "event": "attempt_start", "input_keys": list(payload.keys())})
            except Exception:
                pass
        out = await DesignAgent.arun(json.dumps(payload))
        try:
            style_json = extract_json_string(out.content)
            style = StyleHints.model_validate_json(style_json)
            if sse_queue:
                try:
                    await sse_queue.put({
                        "type": "agent", "role": "designer", "event": "attempt_success", 
                        "message": f"Created design with {style.fonts.get('title', 'default')} fonts and {style.master_layout} layout",
                        "ms": int((time.time()-t0)*1000), 
                        "fonts": style.fonts,
                        "palette": dict(list(style.palette.items())[:3]) if style.palette else {},  # First 3 colors
                        "master_layout": style.master_layout,
                        "output_sample": {"fonts": style.fonts, "image_style": style.image_style}
                    })
                except Exception:
                    pass
            return style
        except Exception as e:
            last_err = e
            payload["__retry_note"] = "Return VALID JSON object only. No code fences. Fields must be simple types (strings/ints)."
            if sse_queue:
                try:
                    await sse_queue.put({
                        "type": "agent", "role": "designer", "event": "attempt_error",
                        "message": f"Design attempt failed: {str(e)[:100]}...",
                        "error": str(e)
                    })
                except Exception:
                    pass
    raise ValueError(f"DesignAgent produced invalid JSON after retries: {last_err}")
