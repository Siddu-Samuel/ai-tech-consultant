import { z } from "zod";
import { config as loadDotenv } from "dotenv";
import { resolve } from "node:path";

loadDotenv({ path: resolve(process.cwd(), "../.env"), quiet: true });

const stringBoolean = (fallback: boolean) => z.string().default(String(fallback)).transform((value) => value.toLowerCase() === "true");

const envSchema = z.object({
  APP_ENV: z.enum(["demo", "test", "production"]).default("demo"),
  INBOX_AGENT_PORT: z.coerce.number().int().min(1).max(65535).default(8002),
  REPOSITORY_MODE: z.enum(["memory", "postgres"]).default("memory"),
  DATABASE_URL: z.string().default("postgresql://consultant:consultant@localhost:5432/consultant"),
  ANTHROPIC_API_KEY: z.string().default(""),
  CLAUDE_MODEL_PRIMARY: z.string().default(""),
  KNOWLEDGE_BRAIN_URL: z.string().url().default("http://localhost:8001"),
  TASK1_SERVICE_TOKEN: z.string().default(""),
  ADMIN_API_TOKEN: z.string().default(""),
  EMAIL_PROVIDER: z.enum(["simulated", "resend"]).default("simulated"),
  RESEND_API_KEY: z.string().default(""),
  EMAIL_FROM: z.string().default("AI Tech Consultant <onboarding@resend.dev>"),
  AUTO_SEND_ENABLED: stringBoolean(false),
  GLOBAL_AUTOMATION_DISABLED: stringBoolean(true),
  COMPANY_NAME: z.string().default("Brilliant Directories Support"),
  COMPANY_TONE: z.string().max(500).default("Helpful, concise, and professional"),
  CLAUDE_INPUT_COST_PER_MTOK: z.coerce.number().nonnegative().optional(),
  CLAUDE_OUTPUT_COST_PER_MTOK: z.coerce.number().nonnegative().optional(),
});

export const config = envSchema.parse(process.env);
export const demoMode = config.APP_ENV !== "production" || !config.ANTHROPIC_API_KEY;
