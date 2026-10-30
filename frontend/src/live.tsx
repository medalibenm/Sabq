// One live connection for the whole app (`/app/stream`, Server-Sent Events). The browser
// reconnects by itself and sends Last-Event-ID, so the backend replays what was missed.

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import type { Article } from "./api/client";

type Listener = (article: Article) => void;

interface Live {
  up: boolean;
  /** Bumped when the browser fell behind: reload the list instead of waiting for events. */
  resets: number;
  subscribe: (listener: Listener) => () => void;
}

const Context = createContext<Live | null>(null);
const RETRY_MS = 5000;

export function LiveProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const listeners = useRef(new Set<Listener>());
  const [up, setUp] = useState(true);
  const [resets, setResets] = useState(0);

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    function connect() {
      source = new EventSource("/app/stream");
      source.onopen = () => setUp(true);
      source.onerror = () => {
        setUp(false);
        if (source?.readyState === EventSource.CLOSED && !stopped) {
          // the browser gave up (a refused request, not a dropped one): maybe the session ended
          client.invalidateQueries({ queryKey: ["me"] });
          setResets((n) => n + 1);
          retry = setTimeout(connect, RETRY_MS);
        }
      };
      source.addEventListener("article", (event) => {
        const article = JSON.parse(event.data) as Article;
        listeners.current.forEach((listener) => listener(article));
      });
      source.addEventListener("reload", () => setResets((n) => n + 1));
      source.addEventListener("logout", () => {
        source?.close();
        client.invalidateQueries({ queryKey: ["me"] });
      });
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      source?.close();
    };
  }, [client]);

  const subscribe = useRef((listener: Listener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }).current;

  return <Context.Provider value={{ up, resets, subscribe }}>{children}</Context.Provider>;
}

export function useLive(): Live {
  const live = useContext(Context);
  if (!live) throw new Error("useLive outside LiveProvider");
  return live;
}
