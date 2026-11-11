import { useEffect, useRef, useState, useCallback } from "react";
import { evaluateFpsSample } from "./focusSearchUtils";

interface UseFpsMonitorOptions {
  enabled: boolean;
  threshold: number;
  streakRequired: number;
  sampleWindowMs?: number;
  cooldownUntil?: number;
  onFallbackTriggered: (measuredFps: number) => void;
}

/**
 * Measures real browser rendering FPS via requestAnimationFrame.
 * Automatically notifies when sustained FPS drops below the configured threshold,
 * while ignoring background tab throttling (document.hidden).
 */
export function useFpsMonitor({
  enabled,
  threshold,
  streakRequired,
  sampleWindowMs = 500,
  cooldownUntil = 0,
  onFallbackTriggered,
}: UseFpsMonitorOptions) {
  const [fps, setFps] = useState<number>(60);
  const lowStreakRef = useRef<number>(0);
  const simulatedDropRef = useRef<{ active: boolean; fakeFps: number }>({
    active: false,
    fakeFps: 12,
  });
  const onFallbackRef = useRef(onFallbackTriggered);
  onFallbackRef.current = onFallbackTriggered;

  // Reset streak whenever monitoring mode or threshold changes
  useEffect(() => {
    lowStreakRef.current = 0;
  }, [enabled, threshold]);

  useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();
    let animId = 0;

    const handleVisibilityChange = () => {
      // Reset counters when switching tabs so browser throttling does not trigger fallback
      frameCount = 0;
      lastTime = performance.now();
      lowStreakRef.current = 0;
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    const tick = (now: number) => {
      frameCount += 1;
      const elapsed = now - lastTime;

      if (elapsed >= sampleWindowMs) {
        const measuredFps = simulatedDropRef.current.active
          ? simulatedDropRef.current.fakeFps
          : Math.round((frameCount * 1000) / elapsed);

        setFps(measuredFps);

        if (enabled) {
          const evalRes = evaluateFpsSample(lowStreakRef.current, {
            fps: measuredFps,
            threshold,
            streakRequired,
            isTabHidden: document.hidden,
            elapsedMs: elapsed,
            isCooldownActive: Date.now() < cooldownUntil,
          });
          lowStreakRef.current = evalRes.nextLowStreak;

          if (evalRes.shouldTriggerFallback) {
            lowStreakRef.current = 0;
            simulatedDropRef.current.active = false;
            onFallbackRef.current(measuredFps);
          }
        }

        frameCount = 0;
        lastTime = now;
      }

      animId = requestAnimationFrame(tick);
    };

    animId = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(animId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [enabled, threshold, streakRequired, sampleWindowMs, cooldownUntil]);

  const triggerSimulatedLowFps = useCallback(
    (fakeFps: number = Math.max(8, threshold - 10)) => {
      if (!enabled) return;
      simulatedDropRef.current = { active: true, fakeFps };
      setFps(fakeFps);
      // Fast-forward streak check immediately on the next sample window
      lowStreakRef.current = Math.max(0, streakRequired - 1);
    },
    [enabled, threshold, streakRequired]
  );

  return { fps, triggerSimulatedLowFps };
}

