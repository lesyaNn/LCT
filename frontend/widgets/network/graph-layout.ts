import type { NetworkNodeKind } from '@/shared/lib/network-repository';

/**
 * Framework-free force-directed layout for the user↔university graph.
 * Kept DOM/React-independent so the exact shipped step function can run
 * headless (e.g. layout quality checks in Node).
 */

export interface SimNode {
  id: string;
  kind: NetworkNodeKind;
  label: string;
  sub: string;
  degree: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number | null;
  fy: number | null;
  r: number;
  /** Collision radius: glyph plus a reserve for the caption below. */
  cr: number;
  /** Repulsion weight: hubs push harder so they don't collect tight groups. */
  chg: number;
}

export interface SimEdge {
  id: string;
  a: SimNode;
  b: SimNode;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

const REPULSION = 9500;
const REPULSION_CUTOFF = 460;
const MIN_D2 = 1600;
const SPRING_BASE = 105;
const SPRING_DEGREE = 15;
const SPRING_STIFFNESS = 0.018;
const MIDPOINT_RADIUS = 80;
const MIDPOINT_STRENGTH = 4;
const GRAVITY = 0.005;
const DAMPING = 0.86;
const MAX_STEP = 9;

/**
 * Uniform disc filling: nodes start evenly spread (largest degree first,
 * towards the centre) instead of collapsing inward from a single ring.
 */
export function initialPosition(index: number): { x: number; y: number } {
  const radius = 46 * Math.sqrt(index + 0.5);
  const angle = index * GOLDEN_ANGLE;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export interface LayoutNodeInput {
  id: string;
  kind: NetworkNodeKind;
  label: string;
  sub: string;
  degree: number;
}

export function createSimNodes(
  inputs: readonly LayoutNodeInput[],
  cached: ReadonlyMap<string, { x: number; y: number }>,
): SimNode[] {
  const ordered = [...inputs].sort((left, right) => right.degree - left.degree);
  return ordered.map((node, index) => {
    const cachedPoint = cached.get(node.id);
    const start = initialPosition(index);
    const r = (node.kind === 'user' ? 7 : 8) + Math.min(node.degree, 10) * 0.9;
    return {
      id: node.id,
      kind: node.kind,
      label: node.label,
      sub: node.sub,
      degree: node.degree,
      x: cachedPoint?.x ?? start.x,
      y: cachedPoint?.y ?? start.y,
      vx: 0,
      vy: 0,
      fx: null,
      fy: null,
      r,
      cr: r + 12,
      chg: 1 + 0.25 * Math.min(node.degree, 12),
    };
  });
}

/**
 * One force-directed step. Mutates node positions/velocities in place,
 * returns the largest single-node displacement (stabilisation signal).
 */export function stepForces(nodes: SimNode[], edges: SimEdge[], alpha: number): number {
  // Long-range charge: hubs repel harder so they cannot grow tight packs.
  for (let i = 0; i < nodes.length; i += 1) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j += 1) {
      const b = nodes[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const d2 = Math.max(MIN_D2, dx * dx + dy * dy);
      if (d2 > REPULSION_CUTOFF * REPULSION_CUTOFF) continue;
      const d = Math.sqrt(d2);
      const force = ((REPULSION * a.chg * b.chg * alpha) / d2);
      const ux = dx / d;
      const uy = dy / d;
      a.vx += ux * force;
      a.vy += uy * force;
      b.vx -= ux * force;
      b.vy -= uy * force;
    }
  }

  // Springs: longer rest around high-degree nodes, logical neighbours stay close.
  for (const edge of edges) {
    const dx = edge.b.x - edge.a.x;
    const dy = edge.b.y - edge.a.y;
    const d = Math.max(0.01, Math.hypot(dx, dy));
    const rest = SPRING_BASE + SPRING_DEGREE * Math.sqrt(edge.a.degree + edge.b.degree);
    const force = ((d - rest) * SPRING_STIFFNESS * alpha) / d;
    edge.a.vx += dx * force;
    edge.a.vy += dy * force;
    edge.b.vx -= dx * force;
    edge.b.vy -= dy * force;
  }

  // Keep unrelated nodes off the lines: push non-incident nodes away from
  // edge midpoints so links rarely cross nodes and captions.
  for (const edge of edges) {
    const mx = (edge.a.x + edge.b.x) / 2;
    const my = (edge.a.y + edge.b.y) / 2;
    for (const node of nodes) {
      if (node === edge.a || node === edge.b) continue;
      const dx = node.x - mx;
      const dy = node.y - my;
      const d = Math.hypot(dx, dy);
      if (d >= MIDPOINT_RADIUS || d < 0.01) continue;
      const push = ((1 - d / MIDPOINT_RADIUS) * MIDPOINT_STRENGTH * alpha) / d;
      node.vx += dx * push;
      node.vy += dy * push;
    }
  }

  let maxDisp = 0;
  for (const node of nodes) {
    if (node.fx !== null && node.fy !== null) {
      node.x = node.fx;
      node.y = node.fy;
      node.vx = 0;
      node.vy = 0;
      continue;
    }
    // Weak centring: just enough to keep the graph together, never a heap.
    node.vx += (0 - node.x) * GRAVITY * alpha;
    node.vy += (0 - node.y) * GRAVITY * alpha;
    node.vx *= DAMPING;
    node.vy *= DAMPING;
    const stepX = Math.max(-MAX_STEP, Math.min(MAX_STEP, node.vx));
    const stepY = Math.max(-MAX_STEP, Math.min(MAX_STEP, node.vy));
    node.x += stepX;
    node.y += stepY;
    maxDisp = Math.max(maxDisp, Math.abs(stepX), Math.abs(stepY));
  }

  // Positional collision: guarantees personal space (glyph + caption
  // reserve), which pure forces alone cannot enforce.
  for (let pass = 0; pass < 2; pass += 1) {
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        const minDist = a.cr + b.cr;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d = Math.hypot(dx, dy);
        if (d >= minDist) continue;
        if (d < 0.01) {
          dx = 0.01;
          dy = 0;
          d = 0.01;
        }
        const overlap = ((minDist - d) / d) / 2;
        const aFixed = a.fx !== null;
        const bFixed = b.fx !== null;
        if (!aFixed && !bFixed) {
          a.x -= dx * overlap;
          a.y -= dy * overlap;
          b.x += dx * overlap;
          b.y += dy * overlap;
        } else if (aFixed && !bFixed) {
          b.x += dx * overlap * 2;
          b.y += dy * overlap * 2;
        } else if (!aFixed && bFixed) {
          a.x -= dx * overlap * 2;
          a.y -= dy * overlap * 2;
        }
      }
    }
  }

  return maxDisp;
}

