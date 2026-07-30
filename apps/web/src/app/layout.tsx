import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "KAIROS",
  description: "Moteur de décision achat-revente de montres",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>
        <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-6">
          <header className="flex items-center justify-between border-b border-border py-5">
            <Link href="/opportunities" className="flex items-center gap-2">
              <span className="text-lg font-semibold tracking-tight">
                KAIROS
              </span>
            </Link>
            <nav className="flex items-center gap-6 text-sm text-fg-muted">
              <Link
                href="/opportunities"
                className="transition-colors hover:text-fg"
              >
                Opportunités
              </Link>
              <Link
                href="/portefeuille"
                className="transition-colors hover:text-fg"
              >
                Portefeuille
              </Link>
              <Link
                href="/plateformes"
                className="transition-colors hover:text-fg"
              >
                Plateformes
              </Link>
              <Link
                href="/opportunities/new"
                className="rounded-md bg-accent px-3 py-1.5 font-medium text-bg transition-opacity hover:opacity-90"
              >
                Nouvelle opportunité
              </Link>
            </nav>
          </header>
          <main className="flex-1 py-8">{children}</main>
          <footer className="border-t border-border py-6 text-xs text-fg-muted">
            KAIROS — parcours manuel, décision et portefeuille
          </footer>
        </div>
      </body>
    </html>
  );
}
