# Codex Build Specification --- AI Tech Consultant

**Version:** 1.0\
**Project:** BusinessLabs / Anthropic Applied AI capstone\
**Goal:** Build a complete, runnable, testable AI Tech Consultant from
an empty repository through implementation, evaluation, documentation,
and demo preparation.

------------------------------------------------------------------------

## 0. Instructions to Codex

You are the lead engineer implementing this project. Build the
application end to end, not merely a plan, mockup, or code snippets.

### Required working method

1.  Inspect the current repository and environment before changing
    anything. Do not overwrite existing work blindly.
2.  Confirm the repository root with `git rev-parse --show-toplevel`.
    Never run Git commands that could include files outside the project.
3.  Create and maintain `IMPLEMENTATION_PLAN.md` with milestones and
    status. Work through the plan sequentially.
4.  Implement small vertical slices. After each slice, run relevant
    tests and fix failures before moving on.
5.  Prefer maintainable, typed, understandable code over unnecessary
    abstractions or many agents.
6.  Use Claude through the official Anthropic SDK at the center of AI
    generation. Model identifiers must be configuration values; do not
    hardcode an unverified model ID.
7.  Do not fabricate test results, model comparisons, screenshots, API
    calls, costs, or completed features. Mark anything not actually
    executed as pending.
8.  Do not leave core behavior as TODOs, pseudocode, hardcoded fake
    responses, or empty handlers. If an external service needs
    credentials, implement the real integration and a clearly labelled
    deterministic test mode.
9.  Never expose secrets. Keep `.env` out of Git. Create `.env.example`
    with placeholders only.
10. Do not automatically commit or push changes. First ensure the Git
    root is correct and show the user the proposed status.
11. Do not ask questions unless truly blocked. Choose sensible defaults,
    document them, and continue.
12. At the end of each milestone, report: files changed, commands run,
    test results, known gaps, and the next milestone.
13. Before declaring completion, run the full test suite, static checks,
    and startup smoke tests. Report actual outcomes.
14. Preserve the required language boundaries: Task 1 Python, Task 2
    TypeScript, Task 3 Python. The frontend may use TypeScript/React.
15. Do not copy the internal implementation of Task 1 into Tasks 2 or 3.
    Both must call Task 1 over HTTP.

### Definition of done

The repository starts with one documented command; the three workflows
operate end to end; Task 1 has image-aware RAG, citations, daily
incremental ingestion, and human escalation; Task 2 has at least 50
synthetic realistic emails, review/feedback, and an auditable
20-consecutive-unchanged-draft eligibility rule; Task 3 has three
role-played transcript fixtures, scope/estimate/proposal generation,
follow-up diff against an approved baseline, and human approval; each
task has at least 20 evaluation cases; at least two Claude model
choices/configurations are compared on the same cases with measured
quality, cost, and speed; documentation and demo plan are complete.

Do not claim that an unrun external API integration or a feature blocked
by credentials is verified. Use a deterministic test mode for automated
tests, but make the UI clearly distinguish test/demo mode from real
model execution.

------------------------------------------------------------------------

## 1. Product summary

Build a reusable AI Tech Consultant for software/service businesses. It
has three connected applications:

1.  **Knowledge Brain (Python):** crawls the Brilliant Directories
    Solution Center, extracts text and screenshots, builds a searchable
    knowledge store, answers questions with evidence/citations, abstains
    when evidence is insufficient, creates human escalations, and
    incrementally refreshes content daily.
2.  **Inbox Agent (TypeScript):** classifies customer emails, calls the
    Knowledge Brain API, drafts source-grounded replies, supports human
    edit/approve/reject/escalate, stores feedback, and tracks when a
    category may qualify for a controlled autonomous-send trial.
3.  **Meeting to Scope (Python):** processes long meeting transcripts,
    extracts structured requirements, checks feasibility through the
    Knowledge Brain API, creates a scope of work, task-level
    low/likely/high estimates, and proposal, then compares follow-up
    meetings against the approved baseline and requires human approval.

The system is designed for multiple software/service businesses in the
future, so isolate business-specific configuration (name, tone, email
policies, hourly rate, currency, timezone, knowledge source) from code.
For this capstone, use the specified Brilliant Directories help center
as the primary knowledge source.

### Required source

