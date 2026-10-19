import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { classifyEmail } from "../src/classifier.js";
import { emailInputSchema } from "../src/schemas.js";

const fixture = readFileSync(resolve(process.cwd(), "../evals/inbox_emails.jsonl"), "utf8")
  .split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as {
    id: string; subject: string; body: string; expected: Record<string, unknown>;
  });

describe("synthetic inbox evaluation set", () => {
  it("contains at least 50 unique, valid customer emails", () => {
    expect(fixture.length).toBeGreaterThanOrEqual(50);
    expect(new Set(fixture.map((item) => item.id)).size).toBe(fixture.length);
    for (const row of fixture) expect(emailInputSchema.safeParse({ subject: row.subject, body: row.body }).success).toBe(true);
  });

  it.each(fixture.map((row) => [row.id, row] as const))("classifies %s against its labeled case", (_id, row) => {
    const actual = classifyEmail({ subject: row.subject, body: row.body });
    for (const key of ["category", "subcategory", "urgency", "risk"] as const) {
      expect.soft(actual[key], `${row.id} ${key}`).toBe(row.expected[key]);
    }
  });
});
