import { useState } from "react";
import type { ProgressDetail } from "../api";
import { LeanName } from "./LeanName";

// What a result relies on (proposal C-29): what the system re-checked, and
// what it trusts without checking. Nothing is shown as checked that was not.

type Status = "checked" | "trusted" | "open";

const STATUS: Record<Status, { icon: string; label: string }> = {
  checked: { icon: "✓", label: "checked" },
  trusted: { icon: "◇", label: "trusted" },
  open: { icon: "!", label: "not reviewed" },
};

function Chip({ status, label }: { status: Status; label?: string }) {
  return (
    <span className={`basis-chip basis-${status}`}>
      <span aria-hidden="true">{STATUS[status].icon}</span> {label ?? STATUS[status].label}
    </span>
  );
}

const fmt = (n: number) => n.toLocaleString("en").replace(/,/g, " ");
const short = (rev: string) => rev.slice(0, 8);
const commitUrl = (url: string, rev: string) =>
  `${url.replace(/\/$/, "").replace(/\.git$/, "")}/commit/${rev}`;
const LIB_NAMES: Record<string, string> = { mathlib: "Mathlib", batteries: "Batteries" };

export function Basis({ d }: { d: ProgressDetail }) {
  const b = d.basis;
  const defs = d.library_definitions;
  const [all, setAll] = useState(false);
  const FOLD = 10; // long lists (Navier–Stokes: 37) start folded
  const shownDefs = defs && !all ? defs.slice(0, FOLD) : defs;
  const mathlib = b?.libraries.find((l) => l.name === "mathlib");
  const others = b?.libraries.filter((l) => l.name !== "mathlib") ?? [];
  return (
    <section className="card">
      <h3>What the result relies on</h3>
      <p className="muted small">
        A formal result is only as good as what it is built on. This is what the system checked
        itself, and what it trusts without checking.
      </p>
      {!b ? (
        <p className="muted">Not recorded for this submission.</p>
      ) : (
        <ul className="basis">
          <li>
            {b.replayed && b.replay_failures === 0 ? (
              <Chip status="checked" />
            ) : (
              <Chip status="open" label={b.replayed ? "rejected" : "not re-checked"} />
            )}
            <div>
              <strong>The submission's own proofs</strong>
              <p>
                {b.replayed
                  ? `${fmt(b.modules_replayed)} modules with ${fmt(b.constants_replayed)} declarations, re-checked by Lean's kernel; ${b.replay_failures === 0 ? "none rejected" : `${b.replay_failures} rejected`}.`
                  : "The kernel replay did not run for this submission."}
              </p>
            </div>
          </li>
          <li>
            <Chip status="checked" />
            <div>
              <strong>Axioms</strong>
              <p>
                Only the standard ones: <code>{b.axioms.join(", ")}</code>.
              </p>
            </div>
          </li>
          {mathlib && (
            <li>
              <Chip status={b.libraries_replayed ? "checked" : "trusted"} />
              <div>
                <strong>
                  Mathlib{" "}
                  <a href={commitUrl(mathlib.url, mathlib.rev)}>
                    <code>{short(mathlib.rev)}</code>
                  </a>
                  {others.length > 0 &&
                    ` and ${others.length} further official ${others.length === 1 ? "package" : "packages"}`}
                </strong>
                <p>
                  From their official sources
                  {b.hardened_unchanged
                    ? `, unchanged by the build${b.hardened_files ? ` (${fmt(b.hardened_files)} files compared)` : ""}`
                    : ""}
                  .{" "}
                  {b.libraries_replayed
                    ? "Re-checked by the kernel as well."
                    : b.modules_trusted > 0
                      ? `Not re-checked here: ${fmt(b.modules_trusted)} library modules are trusted as far as Mathlib's own checks.`
                      : "Not re-checked here: trusted as far as Mathlib's own checks."}
                </p>
                {others.length > 0 && (
                  <details className="basis-more">
                    <summary>The further packages</summary>
                    <ul>
                      {others.map((l) => (
                        <li key={l.name}>
                          {LIB_NAMES[l.name] ?? l.name}{" "}
                          <a href={commitUrl(l.url, l.rev)}>
                            <code>{short(l.rev)}</code>
                          </a>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </li>
          )}
          <li>
            <Chip status={b.second_kernel ? "checked" : "trusted"} />
            <div>
              <strong>Lean's kernel {b.toolchain}</strong>
              <p>
                {b.second_kernel
                  ? "Confirmed by a second, independent kernel."
                  : "Trusted. A second, independent kernel has not checked this result yet."}
              </p>
            </div>
          </li>
        </ul>
      )}
      <div className="basis-defs">
        <h4>Library definitions the statements use</h4>
        {defs === null ? (
          <p className="muted small">
            Listed once the planted errors of this paper are revealed: a planted copy can use a
            definition the real statements do not.
          </p>
        ) : defs.length === 0 ? (
          <p className="muted small">None recorded.</p>
        ) : (
          <>
            <p className="muted small">
              The statements mean what these definitions mean. Every ticket lists the ones it uses,
              with their conventions, and its reviewers check the use. Whether a definition itself
              is right, that Mathlib's definition is the textbook one, is not reviewed yet (proposal
              C-27).
            </p>
            <table>
              <thead>
                <tr>
                  <th>Definition</th>
                  <th>From</th>
                  <th>Used by</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(shownDefs ?? []).map((g) => (
                  <tr key={g.name}>
                    <td>
                      <LeanName text={g.name} title={g.type} />
                      {g.note && <div className="muted small">{g.note}</div>}
                    </td>
                    <td>{g.origin === "library" ? "Mathlib" : "Lean core"}</td>
                    <td className="small">
                      {g.used_by.length === 1 ? (
                        <LeanName text={g.used_by[0]} />
                      ) : (
                        `${g.used_by.length} declarations`
                      )}
                    </td>
                    <td>
                      <Chip status={g.reviewed ? "checked" : "open"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {defs.length > FOLD && (
              <p>
                <button className="link small" onClick={() => setAll(!all)}>
                  {all ? "Show fewer" : `Show all ${defs.length}`}
                </button>
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
