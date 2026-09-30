import { expect, test, type Page } from "@playwright/test";

/**
 * Le parcours complet, sans qu'aucun comparable ne soit saisi à la main :
 * confirmer la référence suffit.
 *
 * Ici **rien n'est intercepté** : l'API réelle lance la recherche en tâche de
 * fond, appelle un faux serveur eBay sur une vraie prise réseau (voir
 * `apps/api/tests/fake_ebay_server.py`), contrôle l'identité de chaque annonce,
 * enregistre les comparables, recalcule la cote — et l'écran suit.
 *
 * C'est un simulacre de **données** : il prouve la chaîne de bout en bout, pas
 * que eBay répond. L'accès réel se prouve avec `python -m
 * app.market_search.probe` et de vrais identifiants.
 *
 * Activé par `E2E_FAKE_EBAY=1` : l'API doit alors tourner avec EBAY_CLIENT_ID,
 * EBAY_CLIENT_SECRET et EBAY_API_BASE_URL pointant vers le faux serveur.
 */

test.skip(
  process.env.E2E_FAKE_EBAY !== "1",
  "Nécessite l'API démarrée avec le faux serveur eBay (E2E_FAKE_EBAY=1).",
);

const EMAIL = process.env.E2E_EMAIL ?? "essai@kairos.local";
const PASSWORD =
  process.env.E2E_PASSWORD ?? "mot-de-passe-essai-suffisamment-long";

async function signIn(page: Page) {
  await page.goto("/connexion");
  await page.getByLabel(/adresse|email/i).fill(EMAIL);
  await page.getByLabel(/mot de passe/i).fill(PASSWORD);
  await page
    .locator("form")
    .getByRole("button", { name: /se connecter/i })
    .click();
  await page.waitForURL((url) => !url.pathname.includes("/connexion"));
}

test("confirmer la référence lance la recherche, alimente le moteur et affiche la cote", async ({
  page,
}) => {
  await signIn(page);

  // Une référence neuve : les comparables appartiennent à la référence, un
  // rejeu retrouverait ceux de l'exécution précédente.
  const reference = `RC${Date.now()}`;
  await page.goto("/opportunities/new");
  await page
    .locator('input[name="manual_identifier"]')
    .fill(`E2E-PARCOURS-${Date.now()}`);
  await page.locator('input[name="brand"]').fill("Omega");
  await page.locator('input[name="reference"]').fill(reference);
  await page.getByRole("button", { name: /Créer l'opportunité/i }).click();
  await page.waitForURL(/\/opportunities\/[0-9a-f-]{36}$/);

  // Aucune recherche tant que la référence n'est pas confirmée.
  await expect(
    page.getByText("Confirmez la référence : KAIROS cherchera alors"),
  ).toBeVisible();

  // Le seul geste de l'utilisateur : confirmer la référence.
  await page
    .getByPlaceholder(/Motif \(ex\. référence visible/i)
    .fill("Référence lue sur le cadran et le fond du boîtier.");
  await page.getByRole("button", { name: "Confirmer", exact: true }).click();

  // KAIROS cherche seul, sans aucun bouton.
  await expect(page.getByTestId("search-headline")).toHaveText(
    "2 nouveaux comparables exacts ajoutés (2 au total pour cette référence).",
    { timeout: 30_000 },
  );

  const block = page.getByTestId("search-source");
  await expect(block).toContainText("eBay");
  // Quatre annonces lues : deux exactes, un voisin, une « pour pièces » — les
  // deux écartées le sont avec leur motif, aucune n'est substituée.
  await expect(block).toContainText("4 annonces lues · 2 retenues · 2 écartées");
  await block.getByText("Voir le détail de cette source").click();
  await expect(block).toContainText("Référence exacte absente du titre");
  await expect(block).toContainText("Pièce détachée, accessoire seul");
  await expect(block).toContainText("HTTP 200");

  // Les comparables sont là, marqués comme issus de la recherche automatique.
  await expect(page.getByText("recherche automatique")).toHaveCount(2);
  await expect(page.getByText("Aucun comparable")).toHaveCount(0);

  // Et la cote est apparue, sans « Calculer » : le moteur a été alimenté.
  await expect(page.getByText("Prudente", { exact: true })).toBeVisible();
  await expect(page.getByText("Centrale", { exact: true })).toBeVisible();
  await expect(page.getByText("Favorable", { exact: true })).toBeVisible();

  // La nature des prix est dite : des annonces observées, pas des ventes.
  await expect(page.getByTestId("market-search")).toContainText(
    "ce ne sont pas des ventes conclues",
  );
  await expect(page.getByTestId("search-freshness")).toContainText("Relevé");
});
