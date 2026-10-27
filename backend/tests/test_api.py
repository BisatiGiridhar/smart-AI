"""API integration tests (require the packages in requirements.txt; skipped otherwise)."""
import importlib.util
import os
import tempfile
import unittest

HAVE_API = all(importlib.util.find_spec(m) for m in ("fastapi", "sqlalchemy", "httpx", "pydantic"))


@unittest.skipUnless(HAVE_API, "API dependencies not installed")
class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ.update({"DATABASE_URL": f"sqlite:///{cls.tmp}/t.db", "JWT_SECRET": "x" * 40, "STORAGE_DIR": f"{cls.tmp}/f",
                           "DATASET_DIR": f"{cls.tmp}/d", "ENABLE_DENSE": "false", "ENABLE_RERANK": "false",
                           "RATE_LIMIT_PER_MINUTE": "10000"})
        from fastapi.testclient import TestClient

        from app.db import Base, engine
        from app.main import app
        Base.metadata.create_all(engine)
        cls.c = TestClient(app)
        cls.c.__enter__()

    def h(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_flow(self):
        c = self.c
        self.assertTrue(c.get("/api/auth/bootstrap-status").json()["needs_bootstrap"])
        r = c.post("/api/auth/bootstrap", json={"email": "admin@example.org", "password": "correct-horse-battery",
                                                 "workspace_name": "Test"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(c.post("/api/auth/bootstrap", json={"email": "b@example.org", "password": "x" * 12,
                                                              "workspace_name": "X"}).status_code, 409)
        self.assertEqual(c.post("/api/auth/login", json={"email": "admin@example.org", "password": "wrong"}).status_code, 401)
        tok = c.post("/api/auth/login", json={"email": "admin@example.org", "password": "correct-horse-battery"}).json()["access_token"]
        self.assertEqual(c.get("/api/dashboard").status_code, 401)
        d = c.get("/api/dashboard", headers=self.h(tok)).json()
        self.assertEqual(d["counts"]["synthetic_resumes"], 0)  # empty state, no invented numbers
        # reviewer cannot import datasets (server-side check)
        c.post("/api/auth/members", headers=self.h(tok), json={"email": "rev@example.org", "password": "reviewer-pass-123",
                                                               "role": "reviewer"})
        rtok = c.post("/api/auth/login", json={"email": "rev@example.org", "password": "reviewer-pass-123"}).json()["access_token"]
        self.assertEqual(c.post("/api/datasets/huggingface", headers=self.h(rtok), json={"repo_id": "a/b"}).status_code, 403)
        # job + rubric approval flow
        j = c.post("/api/jobs", headers=self.h(tok), json={"title": "Backend Engineer",
                                                           "text": "Requirements\nPython and PostgreSQL, 3 years"}).json()
        a = c.post(f"/api/jobs/{j['id']}/analyze", headers=self.h(tok)).json()
        rub = c.post(f"/api/jobs/{j['id']}/rubrics", headers=self.h(tok), json={"criteria": a["draft_criteria"],
                                                                                "origin": "auto_draft"}).json()
        self.assertEqual(rub["status"], "draft")
        self.assertEqual(c.post(f"/api/rubrics/{rub['id']}/approve", headers=self.h(tok)).json()["status"], "approved")
        self.assertEqual(c.post(f"/api/rubrics/{rub['id']}/approve", headers=self.h(tok)).status_code, 409)
        # logout revokes the token
        c.post("/api/auth/logout", headers=self.h(tok))
        self.assertEqual(c.get("/api/auth/me", headers=self.h(tok)).status_code, 401)
