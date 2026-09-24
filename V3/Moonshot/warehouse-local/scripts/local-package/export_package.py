"""Create a fresh, self-contained Windows staging tree while the API is stopped.

This script intentionally does not make an archive.  The caller must stop the
API before running it and keep the API stopped until all SQLite backups finish.
"""

from __future__ import annotations

import ast
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = ROOT / ".local" / "package-build" / "warehouse-local-current"
OUT = BUILD_ROOT / "warehouse-local"

COPY_ROOTS = ("artifacts", "lib", "scripts", "tests", "attached_assets")
WEB_APPS = {
    "legacy-review": "/",
    "fde-bazaar": "/fde-bazaar/",
    "robot-lifecycle": "/robot-lifecycle/",
    "docksight-client-pitch": "/docksight-client-pitch/",
}
DATABASES = {
    Path("artifacts/api-server/.local/fulfillment.sqlite"),
    Path("artifacts/api-server/.local/bazaar.sqlite"),
    Path(
        "artifacts/api-server/brownfield/"
        "AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2/"
        "data/warehouse_legacy.db"
    ),
}

# Names in this set are generated, private, historical, or reproducible.  In
# particular, all of artifacts/api-server/.local is omitted and the two live
# stores are reintroduced below with SQLite's backup API.
SKIP_DIRECTORIES = {
    ".agents",
    ".cache",
    ".git",
    ".history",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "backups",
    "cache",
    "caches",
    "coverage",
    "downloads",
    "exports",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "profile",
    "profiles",
    "replays",
    "test-results",
}
SKIP_SUFFIXES = (".pyc", ".pyo", ".tsbuildinfo", "-wal", "-shm", "-journal")
ROOT_FILES = (
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "tsconfig.json",
    "tsconfig.base.json",
    ".npmrc",
    ".gitignore",
    "pyproject.toml",
    "uv.lock",
    "replit.md",
    "playwright.lifecycle.config.ts",
    "main.py",
)
LOCAL_PACKAGE_FILES = (
    "local_server.py",
    "requirements.txt",
    "Setup-Local.ps1",
    "Start-Local.ps1",
    "LOCAL_SETUP_WINDOWS.md",
    "TEST_REPORT.md",
)


def _ignore(directory: str, names: list[str]) -> list[str]:
    """shutil.copytree ignore callback; never inspect file contents."""
    ignored = []
    for name in names:
        path = Path(directory, name)
        lowered = name.lower()
        if path.is_dir() and (
            name in SKIP_DIRECTORIES or lowered in SKIP_DIRECTORIES
        ):
            ignored.append(name)
        elif (
            name == ".local"
            or lowered.startswith(".env")
            or lowered in {".profile", ".bash_history", ".zsh_history", ".ds_store"}
            or name.endswith(SKIP_SUFFIXES)
            or Path(name).suffix.lower() in {".sqlite", ".db"}
            or name in {"operational-maintenance.lock"}
        ):
            ignored.append(name)
        # dist is copied only for the four explicitly built web applications.
        elif path.is_dir() and name == "dist":
            ignored.append(name)
    return ignored


