import { useEffect, useRef } from "react";

/**
 * P4-11-01: клиентский PNG-экспорт графиков на мок-данных (без бэка).
 *
 * Данные захардкожены из `docs/mocks/analytics-overview.json` (P4-14-01,
 * сверены с `Overview` вживую в Dev-3).
 * TODO(P4, доработка): заменить MOCK_* на `GET /api/v1/analytics/overview`
 * через apiFetch — эндпоинт уже есть в merged-ветке (Dev-2), нужен только
 * P4_FILTER_PROVIDER на бэке для непустых фильтров; server-side PNG нужен
 * только для встраивания графиков в PDF-отчёт (P4-04-01).
 * Отложено: тулбар fullscreen/PDF, e2e-скриншоты.
 */

export type HealthBucket = { range: string; count: number };
export type ProgramStatus = { status: string; count: number };
export type TrendPoint = { date: string; avg_score: number };

// Мок из docs/mocks/analytics-overview.json (P4-14-01).
export const MOCK_HEALTH_DIST: HealthBucket[] = [
  { range: "0-20", count: 0 },
  { range: "21-40", count: 1 },
  { range: "41-60", count: 2 },
  { range: "61-80", count: 4 },
  { range: "81-100", count: 3 },
];

export const MOCK_PROGRAM_STATUSES: ProgramStatus[] = [
  { status: "planned", count: 5 },
  { status: "active", count: 12 },
  { status: "launched", count: 8 },
  { status: "archived", count: 2 },
];

/** RAG-пирог собирается из kpi analytics-overview.json. */
export const MOCK_RAG = [
  { label: "Красные", count: 3, color: "#dc2626" },
  { label: "Жёлтые", count: 4, color: "#eab308" },
  { label: "Зелёные", count: 3, color: "#16a34a" },
];

export const MOCK_TREND: TrendPoint[] = [
  { date: "2026-08-01", avg_score: 65 },
  { date: "2026-09-01", avg_score: 67 },
  { date: "2026-09-15", avg_score: 67 },
];

const PALETTE = ["#2563eb", "#7c3aed", "#0891b2", "#db2777", "#ea580c", "#16a34a"];

function todayStamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
}

/** Скачивание PNG из canvas (2x DPR уже заложен в отрисовку). */
export function exportCanvasAsPng(canvas: HTMLCanvasElement, slug: string): void {
  const link = document.createElement("a");
  link.href = canvas.toDataURL("image/png");
  link.download = `chart-${slug}-${todayStamp()}.png`;
  link.click();
}

function setupHiDpi(canvas: HTMLCanvasElement, cssW: number, cssH: number): CanvasRenderingContext2D | null {
  const dpr = 2; // фиксированный 2x для ретины (ТЗ: высокое качество)
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  canvas.style.width = `${cssW}px`;
  canvas.style.height = `${cssH}px`;
  const ctx = canvas.getContext("2d");
  if (ctx) ctx.scale(dpr, dpr);
  return ctx;
}

function drawBar(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const data = MOCK_HEALTH_DIST;
  const max = Math.max(1, ...data.map((d) => d.count));
  const padL = 28;
  const padB = 34;
  const cw = w - padL - 8;
  const ch = h - 12 - padB;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#64748b";
  ctx.font = "11px system-ui, sans-serif";
  data.forEach((d, i) => {
    const bw = cw / data.length;
    const bh = (d.count / max) * (ch - 20);
    const x = padL + i * bw + 8;
    const y = 12 + (ch - 20 - bh);
    ctx.fillStyle = PALETTE[i % PALETTE.length];
    ctx.fillRect(x, y, bw - 16, bh);
    ctx.fillStyle = "#0f172a";
    ctx.fillText(String(d.count), x + (bw - 16) / 2 - 3, y - 4);
    ctx.fillStyle = "#64748b";
    ctx.fillText(d.range, x, h - 12);
  });
}

