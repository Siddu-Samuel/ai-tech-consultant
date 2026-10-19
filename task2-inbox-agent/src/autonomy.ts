import { config } from "./config.js";
import type { AutonomyState, EmailCase } from "./repository.js";

export function categoryKey(emailCase: EmailCase): string | null {
  return emailCase.classification?.subcategory ?? null;
}

export function isQualifyingUnchangedSend(emailCase: EmailCase, actualSent: boolean, unmodified: boolean): boolean {
  return actualSent
    && unmodified
    && !emailCase.modified
    && emailCase.classification?.risk === "low"
    && emailCase.classification.urgency !== "urgent"
    && !emailCase.needsHumanApproval
    && emailCase.approvalStatus === "approved"
    && emailCase.status === "sent";
}

export function mayAutonomouslySend(emailCase: EmailCase, state: AutonomyState | null): boolean {
  return config.AUTO_SEND_ENABLED
    && !config.GLOBAL_AUTOMATION_DISABLED
    && config.EMAIL_PROVIDER !== "simulated"
    && state?.eligible === true
    && state.enabled
    && emailCase.classification?.risk === "low"
    && emailCase.classification.urgency !== "urgent"
    && !emailCase.needsHumanApproval
    && emailCase.status === "drafted";
}
