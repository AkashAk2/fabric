import os
from agno.models.google import Gemini

def _bool_env(n, d=False): return os.getenv(n, str(d)).strip().lower() in ("1","true","yes","y")

def make_model(id="gemini-2.5-flash"):
    return Gemini(
        id=id,
        vertexai=_bool_env("GOOGLE_GENAI_USE_VERTEXAI", False),
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT",""),
        location=os.getenv("GOOGLE_CLOUD_LOCATION","us-central1"),
    temperature=0.0,
    )

def fast_model():   return make_model("gemini-2.5-flash")
def strong_model(): return make_model("gemini-2.5-pro")

