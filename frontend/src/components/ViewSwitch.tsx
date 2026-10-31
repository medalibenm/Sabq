// The Articles / Events choice: above the stream on a wide screen, under the header on a small one.

import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { StoryState } from "../api/client";
import { useFilters } from "../lib/useFilters";
import { useRadarView } from "../lib/useRadarView";
import type { RadarView } from "../lib/useRadarView";
import { usePrefs } from "../prefs";
import { Segmented } from "./bits";
import { useFacets } from "./FilterRail";

const REFRESH_MS = 60_000;
export const STORIES_LIMIT = 50; // the API's default: more may exist, so the count must not look exact

export function useStories(state: StoryState) {
  const { filters } = useFilters();
  return useQuery({
    queryKey: ["stories", filters, state],
    queryFn: () => api.stories(filters, state),
    refetchInterval: REFRESH_MS,
    placeholderData: (previous) => previous,
  });
}

export function ViewSwitch({ userId, className = "" }: { userId: number; className?: string }) {
  const { L } = usePrefs();
  const { view, setView } = useRadarView(userId);
  const articles = useFacets().data?.total;
  const events = useStories("all").data?.length;

  const eventCount = events === undefined ? undefined : `${events}${events >= STORIES_LIMIT ? "+" : ""}`;
  const withCount = (label: string, n: number | string | undefined) =>
    // isolated so that "50+" keeps its order inside Arabic text
    n === undefined ? label : `${label} · ⁦${n}⁩`;

  return (
    <Segmented<RadarView>
      label={L.views}
      value={view}
      onChange={setView}
      className={`view-switch ${className}`}
      options={[
        { value: "articles", label: withCount(L.viewArticles, articles), hint: L.viewArticlesHint },
        { value: "events", label: withCount(L.viewEvents, eventCount), hint: L.viewEventsHint },
      ]}
    />
  );
}
