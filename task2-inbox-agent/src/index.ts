import express from "express";

import { config } from "./config.js";
import { InboxAgent } from "./agent.js";
import { createRepository } from "./repository.js";
import { createRouter, safeErrorMiddleware } from "./routes.js";

export const repository = await createRepository();
export const agent = new InboxAgent(repository);
export const app = express();

app.disable("x-powered-by");
app.use(express.json({ limit: "256kb" }));
app.use(createRouter(repository, agent));
app.use(safeErrorMiddleware);

if (process.env.NODE_ENV !== "test") {
  app.listen(config.INBOX_AGENT_PORT, "0.0.0.0", () => {
    console.info(`Inbox Agent listening on port ${config.INBOX_AGENT_PORT} (${config.APP_ENV})`);
  });
}
