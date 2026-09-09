import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    // Environnement Node volontairement : ce qui est vérifié ici est la
    // politique du client — quelle clé part avec quelle requête — et non le
    // rendu. Un DOM simulé ajouterait une dépendance sans rien prouver de plus.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
