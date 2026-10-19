import { randomUUID } from "node:crypto";

import { classifyEmail } from "./classifier.js";
import { config, demoMode } from "./config.js";
import { draftReply, DraftingUnavailableError, safeAcknowledgement } from "./drafting.js";
import { createFeedback } from "./feedback.js";
import { queryKnowledge, KnowledgeUnavailableError } from "./knowledge-client.js";
import { categoryKey, isQualifyingUnchangedSend, mayAutonomouslySend } from "./autonomy.js";
import type { EmailCase, EmailRepository } from "./repository.js";
import type { ReviewRequest } from "./schemas.js";
import { sendReply } from "./send.js";

function sameSubstantiveText(left: string, right: string): boolean {
  return left.replace(/\s+/g, " ").trim() === right.replace(/\s+/g, " ").trim();
}

export class InboxAgent {
  private readonly inFlight = new Map<string, Promise<EmailCase>>();

  constructor(private readonly repository: EmailRepository) {}

  async process(id: string): Promise<EmailCase> {
    const running = this.inFlight.get(id);
    if (running) return running;
    const promise = this.processOnce(id);
    this.inFlight.set(id, promise);
    try {
      return await promise;
    } finally {
      this.inFlight.delete(id);
    }
  }

  private async processOnce(id: string): Promise<EmailCase> {
    const emailCase = await this.repository.getCase(id);
    if (!emailCase) throw new Error("Email case was not found");
    if (emailCase.status !== "new") return emailCase;

    const classification = classifyEmail(emailCase.input);
    let knowledge = null;
    let knowledgeFailure: string | null = null;
    if (["how_to", "troubleshooting", "project_request"].includes(classification.category)) {
      try {
        const question = classification.knowledgeQuestion || emailCase.input.subject;
        knowledge = await queryKnowledge(question, emailCase.input.customerId);
      } catch (error) {
        knowledgeFailure = error instanceof KnowledgeUnavailableError ? error.message : "Knowledge Brain request failed";
      }
    }

    let draftMetadata: Awaited<ReturnType<typeof draftReply>> | null = null;
    let draft = safeAcknowledgement(
      classification,
      knowledgeFailure ?? (knowledge ? "" : "Product facts require review before a customer response."),
    );
    let modelId = "none-safe-acknowledgement";
    let promptVersion = "inbox-safe-ack-v1";
    let latencyMs = 0;
    let inputTokens: number | null = null;
    let outputTokens: number | null = null;
    let costUsd: number | null = null;
    let mode: "demo" | "live" = demoMode ? "demo" : "live";

    if (knowledge && !knowledgeFailure) {
      try {
        draftMetadata = await draftReply(emailCase.input, classification, knowledge);
        draft = draftMetadata.value;
        modelId = draftMetadata.modelId;
        promptVersion = draftMetadata.promptVersion;
        latencyMs = draftMetadata.latencyMs;
        inputTokens = draftMetadata.inputTokens;
        outputTokens = draftMetadata.outputTokens;
        costUsd = draftMetadata.costUsd;
        mode = draftMetadata.mode;
      } catch (error) {
        const reason = error instanceof DraftingUnavailableError ? error.message : "Draft generation failed";
        draft = safeAcknowledgement(classification, reason);
        modelId = "none-safe-acknowledgement";
      }
    }

    const saved = await this.repository.saveDraft(id, {
      classification,
      knowledge,
      draft,
      modelId,
      promptVersion,
      latencyMs,
      inputTokens,
      outputTokens,
      costUsd,
      mode,
    });
    await this.repository.addFeedback(createFeedback(id, "drafted", {
      afterText: draft.draft,
      reason: knowledgeFailure ?? draft.reason_for_escalation,
    }));

    const key = categoryKey(saved);
    if (key && (draft.needs_human_approval || !knowledge || knowledge.status !== "answered")) {
      await this.repository.recordAutonomyOutcome(key, false, draft.reason_for_escalation ?? "A safety check failed.");
    }

    if (key) {
      const state = (await this.repository.listAutonomy()).find((item) => item.categoryKey === key) ?? null;
      if (mayAutonomouslySend(saved, state)) return this.autonomousSend(saved, key);
    }
    return saved;
  }

