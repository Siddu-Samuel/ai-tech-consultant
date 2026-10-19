import { describe, expect, it, vi } from "vitest";
import { queryKnowledge, KnowledgeUnavailableError } from "../src/knowledge-client.js";
import { MemoryRepository } from "../src/repository.js";
import { feedbackSummary } from "../src/feedback.js";

describe("Task 1 HTTP client", () => {
  it("sends product questions only through the documented Knowledge Brain query API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      answer: "Use search settings.", status: "answered", sources: [{ title: "Search", url: "https://docs.example/search", chunk_id: "c1" }],
      image_references: [], needs_human: false, escalation_id: null, request_id: "req-1", mode: "demo",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    try {
      const result = await queryKnowledge("How do I configure search?");
      expect(result.status).toBe("answered");
      expect(fetchMock.mock.calls[0]?.[0]).toContain("/query");
      expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ question: "How do I configure search?" });
    } finally { fetchMock.mockRestore(); }
  });

  it("rejects malformed Knowledge Brain responses", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    try { await expect(queryKnowledge("Question")).rejects.toBeInstanceOf(KnowledgeUnavailableError); }
    finally { fetchMock.mockRestore(); }
  });
});

describe("persistent workflow rules", () => {
  it("requires 20 actual unchanged sends and resets eligibility after failure", async () => {
    const repository = new MemoryRepository();
    await repository.initialize([]);
    let state;
    for (let i = 0; i < 19; i += 1) state = await repository.recordAutonomyOutcome("how_to_general", true, null);
    expect(state?.eligible).toBe(false);
    state = await repository.recordAutonomyOutcome("how_to_general", true, null);
    expect(state?.eligible).toBe(true);
    expect(state?.consecutiveUnchangedCount).toBe(20);
    state = await repository.recordAutonomyOutcome("how_to_general", false, "edited");
    expect(state?.eligible).toBe(false);
    expect(state?.consecutiveUnchangedCount).toBe(0);
  });

  it("summarizes reviewer feedback without discarding edits or rejection reasons", () => {
    const summary = feedbackSummary([
      { id: "1", caseId: "a", eventType: "edited", beforeText: "draft", afterText: "fixed", reviewer: "r", reason: "wrong feature", createdAt: "" },
      { id: "2", caseId: "b", eventType: "rejected", beforeText: null, afterText: null, reviewer: "r", reason: "Wrong feature!", createdAt: "" },
    ]);
    expect(summary.edited).toBe(1);
    expect(summary.rejected).toBe(1);
    expect(summary.commonReasons[0]).toBe("wrong feature");
  });
});
