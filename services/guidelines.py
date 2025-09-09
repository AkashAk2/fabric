import json

GUIDELINES = {
  "brand": {
    "name": "Infosys Consulting",
    "logo_rules": {"placement": "top-right", "min_size_px": 120, "safe_zone_px": 24},
    "palette": {
      "infosys_blue": "#3781C2", "black": "#000000", "white": "#FFFFFF",
      "process_green": "#00A651", "alert_orange": "#FF8C00", "neutral_gray": "#6C757D",
      "text_on_light": "#111111", "text_on_dark": "#FFFFFF",
      "bg_light": "#FFFFFF", "bg_dark": "#0B0B0B"
    },
    "fonts": {
      "title_family": "Arial", "title_min_pt": 28,
      "section_family": "Arial", "section_min_pt": 22,
      "body_family": "Arial", "body_min_pt": 16,
      "callout_family": "Arial", "callout_min_pt": 14
    }
  },
  "visual_rules": {
    "aspect_ratio": "16:9", "canvas_px": [1920,1080],
    "margins_min_px": 60, "white_space_min_pct": 20,
    "alignment": {"title":"center","body":"left"},
    "containers": {"radius_px":8,"shadow_blur":4,"shadow_offset":2,"shadow_opacity_pct":30,"shadow_color":"#6C757D"},
    "icons": {"style":"flat","vector_only":True,"palette_enforced":True},
    "image_style": "photo-real, clean lighting, light background; brand colors only in accents; no watermarks; no clipart",
    "wcag_contrast": "AA",
    "allow_off_brand_colors": False,
    "templates": [
      "Title Slide","Section Divider","Title and Content","Title and Two Content",
      "Image Full","Business/Technical Split","Action Plan","Appendix"
    ]
  },
  "audience": {
    "executive": {"focus":["business value","ROI","risk mitigation","market positioning"],"elements":["Executive Takeaway"]},
    "technical": {"focus":["architecture","data flows","benchmarks","security","scalability","compliance"],"elements":["Technical Deep Dive"]},
    "mixed": {"pattern":"split","elements":["Executive Takeaway","Technical Deep Dive","glossary"]}
  },
  "content_rules": {
    "slide_count_min": 8, "slide_count_max": 20,
    "bullets_per_slide_min": 2, "bullets_per_slide_max": 5,
    "bullet_char_limit": 120, "one_message_per_slide": True,
    "avoid": ["jargon (unless defined)","hyperbole","marketing fluff"],
    "tone": "concise, confident, concrete; active voice",
    "structures": { "preferred":["SCQA","Pyramid"],
      "sequence":["Title","Executive Summary","Body","Case Studies","Action Plan","Appendix"] },
    "slide_types": ["title","agenda","overview","insight","data","process","case","action_plan","image","conclusion","appendix"]
  },
  "key_concepts_protocol": ["definition","business_analogy","technical_sidebar","diagram","case_study"],
  "data_evidence": {
    "credible_sources":["Infosys Research","Gartner","Forrester","World Economic Forum"],
    "visualization":{"require_labels":True,"no_3d":True,"on_brand":True},
    "benchmarking": True, "citation_format":"[Source, Year]"
  },
  "compliance_checklist": {
    "visual":["brand_palette_only","fonts_arial_or_calibri","min_60px_margins","16x9","on_brand_icons"],
    "content":["one_clear_message","SCQA_or_Pyramid","key_concepts_protocol","evidence_visualized","actionable_reco","case_when_applicable"],
    "technical":["no_cropped_text","legible_diagrams","accessibility_contrast","image_alt_text","links_work"],
    "brand":["infosys_blue_accent","slide_number_section_marker","consistent_headers_footers"]
  },
  "iteration": { "temperature": 0.0, "self_consistency_versions": 3, "multi_model_validation": True, "require_100_pct_visual_and_brand": True },
  "imagery_policy": { "allowed_sources":["generated","licensed_stock"], "disallowed":["watermarks","generic_clipart"], "subject_alignment":"must be directly relevant to headline and bullets" },
  "banned_phrases": ["revolutionize","industry-leading","next-gen"],
  "storytelling_framework": { "SCQA": ["Situation","Complication","Question","Answer"], "Pyramid": ["Recommendation","Arguments","Evidence"] },
  "audience_slide_elements": {
    "executive": ["Executive Takeaway"],
    "technical": ["Technical Deep Dive"],
    "mixed": ["Executive Takeaway","Technical Deep Dive","Glossary"]
  }
}

def load_guideline_profile(_profile_id: str | None) -> dict:
    return json.loads(json.dumps(GUIDELINES))
