import { classifiedEmailSchema, type ClassifiedEmail, type EmailInput } from "./schemas.js";

const patterns: Array<{ category: ClassifiedEmail["category"]; match: RegExp }> = [
  { category: "refund_cancellation", match: /refund|cancel|cancellation|chargeback|reimburse/i },
  { category: "complaint", match: /complain|unacceptable|disappointed|angry|terrible|frustrat|poor service/i },
  { category: "follow_up", match: /following up|follow-up|checking in|any update|as discussed|next steps/i },
  { category: "quote_request", match: /quote|pricing|price|cost|estimate|budget/i },
  { category: "project_request", match: /build|develop|custom feature|integration|new website|project|implementation/i },
  { category: "troubleshooting", match: /error|broken|not working|can't|cannot|failed|issue|bug|stuck|unable/i },
  { category: "how_to", match: /how (do|can|should)|where (do|can)|steps to|guide me|show me/i },
];

function subcategory(category: ClassifiedEmail["category"], text: string): string {
  if (category === "refund_cancellation") {
    if (/chargeback/i.test(text)) return "refund_cancellation_general";
    return "refund_cancellation_refund_policy";
  }
  if (category === "project_request" && /single sign.on|sso|login|password|account access/i.test(text)) return "project_request_login_access";
  if (category === "other_ambiguous" && /login|password|account access|sign in|security|compromis/i.test(text)) return "other_ambiguous_login_access";
  if (/filter|search/i.test(text)) return `${category}:search_filters`.replaceAll(":", "_");
  if (/login|password|account access|sign in|single sign.on|\bsso\b/i.test(text)) return `${category}_login_access`;
  if (/checkout|payment|billing/i.test(text)) return `${category}_checkout_billing`;
  if (/email|notification/i.test(text)) return `${category}_email_notifications`;
  if (/mobile|phone|responsive/i.test(text)) return `${category}_mobile_experience`;
  if (/refund|cancel/i.test(text)) return `${category}_refund_policy`;
  return `${category}_general`;
}

export function classifyEmail(email: EmailInput): ClassifiedEmail {
  const text = `${email.subject}\n${email.body}`;
  const category = patterns.find((item) => item.match.test(text))?.category ?? "other_ambiguous";
  const urgent = /urgent|immediately|service is down|security breach|account compromised|disable access right away/i.test(text);
  const highUrgency = /today|asap|blocked/i.test(text);
  const sensitive = ["project_request", "refund_cancellation", "complaint", "quote_request"].includes(category)
    || /password|security|legal|chargeback|lawsuit|compromised|account access|sign in|login/i.test(text);
  const risk = sensitive ? "high" : category === "other_ambiguous" ? "medium" : "low";
  const lowSignals = /how do i|how should i|where can i|how can i|steps to|show me how|can you help|cannot complete|custom feature|migration|appointment booking|redesign|how much does .* cost|duplicate charge|chargeback/i.test(text)
    || (category === "project_request" && !/single sign.on|\bsso\b|login|password/i.test(text));
  const urgency = urgent ? "urgent" : highUrgency ? "high" : lowSignals && !(category === "how_to" && /password|login|sign in/i.test(text)) ? "low" : "normal";
  const question = email.body.replace(/\b(?:hi|hello|dear)\b[^\n,.!?]*/gi, "").trim().slice(0, 1000);
  const summary = `${email.subject}: ${email.body.replace(/\s+/g, " ").slice(0, 180)}`;
  return classifiedEmailSchema.parse({
    category,
    subcategory: subcategory(category, text),
    urgency,
    risk,
    summary,
    knowledgeQuestion: question,
  });
}
