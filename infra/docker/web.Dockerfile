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

# Les dépendances de développement — typescript, eslint, tailwind, vitest —
# restent dans l'image. Ce n'est pas l'idéal, c'est assumé.
#
# L'étape d'élagage était `pnpm install --frozen-lockfile --prod`. Elle a
# échoué au premier déploiement réel : pour ne garder que les dépendances de
# production, pnpm supprime et reconstruit `node_modules`, et il refuse cette
# suppression sans confirmation interactive — or une construction Docker n'a
# pas de terminal.
#
#   ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY
#
# Un réglage existe pour passer outre. Il n'est pas retenu : le gain est
# quelques centaines de mégaoctets sur un disque de 75 Go, et le prix serait
# une option de contournement dans le chemin de construction, à revérifier à
# chaque montée de version de pnpm. Une image un peu grasse qui se construit
# vaut mieux qu'une image fine qui casse le déploiement.


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
