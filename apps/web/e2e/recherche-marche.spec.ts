import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * La recherche autonome de comparables, jouée dans un vrai navigateur.
 *
 * **Ce que ce fichier prouve, et ce qu'il ne prouve pas.** Les réponses de
 * l'API de recherche sont interceptées par le navigateur : elles viennent de ce
 * fichier, pas d'une place de marché. Il vérifie donc l'*écran* — progression,
 * résultats partiels, diagnostic exact d'un refus, données insuffisantes,
 * fraîcheur, actualisation — et **pas l'accès aux données**, qui ne se prouve
 * qu'avec de vrais identifiants (`python -m app.market_search.probe`).
 *
 * L'opportunité, elle, est créée et sa référence confirmée par la vraie API.
 */

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

async function createOpportunity(page: Page, confirm: boolean) {
  const reference = `RM${Date.now()}`;
  await page.goto("/opportunities/new");
  await page
    .locator('input[name="manual_identifier"]')
    .fill(`E2E-RECHERCHE-${Date.now()}`);
  // Une marque que le faux serveur eBay de la CI ne connaît pas : la recherche
  // réelle, déclenchée par la confirmation, ne doit pas ajouter de comparables
  // sous des réponses interceptées.
  await page.locator('input[name="brand"]').fill("Longines");
  await page.locator('input[name="reference"]').fill(reference);
  await page.getByRole("button", { name: /Créer l'opportunité/i }).click();
  await page.waitForURL(/\/opportunities\/[0-9a-f-]{36}$/);
  if (confirm) {
    await page
      .getByPlaceholder(/Motif \(ex\. référence visible/i)
      .fill("Référence lue sur le cadran et le fond du boîtier.");
    await page.getByRole("button", { name: "Confirmer", exact: true }).click();
    await expect(page.getByText("Confirmée").first()).toBeVisible();
  }
  return page.url().split("/").pop() as string;
}

const NOW = "2026-09-30T12:00:00Z";

function source(overrides: Record<string, unknown> = {}) {
  return {
    source: "ebay",
    status: "ok",
    message: null,
    started_at: NOW,
    finished_at: NOW,
    elapsed_s: 3.4,
    complete: true,
    requests: [
      { label: "jeton OAuth", http_status: 200, elapsed_s: 0.3, note: null },
      {
        label: "EBAY_FR « Omega 1561.61.00 » (page 1)",
        http_status: 200,
        elapsed_s: 0.6,
        note: null,
      },
    ],
    requests_count: 2,
    read: 40,
    accepted: 2,
    recorded: 2,
    already_known: 0,
    duplicates: 0,
    fx_unavailable: 0,
    rejected: { reference_not_stated: 37, not_a_complete_watch: 1 },
    rejected_examples: [
      {
        title: "Omega Constellation Mini 1562.30 quartz",
        code: "reference_not_stated",
        detail: "…",
      },
    ],
    informational: [],
    recorded_items: [
      {
        comparable_id: "00000000-0000-4000-8000-000000000001",
        title: "Omega Constellation 1561.61.00 acier",
        url: "https://www.ebay.fr/itm/111",
        amount: "850.00",
        currency: "EUR",
        price_kind: "asking",
      },
    ],
    ...overrides,
  };
}

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: "00000000-0000-4000-8000-0000000000aa",
    opportunity_id: "00000000-0000-4000-8000-0000000000bb",
    status: "succeeded",
    trigger_kind: "refresh",
    policy_version: "1.0.0",
    created_at: NOW,
    started_at: NOW,
    finished_at: NOW,
    sources: [source()],
    summary: {
      stage: "done",
      elapsed_s: 3.4,
      observed_at: NOW,
      comparables_recorded: 2,
      comparables_known_for_reference: 2,
      recorded_by_price_kind: { asking: 2 },
      price_groups: {
        asking_active: {
          label: "Prix demandés, annonces actives",
          count: 2,
          min_eur: "850.00",
          median_eur: "900.00",
          max_eur: "950.00",
        },
      },
      insufficient_data: false,
      insufficient_data_message: null,
      price_nature_note:
        "Prix demandés et enchères en cours observés : ce ne sont pas des ventes conclues.",
      recalculation: null,
    },
    error_code: null,
    error_message: null,
    age_minutes: 12,
    stale: false,
    cache_ttl_hours: 6,
    next_refresh_allowed_at: null,
    ...overrides,
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

test("l'écran suit la recherche : progression, résultat, nature des prix, fraîcheur", async ({
  page,
}) => {
  await signIn(page);
  const id = await createOpportunity(page, true);

  // Séquence servie par le « serveur » : rien, puis en cours, puis terminée.
  let reads = 0;
  let started = false;
  await page.route(/\/market-searches\/latest$/, (route) => {
    if (!started) {
      return json(route, { run: null, configured_sources: ["ebay"] });
    }
    reads += 1;
    const active = reads < 3;
    return json(route, {
      configured_sources: ["ebay"],
      run: active
        ? run({
            status: "running",
            finished_at: null,
            age_minutes: null,
            sources: [],
            summary: { ...run().summary, stage: "searching" },
          })
        : run({ next_refresh_allowed_at: "2999-01-01T00:00:00Z" }),
    });
  });
  await page.route(/\/market-searches$/, (route) => {
    started = true;
    return json(
      route,
      { ...run({ status: "queued", sources: [] }), launched: true, reused: null },
      202,
    );
  });

  await page.goto(`/opportunities/${id}`);
  const panel = page.getByTestId("market-search");
  await expect(panel).toContainText("Aucune recherche pour cette référence");

  await page.getByRole("button", { name: "Lancer la recherche" }).click();
  await expect(page.getByRole("progressbar")).toBeVisible();
  await expect(page.getByTestId("search-headline")).toHaveText(
    /Recherche en cours/,
  );

  // Le résultat arrive sans rechargement de la page.
  await expect(page.getByTestId("search-headline")).toHaveText(
    "2 nouveaux comparables exacts ajoutés (2 au total pour cette référence).",
  );
  await expect(page.getByRole("progressbar")).toHaveCount(0);

  const block = page.getByTestId("search-source");
  await expect(block).toContainText("eBay");
  await expect(block).toContainText("Interrogée");
  await expect(block).toContainText(
    "40 annonces lues · 2 retenues · 38 écartées",
  );

  // Le détail montre pourquoi les voisins ont été écartés, jamais substitués.
  await block.getByText("Voir le détail de cette source").click();
  await expect(block).toContainText("37 ×");
  await expect(block).toContainText("Référence exacte absente du titre");
  await expect(block).toContainText("Requêtes émises");
  await expect(block).toContainText("HTTP 200");

  // Ce ne sont pas des ventes : l'écran le dit à côté du résultat.
  await expect(panel).toContainText("ce ne sont pas des ventes conclues");
  // Et l'âge des données est dit.
  await expect(page.getByTestId("search-freshness")).toContainText(
    "Relevé il y a 12 min",
  );

  // Actualiser est refusé tant que le délai minimal n'est pas écoulé.
  await expect(page.getByRole("button", { name: "Actualiser" })).toBeDisabled();
  await expect(panel).toContainText("Actualisation possible à partir de");
});

test("un refus de la source est affiché avec son diagnostic exact", async ({
  page,
}) => {
  await signIn(page);
  const id = await createOpportunity(page, true);

  await page.route(/\/market-searches\/latest$/, (route) =>
    json(route, {
      configured_sources: ["ebay"],
      run: run({
        status: "failed",
        sources: [
          source({
            status: "blocked",
            message:
              "eBay a refusé l'accès (HTTP 403) : source arrêtée, aucune nouvelle tentative.",
            requests: [
              {
                label: "EBAY_FR « Omega 1561.61.00 » (page 1)",
                http_status: 403,
                elapsed_s: 0.3,
                note: null,
              },
            ],
            requests_count: 1,
            read: 0,
            accepted: 0,
            recorded: 0,
            rejected: {},
            rejected_examples: [],
            recorded_items: [],
          }),
        ],
        summary: {
          ...run().summary,
          comparables_recorded: 0,
          comparables_known_for_reference: 0,
        },
      }),
    }),
  );

  await page.goto(`/opportunities/${id}`);
  await expect(page.getByTestId("search-headline")).toContainText(
    "n'a rien pu obtenir",
  );
  // Un échec n'est pas « aucun résultat » : le statut et le diagnostic exact
  // sont là, avec le code HTTP de la requête.
  const block = page.getByTestId("search-source");
  await expect(block).toContainText("Accès refusé");
  await expect(block).toContainText("HTTP 403");
  await block.getByText("Voir le détail de cette source").click();
  await expect(block).toContainText("→ HTTP 403");
});

test("données insuffisantes : aucune estimation n'est présentée", async ({
  page,
}) => {
  await signIn(page);
  const id = await createOpportunity(page, true);

  await page.route(/\/market-searches\/latest$/, (route) =>
    json(route, {
      configured_sources: ["ebay"],
      run: run({
        summary: {
          ...run().summary,
          comparables_recorded: 1,
          comparables_known_for_reference: 1,
          insufficient_data: true,
          insufficient_data_message:
            "Données insuffisantes : aucune estimation n'est produite. Aucune valeur n'est inventée.",
        },
      }),
    }),
  );

  await page.goto(`/opportunities/${id}`);
  await expect(page.getByTestId("search-headline")).toContainText(
    "Données insuffisantes",
  );
  await expect(page.getByText("Centrale", { exact: true })).toHaveCount(0);
});

test("données anciennes : l'âge est dit et l'actualisation proposée", async ({
  page,
}) => {
  await signIn(page);
  const id = await createOpportunity(page, true);

  await page.route(/\/market-searches\/latest$/, (route) =>
    json(route, {
      configured_sources: ["ebay"],
      run: run({ age_minutes: 500, stale: true }),
    }),
  );

  await page.goto(`/opportunities/${id}`);
  await expect(page.getByTestId("search-freshness")).toContainText(
    "données anciennes",
  );
  await expect(page.getByRole("button", { name: "Actualiser" })).toBeEnabled();
});

test("sans source configurée, l'écran le dit au lieu d'un bouton inerte", async ({
  page,
}) => {
  await signIn(page);
  const id = await createOpportunity(page, true);

  await page.route(/\/market-searches\/latest$/, (route) =>
    json(route, { run: null, configured_sources: [] }),
  );

  await page.goto(`/opportunities/${id}`);
  await expect(page.getByTestId("search-unavailable")).toContainText(
    "aucune source n'est configurée",
  );
  await expect(page.getByRole("button", { name: "Lancer la recherche" })).toHaveCount(0);
});

test("référence non confirmée : pas de recherche sur une référence supposée", async ({
  page,
}) => {
  await signIn(page);
  const id = await createOpportunity(page, false);
  await page.goto(`/opportunities/${id}`);
  await expect(
    page.getByText("Confirmez la référence : KAIROS cherchera alors"),
  ).toBeVisible();
});
