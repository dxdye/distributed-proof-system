import { useEffect, useRef, useState } from "react";
import type { Me } from "../api";

// The account menu in the service bar: who is signed in, the personal pages,
// and signing out. Closes on a click outside, on Escape and on navigation.

const GROUPS: Record<string, string> = {
  expert: "Expert",
  doctoral: "Doctoral student",
  student: "Student",
  other: "Other",
};

export function UserMenu({ me, onSignOut }: { me: Me | null; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const navigate = () => setOpen(false);
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("hashchange", navigate);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("hashchange", navigate);
    };
  }, [open]);

  return (
    <div className="user-menu" ref={box}>
      <button
        className="user-toggle"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="avatar" aria-hidden="true">
          {(me?.pseudonym ?? "?").slice(0, 1).toUpperCase()}
        </span>
        {me?.pseudonym ?? "Account"}
        <span className="caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <div className="user-dropdown" role="menu">
          {me && (
            <div className="user-head">
              <strong>{me.pseudonym}</strong>
              <span className="small muted">
                {GROUPS[me.group] ?? me.group}
                {me.maintainer ? " · Maintainer" : ""}
              </span>
            </div>
          )}
          <a role="menuitem" href="#/history">
            My reviews
          </a>
          <a role="menuitem" href="#/work/preferences">
            Preferences
          </a>
          {me?.maintainer && (
            <a role="menuitem" href="#/admin">
              Maintainers
            </a>
          )}
          <a role="menuitem" href="#/how">
            How it works
          </a>
          <button role="menuitem" className="user-signout" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
