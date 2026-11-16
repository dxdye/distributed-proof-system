import { useState } from "react";
import { api } from "../api";
import { parseTags } from "../tags";

/** Hashtags of a problem (C-44). With `onPick` a tag filters in place;
 * with `href` it leads to a list filtered by it. */
export function Tags({
  tags,
  onPick,
  href,
  active,
}: {
  tags?: string[] | null;
  onPick?: (tag: string) => void;
  href?: (tag: string) => { href: string; onClick: () => void };
  active?: string;
}) {
  if (!tags || tags.length === 0) return null;
  return (
    <span className="tags">
      {tags.map((t) => {
        const cls = t === active ? "tag on" : "tag";
        if (onPick)
          return (
            <button
              key={t}
              className={cls}
              aria-pressed={t === active}
              onClick={() => onPick(t)}
              title={`Show only #${t}`}
            >
              #{t}
            </button>
          );
        if (href) {
          const link = href(t);
          return (
            <a key={t} className={cls} href={link.href} onClick={link.onClick}>
              #{t}
            </a>
          );
        }
        return (
          <span key={t} className={cls}>
            #{t}
          </span>
        );
      })}
    </span>
  );
}

/** Maintainers set the hashtags of a submission: the whole set at once. */
export function TagEditor({
  sid,
  tags,
  onSaved,
}: {
  sid: string;
  tags: string[];
  onSaved: () => void;
}) {
  const [text, setText] = useState(tags.map((t) => `#${t}`).join(" "));
  const [message, setMessage] = useState<string | null>(null);
  const parsed = parseTags(text);
  const save = async () => {
    try {
      const out = await api.admin.setTags(sid, parsed.tags);
      setMessage(out.tags.length ? "Saved." : "Tags removed.");
      onSaved();
    } catch (e) {
      setMessage((e as Error).message);
    }
  };
  return (
    <div className="tag-editor">
      <label className="small" htmlFor="tag-input">
        Hashtags (maintainers): the problem and its kind, so that it is found quickly. Not used for
        the draw.
      </label>
      <div className="tag-editor-row">
        <input
          id="tag-input"
          value={text}
          placeholder="#navier-stokes #millennium-prize"
          onChange={(e) => {
            setText(e.target.value);
            setMessage(null);
          }}
        />
        <button onClick={save} disabled={parsed.bad.length > 0}>
          Save
        </button>
      </div>
      {parsed.bad.length > 0 ? (
        <p className="error small">
          Not a tag: {parsed.bad.join(", ")} (letters a–z, digits and hyphens, 2 to 40 characters)
        </p>
      ) : (
        message && <p className="muted small">{message}</p>
      )}
    </div>
  );
}
