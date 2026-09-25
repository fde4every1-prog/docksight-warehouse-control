# Warehouse local package for Windows

`Warehouse-Local-Windows-Current.zip` contains one top-level
`warehouse-local` folder. It runs four prebuilt browser apps against the shared
Python API on one loopback-only origin:

- DockSight at `/`
- FDE Bazaar at `/fde-bazaar/`
- Robot Fleet Simulator (including Batching Advisor and Transfer Lab) at
  `/robot-lifecycle/`
- DockSight client pitch at `/docksight-client-pitch/`

Canvas (`artifacts\mockup-sandbox`) is included as source/design material only;
it is not served as a fifth app. Node.js is not needed for normal use.

## Numbered setup

1. Install **64-bit Python 3.11** with the Windows `py` launcher. VS Code is
   optional:

   ```powershell
   winget install --exact --id Python.Python.3.11
   winget install --exact --id Microsoft.VisualStudioCode
   ```

2. Open a new PowerShell window. Save
   `Warehouse-Local-Windows-Current.zip` in Downloads, then extract it. Do not
   run from the ZIP preview, `Program Files`, or a read-only directory:

   ```powershell
   New-Item -ItemType Directory -Force -Path "$HOME\Warehouse-Local-Current" | Out-Null
   Expand-Archive -LiteralPath "$HOME\Downloads\Warehouse-Local-Windows-Current.zip" -DestinationPath "$HOME\Warehouse-Local-Current"
   Set-Location "$HOME\Warehouse-Local-Current\warehouse-local"
   ```

3. Optionally open the extracted folder in VS Code:

   ```powershell
   code .
   ```

4. Create the Python 3.11 environment and install dependencies:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\Setup-Local.ps1
   ```

   Setup creates `.venv` and, only when absent, a local `.env` containing:

   ```dotenv
   OPENAI_API_KEY=sk-dummy-replace-with-your-own-key
   OPENAI_BASE_URL=https://api.openai.com/v1
   ```

   The dummy value is not a secret. It lets every non-LLM feature start, but AI
   suggestions explicitly report that the integration is not configured.
   To use the two batching AI APIs, edit only the extracted `.env` and replace
   the dummy key with your own provider key. Never commit or redistribute that
   edited file. The launcher maps these two local settings to the integration
   variables consumed by both APIs. It ignores inherited hosted credentials
   and clears inherited outbound proxy settings.

5. Start the package:

   ```powershell
   .\Start-Local.ps1
   ```

6. Open:

   - DockSight: <http://127.0.0.1:8080/>
   - FDE Bazaar: <http://127.0.0.1:8080/fde-bazaar/>
   - Robot Fleet Simulator: <http://127.0.0.1:8080/robot-lifecycle/>
   - Transfer Lab: <http://127.0.0.1:8080/robot-lifecycle/transfer-lab>
   - Client pitch: <http://127.0.0.1:8080/docksight-client-pitch/>
   - API documentation: <http://127.0.0.1:8080/api/docs>

7. Stop the server with **Ctrl+C** before inspecting or copying a database.

To select another port for one PowerShell session:

```powershell
$env:PORT = "8090"
.\Start-Local.ps1
```

## Data included

Exactly three active SQLite files are required and included:

- `artifacts\api-server\.local\fulfillment.sqlite`
- `artifacts\api-server\.local\bazaar.sqlite`
- `artifacts\api-server\brownfield\AI_FDE_AI_Native_Autonomous_Warehouse_Robotics_Control_Center_v2\data\warehouse_legacy.db`

The package does not include database backup snapshots or replay databases.
There are no companion archives to extract. The launcher refuses to start if
any active database is missing rather than silently creating a replacement.
Your extracted databases evolve independently from hosted copies.

DB Browser for SQLite may inspect these files while the server is stopped.
Avoid direct edits, which bypass inventory, reservation, order, and robot
safety checks.

## Optional source rebuild

The supplied production builds do not need Node.js. To rebuild all four apps,
install Node.js 22 and pnpm 10.26.1:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\Setup-Local.ps1 -InstallBuildTools
pnpm install --frozen-lockfile

$env:PORT = "5173"; $env:BASE_PATH = "/"
pnpm --dir .\artifacts\legacy-review run build

$env:PORT = "5174"; $env:BASE_PATH = "/fde-bazaar/"
pnpm --dir .\artifacts\fde-bazaar run build

$env:PORT = "5175"; $env:BASE_PATH = "/robot-lifecycle/"
pnpm --dir .\artifacts\robot-lifecycle run build

$env:PORT = "5176"; $env:BASE_PATH = "/docksight-client-pitch/"
pnpm --dir .\artifacts\docksight-client-pitch run build

Remove-Item Env:BASE_PATH -ErrorAction SilentlyContinue
Remove-Item Env:PORT -ErrorAction SilentlyContinue
```

## Safety and support boundary

The launcher binds only to `127.0.0.1`. Do not make it network-facing. This is
a local browser application, not a Windows `.exe`, and its demo personas are
not production authentication.

The Python versions of pandas, scikit-learn, joblib, and NumPy are pinned to the
versions recorded by the bundled experimental ML artifact. Runtime API reads
the signed JSON prediction snapshot and does not unpickle the model. See
`TEST_REPORT.md` for verification scope. Linux verification is not proof of
execution on Windows.