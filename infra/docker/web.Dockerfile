# Interface Next.js.
#
# Le contexte de construction est la racine du dépôt, pas `apps/web` :
# l'interface dépend de `@kairos/contracts` par un lien d'espace de travail
# pnpm. Construite depuis `apps/web` seul, l'installation échouait sur une
# dépendance introuvable — le `|| pnpm install` de la version précédente
# masquait la panne sans la résoudre.
#
# Deux étapes, pour que l'image finale ne transporte ni la chaîne de
# construction ni les dépendances de développement.

FROM node:22-slim AS build

WORKDIR /srv
RUN corepack enable

# Les manifestes d'abord : tant qu'ils ne changent pas, Docker réutilise la
# couche d'installation, de loin la plus lente.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/contracts/package.json packages/contracts/
RUN pnpm install --frozen-lockfile

COPY packages/contracts packages/contracts
COPY apps/web apps/web
RUN pnpm --filter @kairos/web build

# Retire ici typescript, eslint, tailwind et vitest : ils n'ont plus rien à
# faire dans une image qui sert des pages.
RUN pnpm install --frozen-lockfile --prod


FROM node:22-slim AS runtime

WORKDIR /srv
RUN corepack enable
ENV NODE_ENV=production

COPY --from=build /srv/node_modules node_modules
COPY --from=build /srv/package.json /srv/pnpm-workspace.yaml ./
COPY --from=build /srv/packages/contracts packages/contracts
COPY --from=build /srv/apps/web apps/web

# Servir des pages ne demande aucun privilège : une faille dans le rendu ne
# doit pas donner root dans le conteneur.
USER node

EXPOSE 3000
CMD ["pnpm", "--filter", "@kairos/web", "start"]
