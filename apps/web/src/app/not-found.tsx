import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md space-y-4 py-16">
      <h1 className="text-xl font-semibold">Page introuvable</h1>
      <p className="text-sm text-fg-muted">
        Ce dossier n&apos;existe pas, ou il appartient à un autre portefeuille.
      </p>
      <Link
        href="/opportunities"
        className="inline-block rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-bg"
      >
        Retour aux opportunités
      </Link>
    </div>
  );
}
