import { createServer } from "node:http";
import { describe, expect, it } from "vitest";

import { app } from "../src/index.js";

describe("GET /health", () => {
  it("returns a validated demo-mode status", async () => {
    const server = createServer(app);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    try {
      const address = server.address();
      if (!address || typeof address === "string") throw new Error("Test server did not bind a TCP port");
      const response = await fetch(`http://127.0.0.1:${address.port}/health`);
      expect(response.status).toBe(200);
      expect(await response.json()).toMatchObject({ status: "ok", service: "inbox-agent", mode: "demo" });
    } finally {
      await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
    }
  });
});
