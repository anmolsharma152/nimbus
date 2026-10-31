import { describe, expect, it } from "vitest";
import { filterRepos, type RepoSummary } from "./repos";

const repo = (id: number, name: string, extra: Partial<RepoSummary> = {}): RepoSummary => ({
  id,
  name,
  full_name: `dev/${name}`,
  html_url: `https://github.com/dev/${name}`,
  stargazers_count: 0,
  ...extra,
});

const repos = [
  repo(1, "nimbus", { language: "Python", description: "Cloud coding agent" }),
  repo(2, "dotfiles", { language: "Shell" }),
  repo(3, "portfolio", { language: "TypeScript", description: null }),
];

describe("filterRepos", () => {
  it("returns everything for a blank query", () => {
    expect(filterRepos(repos, "  ")).toEqual(repos);
  });

  it("matches name, language and description case-insensitively", () => {
    expect(filterRepos(repos, "NIM").map((r) => r.id)).toEqual([1]);
    expect(filterRepos(repos, "shell").map((r) => r.id)).toEqual([2]);
    expect(filterRepos(repos, "agent").map((r) => r.id)).toEqual([1]);
    expect(filterRepos(repos, "dev/port").map((r) => r.id)).toEqual([3]);
  });

  it("keeps the selected repo even when it doesn't match", () => {
    const ids = filterRepos(repos, "shell", "https://github.com/dev/nimbus").map((r) => r.id);
    expect(ids).toEqual([1, 2]);
  });
});