`https://support.brilliantdirectories.com/support/sitemap.xml`

Respect robots/access policies, rate limits, and website terms. Do not
bypass access controls.

------------------------------------------------------------------------

## 2. Technology choices

Use the following default stack unless the existing repository contains
a sound, working choice that should be preserved:

-   Python 3.11+
-   FastAPI + Uvicorn for Python HTTP services
-   Pydantic v2 for Python request/response schemas
-   HTTPX for asynchronous HTTP
-   BeautifulSoup + lxml for HTML/XML parsing
-   Anthropic official Python SDK for Task 1 and Task 3
-   TypeScript strict mode + Node.js LTS for Task 2
-   Anthropic official TypeScript SDK for Task 2
-   Zod for TypeScript validation
-   PostgreSQL + pgvector for persistent article/chunk/vector storage
-   React + TypeScript + Vite for the UI
-   Pytest for Python tests; Vitest for TypeScript tests
-   Docker Compose for local services and one-command startup
-   `.env` for local secrets; `.env.example` for placeholders
-   Git for version control

Embedding model/provider is configurable and separate from Claude chat
models. Choose a practical provider supported by available credentials;
document vector dimensions, pricing, limits, and how to configure it. If
no embedding credentials exist, provide a deterministic local/test
embedding adapter for tests only and label it clearly; do not represent
it as production semantic search.

### Model configuration

Provide environment variables such as: - `ANTHROPIC_API_KEY` -
`CLAUDE_MODEL_PRIMARY` - `CLAUDE_MODEL_COMPARISON` -
`EMBEDDING_PROVIDER` - `EMBEDDING_MODEL` - `DATABASE_URL`

Use model IDs that are currently available to the user's Anthropic
account. Do not guess that a model ID is valid. Make model selection
configurable and record the exact IDs used in evaluation output.

------------------------------------------------------------------------

## 3. Repository structure

Create or adapt to this structure without destroying existing user
files:

``` text
ai-tech-consultant/
  task1-knowledge-brain/
    app/
      __init__.py
      main.py
      config.py
      schemas.py
      database.py
      models.py
      sitemap.py
      crawler.py
      parser.py
      chunking.py
      embeddings.py
      retrieval.py
      answering.py
      image_analysis.py
      escalation.py
      scheduler.py
    tests/
    requirements.txt
    Dockerfile
  task2-inbox-agent/
    src/
      index.ts
      config.ts
      schemas.ts
      knowledge-client.ts
      classifier.ts
      drafting.ts
      feedback.ts
      autonomy.ts
      repository.ts
      routes.ts
    tests/
    package.json
    tsconfig.json
    Dockerfile
  task3-meeting-to-scope/
    app/
      __init__.py
      main.py
      config.py
      schemas.py
      transcript.py
      requirement_extraction.py
      feasibility.py
      scope_generation.py
      estimation.py
      proposal.py
      scope_diff.py
      approval.py
    tests/
    requirements.txt
    Dockerfile
  frontend/
    src/
      app/
      components/
      pages/
      api/
      types/
    package.json
    Dockerfile
  evals/
    knowledge_cases.jsonl
    inbox_emails.jsonl
    scope_cases.jsonl
    run_evals.py
    results/
  sample_data/
    transcripts/
    README.md
  shared-docs/
    api-contract.md
    architecture.md
  docker-compose.yml
  .env.example
  .gitignore
  IMPLEMENTATION_PLAN.md
  README.md
  DESIGN.md
  EVALS.md
  AI_LOG.md
```

The final implementation may adjust the exact files, but must retain
clear separation between the three tasks and the frontend.

------------------------------------------------------------------------

## 4. Data model

Use migrations or an explicit reproducible database initialization
mechanism. Use foreign keys and indexes where appropriate.

### Knowledge Brain entities

**Article** - `id` stable primary key - `url` unique canonical URL -
`title` - `content_hash` - `sitemap_lastmod` nullable - `status`
(`active`, `removed`, `failed`) - `last_ingested_at` - `created_at`,
`updated_at`

**Chunk** - `id` stable primary key - `article_id` foreign key -
`section_heading` - `content` - `embedding` vector with correct
configured dimensions - `metadata` JSON - `content_hash` - `active` -
timestamps

