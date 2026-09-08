"""Un champ importé, et ce qu'on sait de lui.

Le préremplissage pose un risque que la saisie manuelle n'a pas : une valeur
apparaît dans un formulaire sans que rien ne dise d'où elle vient. L'utilisateur
la valide parce qu'elle est là. Si elle a été devinée, l'erreur entre dans le
dossier avec l'autorité d'une donnée vérifiée, et ressort plus tard dans un
calcul de prix maximal.

D'où trois exigences, portées par ce module :

- **la valeur brute est conservée** telle que la page l'écrivait, à côté de la
  valeur normalisée. Une normalisation est une interprétation ; on doit pouvoir
  revenir à ce qui était écrit ;
- **la provenance accompagne la valeur** : importée, corrigée par
  l'utilisateur, ou absente. Une valeur absente reste absente — jamais un
  défaut favorable ;
- **une contradiction est signalée, pas arbitrée.** Quand le titre dit une
  chose et la fiche technique une autre, KAIROS montre les deux.

Ce qui n'est **pas** ici est aussi important : il n'existe aucune fonction qui
complète un champ manquant. Une année, une référence, un diamètre ou un calibre
absent de la page reste absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Provenance(StrEnum):
    """D'où vient la valeur qui est à l'écran."""

    #: Lue dans une page récupérée par le serveur.
    IMPORTED = "imported"
    #: Lue dans un contenu fourni par l'utilisateur (repli assisté).
    ASSISTED = "assisted"
    #: Saisie ou corrigée par l'utilisateur.
    USER = "user"
    #: La page ne la donnait pas. Ce n'est pas une valeur, c'est un constat.
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class Imported:
    """Une valeur, ce qu'elle était avant normalisation, et son origine.

    `raw` est ce que la page écrivait (« Boîtier 40 mm », « GBP 7,995 »).
    `value` est ce que KAIROS en a fait, ou `None` s'il n'a pas su : ne pas
    savoir normaliser n'autorise pas à inventer, et la valeur brute reste
    consultable.
    """

    raw: str | None
    value: Any = None
    provenance: Provenance = Provenance.IMPORTED
    #: Ce qui a permis de lire la valeur : `schema.org/Product.mpn`,
    #: `og:title`… Sert à expliquer une valeur douteuse sans relire la page.
    source: str | None = None
    #: Autres lectures du même champ, quand elles divergent **réellement**.
    #: Une formulation plus détaillée n'est pas une divergence : « Quartz » et
    #: « High-precision Swiss quartz, Caliber Omega 1456 » disent la même
    #: chose, la seconde en plus précis.
    conflicts: tuple[str, ...] = ()
    #: La valeur est proposée, pas établie. Vrai dès qu'une divergence réelle
    #: subsiste : la fiche technique sert à **proposer** une valeur, elle ne
    #: prouve pas qu'elle soit juste. L'utilisateur tranche.
    needs_confirmation: bool = False

    @property
    def is_present(self) -> bool:
        return self.value is not None or (self.raw is not None and self.raw != "")

    def to_json(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "value": _jsonable(self.value),
            "provenance": self.provenance.value,
            "source": self.source,
            "conflicts": list(self.conflicts),
            "needs_confirmation": self.needs_confirmation,
        }


def absent(reason: str | None = None) -> Imported:
    """Le champ n'était pas dans la page.

    Existe pour que l'absence soit une valeur explicite du modèle, et non un
    `None` qu'un appelant distrait remplacerait par un défaut.
    """

    return Imported(raw=None, value=None, provenance=Provenance.ABSENT, source=reason)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        # Chaîne décimale : la règle 2 interdit qu'un montant devienne un
        # flottant JSON en route.
        return str(value)
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


@dataclass(slots=True)
class ListingDraft:
    """Ce qu'une annonce a livré, champ par champ.

    Tous les champs sont `Imported`, y compris ceux qui n'ont rien donné : le
    formulaire doit pouvoir dire « non renseigné » plutôt que de laisser une
    case vide indistincte d'une case jamais remplie.
    """

    # Identité de l'annonce
    platform_code: str = ""
    canonical_url: str = ""
    external_id: Imported = field(default_factory=absent)
    fetched_at: str = ""

    # Montre
    title: Imported = field(default_factory=absent)
    brand: Imported = field(default_factory=absent)
    collection: Imported = field(default_factory=absent)
    reference: Imported = field(default_factory=absent)
    year: Imported = field(default_factory=absent)
    #: « 2010-2020 » tel que Catawiki l'écrit. Conservé à part de `year` :
    #: c'est une information réelle et utile, qui ne devient pas une année
    #: exacte pour autant. Enregistrée, affichée, modifiable.
    production_period: Imported = field(default_factory=absent)
    movement: Imported = field(default_factory=absent)
    calibre: Imported = field(default_factory=absent)
    case_material: Imported = field(default_factory=absent)
    case_diameter_mm: Imported = field(default_factory=absent)
    dial: Imported = field(default_factory=absent)
    bracelet_material: Imported = field(default_factory=absent)
    buckle: Imported = field(default_factory=absent)

    # État et complétude — boîte et papiers séparément, jamais « full set »
    # déduit d'une mention ambiguë.
    declared_condition: Imported = field(default_factory=absent)
    box: Imported = field(default_factory=absent)
    papers: Imported = field(default_factory=absent)
    service_history: Imported = field(default_factory=absent)
    replaced_parts: Imported = field(default_factory=absent)
    description: Imported = field(default_factory=absent)

    # Prix : montant, devise et **nature** du prix. Confondre un prix demandé
    # avec un prix réalisé fausse toute l'analyse (règle 5).
    price_amount: Imported = field(default_factory=absent)
    price_currency: Imported = field(default_factory=absent)
    price_kind: Imported = field(default_factory=absent)

    # Vendeur
    seller_name: Imported = field(default_factory=absent)
    seller_type: Imported = field(default_factory=absent)
    seller_country: Imported = field(default_factory=absent)

    # Conditions de transaction
    shipping: Imported = field(default_factory=absent)
    insurance: Imported = field(default_factory=absent)
    warranty: Imported = field(default_factory=absent)
    returns: Imported = field(default_factory=absent)

    # --- Vente aux enchères -------------------------------------------------
    #
    # Séparés du prix ordinaire, et c'est le point important. Une enchère en
    # cours n'est **ni** un prix d'achat garanti **ni** un prix final : elle
    # monte, et elle peut ne pas atteindre la réserve. La confondre avec un
    # prix demandé ferait calculer une marge sur un montant qui n'existera
    # jamais (règle 5).
    lot_number: Imported = field(default_factory=absent)
    current_bid_amount: Imported = field(default_factory=absent)
    current_bid_currency: Imported = field(default_factory=absent)
    bid_count: Imported = field(default_factory=absent)

    #: Date et heure de clôture. Sans fuseau explicite, l'heure reste absente :
    #: se tromper d'une heure sur une fin d'enchère, c'est la rater.
    closing_at: Imported = field(default_factory=absent)
    closing_timezone: Imported = field(default_factory=absent)

    #: Estimation **de la plateforme**, conservée à part. Ce n'est pas une
    #: estimation KAIROS, et elle n'entre dans aucun calcul : le schéma
    #: distingue d'ailleurs `external_estimate` de `kairos_estimate`.
    estimate_low: Imported = field(default_factory=absent)
    estimate_high: Imported = field(default_factory=absent)
    estimate_currency: Imported = field(default_factory=absent)

    #: `no_reserve`, `not_met`, `met` — uniquement sur mention explicite.
    #: L'absence de mention ne vaut pas « pas de réserve ».
    reserve_status: Imported = field(default_factory=absent)

    #: Frais de livraison, **et** la destination à laquelle ils se rapportent.
    #: Un montant sans destination nommée n'est pas repris : un tarif Pays-Bas
    #: pris pour un tarif France fausse le coût de revient.
    shipping_cost_amount: Imported = field(default_factory=absent)
    shipping_cost_currency: Imported = field(default_factory=absent)
    shipping_destination: Imported = field(default_factory=absent)

    seller_since: Imported = field(default_factory=absent)

    #: Commission acheteur annoncée sur la page du lot. Reprise parce qu'elle
    #: est affichée noir sur blanc et qu'elle pèse sur le coût de revient —
    #: jamais devinée quand la page se tait (« n'invente aucun frais absent »).
    buyer_fee_rate: Imported = field(default_factory=absent)
    buyer_fee_fixed: Imported = field(default_factory=absent)
    buyer_fee_currency: Imported = field(default_factory=absent)

    photos: tuple[str, ...] = ()

    #: Ce que l'extraction n'a pas pu faire, dit en clair à l'utilisateur.
    warnings: tuple[str, ...] = ()

    def fields(self) -> dict[str, Imported]:
        skip = {"platform_code", "canonical_url", "fetched_at", "photos", "warnings"}
        return {
            name: getattr(self, name)
            for name in self.__slots__
            if name not in skip and isinstance(getattr(self, name), Imported)
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "platform_code": self.platform_code,
            "canonical_url": self.canonical_url,
            "fetched_at": self.fetched_at,
            "photos": list(self.photos),
            "warnings": list(self.warnings),
            "fields": {name: value.to_json() for name, value in self.fields().items()},
        }

    @property
    def filled_count(self) -> int:
        return sum(1 for value in self.fields().values() if value.is_present)
