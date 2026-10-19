import { Router } from "express";
import type { Request, Response, NextFunction, RequestHandler } from "express";
import { randomUUID, timingSafeEqual } from "node:crypto";

import { demoMode } from "./config.js";
import { config } from "./config.js";
import { feedbackSummary } from "./feedback.js";
import { emailInputSchema, healthResponseSchema, reviewRequestSchema } from "./schemas.js";
import type { EmailRepository } from "./repository.js";
import type { InboxAgent } from "./agent.js";

export function createRouter(repository: EmailRepository, agent: InboxAgent): Router {
  const router = Router();
  const asyncRoute = (handler: (request: Request, response: Response) => Promise<void>): RequestHandler =>
    (request, response, next) => { void handler(request, response).catch(next); };
  const pathParam = (request: Request, key: string): string | null => {
    const value = request.params[key];
    return typeof value === "string" ? value : null;
  };

  router.get("/health", (_request, response) => {
    const payload = healthResponseSchema.parse({ status: "ok", service: "inbox-agent", mode: demoMode ? "demo" : "live" });
    response.json(payload);
  });

  router.get("/emails", asyncRoute(async (_request, response) => {
    response.json({ cases: await repository.listCases(), mode: demoMode ? "demo" : "live" });
  }));

  router.post("/emails", asyncRoute(async (request, response) => {
    const parsed = emailInputSchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: "Invalid email input", issues: parsed.error.issues.map((issue) => issue.path.join(".")) });
      return;
    }
    const requestId = request.header("Idempotency-Key") ?? randomUUID();
    const emailCase = await repository.createCase(parsed.data, requestId);
    response.status(201).json({ case: emailCase });
  }));

  router.get("/emails/:id", asyncRoute(async (request, response) => {
    const id = pathParam(request, "id");
    if (!id) { response.status(400).json({ error: "Invalid email case id" }); return; }
    const emailCase = await repository.getCase(id);
    if (!emailCase) { response.status(404).json({ error: "Email case not found" }); return; }
    response.json({ case: emailCase });
  }));

  router.post("/emails/:id/process", asyncRoute(async (request, response) => {
    const id = pathParam(request, "id");
    if (!id) { response.status(400).json({ error: "Invalid email case id" }); return; }
    const emailCase = await agent.process(id);
    response.json({ case: emailCase });
  }));

  router.post("/emails/:id/review", asyncRoute(async (request, response) => {
    const id = pathParam(request, "id");
    if (!id) { response.status(400).json({ error: "Invalid email case id" }); return; }
    const parsed = reviewRequestSchema.safeParse(request.body);
    if (!parsed.success) {
      response.status(400).json({ error: "Invalid review action", issues: parsed.error.issues.map((issue) => issue.path.join(".")) });
      return;
    }
    if (parsed.data.action === "edit_approve" && !parsed.data.finalReply?.trim()) {
      response.status(400).json({ error: "finalReply is required for edit_approve" });
      return;
    }
    const emailCase = await agent.review(id, parsed.data);
    response.json({ case: emailCase, simulated: emailCase.status === "sent_simulated" });
  }));

  router.get("/emails/:id/feedback", asyncRoute(async (request, response) => {
    const id = pathParam(request, "id");
    if (!id) { response.status(400).json({ error: "Invalid email case id" }); return; }
    if (!await repository.getCase(id)) { response.status(404).json({ error: "Email case not found" }); return; }
    const events = await repository.listFeedback(id);
    response.json({ events, summary: feedbackSummary(events) });
  }));

  router.get("/autonomy", asyncRoute(async (_request, response) => {
    response.json({
      states: await repository.listAutonomy(),
      autoSendConfigured: config.AUTO_SEND_ENABLED,
      globalDisableActive: config.GLOBAL_AUTOMATION_DISABLED,
      emailProvider: config.EMAIL_PROVIDER,
    });
  }));

  router.patch("/autonomy/:categoryKey/enabled", asyncRoute(async (request, response) => {
    const categoryKey = pathParam(request, "categoryKey");
    if (!categoryKey) { response.status(400).json({ error: "Invalid category key" }); return; }
    if (config.APP_ENV === "production" && !config.ADMIN_API_TOKEN) { response.status(503).json({ error: "Admin authentication is not configured" }); return; }
    if (config.ADMIN_API_TOKEN) {
      const provided = request.header("X-Admin-Token") ?? "";
      const expected = Buffer.from(config.ADMIN_API_TOKEN);
      const actual = Buffer.from(provided);
      if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) { response.status(401).json({ error: "Valid X-Admin-Token header required" }); return; }
    }
    if (typeof request.body?.enabled !== "boolean") { response.status(400).json({ error: "enabled must be a boolean" }); return; }
    const existing = (await repository.listAutonomy()).find((item) => item.categoryKey === categoryKey);
    if (request.body.enabled && !existing?.eligible) { response.status(409).json({ error: "Category must reach the 20-send eligibility threshold first" }); return; }
    const state = await repository.setAutonomyEnabled(categoryKey, request.body.enabled);
    response.json({ state });
  }));

  return router;
}

export function safeErrorMiddleware(error: unknown, _request: Request, response: Response, _next: NextFunction): void {
  const message = error instanceof Error ? error.message : "Request failed";
  if (message === "Email case was not found") { response.status(404).json({ error: "Email case not found" }); return; }
  if (message === "Draft the email before reviewing it") { response.status(409).json({ error: message }); return; }
  response.status(500).json({ error: "The inbox request could not be completed" });
}
