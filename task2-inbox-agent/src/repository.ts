import { randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { config } from "./config.js";
import { emailInputSchema, type ClassifiedEmail, type EmailInput, type GeneratedDraft, type KnowledgeResponse } from "./schemas.js";

export type CaseStatus = "new" | "drafted" | "approved" | "rejected" | "escalated" | "sent_simulated" | "sent" | "send_failed";
export type FeedbackEventType = "drafted" | "edited" | "approved" | "rejected" | "sent_simulated" | "sent" | "send_failed" | "escalated" | "autonomy_decision";

export type FeedbackEvent = {
  id: string;
  caseId: string;
  eventType: FeedbackEventType;
  beforeText: string | null;
  afterText: string | null;
  reviewer: string | null;
  reason: string | null;
  createdAt: string;
};

export type EmailCase = {
  id: string;
  input: EmailInput;
  classification: ClassifiedEmail | null;
  knowledge: KnowledgeResponse | null;
  originalDraft: string | null;
  finalReply: string | null;
  sourceUrls: string[];
  modelId: string | null;
  promptVersion: string | null;
  latencyMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  costUsd: number | null;
  status: CaseStatus;
  approvalStatus: "pending" | "approved" | "rejected" | "escalated";
  needsHumanApproval: boolean;
  reasonForEscalation: string | null;
  nextAction: "review" | "reply" | "investigate" | "escalate" | null;
  modified: boolean;
  mode: "demo" | "live";
  actualSent: boolean;
  sendProviderId: string | null;
  createdAt: string;
  updatedAt: string;
};

export type AutonomyState = {
  categoryKey: string;
  consecutiveUnchangedCount: number;
  eligible: boolean;
  enabled: boolean;
  lastQualifyingEvent: string | null;
  lastFailure: string | null;
  updatedAt: string;
};

export type SeedEmail = EmailInput & { id: string; expected: Record<string, unknown> };

export type DraftMetadata = {
  classification: ClassifiedEmail;
  knowledge: KnowledgeResponse | null;
  draft: GeneratedDraft;
  modelId: string;
  promptVersion: string;
  latencyMs: number;
  inputTokens: number | null;
  outputTokens: number | null;
  costUsd: number | null;
  mode: "demo" | "live";
};

export type ReviewMetadata = {
  finalReply: string;
  status: CaseStatus;
  approvalStatus: EmailCase["approvalStatus"];
  modified: boolean;
  actualSent: boolean;
  sendProviderId?: string | null;
};

export interface EmailRepository {
  initialize(seedEmails: SeedEmail[]): Promise<void>;
  createCase(input: EmailInput, requestId: string): Promise<EmailCase>;
  getCase(id: string): Promise<EmailCase | null>;
  listCases(): Promise<EmailCase[]>;
  saveDraft(id: string, metadata: DraftMetadata): Promise<EmailCase>;
  saveReview(id: string, metadata: ReviewMetadata): Promise<EmailCase>;
  addFeedback(event: Omit<FeedbackEvent, "id" | "createdAt">): Promise<FeedbackEvent>;
  listFeedback(caseId: string): Promise<FeedbackEvent[]>;
  listAutonomy(): Promise<AutonomyState[]>;
  recordAutonomyOutcome(categoryKey: string, qualifyingSend: boolean, failureReason: string | null): Promise<AutonomyState>;
  setAutonomyEnabled(categoryKey: string, enabled: boolean): Promise<AutonomyState>;
}

export class MemoryRepository implements EmailRepository {
  private readonly cases = new Map<string, EmailCase>();
  private readonly requests = new Map<string, string>();
  private readonly events = new Map<string, FeedbackEvent[]>();
  private readonly autonomy = new Map<string, AutonomyState>();

  async initialize(seedEmails: SeedEmail[]): Promise<void> {
    for (const seed of seedEmails) {
      if (!this.cases.has(seed.id)) this.cases.set(seed.id, this.newCase(seed.id, seed));
    }
  }

  private newCase(id: string, input: EmailInput): EmailCase {
    const now = new Date().toISOString();
    return {
      id, input: structuredClone(input), classification: null, knowledge: null, originalDraft: null, finalReply: null,
      sourceUrls: [], modelId: null, promptVersion: null, latencyMs: null, inputTokens: null, outputTokens: null,
      costUsd: null, status: "new", approvalStatus: "pending", modified: false, mode: "demo", actualSent: false,
      needsHumanApproval: true, reasonForEscalation: null, nextAction: null, sendProviderId: null,
      createdAt: now, updatedAt: now,
    };
  }

  async createCase(input: EmailInput, requestId: string): Promise<EmailCase> {
    const existingId = this.requests.get(requestId);
    if (existingId) return structuredClone(this.cases.get(existingId)!);
    const row = this.newCase(randomUUID(), input);
    this.cases.set(row.id, row);
    this.requests.set(requestId, row.id);
    return structuredClone(row);
  }

  async getCase(id: string): Promise<EmailCase | null> {
    const row = this.cases.get(id);
    return row ? structuredClone(row) : null;
  }

  async listCases(): Promise<EmailCase[]> {
    return [...this.cases.values()].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).map((row) => structuredClone(row));
  }

  async saveDraft(id: string, metadata: DraftMetadata): Promise<EmailCase> {
    const row = this.cases.get(id);
    if (!row) throw new Error("Email case was not found");
    if (row.status !== "new") return structuredClone(row);
    row.classification = structuredClone(metadata.classification);
    row.knowledge = metadata.knowledge ? structuredClone(metadata.knowledge) : null;
    row.originalDraft = metadata.draft.draft;
    row.finalReply = metadata.draft.draft;
    row.sourceUrls = [...metadata.draft.source_urls];
    row.modelId = metadata.modelId;
    row.promptVersion = metadata.promptVersion;
    row.latencyMs = metadata.latencyMs;
    row.inputTokens = metadata.inputTokens;
    row.outputTokens = metadata.outputTokens;
    row.costUsd = metadata.costUsd;
    row.status = "drafted";
    row.approvalStatus = "pending";
    row.needsHumanApproval = metadata.draft.needs_human_approval;
    row.reasonForEscalation = metadata.draft.reason_for_escalation;
    row.nextAction = metadata.draft.next_action;
    row.mode = metadata.mode;
    row.updatedAt = new Date().toISOString();
    return structuredClone(row);
  }

  async saveReview(id: string, metadata: ReviewMetadata): Promise<EmailCase> {
    const row = this.cases.get(id);
    if (!row) throw new Error("Email case was not found");
    if (row.status === "sent" || row.status === "sent_simulated") return structuredClone(row);
    row.finalReply = metadata.finalReply;
    row.status = metadata.status;
    row.approvalStatus = metadata.approvalStatus;
    row.modified = metadata.modified;
    row.actualSent = metadata.actualSent;
    row.sendProviderId = metadata.sendProviderId ?? null;
    row.updatedAt = new Date().toISOString();
    return structuredClone(row);
  }

  async addFeedback(event: Omit<FeedbackEvent, "id" | "createdAt">): Promise<FeedbackEvent> {
    const saved = { ...event, id: randomUUID(), createdAt: new Date().toISOString() };
    this.events.set(event.caseId, [...(this.events.get(event.caseId) ?? []), saved]);
    return structuredClone(saved);
  }

  async listFeedback(caseId: string): Promise<FeedbackEvent[]> {
    return structuredClone(this.events.get(caseId) ?? []);
  }

  private stateFor(categoryKey: string): AutonomyState {
    let state = this.autonomy.get(categoryKey);
    if (!state) {
      state = { categoryKey, consecutiveUnchangedCount: 0, eligible: false, enabled: false, lastQualifyingEvent: null, lastFailure: null, updatedAt: new Date().toISOString() };
      this.autonomy.set(categoryKey, state);
    }
    return state;
  }

  async listAutonomy(): Promise<AutonomyState[]> {
    return structuredClone([...this.autonomy.values()]);
  }

  async recordAutonomyOutcome(categoryKey: string, qualifyingSend: boolean, failureReason: string | null): Promise<AutonomyState> {
    const state = this.stateFor(categoryKey);
    if (qualifyingSend) {
      state.consecutiveUnchangedCount += 1;
      state.lastQualifyingEvent = new Date().toISOString();
      state.lastFailure = null;
      state.eligible = state.consecutiveUnchangedCount >= 20;
    } else {
      state.consecutiveUnchangedCount = 0;
      state.eligible = false;
      state.lastFailure = failureReason ?? "A non-qualifying case reset the streak.";
    }
    state.updatedAt = new Date().toISOString();
    return structuredClone(state);
  }

  async setAutonomyEnabled(categoryKey: string, enabled: boolean): Promise<AutonomyState> {
    const state = this.stateFor(categoryKey);
    state.enabled = enabled && state.eligible;
    state.updatedAt = new Date().toISOString();
    return structuredClone(state);
  }
}

