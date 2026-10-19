import { randomUUID } from "node:crypto";

import { config } from "./config.js";
import type { EmailCase } from "./repository.js";

export type SendResult = { status: "sent" | "sent_simulated"; actualSent: boolean; providerId: string | null };

export async function sendReply(emailCase: EmailCase, text: string, idempotencyKey: string): Promise<SendResult> {
  if (config.EMAIL_PROVIDER === "simulated") {
    return { status: "sent_simulated", actualSent: false, providerId: `simulated-${idempotencyKey}` };
  }
  if (!config.RESEND_API_KEY) throw new Error("Resend is selected but RESEND_API_KEY is not configured");
  if (!emailCase.input.from) throw new Error("A validated recipient email address is required to send this reply");

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.RESEND_API_KEY}`,
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey || randomUUID(),
      },
      body: JSON.stringify({
        from: config.EMAIL_FROM,
        to: [emailCase.input.from],
        subject: `Re: ${emailCase.input.subject}`,
        text,
      }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Email provider returned HTTP ${response.status}`);
    const payload: unknown = await response.json();
    if (typeof payload !== "object" || payload === null || !("id" in payload) || typeof payload.id !== "string") {
      throw new Error("Email provider returned an invalid send receipt");
    }
    return { status: "sent", actualSent: true, providerId: payload.id };
  } finally {
    clearTimeout(timeout);
  }
}
