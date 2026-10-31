export interface RepoSummary {
  id: number;
  name: string;
  full_name: string;
  html_url: string;
  stargazers_count: number;
  language?: string | null;
  description?: string | null;
  private?: boolean;
}

/**
 * Case-insensitive match on name, owner/name, language and description.
 * The currently selected repo is always kept, so a filtered <select> never loses its value.
 */
export function filterRepos<T extends RepoSummary>(repos: T[], query: string, selectedUrl = ""): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return repos;
  return repos.filter((r) => {
    if (selectedUrl && r.html_url === selectedUrl) return true;
    return [r.name, r.full_name, r.language, r.description].some(
      (field) => typeof field === "string" && field.toLowerCase().includes(q)
    );
  });
}
