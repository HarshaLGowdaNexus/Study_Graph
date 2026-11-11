/**
 * Central Frontend Graph & Performance Configuration (Rule 5, Task T16).
 * Mirrors backend/app/core/config.py defaults and hydrates live overrides
 * from GET /api/graphs/config so thresholds live in one place.
 */

export interface GraphRuntimeConfig {
  fpsFallbackThreshold: number;
  fpsLowStreakCount: number;
  fpsSampleWindowMs: number;
  defaultSearchHops: number;
  minSearchHops: number;
  maxSearchHops: number;
  maxVisibleNodes: number;
  weakLinkThreshold: number;
  retry3DCooldownMs: number;
}

const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};

export const DEFAULT_GRAPH_CONFIG: GraphRuntimeConfig = {
  fpsFallbackThreshold: Number(env.VITE_GRAPH_FPS_FALLBACK_THRESHOLD ?? 25),
  fpsLowStreakCount: Number(env.VITE_GRAPH_FPS_LOW_STREAK_COUNT ?? 4),
  fpsSampleWindowMs: 500,
  defaultSearchHops: Number(env.VITE_GRAPH_SEARCH_DEFAULT_HOPS ?? 2),
  minSearchHops: 1,
  maxSearchHops: 3,
  maxVisibleNodes: Number(env.VITE_GRAPH_MAX_VISIBLE_NODES ?? 150),
  weakLinkThreshold: 3,
  retry3DCooldownMs: 5000,
};

export async function fetchGraphRuntimeConfig(): Promise<GraphRuntimeConfig> {
  try {
    const res = await fetch("/api/graphs/config");
    if (!res.ok) return DEFAULT_GRAPH_CONFIG;
    const data = await res.json();
    return {
      ...DEFAULT_GRAPH_CONFIG,
      fpsFallbackThreshold: Number(
        data.fps_fallback_threshold ?? DEFAULT_GRAPH_CONFIG.fpsFallbackThreshold
      ),
      fpsLowStreakCount: Number(
        data.fps_low_streak_count ?? DEFAULT_GRAPH_CONFIG.fpsLowStreakCount
      ),
      defaultSearchHops: Number(
        data.default_search_hops ?? DEFAULT_GRAPH_CONFIG.defaultSearchHops
      ),
      minSearchHops: Number(data.min_search_hops ?? DEFAULT_GRAPH_CONFIG.minSearchHops),
      maxSearchHops: Number(data.max_search_hops ?? DEFAULT_GRAPH_CONFIG.maxSearchHops),
      maxVisibleNodes: Number(
        data.max_visible_nodes ?? DEFAULT_GRAPH_CONFIG.maxVisibleNodes
      ),
      weakLinkThreshold: Number(
        data.weak_link_threshold ?? DEFAULT_GRAPH_CONFIG.weakLinkThreshold
      ),
    };
  } catch {
    return DEFAULT_GRAPH_CONFIG;
  }
}

