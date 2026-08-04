import { NextResponse, type NextRequest } from "next/server";

/**
 * Renvoie vers la connexion quand aucune session n'est présentée.
 *
 * Le middleware ne vérifie que la **présence** du cookie, jamais sa validité :
 * il n'a pas accès à la base, et il ne doit surtout pas devenir un second
 * endroit où l'on décide qui a le droit d'entrer. L'autorité reste l'API, qui
 * répond 401 sur un jeton révoqué ou expiré. Ce filtre évite seulement
 * d'afficher une page qui échouerait de toute façon.
 */
export function middleware(request: NextRequest) {
  if (request.cookies.has("kairos_session")) return NextResponse.next();

  const target = new URL("/connexion", request.url);
  return NextResponse.redirect(target);
}

export const config = {
  // Trois exclusions, chacune pour une raison distincte.
  //
  // `api` : les appels d'API ne doivent jamais être redirigés. C'est l'API qui
  // décide qui entre, et rediriger sa propre route de connexion la rendrait
  // inatteignable — l'utilisateur ne pourrait plus se connecter du tout.
  //
  // `connexion` : sans cette exclusion, la redirection tournerait en boucle.
  //
  // Ressources statiques : elles ne portent aucune donnée du portefeuille.
  matcher: ["/((?!api|connexion|_next/static|_next/image|favicon.ico).*)"],
};
