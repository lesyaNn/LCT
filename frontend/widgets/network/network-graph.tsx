'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import {
  getNetworkGraph,
  networkGraphQueryKey,
  type NetworkGraphData,
  type NetworkNode,
  type NetworkNodeKind,
} from '@/shared/lib/network-repository';
import {
  adminUsersQueryKeys,
  listUserScopeOptions,
  scopeLabel,
  updateAdminUser,
  USERS_API_CAPABILITIES,
} from '@/shared/lib/users-repository';
import type { UserRole } from '@/shared/types/user';
import { PageIntro } from '@/shared/ui/page-intro';
import { PageSkeleton } from '@/shared/ui/page-skeleton';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { EmptyState } from '@/shared/ui/empty-state';
import { Button } from '@/shared/ui/rtk/button';
import { SearchField } from '@/shared/ui/rtk/filter-field';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import {
  autoLayout,
  createSimNodes,
  stepForces,
  type LayoutNodeInput,
  type SimEdge,
  type SimNode,
} from './graph-layout';
import styles from './network-graph.module.css';

const STORAGE_KEY = 'network-graph-positions-v1';
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3;
const LABEL_ZOOM_THRESHOLD = 0.5;
const MAX_LABEL_LENGTH = 26;

interface View {
  ox: number;
  oy: number;
  k: number;
}

interface Palette {
  user: string;
  university: string;
  edge: string;
  edgeActive: string;
  text: string;
}

function truncate(value: string, max = MAX_LABEL_LENGTH): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function loadPositions(): Map<string, { x: number; y: number }> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Map();
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) return new Map();
    const result = new Map<string, { x: number; y: number }>();
    for (const [id, point] of Object.entries(parsed)) {
      if (isRecord(point) && typeof point.x === 'number' && typeof point.y === 'number'
        && Number.isFinite(point.x) && Number.isFinite(point.y)) {
        result.set(id, { x: point.x, y: point.y });
      }
    }
    return result;
  } catch {
    return new Map();
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function pathRoundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2;
}

const clock = (): number => performance.now();

/** Lucide-style 24x24 stroke pictograms, drawn inside canvas nodes. */
const USER_SHOULDERS = 'M18 20a6 6 0 0 0-12 0';
const CAP_BOARD = 'M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z';
const CAP_TASSEL = 'M22 10v6';
const CAP_BAND = 'M6 12.5V16a6 3 0 0 0 12 0v-3.5';

function strokeGlyph(ctx: CanvasRenderingContext2D, sx: number, sy: number, r: number, color: string, paint: () => void): void {
  ctx.save();
  ctx.translate(sx, sy);
  const s = (r * 1.05) / 12;
  ctx.scale(s, s);
  ctx.translate(-12, -12);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.2;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  paint();
  ctx.restore();
}

/** user-round without the outer ring: the node disc itself is the round. */
function drawUserGlyph(ctx: CanvasRenderingContext2D, sx: number, sy: number, r: number, color: string): void {
  strokeGlyph(ctx, sx, sy, r, color, () => {
    ctx.beginPath();
    ctx.arc(12, 10, 4, 0, Math.PI * 2);
    ctx.stroke();
    ctx.stroke(new Path2D(USER_SHOULDERS));
  });
}

function drawCapGlyph(ctx: CanvasRenderingContext2D, sx: number, sy: number, r: number, color: string): void {
  strokeGlyph(ctx, sx, sy, r, color, () => {
    ctx.stroke(new Path2D(CAP_BOARD));
    ctx.stroke(new Path2D(CAP_TASSEL));
    ctx.stroke(new Path2D(CAP_BAND));
  });
}

function readPalette(): Palette {
  const fallback: Palette = {
    user: '#7700FF',
    university: '#FF4F12',
    edge: 'rgba(16, 24, 40, 0.22)',
    edgeActive: '#7700FF',
    text: 'rgba(16, 24, 40, 0.85)',
  };
  try {
    const css = getComputedStyle(document.documentElement);
    const pick = (name: string, fb: string): string => css.getPropertyValue(name).trim() || fb;
    return {
      ...fallback,
      user: pick('--rtk-brand-purple', fallback.user),
      university: pick('--rtk-brand-orange', fallback.university),
    };
  } catch {
    return fallback;
  }
}

export function NetworkGraph({ showIntro = true }: { showIntro?: boolean }) {
  const graphQuery = useQuery({
    queryKey: networkGraphQueryKey,
    queryFn: ({ signal }) => getNetworkGraph(signal),
    staleTime: 60_000,
  });

  return (
    <div className={styles.page}>
      {showIntro ? (
        <PageIntro
          title="Граф связей"
          description="Сотрудники CRM и вузы, которые они ведут. Связь определяется доступом пользователя к вузу. Наведите курсор на узел, чтобы увидеть его связи."
        />
      ) : null}
      {graphQuery.isPending ? <PageSkeleton cardCount={3} /> : null}
      {graphQuery.isError && !graphQuery.data ? (
        <RouteErrorState onRetry={() => void graphQuery.refetch()} />
      ) : null}
      {graphQuery.data && graphQuery.data.nodes.length === 0 ? (
        <EmptyState
          title="Нет данных для графа"
          description="В системе пока нет сотрудников с доступом к вузам."
          presentation="large"
        />
      ) : null}
      {graphQuery.data && graphQuery.data.nodes.length > 0 ? <NetworkCanvas data={graphQuery.data} /> : null}
    </div>
  );
}