**ImageAsset** - `id` - `article_id` - `image_url` - `alt_text` -
`nearby_context` - `description` - `analysis_status` - `content_hash` -
timestamps

**IngestionRun** - `id`, `started_at`, `finished_at` - status, URLs
discovered, created, updated, removed, failed - error summary

**IngestionPage** - URL, status, attempts, last error, content hash,
retry-after, updated timestamp

**Escalation** - `id`, question, reason, evidence JSON, status, created
time - approved answer, reviewer, reviewed time, version, expiry if
relevant

**ApprovedKnowledge** - `id`, answer, evidence/source references, scope
(global or customer-specific), approved_by, version, active, expiry

### Inbox entities

**EmailCase** - ID, subject, body, category, urgency, risk, customer
reference - original draft, final reply, source URLs, model/prompt
version - approval status, whether modified, timestamps

**FeedbackEvent** - email case ID, event type
(edited/approved/rejected/sent/escalated) - before/after text or safe
diff, reviewer, reason, timestamp

**AutonomyState** - category, consecutive unchanged count, eligible
flag, enabled flag - last qualifying event, last failure, updated time

### Meeting-to-Scope entities

**Project** - ID, client/project label, approved baseline version,
status, timestamps

**MeetingTranscript** - ID, project ID, meeting date, transcript text,
speakers/metadata, version

**Requirement** - stable ID, project ID, description, status, priority -
source meeting and source passage/timecode - acceptance criteria,
dependencies, feasibility status/evidence - estimate status, version,
active

**EstimateTask** - ID, requirement ID, task description, low/likely/high
hours - rationale, assumptions, dependencies, reviewer status

**ScopeVersion** - ID, project ID, version number, requirements
snapshot, deliverables, exclusions, assumptions, acceptance criteria,
approved flag, approver, approved time

**Proposal** - ID, project ID, scope version, content, pricing
assumptions, status, approval metadata

**ChangeReport** - project ID, baseline version, new
transcript/version - added/removed/modified/conflicting requirements -
estimate impact and review status

Use synthetic demo identifiers and data. Avoid storing unnecessary
personal data.

------------------------------------------------------------------------

## 5. Task 1 --- Knowledge Brain requirements

### 5.1 Sitemap discovery and crawler

-   Parse the sitemap XML and recursively handle sitemap-index files if
    present.
-   Validate allowed host/domain and URL scheme; reject unsafe URLs.
-   Deduplicate canonical URLs.
-   Store sitemap `lastmod` where present.
-   Use polite concurrency, configurable rate limits, timeouts, bounded
    retries, exponential backoff, and a meaningful User-Agent.
-   Checkpoint each page's status so interrupted ingestion resumes.
-   Isolate page failures; one page failure must not terminate the
    entire run.
-   Compute content hashes to detect changes even when sitemap metadata
    is missing/unreliable.
-   Mark removed pages inactive and exclude all their chunks from
    retrieval.
-   Do not re-ingest unchanged pages unnecessarily.
-   Provide a CLI command and API to trigger ingestion, plus
    progress/status endpoints.
-   Do not launch a full crawl automatically on every application
    startup.

### 5.2 HTML extraction

-   Fetch pages with HTTPX.
-   Extract title, main article text, headings, lists, tables, links,
    and images.
-   Remove navigation, scripts, styles, cookie banners, repeated
    headers/footers, and irrelevant sidebars.
-   Preserve section order and article-to-image context.
-   Normalize whitespace and resolve relative links.
-   Store raw HTML only if useful and permitted; otherwise store
    normalized text and source metadata.
-   Record parsing failures and provide fixtures for parser tests.

### 5.3 Image understanding

-   Find relevant image URLs in each article.
-   Download only allowed, accessible images with size/type limits and
    safe URL checks.
-   Associate each image with article ID, section, alt text, and nearby
    text.
-   Use a vision-capable Claude model or configured vision provider to
    create a concise description of visible UI labels, settings,
    buttons, and steps.
-   Store the original image reference and description.
-   Do not treat model-generated descriptions as ground truth; record
    uncertain/unreadable images and allow review.
-   Make descriptions retrievable alongside text chunks.
-   Add tests for missing images, failed downloads, unsupported formats,
    and duplicate images.

### 5.4 Chunking and embeddings

