// Same-origin calls with the session cookie. Types come from docs/openapi.json (`npm run api`).
// Every write sends JSON: the backend's CSRF rule refuses anything else (decisions 2026-10-25).

import type { components } from "./schema";
import type { Filters } from "../lib/stream";

type Schemas = components["schemas"];
export type Article = Schemas["ArticleOut"];
export type ArticleDetail = Schemas["ArticleDetail"];
export type StoryPeer = Schemas["StoryPeer"];
export type ArticlePage = Schemas["ArticlePage"];
export type Story = Schemas["StoryOut"];
export type Source = Schemas["SourceOut"];
export type Wilaya = Schemas["WilayaOut"];
export type Facets = Schemas["FacetsOut"];
export type Member = Schemas["MemberOut"];
export type Me = Schemas["MeOut"];
export type SourceRequest = Schemas["SourceRequestOut"];
export type InviteResult = Schemas["InviteOut"];
export type LinkInfo = Schemas["LinkOut"];
export type StoryState = "all" | "developing" | "closed";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly retryAfter: number | null = null,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: method === "GET" ? undefined : { "Content-Type": "application/json" },
    body: method === "GET" ? undefined : JSON.stringify(body ?? {}),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      // not JSON: the status text will do
    }
    const retry = Number(response.headers.get("Retry-After"));
    throw new ApiError(response.status, detail, retry > 0 ? retry : null);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function query(filters: Partial<Filters>, extra: Record<string, string | undefined> = {}): string {
  const params = new URLSearchParams();
  filters.wilayas?.forEach((code) => params.append("wilaya", code));
  filters.sources?.forEach((slug) => params.append("source", slug));
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  for (const [key, value] of Object.entries(extra)) {
    if (value) params.set(key, value);
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const api = {
  me: () => request<Me>("GET", "/auth/me"),
  login: (email: string, password: string) =>
    request<Me>("POST", "/auth/login", { email, password }),
  logout: () => request<void>("POST", "/auth/logout"),
  updateMe: (display_name: string) => request<Me>("PATCH", "/auth/me", { display_name }),
  forgot: (email: string) => request<unknown>("POST", "/auth/forgot", { email }),
  link: (kind: "invite" | "reset", token: string) =>
    request<LinkInfo>("GET", `/auth/link${query({}, { kind, token })}`),
  acceptInvite: (token: string, password: string, display_name: string) =>
    request<Me>("POST", "/auth/accept-invite", { token, password, display_name }),
  reset: (token: string, password: string) =>
    request<Me>("POST", "/auth/reset", { token, password }),

  articles: (filters: Filters, cursor?: string) =>
    request<ArticlePage>("GET", `/app/articles${query(filters, { cursor })}`),
  article: (id: number) => request<ArticleDetail>("GET", `/app/articles/${id}`),
  facets: (filters: Filters) => request<Facets>("GET", `/app/facets${query(filters)}`),
  stories: (filters: Filters, state: StoryState) =>
    request<Story[]>("GET", `/app/stories${query(filters, { state })}`),
  sources: () => request<Source[]>("GET", "/app/sources"),
  wilayas: () => request<Wilaya[]>("GET", "/app/wilayas"),
  sourceRequests: () => request<SourceRequest[]>("GET", "/app/source-requests"),
  requestSource: (url: string, note: string) =>
    request<SourceRequest>("POST", "/app/source-requests", { url, note }),

  team: () => request<Member[]>("GET", "/app/team"),
  invite: (email: string, role: string, display_name: string) =>
    request<InviteResult>("POST", "/auth/invite", { email, role, display_name }),
  cancelInvite: (id: number) => request<void>("DELETE", `/app/team/${id}`),
};