def _clean_build_environment(base_path: str) -> dict[str, str]:
    """Return only non-secret process settings needed by Vite and pnpm."""
    environment = {
        "NODE_ENV": "production",
        "PORT": "5173",
        "BASE_PATH": base_path,
    }
    for name in ("PATH", "HOME", "USERPROFILE", "TMP", "TEMP", "TMPDIR", "SYSTEMROOT"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _run(command: list[str], cwd: Path, environment: dict[str, str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def _build_web_apps(pnpm: str) -> None:
    """Delete stale output and build exactly the four distributable apps."""
    for app, base_path in WEB_APPS.items():
        app_root = ROOT / "artifacts" / app
        shutil.rmtree(app_root / "dist", ignore_errors=True)
        _run(
            [pnpm, "--filter", f"@workspace/{app}", "run", "build"],
            ROOT,
            _clean_build_environment(base_path),
        )
        index = app_root / "dist" / "public" / "index.html"
        if not index.is_file():
            raise RuntimeError(f"Build did not produce {index}")


def _copy_sources(stage: Path) -> None:
    for name in COPY_ROOTS:
        source = ROOT / name
        if not source.is_dir():
            raise RuntimeError(f"Required source directory is missing: {source}")
        shutil.copytree(source, stage / name, ignore=_ignore)

    for app in WEB_APPS:
        source = ROOT / "artifacts" / app / "dist"
        shutil.copytree(source, stage / "artifacts" / app / "dist")

    for name in ROOT_FILES:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, stage / name)


def _make_manifest_portable(stage: Path) -> None:
    """Remove hosted platform exclusions while retaining all prior adjustments."""
    workspace = stage / "pnpm-workspace.yaml"
    text = workspace.read_text(encoding="utf-8")
    text = "\n".join(
        line
        for line in text.splitlines()
        if not re.search(r':\s*["\']-["\']\s*$', line)
    )
    if not re.search(r"(?m)^supportedArchitectures:", text):
        text += (
            "\n\n# Include native optional packages required by the Windows export.\n"
            "supportedArchitectures:\n"
            "  os:\n"
            "    - win32\n"
            "  cpu:\n"
            "    - x64\n"
        )
    workspace.write_text(text.rstrip() + "\n", encoding="utf-8")

    package_path = stage / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package.get("scripts", {}).pop("preinstall", None)
    package["packageManager"] = "pnpm@10.26.1"
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")


def _install_portable_lock(stage: Path, pnpm: str) -> None:
    """Resolve a Windows-aware lock, then prove it is frozen-install compatible."""
    environment = _clean_build_environment("/")
    common = ["--lockfile-only", "--ignore-scripts"]
    _run([pnpm, "install", *common, "--no-frozen-lockfile"], stage, environment)
    _run([pnpm, "install", *common, "--frozen-lockfile"], stage, environment)
    for modules in stage.rglob("node_modules"):
        if modules.is_dir():
            shutil.rmtree(modules)


def _replace_fcntl_imports(stage: Path, portable_source: Path) -> list[str]:
    """Discover and rewrite every direct fcntl import in packaged Python."""
    api_root = stage / "artifacts" / "api-server"
    portable_target = api_root / "portable_lock.py"
    shutil.copy2(portable_source, portable_target)

    modified = []
    for target in sorted(stage.rglob("*.py")):
        # The compatibility module's guarded POSIX import is intentional.
        if target.name == "portable_lock.py":
            continue
        text = target.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(target))
        except SyntaxError as exc:
            raise RuntimeError(f"Cannot inspect Python imports in {target}") from exc
        has_fcntl = any(
            (
                isinstance(node, ast.Import)
                and any(alias.name == "fcntl" for alias in node.names)
            )
            or (isinstance(node, ast.ImportFrom) and node.module == "fcntl")
            for node in ast.walk(tree)
        )
        if not has_fcntl:
            continue

        replaced = re.sub(
            r"(?m)^(\s*)import\s+fcntl(\s*(?:#.*)?)$",
            r"\1import portable_lock as fcntl\2",
            text,
        )
        replaced = re.sub(
            r"(?m)^(\s*)from\s+fcntl\s+import\s+",
            r"\1from portable_lock import ",
            replaced,
        )
        remaining = ast.parse(replaced, filename=str(target))
        if any(
            (
                isinstance(node, ast.Import)
                and any(alias.name == "fcntl" for alias in node.names)
            )
            or (isinstance(node, ast.ImportFrom) and node.module == "fcntl")
            for node in ast.walk(remaining)
        ):
            raise RuntimeError(f"Unsupported fcntl import form in {target}")
        target.write_text(replaced, encoding="utf-8")
        modified.append(target.relative_to(stage).as_posix())
    return modified


def _backup_databases(stage: Path) -> list[dict[str, object]]:
    snapshots = []
    for relative in sorted(DATABASES):
        source = ROOT / relative
        if not source.is_file():
            raise RuntimeError(f"Required database is missing: {source}")
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
                integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Invalid database snapshot: {source}: {integrity}")
        snapshots.append(
            {
                "path": relative.as_posix(),
                "bytes": destination.stat().st_size,
                "integrity": integrity,
            }
        )

    found = {
        path.relative_to(stage)
        for path in stage.rglob("*")
        if path.is_file() and path.suffix.lower() in {".sqlite", ".db"}
    }
    if found != DATABASES:
        raise RuntimeError(
            "Database allowlist mismatch: "
            f"expected {sorted(map(str, DATABASES))}, found {sorted(map(str, found))}"
        )
    return snapshots


def _tree_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-current-builds", action="store_true",
                        help="Use app builds verified immediately before this export")
    args = parser.parse_args()
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing staging directory: {OUT}")
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise RuntimeError("pnpm is required to build the four web applications")

    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    if args.use_current_builds:
        for app in WEB_APPS:
            if not (ROOT / "artifacts" / app / "dist/public/index.html").is_file():
                raise RuntimeError(f"Missing verified build for {app}")
    else:
        _build_web_apps(pnpm)

    temporary = Path(tempfile.mkdtemp(prefix=".warehouse-local-building-", dir=BUILD_ROOT))
    try:
        _copy_sources(temporary)
        _make_manifest_portable(temporary)

        templates = ROOT / "scripts" / "local-package"
        for name in LOCAL_PACKAGE_FILES:
            shutil.copy2(templates / name, temporary / name)
        fcntl_files = _replace_fcntl_imports(
            temporary, templates / "portable_lock.py"
        )

        # Only literal dummy values are written.  Hosted environment values are
        # neither read nor inherited by the build subprocesses.
        (temporary / ".env").write_text(
            "OPENAI_API_KEY=sk-dummy-replace-with-your-own-key\n"
            "OPENAI_BASE_URL=https://api.openai.com/v1\n",
            encoding="utf-8",
        )

        databases = _backup_databases(temporary)
        (temporary / "DATABASE_MANIFEST.json").write_text(
            json.dumps(
                {
                    "snapshot_utc": datetime.now(timezone.utc).isoformat(),
                    "method": (
                        "API stopped; SQLite backup API; integrity_check on each "
                        "allowlisted database"
                    ),
                    "databases": databases,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        _install_portable_lock(temporary, pnpm)
        size = _tree_size(temporary)
        temporary.rename(OUT)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(f"Created {OUT}")
    print(f"SQLite snapshots: {len(databases)} (exact allowlist)")
    print(f"Windows fcntl substitutions: {len(fcntl_files)}")
    print("Portable pnpm lock generated and frozen-lock validation passed")
    print(f"Staging size: {size / (1024 * 1024):.1f} MiB")


if __name__ == "__main__":
    main()