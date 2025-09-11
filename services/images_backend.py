import os, time, base64
from typing import Optional
from io import BytesIO
from PIL import Image
from models.contracts import AssetManifest

DEFAULT_NEG = (
    "watermark, signature, text overlay, logo, generic clipart, lowres, blurry, "
    "oversaturated, jpeg artifacts, frames, borders"
)

GUIDELINE_STYLE = (
    "photo-real, clean lighting, light background, subtle brand accents, professional"
)


class ImageBackend:
    def generate(self, prompt: str, out_path: str) -> str:
        raise NotImplementedError


class NoopBackend(ImageBackend):
    """Fast local placeholder (transparent 1792x1024 PNG). Useful for tests/offline."""
    def generate(self, prompt: str, out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        Image.new("RGBA", (1792, 1024), (255, 255, 255, 0)).save(out_path)
        return out_path


# --------------------------
# Diffusers (local SDXL)
# --------------------------
class DiffusersSDXLBackend(ImageBackend):
    """
    Local SDXL pipeline via Hugging Face diffusers.
    Pros: fully local, free; Cons: needs decent GPU (CPU works but slow).
    """

    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
        device: Optional[str] = None,
        dtype: Optional[str] = None,
    ):
        import torch
        from diffusers import StableDiffusionXLPipeline

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        torch_dtype = getattr(torch, "float16", None) if device == "cuda" else torch.float32
        if dtype == "float32":
            torch_dtype = torch.float32

        self.pipe = StableDiffusionXLPipeline.from_pretrained(
            model_id, torch_dtype=torch_dtype, use_safetensors=True
        )
        self.pipe.to(self.device)
        # memory tweaks
        try:
            self.pipe.enable_attention_slicing()
            if device == "cuda":
                # if available, offload to CPU when idle
                getattr(self.pipe, "enable_model_cpu_offload", lambda: None)()
        except Exception:
            pass

    def generate(
        self,
        prompt: str,
        out_path: str,
        width: int = 1792,
        height: int = 1024,
        steps: int = 20,
        guidance_scale: float = 5.0,
        seed: Optional[int] = None,
        negative_prompt: str = DEFAULT_NEG,
    ) -> str:
        import torch
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        full_prompt = f"{prompt}, {GUIDELINE_STYLE}"
        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(seed)

        image = self.pipe(
            prompt=full_prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            generator=generator,
        ).images[0]

        image.save(out_path)
        return out_path


# --------------------------
# Automatic1111 WebUI (REST)
# --------------------------
class Automatic1111Backend(ImageBackend):
    """
    Connects to A1111's /sdapi/v1/txt2img.
    Ensure an SDXL model is active in the UI.
    """

    def __init__(self, base_url: Optional[str] = None):
        import requests  # noqa: F401  (lazy import check)
        self._requests = __import__("requests")
        self.base_url = base_url or os.getenv("A1111_BASE_URL", "http://127.0.0.1:7860")

    def generate(
        self,
        prompt: str,
        out_path: str,
        width: int = 1792,
        height: int = 1024,
        steps: int = 25,
        guidance_scale: float = 5.5,
        seed: Optional[int] = None,
        negative_prompt: str = DEFAULT_NEG,
        sampler_name: str = "DPM++ 2M Karras",
    ) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        full_prompt = f"{prompt}, {GUIDELINE_STYLE}"

        payload = {
            "prompt": full_prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": guidance_scale,
            "sampler_name": sampler_name,
            "seed": seed if seed is not None else -1,
            "send_images": True,
            "save_images": False,
        }
        r = self._requests.post(f"{self.base_url}/sdapi/v1/txt2img", json=payload, timeout=600)
        r.raise_for_status()
        data = r.json()
        img_b64 = data["images"][0]
        img = Image.open(BytesIO(base64.b64decode(img_b64)))
        img.save(out_path)
        return out_path


