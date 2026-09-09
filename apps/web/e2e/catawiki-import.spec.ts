import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * « Import assisté Catawiki », joué dans un vrai navigateur.
 *
 * Ce que ce fichier vérifie et que les tests d'API ne peuvent pas voir : que
 * le texte collé atteint le formulaire, qu'une correction faite à la main
 * survit à l'enregistrement, et qu'en rouvrant la fiche des jours plus tard on
 * retrouve encore ce que l'annonce affichait — distinct de ce qu'on a corrigé.
 *
 * Un import juste côté serveur mais qui n'arrive pas à l'écran ne sert à rien.
 */

const LOT_TEXT = readFileSync(
  join(
    __dirname,
    "..",
    "..",
    "api",
    "tests",
    "fixtures",
    "listings",
    "catawiki-lot-reel-jlc.txt",
  ),
  "utf-8",
);

/**
 * Un numéro de lot neuf à chaque exécution.
 *
 * L'URL canonique d'une annonce est unique par portefeuille — c'est la
 * déduplication qui le veut, et c'est une bonne chose. Rejouer le test avec le
 * même lien se heurterait donc à un doublon légitime, et l'échec dirait « lot
 * déjà suivi » au lieu de parler du parcours.
 */
const LOT_NUMBER = String(106500000 + (Date.now() % 90000));
const LOT_URL =
  `https://www.catawiki.com/en/l/${LOT_NUMBER}-jaeger-lecoultre-reverso-duetto` +
  "-diamonds-266-1-44-serviced-women-2010-2020";

const EMAIL = process.env.E2E_EMAIL ?? "essai@kairos.local";
const PASSWORD =
  process.env.E2E_PASSWORD ?? "mot-de-passe-essai-suffisamment-long";

async function signIn(page: Page) {
  await page.goto("/connexion");
  await page.getByLabel(/adresse|email/i).fill(EMAIL);
  await page.getByLabel(/mot de passe/i).fill(PASSWORD);
  // Ciblé dans le formulaire : l'en-tête porte un bouton « Déconnexion » que
  // le même motif attraperait.
  await page
    .locator("form")
    .getByRole("button", { name: /se connecter/i })
    .click();
  await page.waitForURL((url) => !url.pathname.includes("/connexion"));
}

