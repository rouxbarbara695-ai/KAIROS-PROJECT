import type { ImportTraceResponse } from "@/lib/api";

/**
 * Ce que l'annonce affichait au moment de l'import.
 *
 * Sans cet écran, l'import serait un aller simple : les valeurs entreraient
 * dans le dossier et plus rien ne dirait, six semaines plus tard, laquelle
 * venait de l'annonce et laquelle a été corrigée à la main. C'est précisément
 * la question qu'on se pose quand un chiffre paraît faux.
 *
 * Le relevé est **immuable**. Un second import ajoute une lecture ; il
 * n'écrase pas celle-ci — c'est ce qui permet de voir si une enchère
 * s'emballe.
 */

const FIELD_LABELS: Record<string, string> = {
  lot_number: "Numéro de lot",
  title: "Titre du lot",
  brand: "Marque",
  collection: "Modèle",
  reference: "Référence",
  year: "Année",
  production_period: "Période de production",
  movement: "Mouvement",
  calibre: "Calibre",
  case_material: "Matériau du boîtier",
  case_diameter_mm: "Diamètre",
  dial: "Cadran",
  bracelet_material: "Bracelet",
  buckle: "Boucle",
  declared_condition: "État déclaré",
  service_history: "Révision déclarée",
  box: "Boîte",
  papers: "Papiers",
  current_bid_amount: "Enchère en cours",
  current_bid_currency: "Devise",
  bid_count: "Nombre d'enchères",
  closing_at: "Clôture",
  closing_timezone: "Fuseau",
  estimate_low: "Estimation Catawiki (bas)",
  estimate_high: "Estimation Catawiki (haut)",
  reserve_status: "Prix de réserve",
  shipping_cost_amount: "Livraison vers la France",
  shipping_destination: "Destination des frais",
  buyer_fee_rate: "Commission acheteur (taux)",
  buyer_fee_fixed: "Commission acheteur (part fixe)",
  seller_name: "Vendeur",
  seller_type: "Type de vendeur",
  seller_country: "Pays du vendeur",
  warranty: "Garantie d'origine",
  insurance: "Envoi assuré",
  price_kind: "Nature du montant",
  external_id: "Identifiant d'annonce",
  price_amount: "Montant retenu",
  price_currency: "Devise du montant",
  estimate_currency: "Devise de l'estimation",
  buyer_fee_currency: "Devise de la commission",
  shipping_cost_currency: "Devise des frais",
  description: "Description du vendeur",
  returns: "Retours",
  shipping: "Expédition",
  replaced_parts: "Pièces remplacées",
  seller_since: "Vendeur depuis",
};

/**
 * Ordre d'affichage.
 *
 * L'ordre d'insertion d'un dictionnaire n'est pas un ordre de lecture : sans
 * cette liste, « Boîte » précédait « Marque » et l'œil ne trouvait rien. Les
 * champs absents de la liste suivent, par ordre alphabétique.
 */
const FIELD_ORDER = [
  "lot_number",
  "title",
  "brand",
  "collection",
  "reference",
  "production_period",
  "year",
  "movement",
  "calibre",
  "case_material",
  "case_diameter_mm",
  "dial",
  "bracelet_material",
  "buckle",
  "declared_condition",
  "service_history",
  "box",
  "papers",
  "current_bid_amount",
  "current_bid_currency",
  "price_kind",
  "bid_count",
  "reserve_status",
  "closing_at",
  "closing_timezone",
  "estimate_low",
  "estimate_high",
  "estimate_currency",
  "buyer_fee_rate",
  "buyer_fee_fixed",
  "buyer_fee_currency",
  "shipping_cost_amount",
  "shipping_cost_currency",
  "shipping_destination",
  "warranty",
  "insurance",
  "seller_name",
  "seller_type",
  "seller_country",
  "seller_since",
  "description",
];

function rank(name: string): number {
  const index = FIELD_ORDER.indexOf(name);
  return index === -1 ? FIELD_ORDER.length : index;
}

/** La description tient sur plusieurs écrans : on la borne. */
const LONG_FIELDS = new Set(["description", "title"]);
const MAX_SHOWN = 280;

function shorten(text: string): string {
  return text.length > MAX_SHOWN ? `${text.slice(0, MAX_SHOWN)}…` : text;
}