  private async autonomousSend(emailCase: EmailCase, key: string): Promise<EmailCase> {
    const decisionId = randomUUID();
    await this.repository.addFeedback(createFeedback(emailCase.id, "autonomy_decision", { reason: `Eligible category ${key}; send proceeded through enabled safety gates.` }));
    try {
      const result = await sendReply(emailCase, emailCase.finalReply ?? "", `autonomous-${emailCase.id}`);
      const saved = await this.repository.saveReview(emailCase.id, {
        finalReply: emailCase.finalReply ?? "",
        status: result.status,
        approvalStatus: "approved",
        modified: false,
        actualSent: result.actualSent,
        sendProviderId: result.providerId,
      });
      await this.repository.addFeedback(createFeedback(emailCase.id, result.status, { reason: `Automation decision ${decisionId}; provider=${result.providerId ?? "simulated"}` }));
      if (result.actualSent) {
        await this.repository.recordAutonomyOutcome(key, isQualifyingUnchangedSend(saved, true, true), null);
      }
      return saved;
    } catch (error) {
      const saved = await this.repository.saveReview(emailCase.id, {
        finalReply: emailCase.finalReply ?? "",
        status: "send_failed",
        approvalStatus: "pending",
        modified: false,
        actualSent: false,
      });
      await this.repository.addFeedback(createFeedback(emailCase.id, "send_failed", { reason: error instanceof Error ? error.message : "Send failed" }));
      await this.repository.recordAutonomyOutcome(key, false, "Autonomous send failed.");
      return saved;
    }
  }

  async review(id: string, request: ReviewRequest): Promise<EmailCase> {
    const current = await this.repository.getCase(id);
    if (!current) throw new Error("Email case was not found");
    if (current.status === "sent" || current.status === "sent_simulated") return current;
    if (current.status === "new") throw new Error("Draft the email before reviewing it");

    const key = categoryKey(current);
    if (request.action === "reject" || request.action === "escalate") {
      const rejected = request.action === "reject";
      const saved = await this.repository.saveReview(id, {
        finalReply: current.finalReply ?? current.originalDraft ?? "",
        status: rejected ? "rejected" : "escalated",
        approvalStatus: rejected ? "rejected" : "escalated",
        modified: current.modified,
        actualSent: false,
      });
      await this.repository.addFeedback(createFeedback(id, rejected ? "rejected" : "escalated", {
        beforeText: current.originalDraft,
        reviewer: request.reviewer,
        reason: request.reason ?? null,
      }));
      if (key) await this.repository.recordAutonomyOutcome(key, false, request.reason ?? `Case was ${request.action}.`);
      return saved;
    }

    const finalReply = request.action === "edit_approve" ? request.finalReply : current.originalDraft;
    if (!finalReply?.trim()) throw new Error("An approved reply must contain text");
    const modified = !sameSubstantiveText(finalReply, current.originalDraft ?? "");
    let sendResult;
    try {
      sendResult = await sendReply(current, finalReply, `human-approved-${id}`);
    } catch (error) {
      const saved = await this.repository.saveReview(id, {
        finalReply,
        status: "send_failed",
        approvalStatus: "approved",
        modified,
        actualSent: false,
      });
      await this.repository.addFeedback(createFeedback(id, "approved", { beforeText: current.originalDraft, afterText: finalReply, reviewer: request.reviewer, reason: request.reason ?? null }));
      await this.repository.addFeedback(createFeedback(id, "send_failed", { afterText: finalReply, reviewer: request.reviewer, reason: error instanceof Error ? error.message : "Send failed" }));
      if (key) await this.repository.recordAutonomyOutcome(key, false, "Send failure reset the unchanged-draft streak.");
      return saved;
    }

    const saved = await this.repository.saveReview(id, {
      finalReply,
      status: sendResult.status,
      approvalStatus: "approved",
      modified,
      actualSent: sendResult.actualSent,
      sendProviderId: sendResult.providerId,
    });
    if (modified) {
      await this.repository.addFeedback(createFeedback(id, "edited", { beforeText: current.originalDraft, afterText: finalReply, reviewer: request.reviewer, reason: request.reason ?? null }));
    }
    await this.repository.addFeedback(createFeedback(id, "approved", { beforeText: current.originalDraft, afterText: finalReply, reviewer: request.reviewer, reason: request.reason ?? null }));
    await this.repository.addFeedback(createFeedback(id, sendResult.status, { afterText: finalReply, reviewer: request.reviewer, reason: sendResult.providerId ?? "" }));

    if (key && (modified || (sendResult.actualSent && !isQualifyingUnchangedSend(saved, true, !modified)))) {
      await this.repository.recordAutonomyOutcome(key, false, modified ? "Draft was substantively edited." : "Sent case failed the autonomy safety checks.");
    } else if (key && sendResult.actualSent) {
      await this.repository.recordAutonomyOutcome(key, isQualifyingUnchangedSend(saved, true, !modified), null);
    }
    return saved;
  }
}
