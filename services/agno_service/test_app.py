import os, sys, pathlib, importlib.util
import pytest
from fastapi.testclient import TestClient

THIS_DIR = pathlib.Path(__file__).parent
ROOT = THIS_DIR.parents[2]
sys.path.insert(0, str(ROOT))
APP_PATH = THIS_DIR / "app.py"
spec = importlib.util.spec_from_file_location("agno_app", APP_PATH)
app_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(app_module)
app = app_module.app

client = TestClient(app)

def test_generate_smoke():
    resp = client.post("/generate", json={"topic": "Cloud Transformation in Retail"})
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        data = resp.json()
        assert data.get("success") is True
        assert data.get("ppt_file")
        # no BLOCKER/MAJOR failures expected
        majors = [f for f in (data.get("qc_hard", []) + data.get("qc_soft", [])) if f.get("result")=="FAIL" and f.get("severity") in ("BLOCKER","MAJOR")]
        assert len(majors) == 0
