FROM node:22-slim

WORKDIR /srv
COPY package.json ./
COPY . .
RUN corepack enable && pnpm install --frozen-lockfile || pnpm install
RUN pnpm --filter @kairos/web build

EXPOSE 3000
CMD ["pnpm", "--filter", "@kairos/web", "start"]
