/**
 * Pure helper utilities for Topic Search (with aliases), K-Hop Focused Subgraphs,
 * and FPS Fallback State Evaluation (Task T16: Features F13, F15; Risks R09, R14).
 */

export interface SearchTopicSuggestion {
  id: string;
  subject_id: string;
  subject_name: string;
  keyword: string;
  aliases: string[];
  matched_alias?: string | null;
  explanation: string;
  real_world_use?: string;
  module_no: number;
  reviewed: boolean;
  cluster_label?: string;
  source?: "database" | "local";
}

export interface RawGraphNode {
  id: string;
  name?: string;
  keyword: string;
  aliases?: string[];
  explanation?: string;
  real_world_use?: string;
  module_no?: number;
  reviewed?: boolean;
  cluster_id?: string | null;
  cluster_label?: string;
  parent_cluster_label?: string;
  subject_id?: string;
  subject_name?: string;
  hop_distance?: number;
  is_focus?: boolean;
}

export interface RawGraphLink {
  id: string;
  source: any;
  target: any;
  strength?: number;
  scope?: string;
}

export function getEndpointId(endpoint: string | { id?: string } | any): string {
  return typeof endpoint === "object" && endpoint !== null ? String(endpoint.id) : String(endpoint);
}

/**
 * Ranks and filters local graph nodes by matching both canonical keyword and aliases.
 */
export function matchLocalTopics(
  nodes: RawGraphNode[],
  query: string,
  limit: number = 10
): SearchTopicSuggestion[] {
  const cleaned = query.trim().toLowerCase();
  if (!cleaned) return [];

  interface RankedMatch {
    rank: number;
    suggestion: SearchTopicSuggestion;
  }

  const matches: RankedMatch[] = [];

  for (const node of nodes) {
    const keyword = node.keyword || node.name || "";
    const kwLower = keyword.toLowerCase();
    const aliases = Array.isArray(node.aliases) ? node.aliases.filter(Boolean) : [];
    const matchingAliases = aliases.filter((a) => a.toLowerCase().includes(cleaned));
    const kwMatch = kwLower.includes(cleaned);

    if (!kwMatch && matchingAliases.length === 0) continue;

    let rank = 3;
    if (kwLower === cleaned) {
      rank = 0;
    } else if (kwLower.startsWith(cleaned)) {
      rank = 1;
    } else if (matchingAliases.some((a) => a.toLowerCase() === cleaned)) {
      rank = 2;
    }

    const matchedAlias =
      matchingAliases.length > 0 && (!kwMatch || rank === 2)
        ? matchingAliases[0]
        : null;

    matches.push({
      rank,
      suggestion: {
        id: node.id,
        subject_id: node.subject_id || "",
        subject_name: node.subject_name || "Subject",
        keyword,
        aliases,
        matched_alias: matchedAlias,
        explanation: node.explanation || "",
        real_world_use: node.real_world_use || "",
        module_no: node.module_no || 1,
        reviewed: Boolean(node.reviewed),
        cluster_label: node.cluster_label || "General",
        source: "local",
      },
    });
  }

  matches.sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank;
    return a.suggestion.keyword.localeCompare(b.suggestion.keyword);
  });

  return matches.slice(0, limit).map((m) => m.suggestion);
}

/**
 * Merges live database search results with in-memory graph results without duplicates.
 */
export function mergeSearchSuggestions(
  remoteResults: SearchTopicSuggestion[],
  localResults: SearchTopicSuggestion[],
  limit: number = 10
): SearchTopicSuggestion[] {
  const seen = new Set<string>();
  const combined: SearchTopicSuggestion[] = [];

  for (const item of remoteResults) {
    if (!seen.has(item.id)) {
      seen.add(item.id);
      combined.push({ ...item, source: "database" });
    }
  }
  for (const item of localResults) {
    if (!seen.has(item.id)) {
      seen.add(item.id);
      combined.push({ ...item, source: "local" });
    }
  }

  return combined.slice(0, limit);
}

export interface KHopSubgraphResult<N extends RawGraphNode, L extends RawGraphLink> {
  nodes: (N & { hop_distance: number; is_focus: boolean })[];
  links: L[];
  focusNode: (N & { hop_distance: number; is_focus: boolean }) | null;
  hiddenWeakCount: number;
}

/**
 * Extracts a focused K-hop neighborhood around centerTopicId using Breadth-First Search.
 * Stronger edges are traversed first so capping at maxNodes preserves the closest core links.
 */
