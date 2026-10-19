import { z } from "zod";

export const emailCategorySchema = z.enum([
  "how_to",
  "troubleshooting",
  "project_request",
  "refund_cancellation",
  "complaint",
  "quote_request",
  "follow_up",
  "other_ambiguous",
]);

export const emailInputSchema = z.object({
  subject: z.string().trim().min(1).max(300),
  body: z.string().trim().min(1).max(10000),
  customerReference: z.string().trim().max(120).optional(),
  customerId: z.string().trim().max(120).optional(),
  from: z.string().email().max(254).optional(),
}).strict();

export const task1SourceSchema = z.object({ title: z.string(), url: z.string().url(), chunk_id: z.string() });
export const knowledgeResponseSchema = z.object({
  answer: z.string(),
  status: z.enum(["answered", "insufficient_evidence"]),
  sources: z.array(task1SourceSchema),
  image_references: z.array(z.object({ url: z.string().url(), alt_text: z.string(), description: z.string(), analysis_status: z.string() })),
  needs_human: z.boolean(),
  escalation_id: z.string().nullable(),
  request_id: z.string(),
  mode: z.enum(["demo", "live"]),
  model: z.string().nullable().optional(),
});

export const classifiedEmailSchema = z.object({
  category: emailCategorySchema,
  subcategory: z.string().regex(/^[a-z0-9_]{2,60}$/),
  urgency: z.enum(["low", "normal", "high", "urgent"]),
  risk: z.enum(["low", "medium", "high"]),
  summary: z.string().min(1).max(500),
  knowledgeQuestion: z.string().max(1000),
});

export const generatedDraftSchema = z.object({
  summary: z.string().min(1).max(500),
  draft: z.string().min(1).max(8000),
  source_urls: z.array(z.string().url()).max(10),
  needs_human_approval: z.boolean(),
  next_action: z.enum(["review", "reply", "investigate", "escalate"]),
  reason_for_escalation: z.string().max(1000).nullable(),
});

export const reviewRequestSchema = z.object({
  action: z.enum(["approve", "edit_approve", "reject", "escalate"]),
  finalReply: z.string().max(8000).optional(),
  reviewer: z.string().trim().min(1).max(120),
  reason: z.string().max(1000).optional(),
}).strict();

export const healthResponseSchema = z.object({
  status: z.literal("ok"),
  service: z.literal("inbox-agent"),
  mode: z.enum(["demo", "live"]),
});

export type HealthResponse = z.infer<typeof healthResponseSchema>;
export type EmailInput = z.infer<typeof emailInputSchema>;
export type KnowledgeResponse = z.infer<typeof knowledgeResponseSchema>;
export type ClassifiedEmail = z.infer<typeof classifiedEmailSchema>;
export type GeneratedDraft = z.infer<typeof generatedDraftSchema>;
export type ReviewRequest = z.infer<typeof reviewRequestSchema>;
