import { expect, test, type Page } from "@playwright/test";

/**
 * Le recalcul automatique, joué dans un vrai navigateur.
 *
 * Ce que ce fichier vérifie et que les tests d'API ne peuvent pas voir : que la
 * cote **apparaît à l'écran** sans que l'utilisateur presse « Calculer ». Un
 * recalcul juste côté serveur mais que le panneau ne relit pas laisserait
 * l'écran mentir : « aucune cote » alors qu'elle existe.
 *
 * Le compte d'essai n'a pas de capital : l'analyse ne peut donc pas être
 * publiée, et c'est le cas que le message doit dire honnêtement. La cote, elle,
 * doit suivre.
 */

/**
 * Une référence neuve à chaque exécution.
 *
 * Les comparables appartiennent à une **référence**, pas à une opportunité :
 * rejouer le test avec « Tudor 79030N » retrouverait ceux de l'exécution
 * précédente, et l'étape « un seul comparable ne fait pas de cote » ne serait
 * plus vraie. Une référence unique rend le test indépendant de l'état de la
 * base, comme le numéro de lot unique du parcours Catawiki.
 */
const REFERENCE = `E2E${Date.now()}`;

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

async function addComparable(page: Page, amount: string, seller: string) {
  const form = page.locator("form").filter({
    has: page.locator('input[name="source_name"]'),
  });
  await form.locator('input[name="source_name"]').fill("Chrono24");
  await form.locator('input[name="seller_fingerprint"]').fill(seller);
  await form.locator('input[name="amount"]').fill(amount);
  await form.getByRole("button", { name: "Ajouter", exact: true }).click();
}

test("deux comparables suffisent : la cote apparaît sans presser « Calculer »", async ({
  page,
}) => {
  await signIn(page);

  // --- Une opportunité manuelle, sa référence confirmée ------------------
  await page.goto("/opportunities/new");
  await page
    .locator('input[name="manual_identifier"]')
    .fill(`E2E-RECALCUL-${Date.now()}`);
  await page.locator('input[name="brand"]').fill("Tudor");
  await page.locator('input[name="reference"]').fill(REFERENCE);
  await page.getByRole("button", { name: /Créer l'opportunité/i }).click();
  await page.waitForURL(/\/opportunities\/[0-9a-f-]{36}$/);

  await page
    .getByPlaceholder(/Motif \(ex\. référence visible/i)
    .fill("Référence lue sur le cadran et le fond du boîtier.");
  await page.getByRole("button", { name: "Confirmer", exact: true }).click();

  // --- Rien à voir tant qu'il n'y a pas de cote --------------------------
  await expect(page.getByText(/Aucun comparable/i)).toBeVisible();
  await expect(page.getByText("Centrale", { exact: true })).toHaveCount(0);

  // --- Premier comparable : pas de cote, et l'écran le dit sans alarme ---
  await page.getByText("Ajouter un comparable").click();
  await addComparable(page, "3500.00", "vendeur-un");

  const notice = page.getByText(/Comparable ajouté\./);
  await expect(notice).toBeVisible();
  await expect(notice).toContainText(/au moins deux comparables/i);
  // Un seul comparable ne fait pas de cote : rien n'apparaît, et ce n'est pas
  // présenté comme une panne.
  await expect(notice).not.toContainText(/échoué/i);
  await expect(page.getByText("Centrale", { exact: true })).toHaveCount(0);

  // --- Deuxième comparable : la cote suit toute seule --------------------
  await addComparable(page, "3600.00", "vendeur-deux");

  await expect(page.getByText(/recalculée? automatiquement/i)).toBeVisible();

  // Le point qu'aucun test d'API ne peut voir : le panneau de cote s'est mis
  // à jour **sans rechargement et sans clic**.
  await expect(page.getByText("Prudente", { exact: true })).toBeVisible();
  await expect(page.getByText("Centrale", { exact: true })).toBeVisible();
  await expect(page.getByText("Favorable", { exact: true })).toBeVisible();

  // Sans capital, l'analyse ne peut pas être publiée : l'écran le dit au lieu
  // de laisser croire que tout a été calculé.
  await expect(page.getByText(/l'analyse n'a pas pu l'être/i)).toBeVisible();
});
