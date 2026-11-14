import { useCallback, useEffect, useState } from "react";
import { api, type Post, type Thread, type ThreadSummary } from "../api";
import { Infoview } from "../components/Infoview";
import { Reference } from "../components/Reference";
import { QUESTION_LABELS } from "./LeaseView";

// Discussion after the decision (proposal C-25): one thread per declaration,
// opened once all its tickets are decided and the planted errors of its
// submission are revealed. Posts are anonymous unless the author shows the
// pseudonym; votes only sort and never enter trust or decisions.

export const threadHref = (sid: string, decl: string) =>
  `#/thread/${encodeURIComponent(sid)}/${encodeURIComponent(decl)}`;

const OUTCOMES: Record<string, string> = {
  accepted: "accepted",
  error: "error found",
};

function since(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en", {
    month: "short",
    year: "numeric",
  });
}

/** Up- and downvotes: they sort and never count towards trust or decisions. */
function Votes({
  score,
  mine,
  onVote,
  disabled,
  up,
  down,
}: {
  score: number;
  mine: number;
  onVote: (value: number) => void;
  disabled: string | null; // why voting is not possible, or null
  up: string;
  down: string;
}) {
  return (
    <div className="votes" aria-label="Votes">
      <button
        className={mine === 1 ? "vote on" : "vote"}
        disabled={disabled !== null}
        title={disabled ?? up}
        aria-pressed={mine === 1}
        onClick={() => onVote(mine === 1 ? 0 : 1)}
      >
        ▲
      </button>
      <span className="score">{score}</span>
      <button
        className={mine === -1 ? "vote on" : "vote"}
        disabled={disabled !== null}
        title={disabled ?? down}
        aria-pressed={mine === -1}
        onClick={() => onVote(mine === -1 ? 0 : -1)}
      >
        ▼
      </button>
    </div>
  );
}

const THREAD_UP = "Worth reading. Votes sort the discussions; they say nothing about the decision.";
const THREAD_DOWN =
  "Not worth reading. Votes sort the discussions; they say nothing about the decision.";

