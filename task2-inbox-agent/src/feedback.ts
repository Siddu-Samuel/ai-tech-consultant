import { randomUUID } from "node:crypto";

import type { FeedbackEvent, FeedbackEventType } from "./repository.js";

export function createFeedback(
  caseId: string,
  eventType: FeedbackEventType,
  fields: Partial<Pick<FeedbackEvent, "beforeText" | "afterText" | "reviewer" | "reason">> = {},
): Omit<FeedbackEvent, "id" | "createdAt"> {
  return {
    caseId,
    eventType,
    beforeText: fields.beforeText ?? null,
    afterText: fields.afterText ?? null,
    reviewer: fields.reviewer ?? null,
    reason: fields.reason ?? null,
  };
}

export function feedbackSummary(events: FeedbackEvent[]): { edited: number; rejected: number; commonReasons: string[] } {
  const reasons = new Map<string, number>();
  for (const event of events) {
    if (!event.reason) continue;
    const reason = event.reason.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    if (reason) reasons.set(reason, (reasons.get(reason) ?? 0) + 1);
  }
  return {
    edited: events.filter((event) => event.eventType === "edited").length,
    rejected: events.filter((event) => event.eventType === "rejected").length,
    commonReasons: [...reasons.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([reason]) => reason),
  };
}

export function idempotencyKeyForSend(caseId: string): string {
  return `email-case-${caseId}`;
}

export function newFeedbackId(): string {
  return randomUUID();
}
