import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { Pool, type PoolClient } from "pg";

import type {
  AutonomyState,
  CaseStatus,
  DraftMetadata,
  EmailCase,
  EmailRepository,
  FeedbackEvent,
  ReviewMetadata,
  SeedEmail,
} from "./repository.js";
import type { EmailInput } from "./schemas.js";

type DbRow = Record<string, unknown>;

function asJson<T>(value: unknown): T {
  return (typeof value === "string" ? JSON.parse(value) : value) as T;
}

function mapCase(row: DbRow): EmailCase {
  return {
    id: String(row.id),
    input: asJson<EmailInput>(row.input_json),
    classification: row.classification_json ? asJson(row.classification_json) : null,
    knowledge: row.knowledge_json ? asJson(row.knowledge_json) : null,
    originalDraft: row.original_draft === null ? null : String(row.original_draft),
    finalReply: row.final_reply === null ? null : String(row.final_reply),
    sourceUrls: asJson<string[]>(row.source_urls ?? []),
    modelId: row.model_id === null ? null : String(row.model_id),
    promptVersion: row.prompt_version === null ? null : String(row.prompt_version),
    latencyMs: row.latency_ms === null ? null : Number(row.latency_ms),
    inputTokens: row.input_tokens === null ? null : Number(row.input_tokens),
    outputTokens: row.output_tokens === null ? null : Number(row.output_tokens),
    costUsd: row.cost_usd === null ? null : Number(row.cost_usd),
    status: String(row.status) as CaseStatus,
    approvalStatus: String(row.approval_status) as EmailCase["approvalStatus"],
    needsHumanApproval: Boolean(row.needs_human_approval),
    reasonForEscalation: row.reason_for_escalation === null ? null : String(row.reason_for_escalation),
    nextAction: row.next_action === null ? null : row.next_action as EmailCase["nextAction"],
    modified: Boolean(row.modified),
    mode: String(row.mode) as EmailCase["mode"],
    actualSent: Boolean(row.actual_sent),
    sendProviderId: row.send_provider_id === null ? null : String(row.send_provider_id),
    createdAt: new Date(String(row.created_at)).toISOString(),
    updatedAt: new Date(String(row.updated_at)).toISOString(),
  };
}

function mapAutonomy(row: DbRow): AutonomyState {
  return {
    categoryKey: String(row.category_key),
    consecutiveUnchangedCount: Number(row.consecutive_unchanged_count),
    eligible: Boolean(row.eligible),
    enabled: Boolean(row.enabled),
    lastQualifyingEvent: row.last_qualifying_event ? new Date(String(row.last_qualifying_event)).toISOString() : null,
    lastFailure: row.last_failure === null ? null : String(row.last_failure),
    updatedAt: new Date(String(row.updated_at)).toISOString(),
  };
}

export class PostgresRepository implements EmailRepository {
  private readonly pool: Pool;

  constructor(connectionString: string) {
    this.pool = new Pool({ connectionString, max: 8, connectionTimeoutMillis: 5000, idleTimeoutMillis: 30_000 });
  }

  async initialize(seedEmails: SeedEmail[]): Promise<void> {
    const migrationPath = resolve(process.cwd(), "migrations", "001_init.sql");
    await this.pool.query(await readFile(migrationPath, "utf8"));
    const count = await this.pool.query<{ count: string }>("SELECT count(*)::text AS count FROM email_cases");
    if (Number(count.rows[0]?.count ?? 0) > 0) return;
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      for (const seed of seedEmails) {
        const { id, expected, ...input } = seed;
        await client.query(
          "INSERT INTO email_cases(id,input_json,fixture_expected) VALUES($1,$2::jsonb,$3::jsonb) ON CONFLICT(id) DO NOTHING",
          [id, JSON.stringify(input), JSON.stringify(expected)],
        );
      }
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
  }

  private async getWith(client: PoolClient | Pool, id: string): Promise<EmailCase | null> {
    const result = await client.query("SELECT * FROM email_cases WHERE id=$1", [id]);
    return result.rows[0] ? mapCase(result.rows[0]) : null;
  }

  async createCase(input: EmailInput, requestId: string): Promise<EmailCase> {
    const id = randomUUID();
    const result = await this.pool.query(
      "INSERT INTO email_cases(id,request_id,input_json) VALUES($1,$2,$3::jsonb) ON CONFLICT(request_id) DO UPDATE SET request_id=excluded.request_id RETURNING *",
      [id, requestId, JSON.stringify(input)],
    );
    return mapCase(result.rows[0]);
  }

  async getCase(id: string): Promise<EmailCase | null> {
    return this.getWith(this.pool, id);
  }

  async listCases(): Promise<EmailCase[]> {
    const result = await this.pool.query("SELECT * FROM email_cases ORDER BY created_at DESC LIMIT 200");
    return result.rows.map(mapCase);
  }