export function Discussions() {
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api.discussions().then(setThreads, (e) => setError((e as Error).message));
  }, []);
  useEffect(load, [load]);
  if (error) return <p className="error">{error}</p>;
  if (!threads) return <p className="muted">Loading…</p>;
  return (
    <section className="card">
      <h2>Discussions</h2>
      <p className="muted">
        Once a declaration is decided, everyone who reviewed it can share their verdict, and anyone
        can join the discussion. Threads open only after the decision, so that nobody's verdict is
        influenced. Votes sort the discussions and the posts: they say what is worth reading, never
        whether a decision is right, and they never count towards trust.
      </p>
      {threads.length === 0 ? (
        <p className="muted">No discussion is open yet: declarations are still under review.</p>
      ) : (
        <ul className="thread-list">
          {threads.map((t) => (
            <li key={`${t.submission_id}:${t.declaration}`}>
              <Votes
                score={t.score}
                mine={t.my_vote}
                disabled={null}
                up={THREAD_UP}
                down={THREAD_DOWN}
                onVote={(v) => api.voteThread(t.submission_id, t.declaration, v).then(load)}
              />
              <div>
                <a href={threadHref(t.submission_id, t.declaration)}>
                  <code>{t.declaration}</code>
                </a>{" "}
                <span className={`badge outcome-${t.outcome}`}>
                  {OUTCOMES[t.outcome] ?? t.outcome}
                </span>
                {t.can_share && <span className="badge share-hint">you can share your review</span>}
                <div className="muted small">
                  {t.paper} · {t.domain} · {t.posts} {t.posts === 1 ? "post" : "posts"}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PostCard({
  post,
  onChange,
  signedIn = true,
}: {
  post: Post;
  onChange: () => void;
  signedIn?: boolean;
}) {
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState("");
  const noVote = post.is_me ? "Your own post" : signedIn ? null : "Sign in to vote";
  if (post.hidden) {
    return (
      <article className="post hidden-post">
        <p className="muted small">Hidden by a maintainer: {post.hidden}</p>
      </article>
    );
  }
  return (
    <article className={post.kind === "review" ? "post review-post" : "post"}>
      <Votes
        score={post.score}
        mine={post.my_vote}
        disabled={noVote}
        up="Useful"
        down="Not useful"
        onVote={(v) => api.vote(post.post_id, v).then(onChange)}
      />
      <div className="post-body">
        <div className="post-head">
          <strong>{post.author}</strong>
          {post.is_me && <span className="muted small">(you)</span>}
          {post.maintainer && <span className="badge maintainer">Maintainer</span>}
          {post.reviewed_here && <span className="badge">reviewed this</span>}
          <span className="muted small">member since {since(post.member_since)}</span>
          {post.ai_used && <span className="muted small">· AI-assisted</span>}
        </div>
        {post.kind === "review" && (
          <p>
            <span className={`badge verdict-${post.verdict}`}>
              verdict: {post.verdict === "incorrect" ? "problem found" : "faithful"}
            </span>{" "}
            {(post.failed ?? []).map((f) => (
              <span key={f} className="badge warn">
                {QUESTION_LABELS[f] ?? f}
              </span>
            ))}
          </p>
        )}
        <p className="post-text">
          {post.kind === "review" ? post.reason || "(no justification)" : post.text}
        </p>
        {!post.is_me && signedIn && (
          <div className="post-actions">
            {post.reported_by_me ? (
              <span className="muted small">
                You reported this post.{" "}
                <button
                  className="link small"
                  title="Take the report back; maintainers will no longer see it"
                  onClick={() => api.withdrawReport(post.post_id).then(onChange)}
                >
                  Withdraw report
                </button>
              </span>
            ) : reporting ? (
              <span className="report">
                <input
                  placeholder="Why should a maintainer look at this?"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <button
                  className="secondary small"
                  disabled={!reason.trim()}
                  onClick={() =>
                    api.report(post.post_id, reason).then(() => {
                      setReporting(false);
                      setReason("");
                      onChange();
                    })
                  }
                >
                  Report
                </button>
                <button
                  className="link small"
                  onClick={() => {
                    setReporting(false);
                    setReason("");
                  }}
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button className="link small" onClick={() => setReporting(true)}>
                Report
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

export function ThreadView({ sid, decl }: { sid: string; decl: string }) {
  const [thread, setThread] = useState<Thread | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [named, setNamed] = useState(false);
  const [ai, setAi] = useState("");
  const [aiUsed, setAiUsed] = useState(false);
  const [reopen, setReopen] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    api.thread(sid, decl).then(
      (t) => {
        setThread(t);
        setNamed(t.me.named);
      },
      (e) => setError((e as Error).message),
    );
  }, [sid, decl]);
  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>, done?: string) {
    setMessage(null);
    try {
      await action();
      if (done) setMessage(done);
      load();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!thread) return <p className="muted">Loading…</p>;
  const me = thread.me;
  return (
    <div>
      <section className="card">
        <p className="small">
          <a href="#/discussions">← All discussions</a>
        </p>
        <div className="thread-head">
          <Votes
            score={thread.score}
            mine={thread.my_vote}
            disabled={null}
            up={THREAD_UP}
            down={THREAD_DOWN}
            onVote={(v) => api.voteThread(sid, decl, v).then(load)}
          />
          <h2>
            <code>{thread.declaration}</code>{" "}
            <span className={`badge outcome-${thread.outcome}`}>
              {OUTCOMES[thread.outcome] ?? thread.outcome}
            </span>
          </h2>
        </div>
        <p className="muted small">
          {thread.paper} · {thread.domain} · <a href={thread.repo_url}>{thread.repo_url}</a> @{" "}
          <code>{thread.commit.slice(0, 12)}</code>
        </p>
        <Reference
          view={thread.view}
          passage={thread.paper_passage}
          paperRef={null}
          leaseId=""
          contested={false}
          minChars={30}
          active={false}
        />
        <details className="lean-details">
          <summary>Lean statement</summary>
          <Infoview view={thread.view} />
        </details>
      </section>

      <section className="card">
        <h3>
          {thread.posts.length} {thread.posts.length === 1 ? "post" : "posts"}
        </h3>
        {thread.posts.map((p) => (
          <PostCard key={p.post_id} post={p} onChange={load} />
        ))}
        {thread.posts.length === 0 && <p className="muted">No posts yet.</p>}
      </section>

      <section className="card">
        <h3>Join the discussion</h3>
        <p className="muted small">
          {me.named
            ? "You show your pseudonym in this thread, for all your posts here."
            : `You appear as ${me.label ?? "a new letter (Reviewer A, B, …)"}. Showing your pseudonym applies to all your posts in this thread and links it to your reviews in the published audit log.`}
        </p>
        {me.can_share && (
          <div className="share-box">
            <p>
              You reviewed this declaration. Share your verdict and justification with the others?
            </p>
            <button
              className="secondary"
              onClick={() => run(() => api.share(sid, decl, named), "Your review is shared.")}
            >
              Share my review
            </button>
          </div>
        )}
        <label>
          Comment
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={named}
            disabled={me.named}
            onChange={(e) => setNamed(e.target.checked)}
          />
          Show my pseudonym in this thread
        </label>
        <label className="inline">
          <input type="checkbox" checked={aiUsed} onChange={(e) => setAiUsed(e.target.checked)} />I
          used an AI assistant for this post
        </label>
        {aiUsed && (
          <input placeholder="Which one?" value={ai} onChange={(e) => setAi(e.target.value)} />
        )}
        <p>
          <button
            disabled={!text.trim() || (aiUsed && !ai.trim())}
            onClick={() =>
              run(async () => {
                await api.post(sid, decl, text, named, aiUsed ? ai : null);
                setText("");
              })
            }
          >
            Post
          </button>
        </p>
        <div className="reopen">
          {thread.reopen_pending ? (
            <p className="muted small">
              A reopen request for this declaration is with the maintainers.
            </p>
          ) : reopen === null ? (
            <button className="link small" onClick={() => setReopen("")}>
              This decision looks wrong — ask the maintainers to reopen it
            </button>
          ) : (
            <>
              <label>
                What is wrong with the decision? (at least 30 characters)
                <textarea rows={3} value={reopen} onChange={(e) => setReopen(e.target.value)} />
              </label>
              <button
                className="secondary"
                disabled={reopen.trim().length < 30}
                onClick={() =>
                  run(async () => {
                    await api.requestReopen(sid, decl, reopen);
                    setReopen(null);
                  }, "Sent to the maintainers. Discussion never changes a decision by itself.")
                }
              >
                Request reopening
              </button>
            </>
          )}
        </div>
        {message && <p className="muted">{message}</p>}
      </section>
    </div>
  );
}
