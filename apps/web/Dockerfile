FROM node:22-bookworm-slim

WORKDIR /app/apps/web
RUN corepack enable

COPY apps/web/ ./
RUN corepack pnpm install --frozen-lockfile

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN corepack pnpm build

EXPOSE 3000
CMD ["corepack", "pnpm", "start", "--hostname", "0.0.0.0"]
