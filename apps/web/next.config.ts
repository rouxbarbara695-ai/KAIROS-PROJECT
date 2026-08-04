import type { NextConfig } from "next";

/**
 * L'API est servie sous la même origine que l'interface.
 *
 * Ce n'est pas un détail de confort : la session vit dans un cookie, et un
 * cookie posé par une autre origine reste invisible au serveur Next. Le
 * middleware ne pourrait pas le lire, les composants serveur ne pourraient pas
 * le transmettre, et l'utilisateur serait connecté du point de vue de l'API
 * tout en paraissant déconnecté du point de vue des pages.
 *
 * La réécriture supprime aussi tout besoin de CORS côté navigateur : il n'y a
 * plus qu'une origine.
 */
const API_ORIGIN = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
