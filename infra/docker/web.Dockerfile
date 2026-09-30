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
ENV NODE_ENV=production

COPY --from=build /srv/node_modules node_modules
COPY --from=build /srv/package.json /srv/pnpm-workspace.yaml ./
COPY --from=build /srv/packages/contracts packages/contracts
COPY --from=build /srv/apps/web apps/web

# Servir des pages ne demande aucun privilège : une faille dans le rendu ne
# doit pas donner root dans le conteneur.
USER node

# Next.js est lancé directement, sans passer par pnpm.
#
# Le démarrage passait par `pnpm --filter @kairos/web start`. Rien ne fixe la
# version de pnpm : `corepack` prend la plus récente. Les versions récentes
# vérifient, avant d'exécuter une commande, que `node_modules` est à jour, et
# tentent de le réinstaller. Or l'utilisateur `node` n'a pas le droit d'écrire
# dans `/srv` — c'est voulu — et le conteneur redémarrait en boucle :
#
#   ERR_PNPM_PACKAGE_MANAGER_REMOVE_MODULES_DIR
#   Failed to remove /srv/node_modules/.pnpm from the modules directory:
#   Permission denied (os error 13)
#
# Huit semaines plus tôt, la version de pnpm de l'époque ne le faisait pas :
# l'image n'a pas changé, c'est l'outil qui a bougé sous elle. Servir des
# pages n'a pas besoin de gestionnaire de paquets. Le lancer directement
# retire la dépendance à sa version — et le téléchargement de pnpm par
# `corepack` à chaque démarrage du conteneur.
WORKDIR /srv/apps/web

EXPOSE 3000
CMD ["./node_modules/.bin/next", "start"]
