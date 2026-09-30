"""Faux serveur eBay pour le parcours navigateur de la CI — jamais en production.

Il parle le protocole de l'API Browse (jeton OAuth, recherche d'annonces) sur
une vraie prise réseau : le parcours complet — API réelle, tâche de fond, base,
interface — s'exécute sans identifiants. C'est un **simulacre de données** : il
prouve que la chaîne fonctionne, pas que eBay répond. Pour cela, voir
`python -m app.market_search.probe`.

Pour une requête « Omega RM123 » (et seulement Omega), il renvoie deux
annonces exactes, un voisin dont la référence n'est qu'à un caractère de la
bonne, et une annonce « pour pièces » : de quoi éprouver le contrôle
d'identité de bout en bout.

Usage : python tests/fake_ebay_server.py [port]
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit


def _items(query: str) -> list[dict[str, object]]:
    parts = query.split()
    if len(parts) < 2:
        return []
    # La référence est lue sans espaces : « RC 123 » et « RC123 » sont la même.
    brand, reference = parts[0], "".join(parts[1:])
    # Seule la marque « Omega » a des annonces : les autres parcours de la CI
    # confirment leurs références sans que des comparables leur tombent dessus.
    if brand.lower() != "omega":
        return []

    def item(suffix: str, title: str, price: str) -> dict[str, object]:
        return {
            "itemId": f"v1|{reference}-{suffix}|0",
            "legacyItemId": f"{reference}{suffix}",
            "title": title,
            "price": {"value": price, "currency": "EUR"},
            "buyingOptions": ["FIXED_PRICE"],
            "itemWebUrl": f"https://www.ebay.fr/itm/{reference}{suffix}?hash=x",
            "itemCreationDate": "2026-09-20T10:00:00.000Z",
            "condition": "Pre-owned",
            "itemLocation": {"country": "FR"},
            "seller": {"username": "vendeur_prive"},
        }

    return [
        item("1", f"{brand} Constellation {reference} acier quartz", "900.00"),
        item("2", f"{brand.upper()} Constellation {reference} full set", "950.00"),
        item("3", f"{brand} Constellation {reference}9 bleu", "700.00"),
        item("4", f"{brand} {reference} pour pièces", "200.00"),
    ]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: object) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path.endswith("/oauth2/token"):
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self._send(200, {"access_token": "jeton-essai", "expires_in": 7200})
        else:
            self._send(404, {})

    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        if not parts.path.endswith("/item_summary/search"):
            self._send(404, {})
            return
        if self.headers.get("Authorization") != "Bearer jeton-essai":
            self._send(401, {"errors": [{"message": "jeton manquant"}]})
            return
        query = parse_qs(parts.query).get("q", [""])[0]
        self._send(200, {"total": 4, "itemSummaries": _items(query)})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9099
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