export function loadSeedEmails(): SeedEmail[] {
  const candidates = [
    resolve(process.cwd(), "data", "inbox_emails.jsonl"),
    resolve(process.cwd(), "evals", "inbox_emails.jsonl"),
    resolve(process.cwd(), "..", "evals", "inbox_emails.jsonl"),
  ];
  const fixturePath = candidates.find(existsSync);
  if (!fixturePath) throw new Error("Synthetic inbox fixture file was not found; expected data/inbox_emails.jsonl or ../evals/inbox_emails.jsonl");
  return readFileSync(fixturePath, "utf8").split(/\r?\n/).filter(Boolean).map((line) => {
    const value: unknown = JSON.parse(line);
    if (typeof value !== "object" || value === null || !("expected" in value) || !("id" in value)) {
      throw new Error("Inbox fixture has an invalid record shape");
    }
    const row = value as Record<string, unknown>;
    const input = emailInputSchema.parse({
      subject: row.subject,
      body: row.body,
      customerReference: row.customerReference,
      customerId: row.customerId,
      from: row.from,
    });
    return { id: String(row.id), expected: row.expected as Record<string, unknown>, ...input };
  });
}

export async function createRepository(seedEmails = loadSeedEmails()): Promise<EmailRepository> {
  if (config.REPOSITORY_MODE === "memory") {
    const repository = new MemoryRepository();
    await repository.initialize(seedEmails);
    return repository;
  }
  const { PostgresRepository } = await import("./repository-postgres.js");
  const repository = new PostgresRepository(config.DATABASE_URL);
  await repository.initialize(seedEmails);
  return repository;
}