const VALUE_LABELS: Record<string, string> = {
  current_bid: "enchère en cours",
  asking: "prix demandé",
  no_reserve: "aucun prix de réserve",
  not_met: "non atteint",
  met: "atteint",
  declared: "déclarée par le vendeur",
  professional: "professionnel",
  private: "particulier",
};

const PROVENANCE_LABELS: Record<string, string> = {
  imported: "récupéré par KAIROS",
  assisted: "lu dans le contenu que vous avez collé",
  user: "saisi par vous",
  absent: "non renseigné par l'annonce",
};

function display(value: unknown, raw: string | null | undefined): string {
  if (value === null || value === undefined) return raw ?? "Non renseigné";
  if (typeof value === "boolean") return value ? "Oui" : "Non";
  const text = String(value);
  return VALUE_LABELS[text] ?? text;
}

export function ImportTrace({ items }: { items: ImportTraceResponse[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-fg-muted">
        Ce dossier a été saisi à la main : il n&apos;y a pas de relevé
        d&apos;annonce à afficher.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {items.map((item) => (
        <Reading key={item.observed_at} item={item} />
      ))}
    </div>
  );
}

function Reading({ item }: { item: ImportTraceResponse }) {
  const fields = Object.entries(item.fields ?? {}).sort(
    ([left], [right]) => rank(left) - rank(right) || left.localeCompare(right),
  );
  const read = fields.filter(([, field]) => field.provenance !== "absent");
  const missing = fields.filter(([, field]) => field.provenance === "absent");
  const toConfirm = read.filter(([, field]) => field.needs_confirmation);
  const warnings = item.warnings ?? [];

  return (
    <div className="space-y-3">
      <p className="text-xs text-fg-muted">
        Relevé du{" "}
        {new Date(item.observed_at).toLocaleString("fr-FR", {
          dateStyle: "long",
          timeStyle: "short",
        })}
        {item.access_mode === "assisted" &&
          " — import assisté, contenu que vous avez fourni"}
        . {read.length} champ{read.length > 1 ? "s" : ""} lu
        {read.length > 1 ? "s" : ""}.
      </p>

      {toConfirm.length > 0 && (
        <div className="rounded-md border border-border bg-bg p-3">
          <p className="mb-2 text-sm font-medium">À confirmer</p>
          <ul className="space-y-1.5 text-xs text-fg-muted">
            {toConfirm.map(([name, field]) => (
              <li key={name}>
                <span className="font-medium text-fg">
                  {FIELD_LABELS[name] ?? name}
                </span>{" "}
                — {display(field.value, field.raw)}
                {(field.conflicts ?? []).length > 0 && (
                  <>
                    {" "}
                    ; l&apos;annonce dit aussi :{" "}
                    {(field.conflicts ?? []).join(" ; ")}
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {read.map(([name, field]) => (
          <div
            key={name}
            className="flex items-baseline justify-between gap-3 border-b border-border py-1.5"
          >
            <dt className="text-fg-muted">{FIELD_LABELS[name] ?? name}</dt>
            <dd className="max-w-[60%] text-right">
              {LONG_FIELDS.has(name) ? (
                // Bornée au rendu plutôt qu'en CSS : une description de
                // vendeur fait plusieurs écrans et écraserait le tableau.
                // Le texte entier reste dans l'info-bulle et en base.
                <span title={String(field.value ?? "")}>
                  {shorten(display(field.value, field.raw))}
                </span>
              ) : (
                display(field.value, field.raw)
              )}
              {/* La valeur brute est montrée dès qu'elle diffère de la valeur
                  retenue : « 266.1.44 - Serviced » explique d'où vient
                  « 266.1.44 », et permet de contester la normalisation. */}
              {!LONG_FIELDS.has(name) &&
                field.raw &&
                String(field.value ?? "") !== field.raw && (
                  <span className="block text-xs text-fg-muted">
                    tel qu&apos;affiché : {field.raw}
                  </span>
                )}
              <span className="block text-xs text-fg-muted">
                {PROVENANCE_LABELS[field.provenance] ?? field.provenance}
              </span>
            </dd>
          </div>
        ))}
      </dl>

      {missing.length > 0 && (
        <p className="text-xs text-fg-muted">
          <span className="font-medium">
            Non renseigné par l&apos;annonce :
          </span>{" "}
          {missing.map(([name]) => FIELD_LABELS[name] ?? name).join(", ")}.
        </p>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-1 text-xs text-fg-muted">
          {warnings.map((warning) => (
            <li key={warning}>— {warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
