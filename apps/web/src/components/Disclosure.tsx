/**
 * Repli natif `<details>` : pas de JavaScript, état géré par le navigateur,
 * accessible au clavier par construction. Les écrans de correction ne sont
 * pas l'action principale d'une fiche — ils restent à portée sans occuper la
 * page.
 */
export function Disclosure({
  summary,
  children,
}: {
  summary: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group border-t border-border pt-3 first:border-0 first:pt-0">
      <summary className="cursor-pointer list-none text-sm font-medium text-fg-muted transition-colors hover:text-fg">
        <span className="inline-flex items-center gap-1.5">
          <span className="text-xs transition-transform group-open:rotate-90">
            ▸
          </span>
          {summary}
        </span>
      </summary>
      <div className="pt-3">{children}</div>
    </details>
  );
}
