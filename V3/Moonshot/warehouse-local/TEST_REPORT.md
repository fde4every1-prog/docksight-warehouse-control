# Current local package verification report

## Scope

Verification for this revision was performed in the Linux workspace. No claim
is made that the package, PowerShell scripts, native Windows locking branch, or
applications were executed on Windows.

The current package definition is
`Warehouse-Local-Windows-Current.zip`, containing one `warehouse-local`
directory. It includes four prebuilt apps (DockSight, Bazaar, Robot Fleet
Simulator with Transfer Lab, and the client pitch), Canvas source only, and
exactly three active SQLite databases. Backup and replay database snapshots are
not part of the current package.

## Static checks completed

- The local launcher remains bound to `127.0.0.1`.
- All four expected `dist\public\index.html` entry points exist in the Linux
  workspace.
- The launcher requires the fulfillment, Bazaar, and legacy active databases
  before importing the API.
- `.env` is read explicitly from the extracted package root with
  `python-dotenv`, before API import.
- The generated `.env` uses the documented dummy key and standard OpenAI base
  URL. The launcher maps a non-dummy local key to the
  `AI_INTEGRATIONS_OPENAI_*` names consumed by both batching APIs. The dummy
  maps to no integration credentials, producing the APIs' explicit
  “not configured” response.
- Inherited OpenAI integration values and HTTP(S)/ALL proxy values are removed;
  loopback is retained in `NO_PROXY`. No real secret was read or packaged.
- Normal startup serves prebuilt assets and does not require Node.js. The
  optional rebuild path specifies Node.js 22 and pnpm 10.26.1 for all four
  builds.
- `openpyxl` and `python-dotenv` are pinned in the Python requirements.
- The bundled predictive-maintenance metadata records Python 3.11.14, pandas
  3.0.6, scikit-learn 1.9.1, joblib 1.6.0, and NumPy 2.4.6. The matching
  versions are pinned directly; the serving API consumes JSON outputs and does
  not unpickle `model.joblib`.
- A Linux-hosted `pip download` resolution using CPython 3.11, `win_amd64`, and
  binary-only constraints succeeded for the complete requirements set. It
  selected CPython 3.11 Windows wheels for NumPy 2.4.6, pandas 3.0.6,
  scikit-learn 1.9.1, and their compiled dependencies.

## Limitations

- An isolated copy of the final staged package was started on Linux on port 8089.
  All four app entry routes, Bazaar and Transfer Lab nested routes, entry JS/CSS
  assets, API docs, health, fulfillment state, Bazaar orders, and live transfer
  snapshot preview returned HTTP 200. The original packaged snapshot was not
  used for runtime testing and remains unchanged.
- All four frontend production builds passed. The exported pnpm lockfile
  passed frozen-lockfile resolution after Windows optional dependencies were
  restored. Exactly three SQLite files passed integrity checks.
- Runtime smoke checks used the workspace's installed Python dependencies;
  this does not establish a fresh Windows installation.
- No real OpenAI request was made and no real API key was accessed.
- Windows extraction, dependency installation, PowerShell execution, and
  native `LockFileEx` behavior still require verification on a Windows 64-bit
  Python 3.11 machine.
- Any Windows wheel-availability check records package-index availability only;
  it is not equivalent to installing or importing those wheels on Windows.