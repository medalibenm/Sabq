import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { api } from "../api/client";
import type { Me, Source, SourceRequest } from "../api/client";
import { LangTag, LoadError, StateBadge, useWilayaLabel } from "../components/bits";
import { Check, Clock, Close, StateOk, StateStopped } from "../components/icons";
import { fill } from "../lib/text";
import { date, relative, useNow } from "../lib/time";
import { usePrefs } from "../prefs";

type Prefs = ReturnType<typeof usePrefs>;

const REFRESH_MS = 30_000;
const STATE_ORDER: Record<string, number> = { stopped: 0, delayed: 1, ok: 2 };

function kindLabel(L: Prefs["L"], kind: string) {
  return (
    {
      agency: L.kindAgency,
      official: L.kindOfficial,
      national: L.kindNational,
      local: L.kindLocal,
      international: L.kindInternational,
    }[kind] ?? kind
  );
}

function rhythmLabel({ L, count }: Prefs, source: Source) {
  const { edition_hour: hour, articles_per_day: perDay } = source;
  if (hour != null) {
    return hour === 23 || hour === 0 ? L.rhythmMidnight : fill(L.rhythmEdition, { hour });
  }
  if (perDay == null) return L.rhythmLearning;
  if (perDay >= 1) return count("perDay", Math.round(perDay));
  return count("perWeek", Math.max(1, Math.round(perDay * 7)));
}

function useNote() {
  const { L, lang } = usePrefs();
  const now = useNow();
  return (source: Source) => {
    if (source.state === "delayed") return L.noteDelayed;
    if (source.state !== "stopped") return null;
    return source.state_since
      ? fill(L.noteStoppedSince, { since: relative(source.state_since, now, lang) })
      : L.noteStopped;
  };
}

function Summary({ sources }: { sources: Source[] }) {
  const { L } = usePrefs();
  const n = (state: string) => sources.filter((source) => source.state === state).length;
  return (
    <div className="summary">
      <span className="summary-pill ok">
        <StateOk size={13} width={2.4} />
        {n("ok")} {L.stateOk}
      </span>
      {n("delayed") > 0 && (
        <span className="summary-pill warn">
          <Clock size={13} width={2.4} />
          {n("delayed")} {L.stateDelayed}
        </span>
      )}
      {n("stopped") > 0 && (
        <span className="summary-pill bad">
          <StateStopped size={13} width={2.4} />
          {n("stopped")} {L.stateStopped}
        </span>
      )}
    </div>
  );
}

function SourceTable({ sources }: { sources: Source[] }) {
  const prefs = usePrefs();
  const { L, lang } = prefs;
  const now = useNow();
  const wilaya = useWilayaLabel();
  const note = useNote();
  const checked = (source: Source) =>
    source.last_checked_at ? relative(source.last_checked_at, now, lang, true) : L.neverChecked;

  return (
    <>
      <div className="table-wrap desktop-only">
        <table>
          <thead>
            <tr>
              <th scope="col">{L.colSource}</th>
              <th scope="col">{L.colType}</th>
              <th scope="col">{L.colWilaya}</th>
              <th scope="col">{L.colState}</th>
              <th scope="col">{L.colChecked}</th>
              <th scope="col">{L.colRhythm}</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.slug} className={`row-${source.state}`}>
                <th scope="row">
                  <span className="source-name">
                    <bdi>{source.name}</bdi>
                    <LangTag language={source.language} small />
                  </span>
                  {note(source) && <span className="source-note">{note(source)}</span>}
                </th>
                <td className="soft">{kindLabel(L, source.kind)}</td>
                <td>
                  <span className="chips">
                    {source.wilayas.map((code) => (
                      <span className="chip nowrap" key={code}>
                        {wilaya(code)}
                      </span>
                    ))}
                  </span>
                </td>
                <td>
                  <StateBadge state={source.state} />
                </td>
                <td className="soft nowrap">{checked(source)}</td>
                <td className="soft">{rhythmLabel(prefs, source)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="source-cards mobile-only">
        {sources.map((source) => (
          <div key={source.slug} className={`source-card card-${source.state}`}>
            <div className="source-card-top">
              <span className="source-name">
                <bdi>{source.name}</bdi>
                <LangTag language={source.language} small />
              </span>
              <span className="grow" />
              <StateBadge state={source.state} />
            </div>
            <span className="soft">
              {kindLabel(L, source.kind)} · {source.wilayas.map(wilaya).join("، ")} · {checked(source)}
            </span>
            <span className="soft">{rhythmLabel(prefs, source)}</span>
            {note(source) && <span className="source-card-note">{note(source)}</span>}
          </div>
        ))}
      </div>
    </>
  );
}

