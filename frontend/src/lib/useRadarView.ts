// Articles or Events: in the URL so a view can be linked, remembered per user for the next visit.

import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export type RadarView = "articles" | "events";

const storageKey = (userId: number) => `sabq.radarView.${userId}`;

function isView(value: string | null): value is RadarView {
  return value === "articles" || value === "events";
}

function remembered(userId: number): RadarView {
  try {
    const value = localStorage.getItem(storageKey(userId));
    return isView(value) ? value : "articles";
  } catch {
    return "articles";
  }
}

export function useRadarView(userId: number) {
  const [params, setParams] = useSearchParams();
  const inUrl = params.get("view");
  const view = isView(inUrl) ? inUrl : remembered(userId);

  const putInUrl = useCallback(
    (next: RadarView) =>
      setParams(
        (previous) => {
          const updated = new URLSearchParams(previous);
          updated.set("view", next);
          return updated;
        },
        { replace: true },
      ),
    [setParams],
  );

  const setView = useCallback(
    (next: RadarView) => {
      try {
        localStorage.setItem(storageKey(userId), next);
      } catch {
        // private window: the choice lasts until the page closes
      }
      putInUrl(next);
    },
    [userId, putInUrl],
  );

  return { view, setView, putInUrl, inUrl: isView(inUrl) };
}
