FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_BASE=
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ARG NEXT_PUBLIC_AI_MODE=stub
ENV NEXT_PUBLIC_AI_MODE=$NEXT_PUBLIC_AI_MODE
ARG NEXT_PUBLIC_OPENCODE_URL=https://opencode.conall.ru/L3dvcmtzcGFjZQ/session
ENV NEXT_PUBLIC_OPENCODE_URL=$NEXT_PUBLIC_OPENCODE_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
