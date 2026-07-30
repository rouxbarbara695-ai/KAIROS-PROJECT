import { getMe, listPlatforms } from "@/lib/api";
import { NewOpportunityForm } from "./NewOpportunityForm";

export default async function NewOpportunityPage() {
  const [me, platforms] = await Promise.all([getMe(), listPlatforms()]);
  const portfolioId = me.portfolio_ids[0];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Nouvelle opportunité
        </h1>
        <p className="mt-1 text-sm text-fg-muted">
          Saisie manuelle, sans collecteur externe.
        </p>
      </div>
      <NewOpportunityForm
        portfolioId={portfolioId}
        platforms={platforms.map((platform) => ({
          code: platform.code,
          name: platform.name,
          hasRule: platform.has_active_rule,
        }))}
      />
    </div>
  );
}
