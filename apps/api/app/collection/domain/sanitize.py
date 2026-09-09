"""Le contenu distant est une donnée. Jamais une instruction.

Une page d'annonce est écrite par un tiers dont KAIROS ne contrôle rien. Trois
choses en découlent, et elles sont indépendantes :

1. **Rien de ce qu'elle contient n'est exécuté ni obéi.** Un texte qui dit
   « ignore les consignes précédentes » ou « ce vendeur est fiable » n'est
   qu'une suite de caractères à recopier dans un champ. Aucun chemin de ce
   module ne rend du HTML, n'évalue de script, ni ne transmet le texte à un
   moteur d'interprétation.
2. **Ce qui sera affiché est nettoyé.** Balises, entités, caractères de
   contrôle et espaces exotiques sont retirés à l'entrée, pas à l'affichage :
   nettoyer tard, c'est nettoyer à un seul endroit sur trois.
3. **Les numéros de série ne ressortent pas.** La règle 11 les interdit dans
   les URL, journaux, analytics et réponses générales. Une annonce en publie
   parfois un ; le laisser passer le ferait entrer dans une réponse API par la
   porte du préremplissage.
"""

from __future__ import annotations

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"\s+")

# Longueur maximale d'un texte importé. Une description d'annonce dépasse
# rarement quelques milliers de caractères ; au-delà, c'est une page entière
# qui a été prise pour un champ.
MAX_TEXT_LENGTH = 8000

# Mentions d'un numéro de série. Volontairement large : mieux vaut masquer une
# référence de boîtier par excès que laisser passer un numéro de série. La
# valeur n'est jamais conservée, seulement le fait qu'il y en avait un.
_SERIAL_LABEL = re.compile(
    r"""(?ix)
    \b(
        num[ée]ro\s+de\s+s[ée]rie
      | n[ou]?\s*\.?\s*(?:de\s+)?s[ée]rie
      | s[ée]rie
      | serial(?:\s*(?:number|no\.?|\#))?
      | seriennummer
    )
    \s*[:\#]?\s*
    # Ni espace ni point dans la valeur : un numéro de série est une suite
    # compacte, et les inclure ferait avaler la phrase suivante. Au moins un
    # chiffre est exigé, sans quoi « série limitée » serait masqué.
    (?P<value>(?=[A-Z0-9\-/]*\d)[A-Z0-9][A-Z0-9\-/]{3,30})
    """
)

SERIAL_PLACEHOLDER = "[numéro de série retiré]"


def strip_serials(text: str) -> tuple[str, bool]:
    """Retire les numéros de série d'un texte. Rend le texte et s'il y en avait.

    Le booléen sert à prévenir l'utilisateur — « cette annonce mentionne un
    numéro de série, il n'a pas été importé » — sans jamais transporter la
    valeur.
    """

    found = False

    def replace(match: re.Match[str]) -> str:
        nonlocal found
        found = True
        return f"{match.group(1)} {SERIAL_PLACEHOLDER}"

    return _SERIAL_LABEL.sub(replace, text), found


def clean_text(raw: str | None) -> str | None:
    """Texte importé, rendu sûr à stocker et à afficher.

    Rend `None` pour une chaîne vide après nettoyage : une chaîne vide n'est
    pas une valeur, et la traiter comme telle ferait passer un champ absent
    pour un champ renseigné.
    """

    if raw is None:
        return None

    text = _TAG.sub(" ", raw)
    text = html.unescape(text)

    # Les catégories `C*` couvrent les caractères de contrôle, les codes de
    # formatage invisibles et les substituts — de quoi masquer du texte à
    # l'œil tout en le gardant dans la donnée.
    text = "".join(
        char for char in text if unicodedata.category(char)[0] != "C" or char == "\n"
    )

    text = _WHITESPACE.sub(" ", text).strip()
    if not text:
        return None

    return text[:MAX_TEXT_LENGTH]