function RequestForm() {
  const { L } = usePrefs();
  const client = useQueryClient();
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: () => api.requestSource(url.trim(), note.trim()),
    onSuccess: () => {
      setUrl("");
      setNote("");
      client.invalidateQueries({ queryKey: ["source-requests"] });
    },
    onError: () => setError(L.genericError),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!/^https?:\/\/\S+\.\S+/.test(url.trim())) {
      setError(L.badUrl);
      return;
    }
    send.mutate();
  };

  return (
    <form id="request" className="panel-form" onSubmit={submit} noValidate>
      <h2>{L.requestTitle}</h2>
      <p>{L.requestSub}</p>
      <div className="field">
        <label htmlFor="request-url">{L.url}</label>
        <input
          id="request-url"
          className="input latin"
          type="url"
          dir="ltr"
          placeholder="https://"
          value={url}
          aria-invalid={error === L.badUrl}
          onChange={(event) => setUrl(event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="request-note">
          {L.note} <span className="faint">{L.optional}</span>
        </label>
        <textarea
          id="request-note"
          className="input"
          rows={3}
          maxLength={1000}
          placeholder={L.notePlaceholder}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <button type="submit" className="btn primary" disabled={send.isPending}>
        {L.send}
      </button>
    </form>
  );
}

function RequestRow({ request }: { request: SourceRequest }) {
  const { L, lang } = usePrefs();
  const kind =
    request.status === "added" ? "added" : request.status === "refused" ? "declined" : "pending";
  return (
    <div className="request">
      <div className="request-top">
        <span dir="ltr" className="request-url ellipsis latin">
          {request.url}
        </span>
        <span className={`request-state ${kind}`}>
          {kind === "pending" && <Clock size={12} width={2.6} />}
          {kind === "added" && <Check size={12} width={2.8} />}
          {kind === "declined" && <Close size={12} width={2.8} />}
          {L[kind]}
        </span>
      </div>
      <span className="faint">{fill(L.sentOn, { date: date(request.created_at, lang) })}</span>
      {request.reason && (
        <p className="request-reason">{fill(L.declinedReason, { reason: request.reason })}</p>
      )}
    </div>
  );
}

export function Sources({ me }: { me: Me }) {
  const { L, count } = usePrefs();
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: api.sources,
    refetchInterval: REFRESH_MS,
  });
  const requests = useQuery({ queryKey: ["source-requests"], queryFn: api.sourceRequests });
  const rows = [...(sources.data ?? [])].sort(
    (a, b) => (STATE_ORDER[a.state] ?? 3) - (STATE_ORDER[b.state] ?? 3),
  );

  return (
    <main className="main page">
      <div className="sources-layout">
        <section aria-labelledby="sources-heading" className="sources-main">
          <div className="page-head">
            <div>
              <h1 id="sources-heading">{L.sourcesHeading}</h1>
              {sources.data && <p>{count("sources", rows.length)}</p>}
            </div>
            {sources.data && <Summary sources={rows} />}
          </div>
          {sources.isError && <LoadError onRetry={() => sources.refetch()} />}
          {sources.data && <SourceTable sources={rows} />}
          <p className="timezone-note">{L.rhythmHint}</p>
        </section>

        <aside className="sources-side">
          {me.role === "viewer" ? <p className="soft">{L.viewerNoRequests}</p> : <RequestForm />}
          <section aria-labelledby="my-requests" className="requests">
            <h2 id="my-requests">{L.myRequests}</h2>
            {requests.data?.length === 0 && <p className="request-none">{L.noRequests}</p>}
            {requests.data?.map((request) => <RequestRow key={request.id} request={request} />)}
          </section>
        </aside>
      </div>
    </main>
  );
}
