# AI assistance log

This work used one consolidated user brief. These five excerpts are the actual instructions applied; they were not five separate conversations:

1. “Read `Codex_AI_Tech_Consultant_Spec.md` completely. Treat it as the source of truth for this project.”
2. “Act as the lead engineer and build the entire AI Tech Consultant from the existing repository state through a working, tested, documented implementation.”
3. “Task 1 must use Python; Task 2 must use strict TypeScript; Task 3 must use Python.”
4. “Task 2 and Task 3 must consume Task 1 exclusively through its documented HTTP API for product knowledge.”
5. “After every phase, run the relevant tests, fix failures, and report the actual results.”

One generated implementation was rejected during evaluation: the initial inbox urgency fallback classified nearly every non-ambiguous category as low urgency. It disagreed with the labeled customer email fixtures, including normal-priority troubleshooting and follow-up messages. We replaced that fallback with explicit low/high/urgent signals and reran all 50 classification cases; the final measured fixture agreement was 50/50. Scope feasibility stays an HTTP request to Task 1 rather than reusing Task 1's internals, per the source specification.

No model quality, token cost, or Claude latency result is claimed here; the provider credentials and exact comparison model IDs were not configured. See [EVALS.md](EVALS.md).
