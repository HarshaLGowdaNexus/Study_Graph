import { describe, it, expect } from "vitest";
import {
  matchLocalTopics,
  mergeSearchSuggestions,
  extractKHopSubgraph,
  evaluateFpsSample,
  RawGraphNode,
  RawGraphLink,
} from "../focusSearchUtils";

describe("Topic Search with Keywords & Aliases (Feature F13)", () => {
  const sampleNodes: RawGraphNode[] = [
    {
      id: "t1",
      keyword: "TCP Handshake",
      aliases: ["3-way handshake", "SYN ACK handshake"],
      module_no: 4,
      subject_id: "s-cn",
      subject_name: "Computer Networks",
      explanation: "Establishes a reliable TCP connection in 3 packets.",
      reviewed: true,
    },
    {
      id: "t2",
      keyword: "Virtual Memory",
      aliases: ["Demand Paging"],
      module_no: 2,
      subject_id: "s-os",
      subject_name: "Operating Systems",
      explanation: "Maps virtual pages to physical frames.",
      reviewed: true,
    },
  ];

  it("finds the canonical topic when searching by merged alias", () => {
    const hits = matchLocalTopics(sampleNodes, "3-way handshake");
    expect(hits).toHaveLength(1);
    expect(hits[0].id).toBe("t1");
    expect(hits[0].keyword).toBe("TCP Handshake");
    expect(hits[0].matched_alias).toBe("3-way handshake");
    expect(hits[0].module_no).toBe(4);
  });

  it("matches partial keywords case-insensitively and ignores blank input", () => {
    expect(matchLocalTopics(sampleNodes, "   ")).toEqual([]);
    const hits = matchLocalTopics(sampleNodes, "virtual");
    expect(hits).toHaveLength(1);
    expect(hits[0].id).toBe("t2");
    expect(hits[0].matched_alias).toBeNull();
  });

  it("deduplicates remote database and local results preferring database entries", () => {
    const remote = [
      {
        id: "t1",
        subject_id: "s-cn",
        subject_name: "Computer Networks",
        keyword: "TCP Handshake",
        aliases: ["3-way handshake"],
        matched_alias: "3-way handshake",
        explanation: "From DB",
        module_no: 4,
        reviewed: true,
      },
    ];
    const local = matchLocalTopics(sampleNodes, "t");
    const merged = mergeSearchSuggestions(remote, local, 10);
    const t1Entries = merged.filter((m) => m.id === "t1");
    expect(t1Entries).toHaveLength(1);
    expect(t1Entries[0].source).toBe("database");
  });
});

describe("Focused 2-3 Hop Subgraph Extraction (Feature F13, Risk R09)", () => {
  const nodes: RawGraphNode[] = ["n0", "n1", "n2", "n3", "n4", "nWeak"].map((id) => ({
    id,
    keyword: `Topic ${id}`,
    module_no: id === "n0" ? 4 : 1,
  }));

  const links: RawGraphLink[] = [
    { id: "l1", source: "n0", target: "n1", strength: 5 },
    { id: "l2", source: "n1", target: "n2", strength: 4 },
    { id: "l3", source: "n2", target: "n3", strength: 4 },
    { id: "l4", source: "n3", target: "n4", strength: 4 },
    { id: "lw", source: "n0", target: "nWeak", strength: 1 },
  ];

  it("extracts exactly 2 hops by default and hides weak links", () => {
    const sub = extractKHopSubgraph(nodes, links, "n0", 2, {
      includeWeak: false,
      weakThreshold: 3,
    });
    const ids = sub.nodes.map((n) => n.id);
    expect(ids).toEqual(["n0", "n1", "n2"]);
    expect(sub.focusNode?.hop_distance).toBe(0);
    expect(sub.focusNode?.is_focus).toBe(true);
    expect(sub.hiddenWeakCount).toBe(1);
  });

  it("expands to 3 hops cleanly while excluding 4th-hop nodes", () => {
    const sub = extractKHopSubgraph(nodes, links, "n0", 3, {
      includeWeak: false,
      weakThreshold: 3,
    });
    const ids = sub.nodes.map((n) => n.id);
    expect(ids).toEqual(["n0", "n1", "n2", "n3"]);
  });

  it("respects maxNodes cap without dropping the center topic", () => {
    const sub = extractKHopSubgraph(nodes, links, "n0", 3, {
      includeWeak: false,
      weakThreshold: 3,
      maxNodes: 2,
    });
    expect(sub.nodes.map((n) => n.id)).toEqual(["n0", "n1"]);
  });
});

describe("FPS Auto-Fallback Detector (Feature F15, Risk R14, G08)", () => {
  it("triggers fallback after consecutive samples below threshold", () => {
    let streak = 0;
    for (let i = 0; i < 3; i++) {
      const res = evaluateFpsSample(streak, {
        fps: 18,
        threshold: 25,
        streakRequired: 4,
        isTabHidden: false,
        elapsedMs: 500,
        isCooldownActive: false,
      });
      expect(res.shouldTriggerFallback).toBe(false);
      streak = res.nextLowStreak;
    }

    const fourth = evaluateFpsSample(streak, {
      fps: 16,
      threshold: 25,
      streakRequired: 4,
      isTabHidden: false,
      elapsedMs: 500,
      isCooldownActive: false,
    });
    expect(fourth.shouldTriggerFallback).toBe(true);
  });

  it("resets streak if FPS recovers or if browser tab was backgrounded", () => {
    const low = evaluateFpsSample(2, {
      fps: 19,
      threshold: 25,
      streakRequired: 4,
      isTabHidden: false,
      elapsedMs: 500,
      isCooldownActive: false,
    });
    expect(low.nextLowStreak).toBe(3);

    // Background tab throttling must NOT trigger fallback
    const hidden = evaluateFpsSample(low.nextLowStreak, {
      fps: 2,
      threshold: 25,
      streakRequired: 4,
      isTabHidden: true,
      elapsedMs: 500,
      isCooldownActive: false,
    });
    expect(hidden.shouldTriggerFallback).toBe(false);
    expect(hidden.nextLowStreak).toBe(0);

    // Recovery above threshold resets streak
    const recovered = evaluateFpsSample(3, {
      fps: 55,
      threshold: 25,
      streakRequired: 4,
      isTabHidden: false,
      elapsedMs: 500,
      isCooldownActive: false,
    });
    expect(recovered.shouldTriggerFallback).toBe(false);
    expect(recovered.nextLowStreak).toBe(0);
  });
});