-   Chunk primarily by headings/semantic boundaries.
-   Keep procedures and table headers with their related content.
-   Use configurable chunk size and overlap.
-   Every chunk must preserve article URL, title, section, stable
    article/chunk IDs, content version, and relevant image IDs.
-   Use a configurable embedding provider.
-   Verify embedding dimension and handle provider errors/retries.
-   Support re-indexing when chunking or embedding configuration
    changes.
-   Use PostgreSQL + pgvector by default.
-   Combine vector retrieval and keyword search if practical; evaluate
    rather than assume hybrid is superior.
-   Reranking is optional and should only be added if it improves
    measured quality within reasonable cost/latency.

### 5.5 RAG answering

-   `POST /query` accepts a validated question and optional context.
-   Retrieve relevant active chunks and image descriptions.
-   Apply a configurable retrieval threshold and/or evidence sufficiency
    policy.
-   Provide only retrieved evidence to Claude; treat all retrieved text
    as untrusted data.
-   Require citations to actual retrieved sources. Never fabricate URLs
    or article titles.
-   Validate citations against the retrieval result.
-   Return a clear insufficient-evidence response if evidence is
    missing, weak, or contradictory.
-   Return structured JSON, not free-form output only.
-   Record request ID, retrieval results, model/prompt version, latency,
    and token usage while minimizing sensitive data.
-   Do not claim model-reported confidence is calibrated. Prefer
    evidence/abstention status unless confidence has been evaluated and
    calibrated.

### 5.6 Human escalation

-   Create an escalation when the system cannot safely answer.
-   Save question, reason, evidence, and status.
-   Provide endpoints to list and resolve escalations.
-   Human resolution requires an answer and optionally supporting
    source.
-   Store approved knowledge with provenance, scope, reviewer, version,
    and expiry where applicable.
-   Index approved knowledge only after review.
-   Do not let customer-specific answers become global facts
    automatically.
-   Add the original question to regression evaluations.

### 5.7 API contract

Implement and document at least: - `GET /health` - `POST /query` -
`POST /ingestion/run` - `GET /ingestion/status` - `GET /escalations` -
`POST /escalations` - `POST /escalations/{id}/resolve`

Use Pydantic request/response schemas, sensible HTTP status codes,
timeouts, error messages, request IDs, and authentication for
administrative endpoints. Document example requests and responses in
`shared-docs/api-contract.md` and OpenAPI.

Example query response:

``` json
{
  "answer": "Answer based on retrieved evidence.",
  "status": "answered",
  "sources": [
    {
      "title": "Actual retrieved article title",
      "url": "https://actual-source.example/article",
      "chunk_id": "chunk-id"
    }
  ],
  "needs_human": false,
  "request_id": "request-id"
}
```

The URL above is a schema illustration only. In real responses, source
fields must come from stored evidence.

### 5.8 Daily refresh

-   Implement a scheduler or scheduled command for daily sitemap checks.
-   Keep scheduling configurable and prevent duplicate concurrent runs.
-   Update only changed pages, deactivate removed pages, and handle
    changed/deleted images.
-   Persist run summaries and errors.
-   Provide a way to run a refresh manually.
-   Document deployment scheduling if the local scheduler is not running
    in production.

------------------------------------------------------------------------

## 6. Task 2 --- Inbox Agent requirements

### 6.1 Language and client

-   Strict TypeScript with Node.js or Next.js.
-   Task 2 must use a typed HTTP client to call Task 1.
-   Do not implement crawling, embeddings, or vector retrieval inside
    Task 2.
-   Validate API responses with Zod.
-   Use request timeouts, bounded retries where safe, request IDs, and
    clear error states.

### 6.2 Email dataset

Create at least 50 realistic synthetic emails spanning: - How-to -
Troubleshooting - Project request - Refund/cancellation - Complaint -
Quote request - Follow-up - Other/ambiguous

Store expected category, urgency/risk, key facts, expected action,
expected evidence if known, and whether escalation is expected. Do not
use real personal information. Keep a held-out subset for evaluation.

### 6.3 Pipeline

1.  Validate incoming email.
2.  Classify intent/category, urgency, and risk.
3.  Identify the knowledge question.
4.  Call Task 1 API.
5.  Draft reply using evidence and configured company tone.
6.  Validate structured output.
7.  Apply safety/policy checks.
8.  Route to human review or permitted controlled automation.
9.  Store final outcome and feedback.

