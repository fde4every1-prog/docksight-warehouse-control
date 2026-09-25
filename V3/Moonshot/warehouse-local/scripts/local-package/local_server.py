"""Run the exported API and prebuilt web applications on one local origin."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from dotenv import dotenv_values
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
API_ROOT = ROOT / "artifacts" / "api-server"

# Local configuration is deliberately sourced from this extracted package only.
# In particular, do not inherit hosted AI credentials or Replit's outbound
# proxies into a local run.
for name in (
    "AI_INTEGRATIONS_OPENAI_API_KEY",
    "AI_INTEGRATIONS_OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(name, None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

env_path = ROOT / ".env"
if not env_path.is_file():
    raise RuntimeError(f"Missing local configuration: {env_path}. Run Setup-Local.ps1.")
local_env = dotenv_values(env_path)
openai_key = (local_env.get("OPENAI_API_KEY") or "").strip()
openai_base = (local_env.get("OPENAI_BASE_URL") or "").strip()
dummy_key = "sk-dummy-replace-with-your-own-key"
if openai_key and openai_key != dummy_key:
    os.environ["OPENAI_API_KEY"] = openai_key
    os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = openai_key
if openai_base and openai_key and openai_key != dummy_key:
    os.environ["OPENAI_BASE_URL"] = openai_base
    os.environ["AI_INTEGRATIONS_OPENAI_BASE_URL"] = openai_base

os.environ.setdefault("PORT", "8080")
# This launcher deliberately uses only the packaged stores, never an inherited
# hosted database path or remote Control Tower endpoint.
os.environ["FULFILLMENT_DB_PATH"] = str(API_ROOT / ".local/fulfillment.sqlite")
os.environ["BAZAAR_DB_PATH"] = str(API_ROOT / ".local/bazaar.sqlite")
os.environ["CONTROL_TOWER_API_BASE_URL"] = (
    f"http://127.0.0.1:{os.environ['PORT']}/api/fulfillment"
)
required_databases = (
    Path(os.environ["FULFILLMENT_DB_PATH"]),
    Path(os.environ["BAZAAR_DB_PATH"]),
    API_ROOT
    / "brownfield"
    / "AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2"
    / "data"
    / "warehouse_legacy.db",
)
missing_databases = [str(path) for path in required_databases if not path.is_file()]
if missing_databases:
    raise RuntimeError(
        "The package requires all three active SQLite databases; missing: "
        + ", ".join(missing_databases)
    )
sys.path.insert(0, str(API_ROOT))

from baseline_demo import app  # noqa: E402


class SPAStaticFiles(StaticFiles):
    """Serve real files, with index.html as the extensionless client-route fallback."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and not Path(path).suffix:
                return FileResponse(Path(self.directory) / "index.html")
            raise


def _dist(name: str) -> Path:
    directory = ROOT / "artifacts" / name / "dist" / "public"
    if not (directory / "index.html").is_file():
        raise RuntimeError(f"Missing prebuilt application: {directory}")
    return directory


# baseline_demo reserves "/" for its API documentation redirect. In the local
# package the root belongs to Core Warehouse; all actual API routes remain ahead
# of the static mounts, including the catch-all /api mount.
app.router.routes[:] = [
    route
    for route in app.router.routes
    if not (
        isinstance(route, APIRoute)
        and route.path == "/"
        and "GET" in route.methods
    )
]

app.mount(
    "/fde-bazaar",
    SPAStaticFiles(directory=_dist("fde-bazaar"), html=True),
    name="fde-bazaar",
)
app.mount(
    "/robot-lifecycle",
    SPAStaticFiles(directory=_dist("robot-lifecycle"), html=True),
    name="robot-lifecycle",
)
app.mount(
    "/docksight-client-pitch",
    SPAStaticFiles(directory=_dist("docksight-client-pitch"), html=True),
    name="docksight-client-pitch",
)
app.mount(
    "/",
    SPAStaticFiles(directory=_dist("legacy-review"), html=True),
    name="docksight",
)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8080")),
    )