  async saveDraft(id: string, metadata: DraftMetadata): Promise<EmailCase> {
    const result = await this.pool.query(
      `UPDATE email_cases SET classification_json=$2::jsonb,knowledge_json=$3::jsonb,original_draft=$4,final_reply=$4,
      source_urls=$5::jsonb,model_id=$6,prompt_version=$7,latency_ms=$8,input_tokens=$9,output_tokens=$10,cost_usd=$11,
      status='drafted',mode=$12,needs_human_approval=$13,reason_for_escalation=$14,next_action=$15,updated_at=now() WHERE id=$1 AND status='new' RETURNING *`,
      [id, JSON.stringify(metadata.classification), JSON.stringify(metadata.knowledge), metadata.draft.draft,
        JSON.stringify(metadata.draft.source_urls), metadata.modelId, metadata.promptVersion, metadata.latencyMs,
        metadata.inputTokens, metadata.outputTokens, metadata.costUsd, metadata.mode, metadata.draft.needs_human_approval,
        metadata.draft.reason_for_escalation, metadata.draft.next_action],
    );
    const saved = result.rows[0] ? mapCase(result.rows[0]) : await this.getCase(id);
    if (!saved) throw new Error("Email case was not found");
    return saved;
  }

  async saveReview(id: string, metadata: ReviewMetadata): Promise<EmailCase> {
    const result = await this.pool.query(
      "UPDATE email_cases SET final_reply=$2,status=$3,approval_status=$4,modified=$5,actual_sent=$6,send_provider_id=$7,updated_at=now() WHERE id=$1 AND status NOT IN ('sent','sent_simulated') RETURNING *",
      [id, metadata.finalReply, metadata.status, metadata.approvalStatus, metadata.modified, metadata.actualSent, metadata.sendProviderId ?? null],
    );
    const saved = result.rows[0] ? mapCase(result.rows[0]) : await this.getCase(id);
    if (!saved) throw new Error("Email case was not found");
    return saved;
  }

  async addFeedback(event: Omit<FeedbackEvent, "id" | "createdAt">): Promise<FeedbackEvent> {
    const id = randomUUID();
    const result = await this.pool.query(
      "INSERT INTO feedback_events(id,email_case_id,event_type,before_text,after_text,reviewer,reason) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *",
      [id, event.caseId, event.eventType, event.beforeText, event.afterText, event.reviewer, event.reason],
    );
    const row = result.rows[0];
    return { id, caseId: String(row.email_case_id), eventType: row.event_type as FeedbackEvent["eventType"],
      beforeText: row.before_text, afterText: row.after_text, reviewer: row.reviewer, reason: row.reason,
      createdAt: new Date(String(row.created_at)).toISOString() };
  }

  async listFeedback(caseId: string): Promise<FeedbackEvent[]> {
    const result = await this.pool.query("SELECT * FROM feedback_events WHERE email_case_id=$1 ORDER BY created_at", [caseId]);
    return result.rows.map((row) => ({ id: String(row.id), caseId: String(row.email_case_id), eventType: row.event_type as FeedbackEvent["eventType"],
      beforeText: row.before_text, afterText: row.after_text, reviewer: row.reviewer, reason: row.reason,
      createdAt: new Date(String(row.created_at)).toISOString() }));
  }

  async listAutonomy(): Promise<AutonomyState[]> {
    const result = await this.pool.query("SELECT * FROM autonomy_state ORDER BY category_key");
    return result.rows.map(mapAutonomy);
  }

  async recordAutonomyOutcome(categoryKey: string, qualifyingSend: boolean, failureReason: string | null): Promise<AutonomyState> {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      await client.query("INSERT INTO autonomy_state(category_key) VALUES($1) ON CONFLICT(category_key) DO NOTHING", [categoryKey]);
      const current = await client.query("SELECT * FROM autonomy_state WHERE category_key=$1 FOR UPDATE", [categoryKey]);
      const prior = mapAutonomy(current.rows[0]);
      const count = qualifyingSend ? prior.consecutiveUnchangedCount + 1 : 0;
      const result = await client.query(
        "UPDATE autonomy_state SET consecutive_unchanged_count=$2,eligible=$3,enabled=CASE WHEN $3 THEN enabled ELSE FALSE END,last_qualifying_event=CASE WHEN $4 THEN now() ELSE last_qualifying_event END,last_failure=$5,updated_at=now() WHERE category_key=$1 RETURNING *",
        [categoryKey, count, qualifyingSend && count >= 20, qualifyingSend, qualifyingSend ? null : failureReason ?? "A non-qualifying event reset the streak."],
      );
      await client.query("COMMIT");
      return mapAutonomy(result.rows[0]);
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
  }

  async setAutonomyEnabled(categoryKey: string, enabled: boolean): Promise<AutonomyState> {
    await this.pool.query("INSERT INTO autonomy_state(category_key) VALUES($1) ON CONFLICT(category_key) DO NOTHING", [categoryKey]);
    const result = await this.pool.query(
      "UPDATE autonomy_state SET enabled=($2 AND eligible),updated_at=now() WHERE category_key=$1 RETURNING *",
      [categoryKey, enabled],
    );
    return mapAutonomy(result.rows[0]);
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}
