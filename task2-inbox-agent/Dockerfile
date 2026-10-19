FROM node:22-alpine
WORKDIR /app
COPY task2-inbox-agent/package*.json ./
RUN npm ci
COPY task2-inbox-agent/tsconfig.json ./
COPY task2-inbox-agent/src ./src
COPY task2-inbox-agent/migrations ./migrations
COPY evals/inbox_emails.jsonl ./data/inbox_emails.jsonl
EXPOSE 8002
CMD ["npm", "start"]