/**
 * Deterministic pre-layout: settles the graph synchronously BEFORE first
 * paint, so the user immediately sees an arranged graph instead of animated
 * chaos. No randomness anywhere (degree-sorted phyllotaxis start), hence
 * identical input always yields identical positions.
 */
export function prelayoutPositions(
  inputs: readonly LayoutNodeInput[],
  links: ReadonlyArray<readonly [string, string]>,
  maxTicks = 500,
): Map<string, { x: number; y: number }> {
  const nodes = createSimNodes(inputs, new Map());
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const edges: SimEdge[] = [];
  for (const [from, to] of links) {
    const a = byId.get(from);
    const b = byId.get(to);
    if (a && b) edges.push({ id: `${from}::${to}`, a, b });
  }
  let alpha = 1;
  for (let tick = 0; tick < maxTicks; tick += 1) {
    const maxDisp = stepForces(nodes, edges, alpha);
    alpha *= 0.988;
    if (alpha <= 0.008 || (maxDisp < 0.04 && alpha < 0.15)) break;
  }
  return new Map(nodes.map((node) => [node.id, { x: node.x, y: node.y }]));
}

// ---------------------------------------------------------------------------
// Crossing-aware multi-stage auto-layout for the bipartite user↔university
// graph. Plain force simulation alone cannot guarantee few edge crossings,
// so the pipeline is: barycentric layer ordering (optimal-ish order for two
// layers) → layered coordinates → gentle force relaxation with snapshots →
// label-aware overlap removal → metric-driven selection of the best variant.
// Fully deterministic: no randomness at any stage.
// ---------------------------------------------------------------------------

