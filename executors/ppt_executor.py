import os
from pptx import Presentation
from pptx.util import Pt, Inches
from pptx.enum.text import PP_ALIGN
from models.contracts import Plan, StyleHints, AssetManifest
from services.guidelines import load_guideline_profile

class PPTExecutor:
    def __init__(self, template_path="templates/master_theme.potx"):
        self.template_path = template_path

    def _find_layout(self, prs, name, fallback_index=1):
        for i, l in enumerate(prs.slide_layouts):
            if l.name == name: return prs.slide_layouts[i]
        return prs.slide_layouts[fallback_index]

    def render(self, plan: Plan, style: StyleHints, assets: AssetManifest, out_path="output.pptx", guidelines: dict | None = None) -> str:
        # Try template; fallback to blank
        try:
            if os.path.exists(self.template_path):
                prs = Presentation(self.template_path)
            else:
                prs = Presentation()
        except Exception:
            prs = Presentation()
        # Skip setting slide dimensions to avoid EMU conversion issues
        # Most templates already have proper 16:9 dimensions
        # If needed, dimensions can be set via template file instead

        g = guidelines or load_guideline_profile(None)
        g_title_min = int(g["brand"]["fonts"]["title_min_pt"]) if g else 28
        g_body_min = int(g["brand"]["fonts"]["body_min_pt"]) if g else 16
        
        # Parse style font values more robustly
        style_title = 28  # Default
        style_body = 16   # Default
        
        if style.fonts.get("title"):
            title_val = style.fonts["title"]
            if isinstance(title_val, dict) and "size_pt" in title_val:
                style_title = int(title_val["size_pt"])
            elif isinstance(title_val, str):
                style_title = int(''.join(ch for ch in title_val if ch.isdigit()) or 28)
        
        if style.fonts.get("body"):
            body_val = style.fonts["body"]
            if isinstance(body_val, dict) and "size_pt" in body_val:
                style_body = int(body_val["size_pt"])
            elif isinstance(body_val, str):
                style_body = int(''.join(ch for ch in body_val if ch.isdigit()) or 16)
        
        # Ensure we never go below guideline mins
        title_min = max(style_title, g_title_min)
        body_min = max(style_body, g_body_min)
        
        # Force minimum font sizes regardless of style
        title_min = max(title_min, 28)  # Absolute minimum 28pt for titles
        body_min = max(body_min, 16)   # Absolute minimum 16pt for body

        for i, s in enumerate(plan.slides):
            layout_name = style.slide_layouts.get(i) or {
                "image":"Image Full",
                "data":"Title and Content",
                "process":"Title and Two Content",
                "case":"Title and Content",
                "action_plan":"Action Plan",
                "overview":"Title and Content",
                "insight":"Title and Content",
                "agenda":"Title and Content",
                "conclusion":"Title and Content",
                "appendix":"Appendix",
                "title":"Title Slide"
            }.get(s.purpose, "Title and Content")

            slide = prs.slides.add_slide(self._find_layout(prs, layout_name))

            # Title: set explicit run to ensure size/name stick - be very aggressive
            if slide.shapes.title:
                tf = slide.shapes.title.text_frame
                # clear existing content and add a new run with enforced font
                tf.clear()
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.CENTER
                # Set paragraph-level font as well
                p.font.size = Pt(title_min)
                p.font.name = "Arial"
                p.font.bold = True
                # Also set run-level font
                r = p.add_run()
                r.text = s.title
                r.font.size = Pt(title_min)
                r.font.name = "Arial"
                r.font.bold = True
            elif slide.placeholders:
                # Fallback: try first placeholder as title if title shape missing
                for ph in slide.placeholders:
                    if hasattr(ph, 'text_frame') and ph.text_frame:
                        tf = ph.text_frame
                        tf.clear()
                        p = tf.paragraphs[0]
                        p.alignment = PP_ALIGN.CENTER
                        # Set paragraph-level font as well
                        p.font.size = Pt(title_min)
                        p.font.name = "Arial"
                        p.font.bold = True
                        # Also set run-level font
                        r = p.add_run()
                        r.text = s.title
                        r.font.size = Pt(title_min)
                        r.font.name = "Arial"
                        r.font.bold = True
                        break

            # Body bullets (left-aligned)
            body = None
            for ph in slide.placeholders:
                if getattr(ph, "placeholder_format", None) and ph.placeholder_format.type == 1:
                    body = ph.text_frame; break
            # Fallback: look for any text frame that's not the title
            if not body:
                for shape in slide.shapes:
                    if (hasattr(shape, 'text_frame') and shape.text_frame and 
                        shape != slide.shapes.title):
                        body = shape.text_frame
                        break
            if body:
                body.clear()
                for j, b in enumerate(s.bullets):
                    p = body.add_paragraph() if j>0 else body.paragraphs[0]
                    # Use explicit run per bullet to enforce size/name
                    p.clear()
                    p.level = 0
                    p.alignment = PP_ALIGN.LEFT
                    # Set paragraph-level font as well
                    p.font.size = Pt(body_min)
                    p.font.name = "Arial"
                    # Also set run-level font
                    r = p.add_run()
                    r.text = b.text
                    r.font.size = Pt(body_min)
                    r.font.name = "Arial"

            # Image placement + alt text
            img = next((im for im in assets.images if im.slide_index == i), None)
            if img and os.path.exists(img.path):
                # Try picture placeholder first
                pic_ph = next((ph for ph in slide.placeholders
                               if getattr(ph, "placeholder_format", None) and ph.placeholder_format.type==18), None)
                picture = None
                if pic_ph:
                    try:
                        picture = pic_ph.insert_picture(img.path)
                    except Exception:
                        picture = None
                if picture is None:
                    # Fallback: add at a conservative size to avoid dimension errors
                    try:
                        # Place image with smaller, safer dimensions
                        left = Inches(5.0)    # Conservative left position
                        top = Inches(1.5)     # Conservative top position  
                        width = Inches(3.0)   # Conservative width
                        picture = slide.shapes.add_picture(img.path, left, top, width=width)
                    except Exception:
                        picture = None
                if picture is not None:
                    # Ensure alt text is set properly - use image alt_text or slide title as fallback
                    alt_text = img.alt_text or s.title or f"Image for slide {i+1}"
                    picture.alternative_text = alt_text

        prs.save(out_path)
        return os.path.abspath(out_path)
