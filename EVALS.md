# Evaluations and quality gates

## Method

Regression fixtures live in `evals/`: 20 knowledge questions (`knowledge_cases.jsonl`), 50 synthetic customer emails (`inbox_emails.jsonl`), 20 scope cases (`scope_cases.jsonl`), and three explicitly synthetic meeting transcripts. No fixture claims to be a real customer interaction or recording. The test suites exercise deterministic policy and data handling without live credentials. These are regression checks against hand-authored synthetic labels, not a substitute for blinded human review.

| Task | Evaluated behavior | Automated result |
|---|---|---|
| 1 Knowledge Brain | 20 answerable/unknown/conflicting retrieval-policy cases; parser, sitemap, chunk IDs, incremental state, API citations, abstention, image metadata, human escalation, customer scope, audit, scheduler and locking | 30 pytest tests passed; 3 subtests passed (after adding the 20-case regression fixture) |
| 2 Inbox Agent | All 50 fixture categories, subcategories, urgency and risk labels; Task 1 HTTP response validation/errors; feedback summary; 20-send counter and reset; health API | 56 Vitest tests passed; strict TypeScript typecheck passed |
| 3 Meeting to Scope | 20 transcript-to-requirement/estimate/proposal cases; 3 transcript fixtures; long-turn chunking, contradiction flags, unknown feasibility through mocked Task 1 HTTP; approved-baseline additions/removals/modifications and out-of-scope flags; production storage guard | 29 pytest tests passed |

Task 2's 50/50 rule-label agreement is exact matching against the fixture's deterministic reference labels. It does not measure Claude classification, factual reply quality, customer satisfaction, or production mail delivery. Task 3's 20 scope cases test source passage retention, uncertainty behavior, monotonic estimate ranges, proposal disclaimers, and output structure; they are not human-reviewed estimates or semantic model scores. Task 1's fixture tests retrieval-policy helpers and are not a live corpus retrieval benchmark.

## Model comparison protocol and current status

`python evals/run_model_comparison.py` submits the same 20 knowledge cases and passage text to two distinct, account-valid model IDs in `CLAUDE_MODEL_PRIMARY` and `CLAUDE_MODEL_COMPARISON`. It records exact IDs, prompt version, case/reference/response, pass/fail, input/output token use, wall latency, failure reason, and cost only if both configured per-million-token rates are present. Quality is a fixed policy check for supported answers, abstention on unknowns, and conflict handling. `evals/results/model_comparison.jsonl` contains per-case measurements and `model_comparison_status.json` contains a summary.

**This environment did not have an Anthropic key or configured model IDs. No Claude comparison was run; there are no measured quality, speed, or cost results to report.** The runner writes an explicit `blocked/not run` status rather than synthesizing measurements. Exact models compared: none. PostgreSQL/pgvector and Resend are also not live-tested; Docker is unavailable. Set `ANTHROPIC_API_KEY`, `CLAUDE_MODEL_PRIMARY`, `CLAUDE_MODEL_COMPARISON`, `CLAUDE_INPUT_COST_PER_MTOK`, and `CLAUDE_OUTPUT_COST_PER_MTOK`, then rerun to produce measured outputs. Cost remains null if rates are omitted. The classifier and scope estimate rules run locally and have no Claude token cost.

## Known risks and mitigations

- [Brilliant Directories robots guidance](https://support.brilliantdirectories.com/support/solutions/articles/12000075850) describes a default deny-all rule. No live crawl was attempted. The crawler honors live robots rules and fails closed; an authorized robots allowance is needed before ingesting production documentation.
- A small synthetic dataset can overfit rule tuning. Add anonymized, human-labeled examples before judging generalization.
- Heuristic contradiction detection is conservative but not complete. Contradictions and weak retrieval cause escalation where detected; a reviewer remains necessary.
- Demo embeddings are token-hash vectors, and demo generation is extractive/template-based. They are explicitly labelled and not representative of live Claude quality.
- Estimate ranges are transparent planning rules and need engineer review. Scope output cannot promise fixed delivery or price without configured commercial inputs and approval.
- Test suites mock Task 1 for Task 2/3 integration. Live HTTP, keys, model IDs, Resend, and Postgres were not available for end-to-end verification.