export interface LayoutMetrics {
  crossings: number;
  nodeOverlaps: number;
  labelOverlaps: number;
  minGap: number;
  area: number;
  totalEdgeLength: number;
}

export interface AutoLayoutResult {
  positions: Map<string, { x: number; y: number }>;
  before: LayoutMetrics;
  after: LayoutMetrics;
}

interface GeoNode {
  id: string;
  x: number;
  y: number;
  r: number;
  label: string;
}

interface GeoRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Caption pill estimate in world units (mirrors the canvas label drawing). */
function labelRect(node: GeoNode): GeoRect {
  const len = Math.min(node.label.length, 26);
  const w = len * 6.4 + 12;
  const h = 19;
  return { x0: node.x - w / 2, y0: node.y + node.r + 4, x1: node.x + w / 2, y1: node.y + node.r + 4 + h };
}

function orient(ax: number, ay: number, bx: number, by: number, cx: number, cy: number): number {
  return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

function segmentsCross(a: GeoNode, b: GeoNode, c: GeoNode, d: GeoNode): boolean {
  const o1 = orient(a.x, a.y, b.x, b.y, c.x, c.y);
  const o2 = orient(a.x, a.y, b.x, b.y, d.x, d.y);
  const o3 = orient(c.x, c.y, d.x, d.y, a.x, a.y);
  const o4 = orient(c.x, c.y, d.x, d.y, b.x, b.y);
  return o1 * o2 < 0 && o3 * o4 < 0;
}

function rectsCross(r: GeoRect, s: GeoRect): boolean {
  return r.x0 < s.x1 && r.x1 > s.x0 && r.y0 < s.y1 && r.y1 > s.y0;
}

function circleRectDistance(x: number, y: number, r: GeoRect): number {
  const dx = Math.max(r.x0 - x, 0, x - r.x1);
  const dy = Math.max(r.y0 - y, 0, y - r.y1);
  return Math.hypot(dx, dy);
}

export function measureLayout(
  geos: ReadonlyArray<GeoNode>,
  links: ReadonlyArray<readonly [string, string]>,
): LayoutMetrics {
  const byId = new Map(geos.map((node) => [node.id, node]));
  let crossings = 0;
  for (let i = 0; i < links.length; i += 1) {
    const a = byId.get(links[i][0]);
    const b = byId.get(links[i][1]);
    if (!a || !b) continue;
    for (let j = i + 1; j < links.length; j += 1) {
      if (links[i][0] === links[j][0] || links[i][0] === links[j][1]
        || links[i][1] === links[j][0] || links[i][1] === links[j][1]) continue;
      const c = byId.get(links[j][0]);
      const d = byId.get(links[j][1]);
      if (!c || !d) continue;
      if (segmentsCross(a, b, c, d)) crossings += 1;
    }
  }
  let nodeOverlaps = 0;
  let labelOverlaps = 0;
  let minGap = Infinity;
  for (let i = 0; i < geos.length; i += 1) {
    for (let j = i + 1; j < geos.length; j += 1) {
      const a = geos[i];
      const b = geos[j];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      minGap = Math.min(minGap, d - (a.r + b.r));
      if (d < a.r + b.r) nodeOverlaps += 1;
      const ra = labelRect(a);
      const rb = labelRect(b);
      if (rectsCross(ra, rb)
        || circleRectDistance(a.x, a.y, rb) < b.r
        || circleRectDistance(b.x, b.y, ra) < a.r) labelOverlaps += 1;
    }
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const node of geos) {
    minX = Math.min(minX, node.x - node.r);
    minY = Math.min(minY, node.y - node.r);
    maxX = Math.max(maxX, node.x + node.r);
    maxY = Math.max(maxY, node.y + node.r);
  }
  let totalEdgeLength = 0;
  for (const [from, to] of links) {
    const a = byId.get(from);
    const b = byId.get(to);
    if (a && b) totalEdgeLength += Math.hypot(a.x - b.x, a.y - b.y);
  }
  return {
    crossings,
    nodeOverlaps,
    labelOverlaps,
    minGap: minGap === Infinity ? 0 : minGap,
    area: geos.length ? (maxX - minX) * (maxY - minY) : 0,
    totalEdgeLength,
  };
}

function barycenter(neighbours: readonly string[], order: ReadonlyMap<string, number>): number {
  if (!neighbours.length) return Infinity;
  let sum = 0;
  for (const id of neighbours) sum += order.get(id) ?? 0;
  return sum / neighbours.length;
}

/** One barycentric sweep: reorder `moving` by neighbour means in `fixed`. */
function sweep(
  fixed: readonly string[],
  moving: readonly string[],
  adjacency: ReadonlyMap<string, readonly string[]>,
): string[] {
  const order = new Map(fixed.map((id, index) => [id, index]));
  return [...moving].sort((left, right) => {
    const diff = barycenter(adjacency.get(left) ?? [], order) - barycenter(adjacency.get(right) ?? [], order);
    if (diff !== 0) return diff;
    return left < right ? -1 : left > right ? 1 : 0;
  });
}

function compareMetrics(left: LayoutMetrics, right: LayoutMetrics): number {
  if (left.crossings !== right.crossings) return left.crossings - right.crossings;
  if (left.labelOverlaps !== right.labelOverlaps) return left.labelOverlaps - right.labelOverlaps;
  if (left.nodeOverlaps !== right.nodeOverlaps) return left.nodeOverlaps - right.nodeOverlaps;
  return left.totalEdgeLength - right.totalEdgeLength;
}

/**
 * Push overlapping glyphs/captions apart using real shapes (circle glyph +
 * caption pill). Returns true when a clean pass is achieved.
 */
function declutter(geos: GeoNode[], maxPasses = 100): void {
  for (let pass = 0; pass < maxPasses; pass += 1) {
    let clean = true;
    for (let i = 0; i < geos.length; i += 1) {
      for (let j = i + 1; j < geos.length; j += 1) {
        const a = geos[i];
        const b = geos[j];
        // Candidate separations: glyph-glyph, glyph-caption (both ways),
        // caption-caption. Apply the deepest penetration found.
        let pushX = 0;
        let pushY = 0;
        let depth = 0;
        const consider = (dx: number, dy: number, overlap: number) => {
          if (overlap > depth) {
            depth = overlap;
            const d = Math.hypot(dx, dy) || 0.01;
            pushX = (dx / d) * overlap;
            pushY = (dy / d) * overlap;
          }
        };
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const glyphDist = Math.hypot(dx, dy) || 0.01;
        consider(dx, dy, a.r + b.r - glyphDist);
        const ra = labelRect(a);
        const rb = labelRect(b);
        const ac = { x: (ra.x0 + ra.x1) / 2, y: (ra.y0 + ra.y1) / 2 };
        const bc = { x: (rb.x0 + rb.x1) / 2, y: (rb.y0 + rb.y1) / 2 };
        if (circleRectDistance(a.x, a.y, rb) < b.r) {
          consider(a.x - bc.x || 0.01, a.y - bc.y, b.r - circleRectDistance(a.x, a.y, rb));
        }
        if (circleRectDistance(b.x, b.y, ra) < a.r) {
          consider(b.x - ac.x || 0.01, b.y - ac.y, a.r - circleRectDistance(b.x, b.y, ra));
        }
        if (rectsCross(ra, rb)) {
          const ox = Math.min(ra.x1, rb.x1) - Math.max(ra.x0, rb.x0);
          const oy = Math.min(ra.y1, rb.y1) - Math.max(ra.y0, rb.y0);
          if (ox < oy) consider(bc.x >= ac.x ? ox : -ox, 0, ox);
          else consider(0, bc.y >= ac.y ? oy : -oy, oy);
        }
        if (depth > 0.01) {
          clean = false;
          a.x -= pushX / 2;
          a.y -= pushY / 2;
          b.x += pushX / 2;
          b.y += pushY / 2;
        }
      }
    }
    if (clean) return;
  }
}

export function autoLayout(
  inputs: readonly LayoutNodeInput[],
  links: ReadonlyArray<readonly [string, string]>,
): AutoLayoutResult {
  const geoOf = (positions: ReadonlyMap<string, { x: number; y: number }>): GeoNode[] =>
    inputs.map((node) => {
      const point = positions.get(node.id);
      const r = (node.kind === 'user' ? 7 : 8) + Math.min(node.degree, 10) * 0.9;
      return { id: node.id, x: point?.x ?? 0, y: point?.y ?? 0, r, label: node.label };
    });

  // Stage 1 — structure-aware start: barycentric order per layer, then
  // gentle two-column coordinates (slight wave keeps it from looking rigid).
  const users = inputs.filter((node) => node.kind === 'user').map((node) => node.id);
  const unis = inputs.filter((node) => node.kind === 'university').map((node) => node.id);
  const adjU = new Map<string, string[]>();
  const adjV = new Map<string, string[]>();
  for (const [from, to] of links) {
    const userSide = users.includes(from);
    const u = userSide ? from : to;
    const v = userSide ? to : from;
    if (!adjU.has(u)) adjU.set(u, []);
    if (!adjV.has(v)) adjV.set(v, []);
    adjU.get(u)?.push(v);
    adjV.get(v)?.push(u);
  }
  let orderU = [...users].sort();
  let orderV = [...unis].sort();
  for (let sweepIndex = 0; sweepIndex < 8; sweepIndex += 1) {
    orderV = sweep(orderU, orderV, adjV);
    orderU = sweep(orderV, orderU, adjU);
  }
  const GAP = 400;
  const ROW = 56;
  const layered = new Map<string, { x: number; y: number }>();
  orderU.forEach((id, index) => {
    layered.set(id, {
      x: -GAP / 2 + 22 * Math.sin(index * 2.1),
      y: (index - (orderU.length - 1) / 2) * ROW,
    });
  });
  orderV.forEach((id, index) => {
    layered.set(id, {
      x: GAP / 2 + 22 * Math.sin(index * 2.1 + 1),
      y: (index - (orderV.length - 1) / 2) * ROW,
    });
  });

  const before = measureLayout(
    inputs.map((node, index) => {
      const start = initialPosition(index);
      const r = (node.kind === 'user' ? 7 : 8) + Math.min(node.degree, 10) * 0.9;
      return { id: node.id, x: start.x, y: start.y, r, label: node.label };
    }),
    links,
  );

  // Stage 2 — relax the layered start gently, keep the best snapshot.
  const relaxNodes = createSimNodes(inputs, layered);
  const relaxById = new Map(relaxNodes.map((node) => [node.id, node]));
  const relaxEdges: SimEdge[] = [];
  for (const [from, to] of links) {
    const a = relaxById.get(from);
    const b = relaxById.get(to);
    if (a && b) relaxEdges.push({ id: `${from}::${to}`, a, b });
  }
  let best = new Map(layered);
  let bestMetric = measureLayout(geoOf(layered), links);
  let alpha = 0.6;
  for (let tick = 0; tick < 120; tick += 1) {
    stepForces(relaxNodes, relaxEdges, alpha);
    alpha *= 0.988;
    if (tick % 15 === 0 || tick === 119) {
      const snapshot = new Map(relaxNodes.map((node) => [node.id, { x: node.x, y: node.y }] as const));
      const metric = measureLayout(geoOf(snapshot), links);
      if (compareMetrics(metric, bestMetric) < 0) {
        best = snapshot;
        bestMetric = metric;
      }
    }
    if (alpha <= 0.05) break;
  }

  // Stage 3 — real-shape declutter on the winner.
  const decluttered = geoOf(best);
  declutter(decluttered);
  const declutteredMap = new Map(decluttered.map((node) => [node.id, { x: node.x, y: node.y }] as const));

  // Stage 4 — force-only fallback competes too; keep the true minimum.
  const forceOnly = prelayoutPositions(inputs, links, 300);
  const candidates: Array<{ positions: Map<string, { x: number; y: number }>; metric: LayoutMetrics }> = [
    { positions: best, metric: bestMetric },
    { positions: declutteredMap, metric: measureLayout(decluttered, links) },
    { positions: forceOnly, metric: measureLayout(geoOf(forceOnly), links) },
  ];
  candidates.sort((left, right) => compareMetrics(left.metric, right.metric));
  return { positions: candidates[0].positions, before, after: candidates[0].metric };
}
