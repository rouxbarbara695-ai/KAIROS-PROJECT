import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

const CHROMIUM =
  process.env.E2E_CHROMIUM ??
  "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";

/**
 * Essai navigateur du parcours « Import assisté Catawiki ».
 *
 * Ces tests-là ne remplacent pas les tests d'API : ils vérifient ce que les
 * autres ne peuvent pas voir — que le collage atteint bien le formulaire, que
 * la correction survit à l'enregistrement, et qu'en rouvrant la fiche on
 * retrouve encore ce que l'annonce disait. Un import correct côté serveur mais
 * qui n'arrive pas à l'écran ne sert à rien.
 *
 * Le navigateur est celui de l'image (`PLAYWRIGHT_BROWSERS_PATH`) : rien n'est
 * téléchargé au lancement.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // Un seul ouvrier : les tests partagent le portefeuille du compte d'essai,
  // et deux parcours simultanés se marcheraient dessus.
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    // Le navigateur de l'image, quand il y est. Playwright réclamerait sinon
    // un build précis correspondant à sa version, et le télécharger n'est ni
    // permis ni souhaitable ici. `E2E_CHROMIUM` laisse la main ailleurs.
    launchOptions: existsSync(CHROMIUM) ? { executablePath: CHROMIUM } : {},
    // Une capture par échec : c'est la première chose qu'on regarde, et sans
    // elle un échec en intégration continue ne se diagnostique pas.
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