function NetworkCanvas({ data }: { data: NetworkGraphData }) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const simRef = useRef<{ nodes: SimNode[]; edges: SimEdge[]; byId: Map<string, SimNode>; neighbors: Map<string, Set<string>> } | null>(null);
  const viewRef = useRef<View>({ ox: 0, oy: 0, k: 1 });
  const paletteRef = useRef<Palette | null>(null);
  const alphaRef = useRef(0);
  const rafRef = useRef(0);
  const runningRef = useRef(false);
  const pointersRef = useRef(new Map<number, { x: number; y: number }>());
  const dragRef = useRef<{
    mode: 'node' | 'pan' | 'pinch' | null;
    node: SimNode | null;
    moved: boolean;
    startX: number;
    startY: number;
    lastX: number;
    lastY: number;
    pinchDist: number;
  }>({ mode: null, node: null, moved: false, startX: 0, startY: 0, lastX: 0, lastY: 0, pinchDist: 0 });
  const posCacheRef = useRef(loadPositions());
  const viewAnimRef = useRef(0);
  const bornAtRef = useRef(0);
  const hoverRef = useRef<string | null>(null);
  const selectedRef = useRef<string | null>(null);
  const sizeRef = useRef({ w: 0, h: 0 });

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const mountedRef = useRef(false);

  const { user: currentUser } = useAuth();
  const canAssign = Boolean(
    currentUser && hasPermission(currentUser, 'admin.users') && USERS_API_CAPABILITIES.updateRoleAndScope,
  );

  const nodeById = useMemo(() => new Map<string, NetworkNode>(data.nodes.map((node) => [node.id, node])), [data]);

  const neighborInfo = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const edge of data.edges) {
      const userList = map.get(edge.userId) ?? [];
      userList.push(edge.universityId);
      map.set(edge.userId, userList);
      const uniList = map.get(edge.universityId) ?? [];
      uniList.push(edge.userId);
      map.set(edge.universityId, uniList);
    }
    for (const list of map.values()) {
      list.sort((left, right) => {
        const leftNode = nodeById.get(left);
        const rightNode = nodeById.get(right);
        return (leftNode?.label ?? '').localeCompare(rightNode?.label ?? '', 'ru');
      });
    }
    return map;
  }, [data, nodeById]);

  const suggestions = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('ru-RU');
    if (!query) return [];
    return data.nodes
      .filter((node) => node.label.toLocaleLowerCase('ru-RU').includes(query))
      .slice(0, 7);
  }, [data, search]);

  const selectedNode = selectedId ? nodeById.get(selectedId) ?? null : null;
  const selectedLinkedIds = selectedId ? neighborInfo.get(selectedId) ?? [] : [];

  const draw = useCallback((): void => {
    const canvas = canvasRef.current;
    const sim = simRef.current;
    const palette = paletteRef.current;
    if (!canvas || !sim || !palette) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const { w, h } = sizeRef.current;
    if (w === 0 || h === 0) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const view = viewRef.current;
    const focusId = hoverRef.current ?? selectedRef.current;
    const focusSet = new Set<string>();
    if (focusId) {
      focusSet.add(focusId);
      for (const id of sim.neighbors.get(focusId) ?? []) focusSet.add(id);
    }
    const dimmed = focusSet.size > 0;
    const toScreen = (x: number, y: number): [number, number] => [x * view.k + view.ox, y * view.k + view.oy];
    const now = clock();
    const appearProgress = Math.min(1, (now - bornAtRef.current) / 450);
    const appearScale = 0.3 + 0.7 * (1 - (1 - appearProgress) ** 3);

    for (const edge of sim.edges) {
      const [ax, ay] = toScreen(edge.a.x, edge.a.y);
      const [bx, by] = toScreen(edge.b.x, edge.b.y);
      const active = focusSet.size === 0 || (focusSet.has(edge.a.id) && focusSet.has(edge.b.id));
      ctx.globalAlpha = dimmed && !active ? 0.08 : 1;
      ctx.strokeStyle = active && dimmed ? palette.edgeActive : palette.edge;
      ctx.lineWidth = active && dimmed ? 2 : 1.4;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const fontSize = 11;
    ctx.font = `400 ${fontSize}px "Rostelecom Basis", Inter, Roboto, Arial, sans-serif`;

    for (const node of sim.nodes) {
      const [sx, sy] = toScreen(node.x, node.y);
      if (sx < -80 || sx > w + 80 || sy < -80 || sy > h + 80) continue;
      const highlighted = focusId === node.id;
      const inFocus = focusSet.size === 0 || focusSet.has(node.id);
      ctx.globalAlpha = dimmed && !inFocus ? 0.18 : 1;
      const r = node.r * view.k * appearScale * (highlighted ? 1.25 : 1);
      const color = node.kind === 'user' ? palette.user : palette.university;

      if (node.kind === 'user') {
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#ffffff';
        ctx.stroke();
        drawUserGlyph(ctx, sx, sy, r, '#ffffff');
      } else {
        drawCapGlyph(ctx, sx, sy, r * 1.35, color);
      }

      if (highlighted || selectedRef.current === node.id) {
        ctx.beginPath();
        ctx.arc(sx, sy, r + 5, 0, Math.PI * 2);
        ctx.lineWidth = 2;
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.7;
        ctx.stroke();
        ctx.globalAlpha = dimmed && !inFocus ? 0.18 : 1;
      }

      const showLabel = view.k >= LABEL_ZOOM_THRESHOLD || highlighted || selectedRef.current === node.id;
      if (showLabel && appearProgress > 0.4) {
        const label = truncate(node.label);
        const metrics = ctx.measureText(label);
        const pillW = metrics.width + 12;
        const pillH = fontSize + 8;
        const pillX = sx - pillW / 2;
        const pillY = sy + r + 4;
        pathRoundRect(ctx, pillX, pillY, pillW, pillH, 7);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
        ctx.fill();
        ctx.fillStyle = palette.text;
        ctx.fillText(label, sx, pillY + 4);
      }
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }, []);

  const stopLoop = useCallback((): void => {
    runningRef.current = false;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = 0;
  }, []);

  const tick = (): void => {
    const sim = simRef.current;
    if (!sim) {
      stopLoop();
      return;
    }
    const alpha = alphaRef.current;
    if (alpha <= 0.008 && dragRef.current.mode !== 'node') {
      alphaRef.current = 0;
      for (const node of sim.nodes) posCacheRef.current.set(node.id, { x: node.x, y: node.y });
      persistPositions();
      draw();
      stopLoop();
      return;
    }
    const { nodes, edges } = sim;
    const maxDisp = stepForces(nodes, edges, alpha);

    alphaRef.current = alpha * 0.988;
    if (maxDisp < 0.04 && alpha < 0.15) alphaRef.current = 0;
    draw();
    rafRef.current = requestAnimationFrame(tick);
  };

  const kick = (alpha: number): void => {
    alphaRef.current = Math.max(alphaRef.current, alpha);
    if (!runningRef.current) {
      runningRef.current = true;
      rafRef.current = requestAnimationFrame(tick);
    }
  };

  function persistPositions(): void {
    try {
      const plain: Record<string, { x: number; y: number }> = {};
      for (const [id, point] of posCacheRef.current) plain[id] = point;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(plain));
    } catch {
      // persistent layout is best-effort; in-memory positions keep working
    }
  }

  const cancelViewAnim = useCallback((): void => {
    if (viewAnimRef.current) cancelAnimationFrame(viewAnimRef.current);
    viewAnimRef.current = 0;
  }, []);

  const animateViewTo = useCallback((target: View, duration = 280): void => {
    cancelViewAnim();
    const from = { ...viewRef.current };
    const start = clock();
    const step = (now: number): void => {
      const t = Math.min(1, (now - start) / duration);
      const e = easeInOut(t);
      viewRef.current = {
        ox: from.ox + (target.ox - from.ox) * e,
        oy: from.oy + (target.oy - from.oy) * e,
        k: from.k + (target.k - from.k) * e,
      };
      draw();
      if (t < 1) {
        viewAnimRef.current = requestAnimationFrame(step);
      } else {
        viewAnimRef.current = 0;
      }
    };
    viewAnimRef.current = requestAnimationFrame(step);
  }, [cancelViewAnim, draw]);

  const fitView = useCallback((animated = true): void => {
    const sim = simRef.current;
    const { w, h } = sizeRef.current;
    if (!sim || sim.nodes.length === 0 || w === 0) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const node of sim.nodes) {
      minX = Math.min(minX, node.x);
      minY = Math.min(minY, node.y);
      maxX = Math.max(maxX, node.x);
      maxY = Math.max(maxY, node.y);
    }
    const bw = Math.max(50, maxX - minX);
    const bh = Math.max(50, maxY - minY);
    const k = Math.max(MIN_ZOOM, Math.min((w - 120) / bw, (h - 120) / bh, 1.4));
    const target: View = {
      k,
      ox: w / 2 - ((minX + maxX) / 2) * k,
      oy: h / 2 - ((minY + maxY) / 2) * k,
    };
    if (animated) animateViewTo(target);
    else {
      cancelViewAnim();
      viewRef.current = target;
      draw();
    }
  }, [animateViewTo, cancelViewAnim, draw]);

  const focusNode = useCallback((id: string): void => {
    const sim = simRef.current;
    const { w, h } = sizeRef.current;
    const node = sim?.byId.get(id);
    if (!node || w === 0) return;
    const k = Math.max(viewRef.current.k, 1.1);
    animateViewTo({ k, ox: w / 2 - node.x * k, oy: h / 2 - node.y * k });
  }, [animateViewTo]);

  const zoomAt = useCallback((cx: number, cy: number, factor: number): void => {
    cancelViewAnim();
    const view = viewRef.current;
    const k = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, view.k * factor));
    const scale = k / view.k;
    viewRef.current = { k, ox: cx - (cx - view.ox) * scale, oy: cy - (cy - view.oy) * scale };
    draw();
  }, [cancelViewAnim, draw]);

  const selectNode = useCallback((id: string | null): void => {
    selectedRef.current = id;
    setSelectedId(id);
  }, []);

  // Keep imperative draw loop in sync with React state.
  useEffect(() => {
    hoverRef.current = hoveredId;
    draw();
  }, [draw, hoveredId]);

  useEffect(() => {
    selectedRef.current = selectedId;
    draw();
  }, [draw, selectedId]);

  // Canvas setup: sizing, simulation, input handlers.
  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;

    paletteRef.current = readPalette();
    bornAtRef.current = clock();

    const layoutInputs: LayoutNodeInput[] = data.nodes.map((node) => ({
      id: node.id,
      kind: node.kind,
      label: node.label,
      sub: node.kind === 'user' ? node.roleLabel : node.city,
      degree: node.degree,
    }));
    const layoutLinks = data.edges.map((edge) => [edge.userId, edge.universityId] as const);

    // Incremental update: carry live coordinates over so existing nodes stay
    // put; only brand-new ids fall back to cache / pre-layout.
    const seed = new Map(posCacheRef.current);
    if (mountedRef.current) {
      for (const node of simRef.current?.nodes ?? []) seed.set(node.id, { x: node.x, y: node.y });
    } else if (layoutInputs.some((node) => !seed.has(node.id))) {
      // First paint: multi-stage auto-layout beforehand — the user sees an
      // arranged graph, not animated chaos.
      const auto = autoLayout(layoutInputs, layoutLinks);
      for (const [id, point] of auto.positions) {
        if (!seed.has(id)) seed.set(id, point);
      }
    }
    const nodes: SimNode[] = createSimNodes(layoutInputs, seed);
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const edges: SimEdge[] = [];
    const neighbors = new Map<string, Set<string>>();
    for (const edge of data.edges) {
      const a = byId.get(edge.userId);
      const b = byId.get(edge.universityId);
      if (!a || !b) continue;
      edges.push({ id: edge.id, a, b });
      if (!neighbors.has(a.id)) neighbors.set(a.id, new Set());
      if (!neighbors.has(b.id)) neighbors.set(b.id, new Set());
      neighbors.get(a.id)?.add(b.id);
      neighbors.get(b.id)?.add(a.id);
    }
    simRef.current = { nodes, edges, byId, neighbors };

    const resize = (): void => {
      const rect = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      sizeRef.current = { w: rect.width, h: rect.height };
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      draw();
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);

    if (!mountedRef.current) {
      fitView(false);
      // Positions already come from auto-layout: only micro-settle, otherwise
      // the optimized geometry would be thrown away by a full re-animation.
      kick(0.25);
      mountedRef.current = true;
    } else {
      // Data refresh (e.g. a new link): gentle local settle, no re-centring.
      kick(0.25);
    }

    const toLocal = (clientX: number, clientY: number): [number, number] => {
      const rect = canvas.getBoundingClientRect();
      return [clientX - rect.left, clientY - rect.top];
    };
    const toWorld = (sx: number, sy: number): [number, number] => {
      const view = viewRef.current;
      return [(sx - view.ox) / view.k, (sy - view.oy) / view.k];
    };
    const hitTest = (sx: number, sy: number): SimNode | null => {
      const sim = simRef.current;
      if (!sim) return null;
      const view = viewRef.current;
      let best: SimNode | null = null;
      let bestDist = Infinity;
      for (const node of sim.nodes) {
        const nx = node.x * view.k + view.ox;
        const ny = node.y * view.k + view.oy;
        const dist = Math.hypot(nx - sx, ny - sy);
        const hitR = node.r * view.k + 10;
        if (dist <= hitR && dist < bestDist) {
          best = node;
          bestDist = dist;
        }
      }
      return best;
    };

    const onPointerDown = (event: PointerEvent): void => {
      canvas.focus({ preventScroll: true });
      canvas.setPointerCapture(event.pointerId);
      const [sx, sy] = toLocal(event.clientX, event.clientY);
      pointersRef.current.set(event.pointerId, { x: sx, y: sy });
      cancelViewAnim();
      if (pointersRef.current.size === 2) {
        const points = [...pointersRef.current.values()];
        dragRef.current = {
          mode: 'pinch', node: null, moved: true,
          startX: 0, startY: 0, lastX: 0, lastY: 0,
          pinchDist: Math.max(1, Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)),
        };
        return;
      }
      const node = hitTest(sx, sy);
      if (node) {
        dragRef.current = { mode: 'node', node, moved: false, startX: sx, startY: sy, lastX: sx, lastY: sy, pinchDist: 0 };
      } else {
        dragRef.current = { mode: 'pan', node: null, moved: false, startX: sx, startY: sy, lastX: sx, lastY: sy, pinchDist: 0 };
      }
    };

    const onPointerMove = (event: PointerEvent): void => {
      const [sx, sy] = toLocal(event.clientX, event.clientY);
      const prev = pointersRef.current.get(event.pointerId);
      pointersRef.current.set(event.pointerId, { x: sx, y: sy });
      const drag = dragRef.current;

      if (drag.mode === 'pinch' && pointersRef.current.size >= 2) {
        const points = [...pointersRef.current.values()];
        const dist = Math.max(1, Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y));
        const mid: [number, number] = [(points[0].x + points[1].x) / 2, (points[0].y + points[1].y) / 2];
        const view = viewRef.current;
        const k = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, view.k * (dist / drag.pinchDist)));
        const scale = k / view.k;
        viewRef.current = { k, ox: mid[0] - (mid[0] - view.ox) * scale, oy: mid[1] - (mid[1] - view.oy) * scale };
        drag.pinchDist = dist;
        draw();
        return;
      }

      if (!prev || event.pointerId !== [...pointersRef.current.keys()][0]) {
        if (drag.mode === null && event.pointerType === 'mouse' && event.buttons === 0) {
          setHoveredId(hitTest(sx, sy)?.id ?? null);
        }
        return;
      }

      if (drag.mode === 'node' && drag.node) {
        const [wx, wy] = toWorld(sx, sy);
        if (Math.hypot(sx - drag.startX, sy - drag.startY) > 4) drag.moved = true;
        drag.node.fx = wx;
        drag.node.fy = wy;
        kick(0.35);
        return;
      }

      if (drag.mode === 'pan') {
        const dx = sx - drag.lastX;
        const dy = sy - drag.lastY;
        if (Math.hypot(sx - drag.startX, sy - drag.startY) > 4) drag.moved = true;
        drag.lastX = sx;
        drag.lastY = sy;
        const view = viewRef.current;
        viewRef.current = { ...view, ox: view.ox + dx, oy: view.oy + dy };
        draw();
        return;
      }

      if (drag.mode === null && event.pointerType === 'mouse' && event.buttons === 0) {
        setHoveredId(hitTest(sx, sy)?.id ?? null);
      }
    };

    const endPointer = (event: PointerEvent): void => {
      pointersRef.current.delete(event.pointerId);
      const drag = dragRef.current;
      if (drag.mode === 'node' && drag.node) {
        const node = drag.node;
        node.fx = null;
        node.fy = null;
        posCacheRef.current.set(node.id, { x: node.x, y: node.y });
        persistPositions();
        if (!drag.moved) selectNode(node.id);
        else kick(0.2);
      } else if (drag.mode === 'pan' && !drag.moved) {
        selectNode(null);
      }
      if (pointersRef.current.size === 0) {
        dragRef.current = { mode: null, node: null, moved: false, startX: 0, startY: 0, lastX: 0, lastY: 0, pinchDist: 0 };
      } else if (pointersRef.current.size === 1) {
        dragRef.current = { mode: null, node: null, moved: false, startX: 0, startY: 0, lastX: 0, lastY: 0, pinchDist: 0 };
      }
    };

    const onWheel = (event: WheelEvent): void => {
      event.preventDefault();
      const [sx, sy] = toLocal(event.clientX, event.clientY);
      const factor = Math.exp(-event.deltaY * (event.ctrlKey ? 0.01 : 0.0015));
      zoomAt(sx, sy, factor);
    };

    const onDoubleClick = (event: MouseEvent): void => {
      const [sx, sy] = toLocal(event.clientX, event.clientY);
      if (!hitTest(sx, sy)) fitView();
    };

    const onKeyDown = (event: KeyboardEvent): void => {
      const view = viewRef.current;
      const step = 40;
      if (event.key === 'Escape') {
        selectNode(null);
        setSearch('');
      } else if (event.key === '+' || event.key === '=') {
        zoomAt(sizeRef.current.w / 2, sizeRef.current.h / 2, 1.2);
      } else if (event.key === '-') {
        zoomAt(sizeRef.current.w / 2, sizeRef.current.h / 2, 1 / 1.2);
      } else if (event.key === '0') {
        fitView();
      } else if (event.key.startsWith('Arrow')) {
        cancelViewAnim();
        const dx = event.key === 'ArrowLeft' ? step : event.key === 'ArrowRight' ? -step : 0;
        const dy = event.key === 'ArrowUp' ? step : event.key === 'ArrowDown' ? -step : 0;
        viewRef.current = { ...view, ox: view.ox + dx, oy: view.oy + dy };
        draw();
        event.preventDefault();
      }
    };

    const onLeave = (): void => setHoveredId(null);

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', endPointer);
    canvas.addEventListener('pointercancel', endPointer);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('dblclick', onDoubleClick);
    canvas.addEventListener('keydown', onKeyDown);
    canvas.addEventListener('pointerleave', onLeave);

    return () => {
      observer.disconnect();
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', endPointer);
      canvas.removeEventListener('pointercancel', endPointer);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('dblclick', onDoubleClick);
      canvas.removeEventListener('keydown', onKeyDown);
      canvas.removeEventListener('pointerleave', onLeave);
      cancelViewAnim();
      stopLoop();
      for (const node of simRef.current?.nodes ?? []) posCacheRef.current.set(node.id, { x: node.x, y: node.y });
      persistPositions();
    };
    // Imperative canvas simulation: helpers intentionally stay referentially
    // unstable so the effect below only re-runs when graph data changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const handleSuggestionSelect = (id: string): void => {
    selectNode(id);
    focusNode(id);
  };

  const handleReset = (): void => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    posCacheRef.current = new Map();
    const sim = simRef.current;
    if (!sim) return;
    const resetInputs: LayoutNodeInput[] = sim.nodes.map((node) => ({
      id: node.id,
      kind: node.kind,
      label: node.label,
      sub: node.sub,
      degree: node.degree,
    }));
    const resetLinks = sim.edges.map((edge) => [edge.a.id, edge.b.id] as const);
    const fresh = autoLayout(resetInputs, resetLinks);
    for (const node of sim.nodes) {
      const point = fresh.positions.get(node.id);
      if (!point) continue;
      node.x = point.x;
      node.y = point.y;
      node.vx = 0;
      node.vy = 0;
    }
    bornAtRef.current = clock();
    fitView(false);
    kick(0.3);
  };

  const kindLabel = (kind: NetworkNodeKind): string => (kind === 'user' ? 'Сотрудник CRM' : 'Вуз');

  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.searchBlock}>
          <SearchField
            label="Поиск узла"
            value={search}
            onChange={setSearch}
            placeholder="Имя сотрудника или название вуза"
          />
          {suggestions.length > 0 ? (
            <ul className={styles.suggestions} role="listbox" aria-label="Найденные узлы">
              {suggestions.map((node) => (
                <li key={node.id} role="option" aria-selected={selectedId === node.id}>
                  <button
                    type="button"
                    className={styles.suggestionItem}
                    onClick={() => handleSuggestionSelect(node.id)}
                  >
                    <span className={`${styles.suggestionKind} ${node.kind === 'user' ? styles.suggestionKindUser : styles.suggestionKindUniversity}`}>
                      {kindLabel(node.kind)}
                    </span>
                    <span className={styles.suggestionLabel}>{node.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className={styles.actions}>
          <Button type="button" size="s" onClick={() => fitView()} aria-label="Центрировать граф">
            Центрировать
          </Button>
          <Button
            type="button"
            size="s"
            onClick={() => zoomAt(sizeRef.current.w / 2, sizeRef.current.h / 2, 1.25)}
            aria-label="Приблизить граф"
          >
            +
          </Button>
          <Button
            type="button"
            size="s"
            onClick={() => zoomAt(sizeRef.current.w / 2, sizeRef.current.h / 2, 0.8)}
            aria-label="Отдалить граф"
          >
            −
          </Button>
          <Button type="button" size="s" onClick={handleReset} aria-label="Сбросить расположение узлов">
            Сбросить вид
          </Button>
        </div>
      </div>

      <div className={styles.stats} aria-live="polite">
        <span className={styles.chip}>Сотрудники: <strong>{data.usersCount}</strong></span>
        <span className={styles.chip}>Вузы: <strong>{data.universitiesCount}</strong></span>
        <span className={styles.chip}>Связи: <strong>{data.linksCount}</strong></span>
        {data.scope === 'own' ? <span className={styles.chip}>Показаны только ваши вузы</span> : null}
        {data.isolatedCount > 0 ? <span className={styles.chip}>Без связей: <strong>{data.isolatedCount}</strong></span> : null}
      </div>

      <div className={styles.stage} ref={wrapRef}>
        <canvas
          ref={canvasRef}
          className={styles.canvas}
          tabIndex={0}
          role="img"
          aria-label={`Граф связей: ${data.usersCount} сотрудников, ${data.universitiesCount} вузов, ${data.linksCount} связей. Стрелки двигают граф, плюс и минус меняют масштаб, ноль центрирует.`}
        />
        <p className={styles.hint}>Колесо мыши — масштаб · перетаскивание — перемещение · двойной клик — центрировать</p>
        <div className={styles.legend} aria-hidden="true">
          <span className={styles.legendItem}>
            <svg className={`${styles.legendIcon} ${styles.legendIconUser}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 20a6 6 0 0 0-12 0" />
              <circle cx="12" cy="10" r="4" />
              <circle cx="12" cy="12" r="10" />
            </svg>
            Сотрудники CRM
          </span>
          <span className={styles.legendItem}>
            <svg className={`${styles.legendIcon} ${styles.legendIconUniversity}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z" />
              <path d="M22 10v6" />
              <path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5" />
            </svg>
            Вузы
          </span>
          <span className={styles.legendItem}><span className={styles.line} />Ведёт вуз</span>
        </div>

        {selectedNode ? (
          <aside className={styles.panel} aria-label="Информация об узле">
            <div className={styles.panelHeader}>
              <span className={`${styles.panelKind} ${selectedNode.kind === 'user' ? styles.panelKindUser : styles.panelKindUniversity}`}>
                {kindLabel(selectedNode.kind)}
              </span>
              <h2 className={styles.panelTitle}>{selectedNode.label}</h2>
              <button type="button" className={styles.panelClose} onClick={() => selectNode(null)} aria-label="Закрыть информацию об узле">
                ×
              </button>
            </div>
            <p className={styles.panelMeta}>
              {selectedNode.kind === 'user' ? (
                <>
                  <span>{selectedNode.roleLabel}</span>
                  {selectedNode.username ? <span>@{selectedNode.username}</span> : null}
                  {selectedNode.email ? <span>{selectedNode.email}</span> : null}
                </>
              ) : (
                <span>{selectedNode.city}</span>
              )}
              {selectedNode.kind === 'user' && selectedNode.allAccess ? (
                <span>Доступ ко всем вузам</span>
              ) : (
                <span>Связей: {selectedNode.degree}</span>
              )}
            </p>
            {(neighborInfo.get(selectedNode.id)?.length ?? 0) > 0 ? (
              <>
                <h3 className={styles.panelSubtitle}>
                  {selectedNode.kind === 'user' ? 'Ведёт вузы' : 'Сотрудники CRM'}
                </h3>
                <ul className={styles.neighborList}>
                  {(neighborInfo.get(selectedNode.id) ?? []).map((neighborId) => {
                    const neighborNode = nodeById.get(neighborId);
                    if (!neighborNode) return null;
                    const showUnlink = selectedNode.kind === 'user'
                      && neighborNode.kind === 'university'
                      && !selectedNode.allAccess
                      && canAssign;
                    return (
                      <li key={neighborId} className={showUnlink ? styles.neighborRow : undefined}>
                        <button
                          type="button"
                          className={styles.neighborButton}
                          onClick={() => handleSuggestionSelect(neighborId)}
                        >
                          <span className={`${styles.neighborDot} ${neighborNode.kind === 'user' ? styles.neighborDotUser : styles.neighborDotUniversity}`} />
                          <span className={styles.neighborName}>{neighborNode.label}</span>
                        </button>
                        {showUnlink ? (
                          <UnlinkUniversityButton
                            key={`${selectedNode.id}-${neighborId}`}
                            userId={selectedNode.id}
                            userName={selectedNode.label}
                            role={selectedNode.role}
                            linkedIds={selectedLinkedIds}
                            universityId={neighborId}
                            universityName={neighborNode.label}
                          />
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </>
            ) : (
              <p className={styles.panelMeta}>Нет связей с другими узлами.</p>
            )}
            {selectedNode.kind === 'university' ? (
              <Link className={styles.panelLink} href={`/universities/${selectedNode.id}`}>
                Открыть паспорт вуза →
              </Link>
            ) : null}
            {selectedNode.kind === 'user' && !selectedNode.allAccess && canAssign ? (
              <AssignUniversityBox
                key={selectedNode.id}
                userId={selectedNode.id}
                userName={selectedNode.label}
                role={selectedNode.role}
                linkedIds={selectedLinkedIds}
              />
            ) : null}
          </aside>
        ) : null}
      </div>
    </>
  );
}

function AssignUniversityBox({ userId, userName, role, linkedIds }: {
  userId: string;
  userName: string;
  role: UserRole;
  linkedIds: string[];
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [choice, setChoice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);

  const scopeOptionsQuery = useQuery({
    queryKey: queryKeys.users.scopeOptions,
    queryFn: listUserScopeOptions,
    staleTime: 5 * 60_000,
    enabled: open,
  });
  const scopeOptions = scopeOptionsQuery.data ?? [];

  const assignMutation = useMutation({
    mutationFn: (universityIds: string[]) =>
      updateAdminUser(userId, { role, scope: { kind: 'universities', universityIds } }),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: networkGraphQueryKey });
      void queryClient.invalidateQueries({ queryKey: queryKeys.universities.all });
      setOpen(false);
      setChoice(null);
      setError(null);
      setToast({ intent: 'success', title: 'Вуз назначен', message: `${updated.name}: ${scopeLabel(updated.scope)}` });
    },
    onError: (cause) => {
      setError(normalizeApiError(cause, { fallbackMessage: 'Не удалось назначить вуз.' }).message);
    },
  });

  const candidates = scopeOptions.filter((option) => {
    if (linkedIds.includes(option.id)) return false;
    const query = filter.trim().toLocaleLowerCase('ru-RU');
    return !query || option.name.toLocaleLowerCase('ru-RU').includes(query);
  });

  const confirm = (): void => {
    if (!choice) return;
    if (linkedIds.includes(choice)) {
      setError('Этот вуз уже назначен пользователю.');
      return;
    }
    setError(null);
    assignMutation.mutate([...linkedIds, choice]);
  };

  return (
    <div className={styles.assignBox}>
      {open ? (
        <>
          <h3 className={styles.panelSubtitle}>Назначить вуз — {userName}</h3>
          {scopeOptionsQuery.isPending ? <p className={styles.panelMeta}>Загрузка каталога вузов…</p> : null}
          {scopeOptionsQuery.isError ? (
            <p className={styles.formError} role="alert">
              Не удалось загрузить каталог вузов.{' '}
              <button type="button" className={styles.inlineRetry} onClick={() => void scopeOptionsQuery.refetch()}>
                Повторить
              </button>
            </p>
          ) : null}
          {scopeOptionsQuery.data ? (
            <>
              <SearchField
                label="Поиск вуза"
                value={filter}
                onChange={(value) => { setFilter(value); setChoice(null); }}
                placeholder="Название вуза"
              />
              {candidates.length > 0 ? (
                <ul className={styles.assignList} aria-label="Доступные вузы">
                  {candidates.slice(0, 8).map((option) => (
                    <li key={option.id}>
                      <button
                        type="button"
                        className={`${styles.assignOption} ${choice === option.id ? styles.assignOptionSelected : ''}`}
                        aria-pressed={choice === option.id}
                        onClick={() => { setChoice(option.id); setError(null); }}
                      >
                        {option.name}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className={styles.panelMeta}>
                  {scopeOptions.length > linkedIds.length
                    ? 'Ничего не найдено — уточните запрос.'
                    : 'Все вузы из каталога уже назначены этому пользователю.'}
                </p>
              )}
            </>
          ) : null}
          {error ? <p className={styles.formError} role="alert">{error}</p> : null}
          <div className={styles.assignActions}>
            <Button variant="ghost" size="s" type="button" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="primary"
              size="s"
              type="button"
              loading={assignMutation.isPending}
              disabled={!choice || assignMutation.isPending}
              onClick={confirm}
            >
              Подтвердить
            </Button>
          </div>
        </>
      ) : (
        <Button variant="primary" size="s" type="button" onClick={() => { setError(null); setOpen(true); }}>
          Назначить вуз
        </Button>
      )}
      {toast ? <Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /> : null}
    </div>
  );
}

function UnlinkUniversityButton({ userId, userName, role, linkedIds, universityId, universityName }: {
  userId: string;
  userName: string;
  role: UserRole;
  linkedIds: string[];
  universityId: string;
  universityName: string;
}) {
  const queryClient = useQueryClient();
  const [armed, setArmed] = useState(false);
  const [failed, setFailed] = useState(false);
  const [toast, setToast] = useState<{ intent: ToastIntent; title: string; message?: string } | null>(null);

  const unlinkMutation = useMutation({
    mutationFn: (universityIds: string[]) =>
      updateAdminUser(userId, { role, scope: { kind: 'universities', universityIds } }),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: adminUsersQueryKeys.all });
      void queryClient.invalidateQueries({ queryKey: networkGraphQueryKey });
      void queryClient.invalidateQueries({ queryKey: queryKeys.universities.all });
      setArmed(false);
      setFailed(false);
      setToast({ intent: 'success', title: 'Доступ отозван', message: `${universityName} — ${updated.name}: ${scopeLabel(updated.scope)}` });
    },
    onError: (cause) => {
      setFailed(true);
      setToast({
        intent: 'error',
        title: 'Не удалось снять вуз',
        message: normalizeApiError(cause, { fallbackMessage: 'Попробуйте ещё раз.' }).message,
      });
    },
  });

  const confirm = (): void => {
    setFailed(false);
    unlinkMutation.mutate(linkedIds.filter((id) => id !== universityId));
  };

  if (armed) {
    return (
      <span className={styles.unlinkConfirm}>
        <span className={styles.unlinkQuestion}>Снять «{universityName}»?</span>
        <button
          type="button"
          className={styles.unlinkYes}
          disabled={unlinkMutation.isPending}
          onClick={confirm}
        >
          {unlinkMutation.isPending ? '…' : 'Да'}
        </button>
        <button
          type="button"
          className={styles.unlinkNo}
          disabled={unlinkMutation.isPending}
          onClick={() => { setArmed(false); setFailed(false); }}
        >
          Нет
        </button>
        {failed ? (
          <button type="button" className={styles.inlineRetry} onClick={confirm}>
            Повторить
          </button>
        ) : null}
        {toast ? <Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /> : null}
      </span>
    );
  }

  return (
    <>
      <button
        type="button"
        className={styles.unlinkButton}
        aria-label={`Снять вуз ${universityName} с пользователя ${userName}`}
        title={`Снять с вуза: ${universityName}`}
        onClick={() => setArmed(true)}
      >
        ×
      </button>
      {toast ? <Toast intent={toast.intent} title={toast.title} message={toast.message} onClose={() => setToast(null)} /> : null}
    </>
  );
}