### 6.4 Draft schema

Return fields such as: - `category` - `summary` - `draft` -
`source_urls` - `risk` - `needs_human_approval` - `next_action` -
`reason_for_escalation`

Reject malformed output and never send unsupported claims. If Task 1 is
unavailable, do not fabricate product facts. Refunds, account security,
legal commitments, complaints with serious consequences, and commercial
commitments require human review.

### 6.5 UI

Build a usable inbox screen with: - List of cases and statuses -
Original email - Category, urgency, and risk - Retrieved evidence and
links - Draft editor - Approve, edit-and-approve, reject, escalate
controls - Feedback/reason field - Audit/history view

Use simulated sending by default unless a real provider is deliberately
configured. Clearly label simulated sends. Never report that a real
email was sent if it was not.

### 6.6 Feedback and measurable improvement

Persist original input, generated draft, final sent content, source
URLs, model/prompt version, edits, approval outcome, reviewer reason,
and timestamps. - Analyze recurring edits and rejections. - Improve
versioned prompts/routing/approved examples. - Run the same regression
tests before deploying a change. - Compare quality, latency, and cost
before/after. - Preserve rollback to the previous version. - Do not
claim online model training unless actually implemented.

### 6.7 Twenty-consecutive-unchanged rule

-   Define category/subcategory precisely.
-   Count only cases where the generated draft was actually sent without
    substantive modification and passed required checks.
-   Track the consecutive count per category.
-   Reset/invalidate the streak on edits, rejection, safety failure, or
    relevant quality failure.
-   Reaching 20 makes the category eligible for a controlled trial; it
    does not automatically make every email safe.
-   Keep sensitive/high-risk categories human-approved.
-   Require a configuration flag and a disable switch for any
    autonomous-send trial.
-   Log each autonomous decision and support audit/reversal where
    possible.
-   Add tests for counter increments, resets, category separation, and
    safeguards.

------------------------------------------------------------------------

## 7. Task 3 --- Meeting to Scope requirements

### 7.1 Transcript fixtures

Provide at least three role-played synthetic transcripts or clearly
labelled demo fixtures: - Meeting A: website search, filters, mobile
experience. - Meeting B: checkout, notifications, payment integration. -
Meeting C: follow-up to A with at least one addition, one removal, and
one modification including a delivery expectation change.

The actual capstone asks students to role-play and record meetings. Do
not falsely claim fixture text was recorded with a real person. Document
whether each transcript is a real consented recording/transcription or a
synthetic fixture.

### 7.2 Long-context handling

-   Store the original transcript and metadata.
-   Chunk long transcripts while retaining speaker and timestamp where
    available.
-   Extract structured facts from chunks and merge them.
-   Detect contradictory statements.
-   Link every important requirement/commitment to a source passage.
-   Do not use a summary as the sole evidence for dates, prices, or
    contractual commitments.

### 7.3 Agent stages

Use distinct, testable stages (modules or orchestrated calls): 1.
Transcript analyst: requirements, decisions, constraints, open
questions. 2. Feasibility agent: calls Task 1 API to verify documented
product capabilities. 3. Scope agent: deliverables, exclusions,
assumptions, dependencies, acceptance criteria. 4. Estimation agent:
task breakdown and low/likely/high hours with rationale. 5.
Proposal/review agent: combines outputs, checks consistency, requests
human approval.

Avoid multiple agents with overlapping responsibilities. Each stage
needs a schema, input, output, and error path.

### 7.4 Requirement record

Each requirement must include: - Stable ID - Description - Status
(confirmed/unclear/disputed) - Priority - Source meeting and
passage/timestamp - Acceptance criteria - Dependencies - Feasibility
result and source evidence - Estimate status - Version/active state

Distinguish explicit client statements from AI inference. Missing
knowledge-base evidence must result in "unknown/needs investigation,"
not a claim that a feature does not exist.

### 7.5 Scope of work

Produce: 1. Project objective 2. Current problem 3. Confirmed
requirements 4. Proposed solution 5. Deliverables 6. Explicit exclusions
7. Assumptions and dependencies 8. Acceptance criteria 9. Client
responsibilities 10. Open questions and risks

Acceptance criteria must be testable. Unconfirmed requirements must
remain marked as assumptions/questions.

