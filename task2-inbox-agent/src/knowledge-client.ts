import { randomUUID } from "node:crypto";

import { config } from "./config.js";
import { knowledgeResponseSchema, type KnowledgeResponse } from "./schemas.js";

export class KnowledgeUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "KnowledgeUnavailableError";
  }
}

export async function queryKnowledge(question: string, customerId?: string): Promise<KnowledgeResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  const requestId = randomUUID();
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json", "X-Request-ID": requestId };
    if (customerId) {
      if (!config.TASK1_SERVICE_TOKEN) throw new KnowledgeUnavailableError("Customer-scoped Task 1 access is not configured");
      headers["X-Service-Token"] = config.TASK1_SERVICE_TOKEN;
    }
    const response = await fetch(`${config.KNOWLEDGE_BRAIN_URL}/query`, {
      method: "POST",
      headers,
      body: JSON.stringify({ question, customer_id: customerId }),
      signal: controller.signal,
    });
    if (!response.ok) throw new KnowledgeUnavailableError(`Knowledge Brain returned HTTP ${response.status}`);
    const parsed = knowledgeResponseSchema.safeParse(await response.json());
    if (!parsed.success) throw new KnowledgeUnavailableError("Knowledge Brain returned an invalid response")
    return parsed.data;
  } catch (error) {
    if (error instanceof KnowledgeUnavailableError) throw error;
    const message = error instanceof Error && error.name === "AbortError" ? "Knowledge Brain request timed out" : "Knowledge Brain is unavailable";
    throw new KnowledgeUnavailableError(message);
  } finally {
    clearTimeout(timer);
  }
}
