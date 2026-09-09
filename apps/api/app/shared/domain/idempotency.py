"""Politique d'idempotence : ce qui est comparé, et pendant combien de temps.

Fonctions pures. Le stockage et l'arbitrage des accès concurrents appartiennent
à l'adaptateur, parce qu'ils sont l'affaire de la base.

**Pourquoi cette mécanique existe.** Les écritures financières de KAIROS sont
`append-only` : un achat, une vente, un encaissement et un mouvement de
trésorerie s'ajoutent, ils ne se modifient pas. Un double envoi — un bouton
cliqué deux fois, une requête rejouée après un délai réseau — crée donc deux
opérations *et* deux écritures de trésorerie, et la seule correction possible
est une écriture inverse saisie à la main. C'est le genre de faute qui se
découvre en rapprochant un relevé bancaire, des semaines plus tard.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

KEY_MIN_LENGTH = 1
KEY_MAX_LENGTH = 128

# Vingt-quatre heures. Un renvoi honnête suit l'original de quelques secondes ;
# ce délai couvre largement l'utilisateur qui reprend le lendemain matin après
# une coupure. Le garder plus longtemps aurait un coût réel : une clé conservée
# indéfiniment finit par bloquer une opération légitime qui réemploierait la
# même chaîne.
RETENTION = timedelta(hours=24)

# Au-delà, une réservation sans réponse est tenue pour abandonnée.
#
# Sans ce délai, un processus tué entre la réservation et l'enregistrement de
# sa réponse condamnerait la clé pour vingt-quatre heures : l'utilisateur
# verrait sa reprise refusée sans que rien n'ait abouti. Cinq minutes dépassent
# de loin la durée de toute opération de KAIROS, dont la plus lente écrit trois
# lignes.
IN_PROGRESS_TIMEOUT = timedelta(minutes=5)


def fingerprint(body: bytes) -> str:
    """Empreinte du corps de la requête.

    Sur les octets bruts, pas sur un objet ré-encodé : deux sérialisations du
    même objet peuvent différer par l'ordre des clés ou les espaces, et
    l'empreinte doit refuser exactement ce que l'utilisateur a refusé
    d'envoyer deux fois — pas ce que nous aurions écrit à sa place.
    """

    return hashlib.sha256(body).hexdigest()