# --------------------------
# Stable Horde (free community API)
# --------------------------
# --- Stable Horde (free community API) ---
class StableHordeBackend(ImageBackend):
    """
    Uses the public Stable Horde network (free). Queue-based; zero GPU required.
    """
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://stablehorde.net/api/v2"):
        import requests
        self.requests = requests
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("HORDE_API_KEY", "")
        # Horde wants a Client-Agent string; apikey optional but recommended
        self.headers = {
            "Client-Agent": os.getenv("HORDE_CLIENT_AGENT", "fabric-ai/agno-ppt:1.0"),
            "Content-Type": "application/json",
        }
        if self.api_key:
            self.headers["apikey"] = self.api_key

    def _raise_for_bad(self, resp, context=""):
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = {"text": resp.text}
            raise RuntimeError(f"Stable Horde {context} failed: {resp.status_code} {detail}")

    def generate(
        self,
        prompt: str,
        out_path: str,
        width: int = None,
        height: int = None,
        steps: int = None,
        guidance_scale: float = 6.5,
        seed: Optional[int] = None,
        negative_prompt: str = DEFAULT_NEG,
        model: Optional[str] = None,
    ) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        # Horde requires sizes divisible by 8 (SDXL prefers 64). Clamp just in case.
        def clamp_dim(x: int, base: int = 64) -> int:
            return max(base, int(x / base) * base)

        # Default to a safe, low-kudos size and steps unless overridden
        d_width = int(os.getenv("HORDE_DEFAULT_WIDTH", "768") or 768)
        d_height = int(os.getenv("HORDE_DEFAULT_HEIGHT", "448") or 448)
        d_steps = int(os.getenv("HORDE_DEFAULT_STEPS", "25") or 25)
        width = clamp_dim(width if width else d_width)
        height = clamp_dim(height if height else d_height)
        steps = steps if steps else d_steps
        full_prompt = f"{prompt}, {GUIDELINE_STYLE}"

        # Horde expects seed as a string (use "random" for random seed)
        seed_str = str(seed) if seed is not None else "random"

        params = {
            "sampler_name": "k_dpmpp_2m",
            "cfg_scale": guidance_scale,
            "steps": steps,
            "width": width,
            "height": height,
            "seed": seed_str,
            "n": 1,
            "karras": True,
            "hires_fix": False,
            "clip_skip": 1,
            "tiling": False,
            "post_processing": [],
            # IMPORTANT: Horde expects "negative_prompt"
            "negative_prompt": negative_prompt,
        }

        # Optionally include a valid control type if provided via env
        control_env = os.getenv("HORDE_CONTROL_TYPE", "").strip().lower()
        # Treat common "off" values as unset
        if control_env in {"none", "off", "disabled", "false", "0"}:
            control_env = ""
        valid_controls = {
            "canny",
            "hed",
            "depth",
            "normal",
            "openpose",
            "seg",
            "scribble",
            "fakescribbles",
            "hough",
        }
        if control_env in valid_controls:
            params["control_type"] = control_env

        payload = {
            "prompt": full_prompt,
            "params": params,
            "nsfw": False,
            "censor_nsfw": True,
            "trusted_workers": False,
        }

        # Optional: constrain to a model name IF you know it’s valid on Horde.
        # Safer: omit to let Horde pick a worker/model.
        if model or os.getenv("HORDE_MODEL"):
            payload["models"] = [model or os.getenv("HORDE_MODEL")]

        # Optional debug: log payload (without API key)
        if os.getenv("HORDE_DEBUG", "").strip() not in ("", "0", "false", "False"):
            try:
                safe_headers = {k: v for k, v in self.headers.items() if k.lower() != "apikey"}
                print("[HORDE] Submitting payload:", {**payload, "headers": safe_headers})
            except Exception:
                pass

        # Submit job
        submit = self.requests.post(
            f"{self.base_url}/generate/async", headers=self.headers, json=payload, timeout=60
        )
        # Handle KudosUpfront by auto-downscaling once and retrying
        if submit.status_code == 403:
            try:
                detail = submit.json()
            except Exception:
                detail = {}
            msg = str(detail)
            if isinstance(detail, dict) and (detail.get("rc") == "KudosUpfront" or "KudosUpfront" in msg):
                max_dim = int(os.getenv("HORDE_MAX_DIM", "768") or 768)
                w, h = params.get("width", width), params.get("height", height)
                # scale longest side to max_dim, keep aspect, then round to nearest 64
                scale = max(w / max_dim, h / max_dim, 1.0)
                new_w = max(64, int(round((w / scale) / 64)) * 64)
                new_h = max(64, int(round((h / scale) / 64)) * 64)
                new_w = min(new_w, max_dim)
                new_h = min(new_h, max_dim)
                # Ensure multiples of 64
                def m64(x: int) -> int:
                    return max(64, int(round(x / 64)) * 64)
                new_w, new_h = m64(new_w), m64(new_h)
                # also cap steps to a safer ceiling
                max_steps = int(os.getenv("HORDE_MAX_STEPS", "25") or 25)
                new_steps = min(params.get("steps", steps), max_steps)
                if os.getenv("HORDE_DEBUG", "").strip() not in ("", "0", "false", "False"):
                    print(f"[HORDE] KudosUpfront retry: resizing {w}x{h} -> {new_w}x{new_h}, steps {params.get('steps')} -> {new_steps}")
                params["width"], params["height"] = new_w, new_h
                params["steps"] = new_steps
                payload["params"] = params
                submit = self.requests.post(
                    f"{self.base_url}/generate/async", headers=self.headers, json=payload, timeout=60
                )
        self._raise_for_bad(submit, "submit")
        job_id = submit.json()["id"]

        # Poll for completion
        while True:
            time.sleep(3)
            check = self.requests.get(
                f"{self.base_url}/generate/check/{job_id}", headers=self.headers, timeout=30
            )
            self._raise_for_bad(check, "check")
            if check.json().get("done"):
                break

        # Fetch result
        res = self.requests.get(
            f"{self.base_url}/generate/status/{job_id}", headers=self.headers, timeout=60
        )
        self._raise_for_bad(res, "status")
        out = res.json()
        gens = out.get("generations") or []
        if not gens:
            raise RuntimeError("Stable Horde returned no generations")

        img_field = gens[0].get("img")
        if not isinstance(img_field, str) or not img_field:
            raise RuntimeError("Stable Horde returned an invalid image field")

        # Decode image bytes from base64, data URL, or HTTP URL
        img_bytes: bytes
        try:
            if img_field.startswith("http://") or img_field.startswith("https://"):
                rimg = self.requests.get(img_field, timeout=60)
                rimg.raise_for_status()
                img_bytes = rimg.content
            else:
                b64_part = img_field.split("base64,", 1)[-1]
                try:
                    img_bytes = base64.b64decode(b64_part, validate=True)
                except Exception:
                    # Fallback without strict validation/padding
                    pad = "=" * ((4 - len(b64_part) % 4) % 4)
                    img_bytes = base64.b64decode(b64_part + pad)
        except Exception as e:
            # Persist a small debug blob to inspect failures
            try:
                dbg_dir = os.path.join(os.path.dirname(out_path), "..", "files")
                os.makedirs(dbg_dir, exist_ok=True)
                with open(os.path.join(dbg_dir, "horde_img_debug.bin"), "wb") as f:
                    f.write((img_field or "").encode("utf-8", errors="ignore")[:4096])
            except Exception:
                pass
            raise RuntimeError(f"Failed to decode Horde image data: {e}")

        try:
            img = Image.open(BytesIO(img_bytes))
            img.save(out_path)
        except Exception as e:
            # Save raw bytes for inspection if PIL fails
            try:
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
            except Exception:
                pass
            raise RuntimeError(f"Horde returned non-image or unsupported format: {e}")

        return out_path



