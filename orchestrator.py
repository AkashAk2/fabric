import asyncio, json, os
from typing import List, Optional
from models.contracts import OrchestratorState, QCItem, AssetManifest, ImageItem
from services.guidelines import load_guideline_profile
from services.images_backend import realize_manifest, make_backend
from agents.planner import make_plan
from agents.designer import design_style
from agents.image_agent import plan_images
from agents.critic import critique
from agents.fixer import fix_plan
from executors.ppt_executor import PPTExecutor
from executors.verifier import verify_pptx, extract_ppt_facts

MAX_ATTEMPTS = 2

async def run_pipeline(state: OrchestratorState, sse_queue: Optional[asyncio.Queue] = None):
    g = load_guideline_profile(state.guideline_profile_id)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if sse_queue:
            await sse_queue.put({"type": "stage", "name": "attempt", "attempt": attempt, "status": "RUNNING"})

        if not state.plan:
            if sse_queue:
                await sse_queue.put({"type": "stage", "name": "plan", "status": "RUNNING", "message": f"Planning presentation for topic: '{state.topic}'"})
            try:
                state.plan = await make_plan(state.topic, state.context, sse_queue=sse_queue)
                if sse_queue:
                    # Detailed plan summary
                    slide_summaries = []
                    for i, slide in enumerate(state.plan.slides):
                        slide_summaries.append({
                            "index": i+1,
                            "title": slide.title,
                            "purpose": slide.purpose, 
                            "bullet_count": len(slide.bullets),
                            "bullets": [b.text[:50] + "..." if len(b.text) > 50 else b.text for b in slide.bullets[:2]],  # First 2 bullets, truncated
                            "assets": slide.required_assets
                        })
                    await sse_queue.put({
                        "type": "stage", "name": "plan", "status": "DONE", 
                        "message": f"Created {len(state.plan.slides)} slides covering: {state.plan.topic}",
                        "slides_total": len(state.plan.slides),
                        "slide_details": slide_summaries
                    })
            except Exception as e:
                if sse_queue:
                    await sse_queue.put({"type": "error", "stage": "plan", "message": f"Planning failed: {str(e)}"})
                raise

        if not state.style:
            if sse_queue:
                await sse_queue.put({"type": "stage", "name": "design", "status": "RUNNING", "message": "Creating visual design and style guidelines"})
            try:
                state.style = await design_style(state.plan, g, sse_queue=sse_queue)
                if sse_queue:
                    await sse_queue.put({
                        "type": "stage", "name": "design", "status": "DONE",
                        "message": f"Design created with {state.style.fonts.get('title', 'default')} title font and {state.style.image_style[:50]}... image style",
                        "fonts": state.style.fonts,
                        "palette": state.style.palette,
                        "image_style": state.style.image_style,
                        "master_layout": state.style.master_layout
                    })
            except Exception as e:
                if sse_queue:
                    await sse_queue.put({"type": "error", "stage": "design", "message": f"Design failed: {str(e)}"})
                raise

        if not state.assets:
            if sse_queue:
                await sse_queue.put({"type": "stage", "name": "images", "status": "RUNNING", "message": "Planning and generating images for slides"})
            try:
                manifest = await plan_images(state.plan, state.style, sse_queue=sse_queue)
                # Backfill: ensure images for slides that require them
                want_image_idx = {i for i, sl in enumerate(state.plan.slides) if any((isinstance(a, str) and a.startswith("image:")) for a in sl.required_assets)}
                have_image_idx = {it.slide_index for it in manifest.images}
                missing = sorted(list(want_image_idx - have_image_idx))
                for i in missing:
                    sl = state.plan.slides[i]
                    prompt = f"{state.topic}: {sl.title}. Depict key idea: {', '.join(b.text for b in sl.bullets[:2])}. Style: {state.style.image_style}."
                    manifest.images.append(ImageItem(slide_index=i, prompt=prompt, alt_text=sl.title))
                
                if sse_queue:
                    image_summary = []
                    for img in manifest.images:
                        image_summary.append({
                            "slide": img.slide_index + 1,
                            "prompt": img.prompt[:80] + "..." if len(img.prompt) > 80 else img.prompt,
                            "alt_text": img.alt_text
                        })
                    await sse_queue.put({
                        "type": "stage", "name": "images", "status": "GENERATING",
                        "message": f"Generating {len(manifest.images)} images for slides",
                        "image_count": len(manifest.images),
                        "image_details": image_summary
                    })
                
                # Use env-driven backend; tests will default to Noop backend
                def on_img_progress(idx, slide_index, prompt, path, ms):
                    if sse_queue:
                        try:
                            asyncio.create_task(sse_queue.put({
                                "type": "agent", "role": "image_backend", "event": "generated",
                                "message": f"Generated image for slide {slide_index + 1}: {prompt[:50]}...",
                                "index": idx, "slide_index": slide_index, "ms": ms, "path": path, "prompt": prompt
                            }))
                        except Exception:
                            pass
                state.assets = realize_manifest(manifest, make_backend(), on_progress=on_img_progress)
                if sse_queue:
                    await sse_queue.put({
                        "type": "stage", "name": "images", "status": "DONE", 
                        "message": f"Successfully generated {len(state.assets.images if state.assets else [])} images",
                        "count": len(state.assets.images if state.assets else [])
                    })
            except Exception as e:
                if sse_queue:
                    await sse_queue.put({"type": "error", "stage": "images", "message": f"Image generation failed: {str(e)}"})
                raise

        out_dir = os.path.join(os.path.dirname(__file__), "services", "agno_service")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "output.pptx")
        if sse_queue:
            await sse_queue.put({
                "type": "stage", "name": "render", "status": "RUNNING",
                "message": f"Rendering PowerPoint with {len(state.plan.slides)} slides and {len(state.assets.images if state.assets else [])} images"
            })
        try:
            state.ppt_path = PPTExecutor().render(state.plan, state.style, state.assets, out_path=out_path, guidelines=g)
            if sse_queue:
                await sse_queue.put({
                    "type": "stage", "name": "render", "status": "DONE", 
                    "message": f"PowerPoint rendered successfully: {os.path.basename(state.ppt_path)}",
                    "file": state.ppt_path
                })
        except Exception as e:
            if sse_queue:
                await sse_queue.put({"type": "error", "stage": "render", "message": f"Rendering failed: {str(e)}"})
            raise

        if sse_queue:
            await sse_queue.put({
                "type": "stage", "name": "verify", "status": "RUNNING",
                "message": "Running quality checks on the generated presentation"
            })
        hard_task = asyncio.to_thread(verify_pptx, state.ppt_path, state.plan, state.style, g)
        soft_task = critique(state.plan.dict(), extract_ppt_facts(state.ppt_path), g, sse_queue=sse_queue)
        state.hard_findings, state.soft_findings = await asyncio.gather(hard_task, soft_task)
        
        total_checks = len(state.hard_findings) + len(state.soft_findings)
        failed_checks = len([f for f in (state.hard_findings + state.soft_findings) if f.result == "FAIL"])
        passed_checks = total_checks - failed_checks
        
        if sse_queue:
            await sse_queue.put({
                "type": "stage", "name": "verify", "status": "DONE",
                "message": f"Quality check complete: {passed_checks} passed, {failed_checks} failed out of {total_checks} checks",
                "total_checks": total_checks,
                "passed_checks": passed_checks,
                "failed_checks": failed_checks,
                "hard": [f.dict() for f in state.hard_findings],
                "soft": [f.dict() for f in state.soft_findings],
            })

        failures = [f for f in (state.hard_findings + state.soft_findings) if f.result == "FAIL" and f.severity in ("BLOCKER", "MAJOR")]
        if not failures:
            if sse_queue:
                await sse_queue.put({
                    "type": "stage", "name": "complete", "status": "PASS", "attempt": attempt,
                    "message": f"Presentation completed successfully on attempt {attempt}! All quality gates passed."
                })
            return state
            
        if sse_queue:
            failure_summary = []
            for f in failures[:5]:  # Show first 5 failures
                failure_summary.append({
                    "criterion": f.criterion,
                    "reason": f.reason,
                    "severity": f.severity
                })
            await sse_queue.put({
                "type": "stage", "name": "fix", "status": "RUNNING", "attempt": attempt,
                "message": f"Attempt {attempt} failed with {len(failures)} issues. Starting fixes...",
                "failure_count": len(failures),
                "failure_details": failure_summary
            })
            
        state.plan = await fix_plan(state.plan, [f.dict() for f in failures], sse_queue=sse_queue)
        # Force asset regeneration on next attempt (plan changed)
        state.assets = None
        if sse_queue:
            await sse_queue.put({
                "type": "stage", "name": "fix", "status": "DONE", "attempt": attempt,
                "message": f"Fix attempt {attempt} completed. Revised plan has {len(state.plan.slides)} slides."
            })

    # If we reach here, all attempts failed QC, but return the state anyway 
    # so the user can still download the PPT (as requested)
    if sse_queue:
        await sse_queue.put({
            "type": "stage", "name": "complete", "status": "FAIL", "attempt": MAX_ATTEMPTS,
            "message": f"Presentation completed with QC failures after {MAX_ATTEMPTS} attempt(s). PPT available for download.",
            "final_failures": len(failures)
        })
    return state