test.describe("Import assisté Catawiki", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  test("coller, corriger, enregistrer, rouvrir", async ({ page }) => {
    await page.goto("/opportunities/new");

    // --- 1. Le mode URL, puis le lien du lot -------------------------------
    await page.getByRole("radio", { name: /Annonce en ligne/i }).click();
    await page.getByPlaceholder(/catawiki|https/i).fill(LOT_URL);
    // Le mode d'accès est demandé à la sortie du champ : Catawiki bloque, donc
    // l'interface doit proposer le collage sans faire cliquer pour rien.
    await page.getByPlaceholder(/catawiki|https/i).blur();

    await expect(
      page.getByText(/protège ses pages contre les accès automatisés/i),
    ).toBeVisible();
    // Le bouton de récupération n'est pas proposé : il échouerait à coup sûr.
    await expect(
      page.getByRole("button", { name: /Récupérer les informations/i }),
    ).toHaveCount(0);

    // --- 2. Le collage du texte visible ------------------------------------
    await page.getByPlaceholder(/Contenu de la page/i).fill(LOT_TEXT);
    await page.getByRole("button", { name: /Analyser ce contenu/i }).click();

    // L'aperçu montre ce qui a été lu avant que quoi que ce soit n'entre dans
    // le formulaire.
    await expect(page.getByText(/champs? lus? sur Catawiki/i)).toBeVisible();
    // Le tableau d'aperçu, pas les avertissements qui citent les mêmes
    // valeurs : on veut vérifier ce qui entrera dans le formulaire.
    const preview = page.getByRole("definition");
    await expect(preview.filter({ hasText: "Jaeger-LeCoultre" })).toHaveCount(
      1,
    );
    await expect(preview.filter({ hasText: /^266\.1\.44$/ })).toHaveCount(1);

    // Les avertissements qui comptent sont à l'écran, pas seulement dans la
    // réponse de l'API.
    await expect(page.getByText(/ni un prix final/i)).toBeVisible();
    await expect(page.getByText(/photos ne sont pas reprises/i)).toBeVisible();
    await expect(page.getByText(/relatif/i).first()).toBeVisible();

    // --- 3. Reprise dans le formulaire -------------------------------------
    await page
      .getByRole("button", {
        name: /Reprendre ces valeurs dans le formulaire/i,
      })
      .click();

    await expect(page.locator('input[name="brand"]')).toHaveValue(
      "Jaeger-LeCoultre",
    );
    await expect(page.locator('input[name="reference"]')).toHaveValue(
      "266.1.44",
    );
    await expect(page.locator('input[name="amount"]')).toHaveValue("4150");
    await expect(page.locator('input[name="country_code"]')).toHaveValue("FR");

    // --- 4. Une correction à la main ---------------------------------------
    // L'annonce dit « Yellow gold » dans la fiche et « 18k white gold » dans
    // la description : l'utilisateur tranche, et sa décision doit tenir.
    await page.locator('input[name="reference"]').fill("266.1.44-CORRIGE");

    // --- 5. Enregistrement --------------------------------------------------
    await page.getByRole("button", { name: /Créer l'opportunité/i }).click();
    await page.waitForURL(/\/opportunities\/[0-9a-f-]{36}$/);
    const url = page.url();

    await expect(
      page.getByRole("heading", { name: /Jaeger-LeCoultre/i }),
    ).toBeVisible();

    // --- 6. On quitte, puis on rouvre ---------------------------------------
    await page.goto("/opportunities");
    await page.goto(url);

    // La correction est là.
    await expect(page.getByText("266.1.44-CORRIGE").first()).toBeVisible();

    // Et le relevé d'annonce aussi, sous son nom.
    const trace = page.locator("section, div").filter({
      hasText: "Import assisté Catawiki",
    });
    await expect(trace.first()).toBeVisible();

    // Ce que l'annonce affichait est conservé **tel quel**, à côté de la
    // correction : c'est toute la question qu'on se pose six semaines plus
    // tard devant un chiffre qui paraît faux.
    await expect(page.getByText("266.1.44 - Serviced").first()).toBeVisible();
    await expect(
      page.getByText(/Période de production/i).first(),
    ).toBeVisible();
    await expect(page.getByText("2010-2020").first()).toBeVisible();
    await expect(page.getByText(/Révision déclarée/i).first()).toBeVisible();
    await expect(page.getByText(/Enchère en cours/i).first()).toBeVisible();
    await expect(page.getByText(/Estimation Catawiki/i).first()).toBeVisible();

    // La provenance accompagne chaque valeur.
    await expect(
      page.getByText(/lu dans le contenu que vous avez collé/i).first(),
    ).toBeVisible();

    // Les divergences réelles sont présentées comme telles.
    await expect(page.getByText("À confirmer").first()).toBeVisible();

    // Et ce qui manquait manque encore, dit en clair.
    await expect(
      page.getByText(/Non renseigné par l'annonce/i).first(),
    ).toBeVisible();
  });

  test("une saisie manuelle n'affiche aucun relevé d'annonce", async ({
    page,
  }) => {
    await page.goto("/opportunities/new");

    await page
      .locator('input[name="manual_identifier"]')
      .fill(`E2E-MANUEL-${Date.now()}`);
    await page.locator('input[name="brand"]').fill("Tudor");
    await page.locator('input[name="reference"]').fill("79030N");
    await page.getByRole("button", { name: /Créer l'opportunité/i }).click();
    await page.waitForURL(/\/opportunities\/[0-9a-f-]{36}$/);

    // Rien n'a été importé : rien ne doit être présenté comme venant d'une
    // annonce.
    await expect(page.getByText("Import assisté Catawiki")).toHaveCount(0);
  });
});
