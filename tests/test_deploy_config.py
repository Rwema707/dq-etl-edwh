"""Guards for the Vercel deployment: mistakes here only show up after a deploy, so test them up front."""
import json
import re
import tomllib
import unittest

from tests.helpers import ROOT


def requirement_names(path):
    lines = (ROOT / path).read_text().splitlines()
    return {re.split(r"[\[<>=!~ ]", ln.strip(), maxsplit=1)[0].lower()
            for ln in lines if ln.strip() and not ln.strip().startswith(("#", "-r"))}


class VercelDependencyTests(unittest.TestCase):
    def test_api_requirements_contain_what_the_api_imports(self):
        self.assertTrue({"fastapi", "psycopg"} <= requirement_names("requirements.txt"))

    def test_api_requirements_stay_small(self):
        # pandas/PyYAML/uvicorn belong in requirements-etl.txt: the serverless bundle should not carry them
        self.assertFalse({"pandas", "pyyaml", "numpy", "uvicorn"} & requirement_names("requirements.txt"))

    def test_there_is_exactly_one_source_of_python_dependencies(self):
        """Vercel prefers pyproject.toml over requirements.txt. A pyproject.toml that does not itself list the
        dependencies makes Vercel install nothing ('No module named fastapi' at runtime)."""
        pyproject = ROOT / "pyproject.toml"
        if pyproject.exists():
            deps = tomllib.loads(pyproject.read_text()).get("project", {}).get("dependencies", [])
            names = {re.split(r"[\[<>=!~ ]", d, maxsplit=1)[0].lower() for d in deps}
            self.assertTrue({"fastapi", "psycopg"} <= names,
                            "pyproject.toml exists but does not list the API dependencies; "
                            "Vercel would ignore requirements.txt. Remove it (use ruff.toml for lint settings).")

    def test_lint_settings_live_in_ruff_toml(self):
        settings = tomllib.loads((ROOT / "ruff.toml").read_text())
        self.assertIn("E501", settings["lint"]["ignore"])


class VercelServicesTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "vercel.json").read_text())

    def test_api_entrypoint_points_at_a_real_app_object(self):
        module, _, attr = self.config["services"]["dq-api"]["entrypoint"].partition(":")
        source = (ROOT / (module.replace(".", "/") + ".py")).read_text()
        self.assertRegex(source, rf"(?m)^{attr}\s*=\s*FastAPI\(")

    def test_api_routes_are_under_the_rewritten_prefix(self):
        source = (ROOT / "api" / "app.py").read_text()
        for route in re.findall(r'@app\.get\("([^"]+)"', source):
            self.assertTrue(route == "/" or route.startswith("/api/"), f"{route} would not be reachable via /api/*")


if __name__ == "__main__":
    unittest.main()