export function extractKHopSubgraph<N extends RawGraphNode, L extends RawGraphLink>(
  allNodes: N[],
  allLinks: L[],
  centerTopicId: string,
  hops: number,
  options?: {
    includeWeak?: boolean;
    weakThreshold?: number;
    maxNodes?: number;
    minHops?: number;
    maxHops?: number;
  }
): KHopSubgraphResult<N, L> {
  const minHops = options?.minHops ?? 1;
  const maxHops = options?.maxHops ?? 3;
  const targetHops = Math.max(minHops, Math.min(maxHops, hops));
  const includeWeak = options?.includeWeak ?? false;
  const weakThreshold = options?.weakThreshold ?? 3;
  const maxNodes = options?.maxNodes ?? 150;

  const nodeMap = new Map<string, N>();
  for (const n of allNodes) {
    nodeMap.set(n.id, n);
  }

  if (!nodeMap.has(centerTopicId)) {
    return { nodes: [], links: [], focusNode: null, hiddenWeakCount: 0 };
  }

  // Build adjacency list over active visible edges
  const adjacency = new Map<string, Array<{ neighborId: string; strength: number }>>();
  for (const link of allLinks) {
    const strength = Number(link.strength ?? 1);
    if (!includeWeak && strength < weakThreshold) continue;
    const src = getEndpointId(link.source);
    const tgt = getEndpointId(link.target);
    if (!nodeMap.has(src) || !nodeMap.has(tgt)) continue;

    if (!adjacency.has(src)) adjacency.set(src, []);
    if (!adjacency.has(tgt)) adjacency.set(tgt, []);
    adjacency.get(src)!.push({ neighborId: tgt, strength });
    adjacency.get(tgt)!.push({ neighborId: src, strength });
  }

  const hopMap = new Map<string, number>();
  hopMap.set(centerTopicId, 0);
  const queue: Array<{ id: string; dist: number }> = [{ id: centerTopicId, dist: 0 }];

  while (queue.length > 0) {
    const { id: currId, dist } = queue.shift()!;
    if (dist >= targetHops) continue;

    const neighbors = [...(adjacency.get(currId) || [])].sort(
      (a, b) => b.strength - a.strength
    );

    for (const { neighborId } of neighbors) {
      if (hopMap.has(neighborId)) continue;
      if (hopMap.size >= maxNodes) break;
      hopMap.set(neighborId, dist + 1);
      queue.push({ id: neighborId, dist: dist + 1 });
    }
  }

  const nodes = Array.from(hopMap.entries()).map(([id, hopDist]) => {
    const original = nodeMap.get(id)!;
    return {
      ...original,
      hop_distance: hopDist,
      is_focus: id === centerTopicId,
    };
  });

  const includedIds = new Set(hopMap.keys());
  let hiddenWeakCount = 0;
  const visibleLinks: L[] = [];

  for (const link of allLinks) {
    const src = getEndpointId(link.source);
    const tgt = getEndpointId(link.target);
    const strength = Number(link.strength ?? 1);
    const inSubgraph = includedIds.has(src) && includedIds.has(tgt);
    const touchesFocus = src === centerTopicId || tgt === centerTopicId;

    if (!includeWeak && strength < weakThreshold) {
      if (inSubgraph || touchesFocus) {
        hiddenWeakCount += 1;
      }
      continue;
    }

    if (inSubgraph) {
      visibleLinks.push({
        ...link,
        source: src,
        target: tgt,
      });
    }
  }

  const focusNode = nodes.find((n) => n.id === centerTopicId) || null;
  return { nodes, links: visibleLinks, focusNode, hiddenWeakCount };
}

export interface FpsEvalInput {
  fps: number;
  threshold: number;
  streakRequired: number;
  isTabHidden: boolean;
  elapsedMs: number;
  isCooldownActive: boolean;
}

export interface FpsEvalOutput {
  nextLowStreak: number;
  shouldTriggerFallback: boolean;
}

/**
 * Pure decision function for FPS auto-fallback.
 * Prevents false switches from background browser tabs or momentary 1-frame stutters.
 */
export function evaluateFpsSample(
  currentLowStreak: number,
  sample: FpsEvalInput
): FpsEvalOutput {
  if (sample.isTabHidden || sample.elapsedMs > 2500 || sample.isCooldownActive) {
    return { nextLowStreak: 0, shouldTriggerFallback: false };
  }

  if (sample.fps < sample.threshold) {
    const nextLowStreak = currentLowStreak + 1;
    return {
      nextLowStreak,
      shouldTriggerFallback: nextLowStreak >= sample.streakRequired,
    };
  }

  return { nextLowStreak: 0, shouldTriggerFallback: false };
}
