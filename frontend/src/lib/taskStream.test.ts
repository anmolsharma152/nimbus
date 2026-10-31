import { describe, expect, it } from "vitest";
import {
  isTerminalStatus,
  lastEventId,
  mergeEvents,
  parsePayload,
  reconnectDelay,
  streamUrl,
} from "./taskStream";

type Ev = { id?: number | null; text: string };

describe("mergeEvents", () => {
  it("drops events already seen by id", () => {
    const prev: Ev[] = [{ id: 1, text: "a" }, { id: 2, text: "b" }];
    expect(mergeEvents(prev, [{ id: 2, text: "dup" }, { id: 3, text: "c" }]).map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it("returns the same array when nothing is new, so React can skip a render", () => {
    const prev: Ev[] = [{ id: 1, text: "a" }];
    expect(mergeEvents(prev, [{ id: 1, text: "a" }])).toBe(prev);
  });

  it("keeps persisted events in id order when replay and live events interleave", () => {
    const prev: Ev[] = [{ id: 5, text: "live" }];
    const merged = mergeEvents(prev, [{ id: 3, text: "old" }, { id: 4, text: "old2" }]);
    expect(merged.map((e) => e.id)).toEqual([3, 4, 5]);
  });

  it("appends unpersisted events where they arrive", () => {
    const merged = mergeEvents<Ev>([{ id: 1, text: "a" }], [{ text: "note" }, { text: "note" }]);
    expect(merged.map((e) => e.text)).toEqual(["a", "note", "note"]);
  });
});

describe("helpers", () => {
  it("finds the resume cursor", () => {
    expect(lastEventId([{ id: 3 }, { id: null }, { id: 9 }, {}])).toBe(9);
    expect(lastEventId([])).toBe(0);
  });

  it("recognises terminal statuses case-insensitively", () => {
    expect(isTerminalStatus("COMPLETED")).toBe(true);
    expect(isTerminalStatus("failed")).toBe(true);
    expect(isTerminalStatus("running")).toBe(false);
    expect(isTerminalStatus(null)).toBe(false);
  });

  it("backs off exponentially with jitter, capped at 30s", () => {
    for (let attempt = 0; attempt < 10; attempt++) {
      const ceiling = Math.min(30_000, 1_000 * 2 ** attempt);
      const delay = reconnectDelay(attempt);
      expect(delay).toBeGreaterThanOrEqual(ceiling / 2);
      expect(delay).toBeLessThanOrEqual(ceiling);
    }
  });

  it("builds stream URLs with ticket and resume cursor", () => {
    expect(streamUrl("wss://api", 7, 0, null)).toBe("wss://api/ws/tasks/7");
    expect(streamUrl("wss://api", 7, 12, "t.k+n")).toBe("wss://api/ws/tasks/7?ticket=t.k%2Bn&after=12");
  });

  it("parses payloads from strings, objects and plain text", () => {
    expect(parsePayload('{"status":"running"}')).toEqual({ status: "running" });
    expect(parsePayload({ command: "ls" })).toEqual({ command: "ls" });
    expect(parsePayload("not json")).toEqual({ message: "not json" });
    expect(parsePayload("42")).toEqual({ message: "42" });
    expect(parsePayload(null)).toEqual({});
  });
});
