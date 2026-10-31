import { describe, expect, it } from "vitest";
import { buildThread, splitExitCode, summarizeStatus, type ThreadEvent } from "./taskThread";

let nextId = 1;
const ev = (type: string, payload: object): ThreadEvent => ({
  id: nextId++,
  type,
  payload: JSON.stringify(payload),
  timestamp: "2026-10-31T10:00:00Z",
});

describe("splitExitCode", () => {
  it("strips the exit header", () => {
    expect(splitExitCode("[Exit code: 2]\nboom")).toEqual({ output: "boom", exitCode: 2 });
    expect(splitExitCode("plain")).toEqual({ output: "plain", exitCode: null });
  });
});

describe("buildThread", () => {
  it("starts with the goal and pairs commands with their results", () => {
    const turns = buildThread("Fix the bug", [
      ev("status", { status: "running" }),
      ev("log", { message: "Agent initialized" }),
      ev("command", { command: "pytest" }),
      ev("result", { output: "[Exit code: 1]\n1 failed", exit_code: 1 }),
      ev("command", { command: "ls" }),
    ]);
    expect(turns).toHaveLength(1);
    const [goal] = turns;
    expect(goal.kind).toBe("goal");
    expect(goal.text).toBe("Fix the bug");
    expect(goal.state).toBe("running");
    expect(goal.items.map((i) => i.kind)).toEqual(["log", "command", "command"]);
    expect(goal.items[1]).toMatchObject({ command: "pytest", output: "1 failed", exitCode: 1 });
    expect(goal.items[2]).toMatchObject({ command: "ls" });
    expect(goal.items[2]).not.toHaveProperty("output");
  });

  it("parses the exit code from text when the payload has no exit_code (older events)", () => {
    const [goal] = buildThread("g", [ev("command", { command: "true" }), ev("result", { output: "[Exit code: 0]\n" })]);
    expect(goal.items[0]).toMatchObject({ exitCode: 0, output: "" });
  });

  it("starts a new turn at each follow-up or retry marker and hides the marker", () => {
    const turns = buildThread("g", [
      ev("status", { status: "completed" }),
      ev("log", { message: "💬 Follow-up: add tests", turn: "follow_up", text: "add tests" }),
      ev("status", { status: "running" }),
      ev("command", { command: "pytest" }),
      ev("status", { status: "failed" }),
      ev("log", { message: "🔄 Task restarted by user.", turn: "retry" }),
    ]);
    expect(turns.map((t) => t.kind)).toEqual(["goal", "follow_up", "retry"]);
    expect(turns[0].state).toBe("completed");
    expect(turns[1]).toMatchObject({ text: "add tests", state: "failed" });
    expect(turns[1].items.map((i) => i.kind)).toEqual(["command"]);
    expect(turns[2].items).toEqual([]);
  });

  it("recognises untagged legacy markers", () => {
    const turns = buildThread("g", [
      ev("log", { message: "💬 Follow-up: legacy text" }),
      ev("log", { message: "🔄 Task restarted by user. Relaunching agent reasoning loop..." }),
    ]);
    expect(turns.map((t) => [t.kind, t.text])).toEqual([["goal", "g"], ["follow_up", "legacy text"], ["retry", ""]]);
  });

  it("shows screenshots as items instead of attaching them to a command", () => {
    const [goal] = buildThread("g", [
      ev("command", { command: "shot" }),
      ev("result", { screenshot: "data:image/png;base64,xx", caption: "Home page" }),
      ev("result", { output: "[Exit code: 0]\nok" }),
    ]);
    expect(goal.items.map((i) => i.kind)).toEqual(["command", "screenshot"]);
    expect(goal.items[0]).toMatchObject({ output: "ok", exitCode: 0 });
  });

  it("accepts object payloads and non-JSON text", () => {
    const [goal] = buildThread("g", [
      { id: 900, type: "LOG", payload: { message: "object" }, timestamp: "" },
      { id: 901, type: "log", payload: "not json", timestamp: "" },
    ]);
    expect(goal.items.map((i) => (i.kind === "log" ? i.text : ""))).toEqual(["object", "not json"]);
  });
});

describe("summarizeStatus", () => {
  const turn = buildThread("g", [ev("log", { message: "Agent failed with exception: boom" })])[0];

  it("explains each state", () => {
    expect(summarizeStatus("pending", {}).title).toBe("Queued");
    expect(summarizeStatus("failed", {}, turn)).toMatchObject({ tone: "error", detail: "Agent failed with exception: boom" });
    expect(summarizeStatus("cancelled", {}).title).toBe("Stopped");
    expect(summarizeStatus(undefined, {}).title).toMatch(/Loading/);
  });

  it("names the running command", () => {
    const running = buildThread("g", [ev("command", { command: "npm test" })])[0];
    expect(summarizeStatus("running", {}, running)).toMatchObject({ title: "Running a command", detail: "npm test" });
  });

  it("distinguishes PR, local changes, missing PR and no changes", () => {
    expect(summarizeStatus("completed", { pr_url: "https://github.com/o/r/pull/1" }).title).toBe("Draft PR ready");
    expect(summarizeStatus("completed", { patch_diff: "d" }).title).toBe("Changes ready");
    expect(summarizeStatus("completed", { patch_diff: "d", repo_url: "https://github.com/o/r" }).tone).toBe("warning");
    expect(summarizeStatus("completed", {}).title).toBe("Finished with no file changes");
  });
});
