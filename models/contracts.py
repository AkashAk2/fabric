from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Literal, Dict, Annotated
import re

class Bullet(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=120)]
    note: Optional[str] = None

SlidePurpose = Literal["title","agenda","overview","insight","data","process","case","action_plan","image","conclusion","appendix"]

class Slide(BaseModel):
    title: str
    purpose: SlidePurpose
    bullets: Annotated[List[Bullet], Field(min_length=2, max_length=5)]
    required_assets: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_slide(cls, v):
        """
        Coerce various LLM formats into a valid Slide shape and ensure min bullets.
        - bullets may be missing, string, or list[str|{text,note}]
        - synthesize at least 2 bullets using the title if absent
        """
        if not isinstance(v, dict):
            return v
        bullets = v.get("bullets")
        if bullets is None:
            bullets = []
        if isinstance(bullets, str):
            # split on newlines or • characters
            parts = [p.strip(" •-\t") for p in bullets.splitlines() if p.strip()]
            bullets = parts
        if isinstance(bullets, list):
            norm: List[dict] = []
            for item in bullets:
                if item is None:
                    continue
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        if len(text) > 120:
                            # Trim at last whitespace before limit and add ellipsis
                            cut = text[:117]  # Leave room for ellipsis
                            sp = cut.rfind(" ")
                            # If no space found within reasonable range, cut at word boundary earlier
                            if sp < 80:
                                sp = cut[:100].rfind(" ")
                            cut = cut[:sp] if sp > 0 else cut[:100]
                            text = cut.rstrip() + "…"
                        norm.append({"text": text})
                elif isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    note = item.get("note")
                    if text:
                        if len(text) > 120:
                            cut = text[:117]  # Leave room for ellipsis
                            sp = cut.rfind(" ")
                            if sp < 80:
                                sp = cut[:100].rfind(" ")
                            cut = cut[:sp] if sp > 0 else cut[:100]
                            text = cut.rstrip() + "…"
                        norm.append({"text": text, **({"note": note} if note else {})})
            bullets = norm
        # Ensure at least two bullets
        if not isinstance(bullets, list):
            bullets = []
        if len(bullets) < 2:
            title = str(v.get("title", ""))[:120].strip() or "Key points"
            needed = 2 - len(bullets)
            fillers = [
                {"text": f"Summary: {title}"},
                {"text": f"Implication: {title}"},
            ]
            bullets.extend(fillers[:needed])
        # Trim max 5
        if len(bullets) > 5:
            bullets = bullets[:5]
        v["bullets"] = bullets
        return v

class Plan(BaseModel):
    topic: str
    slides: Annotated[List[Slide], Field(min_length=8, max_length=20)]

    @model_validator(mode="before")
    @classmethod
    def _normalize_plan(cls, v):
        if not isinstance(v, dict):
            return v
        # Some agents return {"plan": {...}}; unwrap
        if "plan" in v and isinstance(v["plan"], dict):
            v = v["plan"]
        slides = v.get("slides")
        # Accept dict of slides keyed by index and convert to list order
        if isinstance(slides, dict):
            try:
                items = sorted(((int(k), val) for k, val in slides.items()), key=lambda x: x[0])
                slides = [val for _, val in items]
            except Exception:
                slides = list(slides.values())
        elif slides is None:
            slides = []
        # Ensure slides is a list for downstream validation
        if not isinstance(slides, list):
            slides = [slides]
        v["slides"] = slides
        return v

class StyleHints(BaseModel):
    palette: Dict[str, str]
    fonts: Dict[str, str]
    master_layout: str
    slide_layouts: Dict[int, str] = Field(default_factory=dict)
    image_style: str
    spacing_rules: Dict[str, int]

    @model_validator(mode="before")
    @classmethod
    def _normalize_style(cls, v):
        if not isinstance(v, dict):
            return v
        # Fonts: coerce numeric values to pt strings
        fonts = v.get("fonts") or {}
        if isinstance(fonts, dict):
            norm_fonts: Dict[str, str] = {}
            for k, val in fonts.items():
                if isinstance(val, (int, float)):
                    norm_fonts[k] = f"{int(val)}pt"
                else:
                    norm_fonts[k] = str(val)
            v["fonts"] = norm_fonts

        # Master layout: accept dict and choose a key if present
        ml = v.get("master_layout")
        if isinstance(ml, dict):
            # Prefer common 16x9 label, else first key
            key = "16x9" if "16x9" in ml else (next(iter(ml.keys())) if ml else "16x9")
            v["master_layout"] = str(key)
        elif ml is not None:
            v["master_layout"] = str(ml)

        # Slide layouts: aim for index->layout name mapping
        sl = v.get("slide_layouts")
        mapping: Dict[int, str] = {}
        if isinstance(sl, list):
            # list of names in order
            mapping = {i: str(name) for i, name in enumerate(sl)}
        elif isinstance(sl, dict):
            # try casting int-like keys; otherwise ignore nested layout specs
            for k, val in sl.items():
                if isinstance(k, int) or (isinstance(k, str) and k.isdigit()):
                    try:
                        mapping[int(k)] = str(val if not isinstance(val, dict) else val.get("name", "")) or "Title and Content"
                    except Exception:
                        continue
            # If no int keys found, leave empty mapping to use executor defaults
        v["slide_layouts"] = mapping

        # Spacing rules: coerce numeric-like strings to int
        sr = v.get("spacing_rules") or {}
        if isinstance(sr, dict):
            norm_sr: Dict[str, int] = {}
            for k, val in sr.items():
                if isinstance(val, (int, float)):
                    norm_sr[k] = int(val)
                else:
                    s = str(val)
                    # extract leading number if present
                    num = "".join(ch for ch in s if ch.isdigit())
                    norm_sr[k] = int(num) if num else 0
            v["spacing_rules"] = norm_sr

        return v

class ImageItem(BaseModel):
    slide_index: int
    prompt: str
    path: Optional[str] = None
    alt_text: Optional[str] = None

class AssetManifest(BaseModel):
    images: List[ImageItem] = Field(default_factory=list)

class QCItem(BaseModel):
    criterion: str
    result: Literal["PASS","FAIL"]
    reason: str
    severity: Literal["BLOCKER","MAJOR","MINOR"] = "MAJOR"

class OrchestratorState(BaseModel):
    topic: str
    context: Optional[str] = None
    guideline_profile_id: Optional[str] = None
    plan: Optional[Plan] = None
    style: Optional[StyleHints] = None
    assets: Optional[AssetManifest] = None
    ppt_path: Optional[str] = None
    hard_findings: List[QCItem] = Field(default_factory=list)
    soft_findings: List[QCItem] = Field(default_factory=list)