### 7.6 Estimation

Break deliverables into engineering tasks (clarification/design,
backend, frontend, integration, testing, deployment/documentation as
appropriate). For each task store: - Low, likely, high hours -
Rationale - Assumptions - Dependencies - Uncertainty - Reviewer status

Calculate totals programmatically. Do not allow the model to invent a
fixed delivery date or price without inputs. If price is generated, use
configured hourly rate, currency, taxes, and pricing rules; label it as
a draft requiring approval.

### 7.7 Proposal

Include executive summary, problem/solution, scope, deliverables,
milestones, effort and pricing assumptions, client responsibilities,
exclusions, dependencies, risks, open questions, and approval steps.
Cross-check proposal against the scope and estimates. Never promise a
feature marked unverified.

### 7.8 Follow-up scope diff

-   Compare the new transcript against the last **human-approved
    baseline**, not an unapproved draft.
-   Match stable requirement IDs where possible.
-   Detect additions, removals, modifications, contradictions, and
    unresolved changes.
-   Re-estimate affected tasks and show impact.
-   Flag potential out-of-scope work for review and possible additional
    quotation.
-   Show original vs new requirement and source passages.
-   Require human approval before promoting a revision to the new
    baseline or sending it to a client.
-   Maintain version history and reviewer/timestamp.

### 7.9 UI

Build a scope workspace with transcript input, extracted requirements,
source passages, feasibility evidence, estimate table, scope/proposal
preview, change report, version history, and approve/reject controls.

------------------------------------------------------------------------

## 8. Frontend requirements

Use React + TypeScript + Vite unless a working frontend already exists.

Provide three primary pages: 1. **Knowledge Chat:** question box,
answer, citations, relevant image references, insufficient-evidence
state, escalation state. 2. **Inbox Review:** email queue, original
message, category/risk, evidence, editable draft, approval actions,
feedback history. 3. **Scope Builder:** transcript selection/upload,
requirements, feasibility, estimates, proposal, baseline comparison,
approval.

Include loading, empty, success, and failure states. Make it clear when
the system is in demo/test mode. Do not use hardcoded "successful" AI
results in production UI. Add basic accessibility, labels, and
responsive layout. Keep UI simple and usable rather than spending time
on decorative animations.

------------------------------------------------------------------------

## 9. Security, safety, and reliability

Implement and test: - Environment-based secrets; `.env` never
committed. - Input size and type limits. - URL/domain validation for
crawler and image downloads; prevent SSRF and local/private network
access. - Timeouts and bounded retries. - Idempotency for ingestion
jobs, escalation resolution, and sending actions. - Prompt-injection
defense: emails, transcripts, webpage text, and retrieved chunks are
untrusted content. - Human approval for client-facing proposals and
high-risk email categories. - Audit records for generated output,
evidence, model/prompt versions, edits, approvals, and sends. - Data
minimization and safe logging; do not log API keys or unnecessary
personal data. - Clear error messages to users, detailed safe logs
internally. - Deleted article chunks must never be returned by
retrieval. - Autonomous sending disabled by default. - A global
emergency disable flag for automation.

------------------------------------------------------------------------

## 10. Evaluation requirements

Create at least 20 cases per task (60 or more total). Keep a fixed
held-out subset and do not silently remove failed cases.

### Knowledge cases

Include direct answer, multi-article answer, image-related fact, no
evidence, conflicting evidence, incorrect citation attempt, changed
article, removed article, malformed input, crawler failure, API timeout,
and escalation resolution.

### Inbox cases

Include all categories, ambiguous email, urgent complaint, refund
request, missing evidence, Knowledge Brain unavailable, prompt injection
in email, invalid model output, human edit, rejection, unchanged draft
counter, reset condition, high-risk category, and duplicate-send
prevention.

### Scope cases

Include explicit and vague requirements, missing acceptance criteria,
existing setting, insufficient feasibility evidence, long transcript,
contradiction, new/removed/modified requirements, out-of-scope change,
estimate uncertainty, proposal consistency, and blocked approval.

### Model comparison

-   Compare at least two Claude models or configurations available to
    the account.
-   Use the same evaluation inputs and equivalent settings wherever
    possible.
-   Record exact model ID, prompt version, timestamp, token usage, cost
    calculation, latency, pass/fail, failure reason.
