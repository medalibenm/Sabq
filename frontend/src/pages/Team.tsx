import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "../api/client";
import type { InviteResult, Me, Member } from "../api/client";
import { LoadError } from "../components/bits";
import { Mail } from "../components/icons";
import { roleLabel } from "../components/Shell";
import { fill, initials } from "../lib/text";
import { relative, useNow } from "../lib/time";
import { usePrefs } from "../prefs";

type Role = "admin" | "editor" | "viewer";

function InviteForm({ onSent }: { onSent: (result: InviteResult) => void }) {
  const { L } = usePrefs();
  const client = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("editor");
  const [error, setError] = useState<string | null>(null);
  const invite = useMutation({
    mutationFn: () => api.invite(email.trim(), role, name.trim()),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ["team"] });
      onSent(result);
    },
    onError: (failure) => {
      const status = failure instanceof ApiError ? failure.status : 0;
      setError(
        status === 409
          ? L.inviteExists
          : status === 403
            ? L.inviteForbidden
            : status === 400
              ? L.inviteBadEmail
              : L.genericError,
      );
    },
  });
  const roles: { key: Role; name: string; description: string }[] = [
    { key: "admin", name: L.roleAdmin, description: L.descAdmin },
    { key: "editor", name: L.roleEditor, description: L.descEditor },
    { key: "viewer", name: L.roleViewer, description: L.descViewer },
  ];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!email.includes("@")) {
      setError(L.inviteBadEmail);
      return;
    }
    invite.mutate();
  };

  return (
    <form className="invite-form" onSubmit={submit} noValidate>
      <h2>{L.invite}</h2>
      <div className="field">
        <label htmlFor="invite-email">{L.email}</label>
        <input
          id="invite-email"
          className="input latin"
          type="email"
          dir="ltr"
          placeholder="name@newsroom.dz"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="invite-name">{L.displayName}</label>
        <input
          id="invite-name"
          className="input"
          type="text"
          maxLength={200}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <fieldset className="roles" role="radiogroup">
        <legend>{L.role}</legend>
        {roles.map((option) => (
          <button
            key={option.key}
            type="button"
            role="radio"
            aria-checked={role === option.key}
            className="role"
            onClick={() => setRole(option.key)}
          >
            <span className="role-dot" aria-hidden="true" />
            <span>
              <strong>{option.name}</strong>
              <small>{option.description}</small>
            </span>
          </button>
        ))}
      </fieldset>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <button type="submit" className="btn primary" disabled={invite.isPending}>
        {L.sendInvite}
      </button>
      <p className="timezone-note">{L.inviteExpiry}</p>
    </form>
  );
}

function SentState({ result, onAgain }: { result: InviteResult; onAgain: () => void }) {
  const { L } = usePrefs();
  return (
    <div role="status" className="sent">
      <span className={result.email_sent ? "sent-icon" : "sent-icon warn"}>
        <Mail size={20} width={2.4} />
      </span>
      <h2>{result.email_sent ? L.sentTitle : L.notSentTitle}</h2>
      {result.email_sent ? (
        <>
          <p>
            {L.sentTo}{" "}
            <bdi dir="ltr" className="strong latin">
              {result.email}
            </bdi>{" "}
            {fill(L.sentAs, { role: roleLabel(L, result.role) })}
          </p>
          <p className="small">{L.sentNext}</p>
        </>
      ) : (
        <p>{L.notSentBody}</p>
      )}
      <button type="button" className="btn primary" onClick={onAgain}>
        {L.inviteAnother}
      </button>
    </div>
  );
}

function MemberRow({ member, me }: { member: Member; me: Me }) {
  const { L, lang } = usePrefs();
  const client = useQueryClient();
  const now = useNow();
  const [resent, setResent] = useState(false);
  const refresh = () => client.invalidateQueries({ queryKey: ["team"] });
  const resend = useMutation({
    mutationFn: () => api.invite(member.email, member.role, member.display_name),
    onSuccess: () => {
      setResent(true);
      refresh();
    },
  });
  const cancel = useMutation({ mutationFn: () => api.cancelInvite(member.id), onSuccess: refresh });
  const pending = member.status === "invited";
  const name = member.display_name || member.email;
  return (
    <li className="member">
      <span className={pending ? "avatar pending" : "avatar"} aria-hidden="true">
        {initials(name)}
      </span>
      <span className="member-who">
        <span className="strong">
          {name} {member.id === me.id && L.you}
        </span>
        <span dir="ltr" className="member-email latin">
          {member.email}
        </span>
      </span>
      <span className="member-role">{roleLabel(L, member.role)}</span>
      <span className={pending ? "member-state pending" : "member-state"}>
        {pending && <Mail size={13} width={2.4} />}
        {pending
          ? fill(L.invitePending, {
              when: member.invited_at ? relative(member.invited_at, now, lang) : "",
            })
          : L.active}
      </span>
      <span className="member-actions">
        {pending && (
          <>
            <button
              type="button"
              className="btn ghost tiny"
              disabled={resend.isPending || resent}
              onClick={() => resend.mutate()}
            >
              {resent ? L.resent : L.resend}
            </button>
            <button
              type="button"
              className="btn quiet tiny"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              {L.cancel}
            </button>
          </>
        )}
      </span>
    </li>
  );
}

export function Team({ me }: { me: Me }) {
  const { L, count } = usePrefs();
  const [sent, setSent] = useState<InviteResult | null>(null);
  const team = useQuery({ queryKey: ["team"], queryFn: api.team });
  const members = team.data ?? [];
  const pending = members.filter((member) => member.status === "invited").length;

  return (
    <main className="main page">
      <div className="team-layout">
        <div className="page-head">
          <div>
            <h1>{fill(L.teamHeadingOf, { org: me.organisation.name })}</h1>
            <p>{L.teamSub}</p>
          </div>
        </div>
        <div className="team-columns">
          <section className="invite">
            {sent ? (
              <SentState result={sent} onAgain={() => setSent(null)} />
            ) : (
              <InviteForm onSent={setSent} />
            )}
          </section>
          <section aria-labelledby="members-heading" className="members">
            <div className="members-head">
              <h2 id="members-heading">{L.members}</h2>
              {team.data && (
                <span className="soft">
                  {count("membersCount", members.length - pending)}
                  {pending > 0 && ` · ${count("pendingInvites", pending)}`}
                </span>
              )}
            </div>
            {team.isError && <LoadError onRetry={() => team.refetch()} />}
            <ul>
              {members.map((member) => (
                <MemberRow key={member.id} member={member} me={me} />
              ))}
            </ul>
          </section>
        </div>
      </div>
    </main>
  );
}
