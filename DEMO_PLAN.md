# Full local demo runbook

This guide runs the app locally in **demo mode**. It does not send real email. Customer emails and meeting transcripts are synthetic. You do not need API keys for this walkthrough; live Claude generation, real email delivery, and product-document ingestion are not part of the no-credentials demo.

## 1. Check prerequisites

Install Python 3.12 or later, Node.js 22 or later (npm is included), and Git for Windows. Open PowerShell in the repository root. Confirm the location:

```powershell
Get-Location
```

It should end with `ai-tech-consultant`. If you are elsewhere, move to the project folder, for example:

```powershell
Set-Location "$HOME\OneDrive\Desktop\ai-tech-consultant"
```

Check versions:

```powershell
python --version
node --version
npm --version
```

## 2. Install dependencies (one time)

Run these from the repository root. Python virtual environments keep each service's dependencies isolated:

```powershell
Set-Location task1-knowledge-brain
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
deactivate
Set-Location ..

Set-Location task3-meeting-to-scope
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
deactivate
Set-Location ..

Set-Location task2-inbox-agent
npm ci
Set-Location ..\frontend
npm ci
Set-Location ..
```

If PowerShell blocks virtual-environment activation, skip the `Activate.ps1` and `deactivate` lines. Run `python -m pip install -r requirements.txt` in that service folder; the run commands below call the service's `.venv\Scripts\python.exe` directly.

## 3. Start the four services

Open **four PowerShell terminals** at the repository root. Keep each terminal open while using the app. These commands explicitly choose local demo storage and bind the APIs to your computer.

**Terminal 1 — Knowledge Brain (port 8001):**

```powershell
Set-Location task1-knowledge-brain
$env:APP_ENV = 'demo'
$env:DATABASE_URL = 'sqlite:///./data/knowledge.db'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

**Terminal 2 — Inbox Review (port 8002):**

```powershell
Set-Location task2-inbox-agent
$env:APP_ENV = 'demo'
$env:REPOSITORY_MODE = 'memory'
npm run start
```

**Terminal 3 — Scope Builder (port 8003):**

```powershell
Set-Location task3-meeting-to-scope
$env:APP_ENV = 'demo'
$env:STORAGE_MODE = 'sqlite'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

**Terminal 4 — Web app (port 5173):**

```powershell
Set-Location frontend
npm run dev -- --port 5173
```

Wait for each terminal to report that its server is running. In a fifth PowerShell window, you can check service health:

```powershell
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:8003/health
```

Then open **http://localhost:5173** in your browser.

## 4. Walk through the app

### Knowledge Chat

Open **Knowledge Chat** and ask:

> How do I configure member search filters?

The local database starts without product documentation, so an insufficient-evidence response and human-review escalation are expected. The app should not invent a sourced product answer. A live product-document crawl is deliberately not run by this demo; ingestion requires a permitted source and configured production-quality embeddings.

### Inbox Review

Open **Inbox Review**, choose **SYN-001 · new** (subject: **Add a search filter**), classify it, and generate a reply draft. The queue shows each fixture ID beside its subject. Inspect the evidence and draft, edit if desired, and approve. In demo mode the outcome should be `sent_simulated`; no email leaves your machine. The email fixture is synthetic.

### Scope Builder

Open **Scope Builder** and paste the sample transcript below. Generate a draft scope, review each requirement and its source passage, feasibility, estimate range, proposal, then approve the scope as a baseline.

```text
[00:10] Client: We need members to filter the directory by location and professional specialty.
[00:32] Consultant: Should visitors see this without signing in?
[00:40] Client: Yes, the filters should be public. We also want the search to work well on mobile.
[01:05] Client: Can you include the initial setup and testing in the proposal?
```

For a follow-up comparison, use the **approved baseline** selector and paste the Meeting C fixture from `evals/meeting_c_followup_scope_change.txt`. It contains a synthetic follow-up with scope changes; generated differences should be reviewed before approval.

## 5. Shut down

In each of the four service terminals, press **Ctrl+C**. Demo data is local: Task 1 uses `task1-knowledge-brain/data/knowledge.db`; Task 2 uses in-memory storage and resets when its process stops; Task 3 uses its local SQLite store.

## 6. Optional: run the automated checks

From the repository root:

```powershell
Set-Location task1-knowledge-brain
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests
Set-Location ..\task3-meeting-to-scope
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests
Set-Location ..\task2-inbox-agent
npm run typecheck
npm test
Set-Location ..\frontend
npm run build
Set-Location ..
```

## Demo limitations

- Do not set `APP_ENV=production` for this walkthrough.
- No Claude API key is needed for the demo. Live Claude generation requires valid `ANTHROPIC_API_KEY` and account-supported model IDs.
- Real email requires a verified Resend account and explicit production configuration; demo approval simulates the send.
- The local Knowledge Brain has no indexed product source by default. It abstains and escalates rather than claiming product facts.
- The crawler honors `robots.txt` and stops if access is disallowed. Obtain source authorization before attempting ingestion.
- This local setup is for evaluation, not public deployment. See `README.md`, `DESIGN.md`, and `EVALS.md` for architecture and verification limits.