-   Measure quality, cost, and speed; include median and tail latency
    where practical.
-   Use human-reviewed references for estimates and scope diffs.
-   Report only measurements actually collected.
-   A smaller/faster model may be used for classification only if tests
    support the choice.
-   Store machine-readable results under `evals/results/` and summarize
    them in `EVALS.md`.

Example CSV fields:
`task,case_id,model_id,prompt_version,expected,actual,passed,input_tokens,output_tokens,latency_ms,cost_usd,failure_reason`

If API keys or billing are unavailable, make the evaluation runner
report "blocked/not run" rather than fabricating results.

------------------------------------------------------------------------

## 11. Testing and quality gates

Implement: - Python unit tests for sitemap parsing, URL validation,
parser, chunking, retrieval filters, citation validation, escalation,
and scope diff. - Python API tests using FastAPI's test client or
HTTPX. - TypeScript unit tests for schema validation, classification
routing, API errors, feedback events, and autonomy counter. -
Integration tests for Task 2/3 calling a mocked Task 1 API. - End-to-end
smoke test for each of the three workflows. - Regression test fixtures
for known failures.

Quality gates: - Python formatting/linting (Ruff recommended). -
TypeScript typecheck and lint. - All automated tests pass. - No secrets
in Git. - Docker Compose starts required services. - `/health` endpoints
respond. - Demo/test mode clearly distinguished from live model mode. -
Failed tests are reported honestly.

Use deterministic mocks in CI so tests do not require live API
credentials. Add a separate opt-in live integration test for Claude and
embeddings.

------------------------------------------------------------------------

## 12. Docker and one-command startup

Create Dockerfiles for the services and a root `docker-compose.yml` that
starts: - PostgreSQL with pgvector - Knowledge Brain - Inbox Agent -
Meeting-to-Scope - Frontend

Provide health checks and service dependencies. Do not run a full crawl
automatically during startup. The first crawl must be triggered
deliberately and should be resumable.

Document one command, for example:

``` bash
docker compose up --build
```

Provide a separate command to run migrations/initialization, a command
to ingest the source, and commands to run tests/evaluations. Ensure the
exact commands work before documenting them.

If Docker is unavailable in the development environment, still provide
and test local startup commands, and state that Docker startup was not
verified.

------------------------------------------------------------------------

## 13. Required documentation

### `README.md` (maximum one page)

-   What the application does
-   Architecture summary
-   Prerequisites
-   Environment configuration
-   One-command startup
-   How to run ingestion
-   How to run tests
-   Demo/test-mode note

### `DESIGN.md` (3--5 pages)

-   Business problem and design rationale
-   Architecture diagram
-   Why Task 1 is a shared API
-   Data model and retrieval approach
-   Agent responsibilities and handoffs
-   Model and database choices
-   Features deferred and why
-   Security, failure modes, limitations, next steps

### `EVALS.md` (2--3 pages)

-   Evaluation methodology and datasets
-   At least 20 cases per task
-   Exact model IDs compared
-   Quality, cost, speed, reliability, and safety results
-   Failures and mitigations
-   Distinguish measured values from pending experiments

### `AI_LOG.md` (maximum one page)

-   Five useful prompts actually used with Codex
-   One genuine example where generated code was rejected or changed and
    why
-   Do not fabricate coding-assistant history.

### `IMPLEMENTATION_PLAN.md`

-   Milestones, tasks, status, test command, blockers, and acceptance
    evidence.
-   Update it as work progresses.

### Demo plan

Prepare a maximum 10-minute demo: - First 30 seconds on camera, as
required by the brief. - Knowledge query with citations and one
insufficient-evidence case. - Inbox email draft, edit/approval, and
feedback. - Transcript-to-scope and follow-up diff. - Show evaluation
results and one genuine failure. - State limitations honestly.

------------------------------------------------------------------------

## 14. Recommended implementation phases

### Phase 0 --- Inspect and plan

Inspect repo, confirm Git root, identify existing code, document plan
and decisions.

### Phase 1 --- Skeleton

Create packages, configuration, schemas, health endpoints, test setup,
and Docker Compose skeleton.

**Exit gate:** services import/start; `/health` works; secrets are
excluded.

### Phase 2 --- Knowledge ingestion