function drawPieSlice(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  parts: { count: number; color: string }[],
  holeRatio: number,
): void {
  const total = parts.reduce((s, p) => s + p.count, 0) || 1;
  let angle = -Math.PI / 2;
  parts.forEach((p) => {
    const next = angle + (p.count / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, angle, next);
    ctx.closePath();
    ctx.fillStyle = p.color;
    ctx.fill();
    angle = next;
  });
  if (holeRatio > 0) {
    ctx.beginPath();
    ctx.arc(cx, cy, r * holeRatio, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
  }
}

function drawLegend(ctx: CanvasRenderingContext2D, items: { label: string; color: string }[], x: number, y: number): void {
  ctx.font = "11px system-ui, sans-serif";
  items.forEach((it, i) => {
    const yy = y + i * 18;
    ctx.fillStyle = it.color;
    ctx.fillRect(x, yy, 10, 10);
    ctx.fillStyle = "#0f172a";
    ctx.fillText(it.label, x + 14, yy + 9);
  });
}

function drawLine(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const data = MOCK_TREND;
  const padL = 32;
  const padB = 28;
  const cw = w - padL - 12;
  const ch = h - 12 - padB;
  const min = Math.min(...data.map((d) => d.avg_score)) - 2;
  const max = Math.max(...data.map((d) => d.avg_score)) + 2;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#e2e8f0";
  ctx.beginPath();
  ctx.moveTo(padL, 12);
  ctx.lineTo(padL, 12 + ch);
  ctx.lineTo(padL + cw, 12 + ch);
  ctx.stroke();
  ctx.strokeStyle = "#2563eb";
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((d, i) => {
    const x = padL + (i / Math.max(1, data.length - 1)) * cw;
    const y = 12 + ch - ((d.avg_score - min) / Math.max(1, max - min)) * ch;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.lineWidth = 1;
  ctx.fillStyle = "#0f172a";
  ctx.font = "11px system-ui, sans-serif";
  data.forEach((d, i) => {
    const x = padL + (i / Math.max(1, data.length - 1)) * cw;
    const y = 12 + ch - ((d.avg_score - min) / Math.max(1, max - min)) * ch;
    ctx.fillStyle = "#2563eb";
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#0f172a";
    ctx.fillText(String(d.avg_score), x - 6, y - 8);
    ctx.fillStyle = "#64748b";
    ctx.fillText(d.date.slice(5), x - 12, 12 + ch + 16);
  });
}

const W = 520;
const H = 300;

function ChartCard({
  slug,
  title,
  kind,
}: {
  slug: string;
  title: string;
  kind: "bar" | "pie" | "donut" | "line";
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = setupHiDpi(canvas, W, H);
    if (!ctx) return;
    if (kind === "bar") drawBar(ctx, W, H);
    else if (kind === "line") drawLine(ctx, W, H);
    else if (kind === "pie") {
      ctx.clearRect(0, 0, W, H);
      drawPieSlice(ctx, 150, 150, 110, MOCK_RAG, 0);
      drawLegend(
        ctx,
        MOCK_RAG.map((r) => ({ label: `${r.label} (${r.count})`, color: r.color })),
        300,
        90,
      );
    } else {
      ctx.clearRect(0, 0, W, H);
      drawPieSlice(
        ctx,
        150,
        150,
        110,
        MOCK_PROGRAM_STATUSES.map((s, i) => ({ count: s.count, color: PALETTE[i % PALETTE.length] })),
        0.55,
      );
      drawLegend(
        ctx,
        MOCK_PROGRAM_STATUSES.map((s, i) => ({
          label: `${s.status} (${s.count})`,
          color: PALETTE[i % PALETTE.length],
        })),
        300,
        80,
      );
    }
  }, [kind]);

  return (
    <div className="card chart-card">
      <div className="chart-head">
        <h3>{title}</h3>
        <button
          className="btn"
          aria-label={`Скачать ${title} в PNG`}
          onClick={() => ref.current && exportCanvasAsPng(ref.current, slug)}
        >
          📥 PNG
        </button>
      </div>
      <canvas ref={ref} role="img" aria-label={`${title} (мок-данные, canvas)`} />
      <p className="muted chart-note">Мок-данные · клик 📥 PNG сохраняет картинку 2x (без бэкенда).</p>
    </div>
  );
}

export function AnalyticsCharts() {
  return (
    <div className="charts-grid">
      <ChartCard slug="health-distribution" title="Health Score: распределение" kind="bar" />
      <ChartCard slug="rag-pie" title="Светофор вузов (RAG)" kind="pie" />
      <ChartCard slug="program-statuses" title="Статусы программ" kind="donut" />
      <ChartCard slug="health-trend" title="Динамика среднего score" kind="line" />
    </div>
  );
}