# --------------------------
# Factory + manifest helper
# --------------------------
def make_backend() -> ImageBackend:
    kind = (os.getenv("IMAGE_BACKEND", "noop") or "noop").strip().lower()
    if kind == "a1111":
        return Automatic1111Backend()
    if kind == "horde":
        return StableHordeBackend()
    if kind == "diffusers":
        return DiffusersSDXLBackend()
    # default safe fallback for tests/offline
    return NoopBackend()


def realize_manifest(
    manifest: AssetManifest,
    backend: Optional[ImageBackend] = None,
    asset_dir: str = "assets",
    on_progress: Optional[callable] = None,
):
    backend = backend or make_backend()
    # Use absolute, predictable asset directory under services/agno_service
    try:
        base_dir = os.path.join(os.path.dirname(__file__), "..", "services", "agno_service", "assets")
        asset_dir = os.path.abspath(base_dir)
    except Exception:
        asset_dir = os.path.abspath(asset_dir)
    os.makedirs(asset_dir, exist_ok=True)
    # Clear existing images when starting a new generation (opt-out with ASSETS_CLEAR_ON_START=0)
    if (os.getenv("ASSETS_CLEAR_ON_START", "1") not in ("0", "false", "False", "no")):
        try:
            for name in os.listdir(asset_dir):
                fn = os.path.join(asset_dir, name)
                if not os.path.isfile(fn):
                    continue
                if any(name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
                    try:
                        os.remove(fn)
                    except Exception:
                        pass
        except Exception:
            pass
    for idx, it in enumerate(manifest.images):
        t0 = time.time()
        # Ensure unique filenames even if slide_index repeats; keep slide-index visible for traceability
        safe_idx = int(idx)
        safe_slide = int(getattr(it, "slide_index", safe_idx) or safe_idx)
        out_path = os.path.join(asset_dir, f"slide_{safe_slide}_{safe_idx}.png")
        it.path = backend.generate(it.prompt, out_path)
        if on_progress:
            try:
                on_progress(idx, it.slide_index, it.prompt, it.path, int((time.time() - t0) * 1000))
            except Exception:
                pass
    return manifest