Sitemap parser, URL validation, crawler, article parser, image
discovery, persistent manifest, retries/checkpointing.

**Exit gate:** small crawl can resume after interruption and does not
duplicate unchanged articles.

### Phase 3 --- Knowledge RAG/API

Database, chunks, embeddings, retrieval, Claude answer generation,
citation validation, abstention, escalation, daily refresh.

**Exit gate:** direct query test returns valid citations; unknown
question escalates; deleted source is not retrieved.

### Phase 4 --- Inbox Agent

Dataset, typed Task 1 client, classification, drafts, review UI,
feedback persistence, autonomy eligibility logic.

**Exit gate:** sample email flows end-to-end; unavailable Knowledge
Brain fails safely; counter tests pass.

### Phase 5 --- Meeting-to-Scope

Transcripts, long-context processing, requirements, feasibility,
estimates, proposal, approved baseline and scope diff.

**Exit gate:** Meeting A generates draft artifacts; Meeting C produces a
change report; unapproved proposal cannot be sent/promoted.

### Phase 6 --- UI and integration

Connect all three workflows, add error/loading states, audit history,
and demo mode.

**Exit gate:** all three end-to-end paths work.

### Phase 7 --- Evaluation

Build 20+ cases/task, run model comparisons, collect cost/speed/quality,
analyze failures, run regression tests.

**Exit gate:** real results are recorded; unrun cases are marked
pending.

### Phase 8 --- Submission readiness

Complete docs, startup command, demo plan, clean secrets, verify Git
status and run all checks.

**Exit gate:** clean reproducible run and honest completion report.

------------------------------------------------------------------------

## 15. Final acceptance checklist

The project is not complete until all applicable items below are
verified.

### Task 1

-   [ ] Sitemap and nested sitemap processing
-   [ ] Polite resumable crawler with persisted status
-   [ ] HTML extraction and image-aware indexing
-   [ ] Chunking, embeddings, and persistent vector retrieval
-   [ ] Grounded answers with validated source citations
-   [ ] Insufficient-evidence handling and human escalation
-   [ ] Daily incremental updates and removal handling
-   [ ] Documented API consumed by both downstream tasks

### Task 2

-   [ ] At least 50 realistic synthetic email cases
-   [ ] Strict TypeScript and validated schemas
-   [ ] Task 1 API client with timeouts/errors
-   [ ] Drafts with evidence and risk classification
-   [ ] Human edit/approve/reject/escalate UI
-   [ ] Feedback history and measurable prompt improvement
-   [ ] Auditable 20-consecutive-unchanged eligibility rule
-   [ ] Autonomous sending disabled by default and safely gated

### Task 3

-   [ ] At least three meeting transcripts/fixtures
-   [ ] Long transcript processing and source references
-   [ ] Feasibility check through Task 1 API
-   [ ] Scope of work and acceptance criteria
-   [ ] Task-level low/likely/high hour estimates
-   [ ] Client proposal with assumptions and exclusions
-   [ ] Follow-up diff against human-approved baseline
-   [ ] Out-of-scope detection and mandatory approval

### Evaluation and delivery

-   [ ] At least 20 evaluation cases per task
-   [ ] At least two model choices/configurations compared
-   [ ] Measured quality, cost, and speed with failures retained
-   [ ] Unit, integration, and end-to-end tests
-   [ ] One-command startup documented and verified where possible
-   [ ] README, DESIGN, EVALS, AI_LOG, IMPLEMENTATION_PLAN complete
-   [ ] Demo plan covers all workflows and a failure
-   [ ] No secrets or accidental unrelated files committed
-   [ ] Completion report distinguishes done, blocked, and unverified
    items

------------------------------------------------------------------------

## 16. First instruction to execute

Start with **Phase 0 only**. Inspect the current working directory and
repository, report the discovered files and Git root, create
`IMPLEMENTATION_PLAN.md`, and then implement Phase 1. Do not attempt to
generate the entire project in one response or one giant code dump.
Continue milestone by milestone, run tests after every milestone, fix
failures, and keep going until the acceptance checklist is satisfied or
a real blocker is documented.

At the end, provide: 1. What is implemented 2. Exact commands to run it
3. Test commands and actual results 4. Environment variables still
required 5. Any incomplete or unverified acceptance criteria 6. The next
action, if a blocker remains
