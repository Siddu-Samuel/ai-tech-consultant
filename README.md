# AI Tech Consultant

Three connected tools share one source of product knowledge: a Python Knowledge Brain for documented answers and image references, a strict TypeScript inbox reviewer, and a Python meeting-to-scope workflow. The React workspace presents Knowledge Chat, Inbox Review, and Scope Builder.

## Local demo

Requirements: Python 3.12+, Node.js 22+, npm. No API keys are needed for the local demo. Follow [DEMO_PLAN.md](DEMO_PLAN.md) for install and four-terminal run steps. Demo emails are synthetic and approval is simulated.

## Docker Compose demo

With Docker Desktop running, copy `.env.example` to `.env`, then run:

```powershell
docker compose up --build
```

Open `http://localhost:5173`. This is demo mode and must not be exposed as a production deployment. Docker was unavailable in the implementation environment, so Compose runtime behavior has not been verified here.

## Single-host production deployment

The production overlay keeps PostgreSQL and all APIs off published host ports. It binds the frontend to loopback for a separately managed TLS reverse proxy. Set `FRONTEND_PORT=8080` in `.env`; place the proxy on the same host and route HTTPS traffic to `127.0.0.1:8080`. Configure HTTPS, **user authentication/SSO**, access restrictions, backups, monitoring, and host firewall rules there. This app does not provide user sign-in; do not expose it to the public internet without an authenticated access layer. Do not publish the service ports directly to the internet.

1. Copy `.env.example` to `.env`; replace all placeholders. Set `FRONTEND_PORT=8080`, a long random URL-safe (letters/digits/`_`/`-`) `POSTGRES_PASSWORD`, random `ADMIN_API_TOKEN` and `TASK1_SERVICE_TOKEN`, account-valid `ANTHROPIC_API_KEY`, `CLAUDE_MODEL_PRIMARY`, `CLAUDE_VISION_MODEL`, `OPENAI_API_KEY`, and supported `EMBEDDING_MODEL`. Leave `APP_ENV=demo` in the file; the production overlay explicitly sets production mode. Keep `.env` private and out of source control.
2. Start and validate the stack:

   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.production.yml config
   docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
   docker compose -f docker-compose.yml -f docker-compose.production.yml ps
   ```

   The config command fails when required secrets or model IDs are missing. PostgreSQL and API containers have no host-published ports; the frontend is only on `127.0.0.1:8080`.
3. Check service health locally: `http://127.0.0.1:8080` serves the frontend; the proxy routes its `/api/...` requests to internal APIs. `docker compose ... ps` should report healthy services. Configure scheduled database backups and test a restore before handling customer data.
4. Keep `EMAIL_PROVIDER=simulated`, `AUTO_SEND_ENABLED=false`, and `GLOBAL_AUTOMATION_DISABLED=true` until Resend is configured and a human has verified sending behavior. For actual delivery, set `EMAIL_PROVIDER=resend`, a verified `EMAIL_FROM`, and `RESEND_API_KEY`; send approval remains required. Do not enable automatic sending for initial deployment.
5. Obtain permission for each crawl source. The crawler honors `robots.txt`; it does not run at startup. Brilliant Directories' published robots guidance describes a default deny-all policy, so do not expect its content to ingest without source-owner authorization.

The overlay is intended for a single Docker host behind a separately operated TLS proxy, not managed container hosting/Kubernetes. Docker startup, live providers, production PostgreSQL, TLS proxy integration, and real email delivery remain unverified in this workspace. The host/operator must supply TLS, secret storage, firewall, backups, updates, and monitoring. See [DESIGN.md](DESIGN.md) and [EVALS.md](EVALS.md) for architecture and verification limits.

For a local demo without Docker, install Task 1 and Task 3 dependencies with `python -m pip install -r requirements.txt` from each service folder, and `npm ci` in Task 2 and `frontend`. Then run each command in its own PowerShell terminal:

```powershell
Push-Location task1-knowledge-brain; $env:APP_ENV='demo'; $env:DATABASE_URL='sqlite:///./data/knowledge.db'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
Push-Location task2-inbox-agent; $env:APP_ENV='demo'; $env:REPOSITORY_MODE='memory'; npm run start
Push-Location task3-meeting-to-scope; $env:APP_ENV='demo'; $env:STORAGE_MODE='sqlite'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
Push-Location frontend; npm run dev -- --port 5173
```

## Deliberate ingestion

After configuring PostgreSQL and the embedding provider, start the services and request ingestion deliberately:

```powershell
Invoke-RestMethod -Method Post http://localhost:8001/ingestion/run -ContentType 'application/json' -Body '{}'
```

The crawler honors `robots.txt` and stops when access is disallowed. Brilliant Directories' published default policy says to disallow all bots; request permission before expecting source content to ingest.

## Verify

```powershell
Push-Location task1-knowledge-brain; python -m pytest -q -p no:cacheprovider tests; Pop-Location
Push-Location task3-meeting-to-scope; python -m pytest -q -p no:cacheprovider tests; Pop-Location
Push-Location task2-inbox-agent; npm ci; npm run typecheck; npm test; Pop-Location
Push-Location frontend; npm ci; npm run build; Pop-Location
python evals/run_model_comparison.py
```

The comparison runner writes measured per-case records only when an API key and two exact Claude model IDs are configured; otherwise it records `blocked/not run`. Required environment variables and limitations are listed in `.env.example` and [EVALS.md](EVALS.md).
