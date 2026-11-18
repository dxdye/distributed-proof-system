/** A Lean name that wraps after a dot or an underscore rather than inside a
 * word; `overflow-wrap: anywhere` on code stays the last resort. <wbr> rather
 * than a zero-width space, so that a copied name is still the same name. */
export function LeanName({
  text,
  className,
  title,
}: {
  text: string;
  className?: string;
  title?: string;
}) {
  const parts = text.split(/(?<=[._])/);
  return (
    <code className={className} title={title}>
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          {i < parts.length - 1 && <wbr />}
        </span>
      ))}
    </code>
  );
}
