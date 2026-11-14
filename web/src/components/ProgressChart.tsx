import { useEffect, useMemo, useRef, useState } from "react";

// Decided declarations over time, for one submission (proposal C-26).
// A single series: a 2px step line in the accent colour, a hairline grid, the
// value at the end of the line, a crosshair with a tooltip, and a table view.
// No legend: the title names the series.

type Point = { at: string; decided: number };

const H = 220;
const M = { top: 22, right: 92, bottom: 28, left: 40 };

function niceStep(max: number): number {
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(Math.max(raw, 1)));
  const n = raw / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag;
}

const day = (t: number) =>
  new Date(t).toLocaleDateString("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
const shortDay = (t: number) =>
  new Date(t).toLocaleDateString("en", { day: "numeric", month: "short" });

export function ProgressChart({ timeline, total }: { timeline: Point[]; total: number }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(320, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [asTable]);

  const pts = useMemo(
    () => timeline.map((p) => ({ t: new Date(p.at).getTime(), v: p.decided })),
    [timeline],
  );
  if (pts.length === 0) return null;

  const t0 = pts[0].t;
  const t1 = Math.max(pts[pts.length - 1].t, t0 + 86_400_000);
  const ymax = Math.max(total, 1);
  const iw = width - M.left - M.right;
  const ih = H - M.top - M.bottom;
  const x = (t: number) => M.left + ((t - t0) / (t1 - t0)) * iw;
  const y = (v: number) => M.top + ih - (v / ymax) * ih;
  const valueAt = (t: number) => {
    let v = pts[0].v;
    for (const p of pts) if (p.t <= t) v = p.v;
    return v;
  };

  const step = niceStep(ymax);
  const yticks: number[] = [];
  for (let v = 0; v < ymax; v += step) yticks.push(v);
  const xticks = Array.from({ length: 4 }, (_, i) => t0 + ((t1 - t0) * i) / 3).filter(
    (t, i, all) => i === 0 || shortDay(t) !== shortDay(all[i - 1]),
  );

  let d = `M${x(pts[0].t)},${y(pts[0].v)}`;
  for (const p of pts.slice(1)) d += `H${x(p.t)}V${y(p.v)}`;
  const last = pts[pts.length - 1];
  const changes = pts.filter((p, i) => i === 0 || p.v !== pts[i - 1].v);

  const hv = hover === null ? null : valueAt(hover);
  const summary = `Decided declarations over time: ${last.v} of ${total} on ${day(last.t)}.`;

  return (
    <div className="chart" ref={box}>
      {asTable ? (
        <table className="chart-table">
          <caption className="sr-only">{summary}</caption>
          <thead>
            <tr>
              <th>Date</th>
              <th>Decided declarations</th>
            </tr>
          </thead>
          <tbody>
            {changes.map((p, i) => (
              <tr key={i}>
                <td>{day(p.t)}</td>
                <td className="num">
                  {p.v} of {total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <>
          <svg
            width={width}
            height={H}
            role="img"
            aria-label={summary}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              const px = Math.min(Math.max(e.clientX - r.left, M.left), M.left + iw);
              setHover(t0 + ((px - M.left) / iw) * (t1 - t0));
            }}
            onPointerLeave={() => setHover(null)}
          >
            {yticks.map((v) => (
              <g key={v}>
                <line className="grid" x1={M.left} x2={M.left + iw} y1={y(v)} y2={y(v)} />
                <text className="tick" x={M.left - 8} y={y(v)} dy="0.32em" textAnchor="end">
                  {v}
                </text>
              </g>
            ))}
            <line className="goal" x1={M.left} x2={M.left + iw} y1={y(ymax)} y2={y(ymax)} />
            <text className="tick" x={M.left} y={y(ymax) - 7}>
              all {total} declarations
            </text>
            {xticks.map((t, i) => (
              <text
                key={t}
                className="tick"
                x={x(t)}
                y={H - 8}
                textAnchor={i === 0 ? "start" : i === xticks.length - 1 ? "end" : "middle"}
              >
                {shortDay(t)}
              </text>
            ))}
            <path className="series" d={d} />
            <circle className="series-dot" cx={x(last.t)} cy={y(last.v)} r={4} />
            <text className="end-label" x={x(last.t) + 10} y={y(last.v)} dy="0.32em">
              {last.v} decided
            </text>
            {hover !== null && hv !== null && (
              <g className="crosshair">
                <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={M.top + ih} />
                <circle cx={x(hover)} cy={y(hv)} r={4} />
              </g>
            )}
          </svg>
          {hover !== null && hv !== null && (
            <div
              className="chart-tip"
              style={{
                left: Math.min(x(hover) + 12, width - 190),
                top: Math.max(y(hv) - 52, 0),
              }}
            >
              <strong>{day(hover)}</strong>
              <span>
                {hv} of {total} declarations decided
              </span>
            </div>
          )}
        </>
      )}
      <p className="chart-foot">
        <button className="link small" onClick={() => setAsTable(!asTable)}>
          {asTable ? "Show as chart" : "Show as table"}
        </button>
      </p>
    </div>
  );
}
