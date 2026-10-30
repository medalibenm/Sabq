// Login, invitations and password reset. The email links land on /accept-invite and
// /reset-password (backend `auth/mail.py`).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../api/client";
import type { Me } from "../api/client";
import { Alert, BrokenLink, Clock, Logo, Mail, Spinner } from "../components/icons";
import { roleLabel } from "../components/Shell";
import { fill } from "../lib/text";
import { usePrefs } from "../prefs";

const MIN_PASSWORD = 10;

function AuthPage({ children }: { children: ReactNode }) {
  const { L, lang, setLang } = usePrefs();
  return (
    <div className="auth">
      <svg aria-hidden="true" className="auth-rings" viewBox="0 0 1200 1200" fill="none">
        <circle cx="600" cy="600" r="220" />
        <circle cx="600" cy="600" r="340" />
        <circle cx="600" cy="600" r="460" />
        <circle cx="600" cy="600" r="580" />
      </svg>
      <div className="auth-brand">
        <Logo size={40} />
        <span>{L.brand}</span>
      </div>
      <div className="auth-card">{children}</div>
      <div className="auth-foot">
        <button
          type="button"
          lang={lang === "ar" ? "fr" : "ar"}
          onClick={() => setLang(lang === "ar" ? "fr" : "ar")}
        >
          {L.otherLang}
        </button>
        <span aria-hidden="true">·</span>
        <span>{L.allTimesAlgiers}</span>
      </div>
    </div>
  );
}

function Notice({ tone, children }: { tone: "bad" | "warn"; children: ReactNode }) {
  return (
    <div role="alert" className={`notice ${tone}`}>
      {tone === "bad" ? <Alert size={18} width={2.2} /> : <Clock size={18} width={2.2} />}
      <span>{children}</span>
    </div>
  );
}

function useSignedIn() {
  const client = useQueryClient();
  const navigate = useNavigate();
  return (me: Me, next = "/") => {
    client.setQueryData(["me"], me);
    navigate(next, { replace: true });
  };
}

const safeNext = (next: string | null) =>
  next && next.startsWith("/") && !next.startsWith("//") ? next : "/";

function countdown(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function Login() {
  const { L } = usePrefs();
  const [params] = useSearchParams();
  const signedIn = useSignedIn();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [wrong, setWrong] = useState(false);
  const [failed, setFailed] = useState(false);
  const [waitUntil, setWaitUntil] = useState(0);
  const [, tick] = useState(0);
  const wait = Math.max(0, Math.ceil((waitUntil - Date.now()) / 1000));

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [wait]);

  const login = useMutation({
    mutationFn: () => api.login(email.trim(), password),
    onSuccess: (me) => signedIn(me, safeNext(params.get("next"))),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 429) {
        setWaitUntil(Date.now() + (error.retryAfter ?? 900) * 1000);
      } else if (error instanceof ApiError && error.status === 401) {
        setWrong(true);
      } else {
        setFailed(true);
      }
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setWrong(false);
    setFailed(false);
    login.mutate();
  };

  return (
    <AuthPage>
      <h1>{L.loginTitle}</h1>
      <p className="auth-sub">{L.loginSub}</p>
      {wrong && <Notice tone="bad">{L.wrongLogin}</Notice>}
      {failed && <Notice tone="bad">{L.genericError}</Notice>}
      {wait > 0 && <Notice tone="warn">{L.limited}</Notice>}
      <form className="auth-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="login-email">{L.email}</label>
          <input
            id="login-email"
            className="input tall latin"
            type="email"
            dir="ltr"
            required
            autoComplete="email"
            placeholder="name@newsroom.dz"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="field">
          <div className="label-row">
            <label htmlFor="login-password">{L.password}</label>
            <Link to="/forgot-password">{L.forgotLink}</Link>
          </div>
          <input
            id="login-password"
            className="input tall latin"
            type="password"
            required
            autoComplete="current-password"
            aria-invalid={wrong}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <button type="submit" className="btn primary tall" disabled={login.isPending || wait > 0}>
          {wait > 0 ? fill(L.retryIn, { time: countdown(wait) }) : L.login}
        </button>
      </form>
    </AuthPage>
  );
}

export function ForgotPassword() {
  const { L } = usePrefs();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const forgot = useMutation({
    mutationFn: () => api.forgot(email.trim()),
    onSuccess: () => setSent(true),
  });

  if (sent) {
    return (
      <AuthPage>
        <span className="auth-icon">
          <Mail size={22} />
        </span>
        <h1>{L.checkTitle}</h1>
        <p role="status" className="auth-text">
          {L.checkPre}{" "}
          <bdi dir="ltr" className="strong latin">
            {email.trim()}
          </bdi>
          {L.checkPost}
        </p>
        <p className="auth-small">
          {L.noMail}{" "}
          <button type="button" className="link" onClick={() => forgot.mutate()}>
            {L.resendMail}
          </button>
        </p>
        <Link className="btn ghost" to="/login">
          {L.backToLogin}
        </Link>
      </AuthPage>
    );
  }
  return (
    <AuthPage>
      <h1>{L.forgotTitle}</h1>
      <p className="auth-text">{L.forgotSub}</p>
      {forgot.isError && <Notice tone="bad">{L.genericError}</Notice>}
      <form
        className="auth-form"
        onSubmit={(event) => {
          event.preventDefault();
          forgot.mutate();
        }}
      >
        <div className="field">
          <label htmlFor="forgot-email">{L.email}</label>
          <input
            id="forgot-email"
            className="input tall latin"
            type="email"
            dir="ltr"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <button type="submit" className="btn primary tall" disabled={forgot.isPending}>
          {L.sendLink}
        </button>
      </form>
      <Link className="auth-back" to="/login">
        {L.backToLogin}
      </Link>
    </AuthPage>
  );
}

function Expired({ kind }: { kind: "invite" | "reset" }) {
  const { L } = usePrefs();
  return (
    <AuthPage>
      <span className="auth-icon bad">
        <BrokenLink size={22} />
      </span>
      <h1>{L.expiredTitle}</h1>
      <p role="alert" className="auth-text">
        {kind === "reset" ? L.expiredReset : L.expiredInvite}
      </p>
      {kind === "reset" && (
        <Link className="btn primary tall" to="/forgot-password">
          {L.newLink}
        </Link>
      )}
      <Link className="auth-back" to="/login">
        {L.backToLogin}
      </Link>
    </AuthPage>
  );
}

function useEmailLink(kind: "invite" | "reset") {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const link = useQuery({
    queryKey: ["link", kind, token],
    queryFn: () => api.link(kind, token),
    enabled: Boolean(token),
    retry: false,
    refetchOnWindowFocus: false,
  });
  return { token, link };
}

function PasswordHint({ id }: { id: string }) {
  const { L } = usePrefs();
  return (
    <span id={id} className="field-hint">
      {L.passHint}
    </span>
  );
}

export function AcceptInvite() {
  const { L } = usePrefs();
  const signedIn = useSignedIn();
  const { token, link } = useEmailLink("invite");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const accept = useMutation({
    mutationFn: () => api.acceptInvite(token, password, name.trim()),
    onSuccess: (me) => signedIn(me),
    onError: () => setError(L.genericError),
  });

  if (!token || link.isError) return <Expired kind="invite" />;
  if (!link.data) {
    return (
      <AuthPage>
        <div className="auth-wait">
          <Spinner size={20} />
        </div>
      </AuthPage>
    );
  }
  const info = link.data;
  const role = roleLabel(L, info.role);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD) {
      setError(L.passShort);
      return;
    }
    accept.mutate();
  };

  return (
    <AuthPage>
      <span className="auth-tag">{L.invitation}</span>
      <h1>{fill(L.inviteTitle, { org: info.organisation })}</h1>
      <p className="auth-text">
        {info.invited_by
          ? fill(L.inviteSubBy, { name: info.invited_by, role })
          : fill(L.inviteSub, { role })}
      </p>
      <div className="auth-email">
        <span>{L.email}</span>
        <span dir="ltr" className="strong latin email">
          {info.email}
        </span>
      </div>
      {error && <Notice tone="bad">{error}</Notice>}
      <form className="auth-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="invite-name">{L.displayName}</label>
          <input
            id="invite-name"
            className="input tall"
            type="text"
            maxLength={200}
            autoComplete="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="invite-password">{L.newPassword}</label>
          <input
            id="invite-password"
            className="input tall latin"
            type="password"
            required
            autoComplete="new-password"
            aria-describedby="invite-password-hint"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <PasswordHint id="invite-password-hint" />
        </div>
        <button type="submit" className="btn primary tall" disabled={accept.isPending}>
          {L.join}
        </button>
      </form>
    </AuthPage>
  );
}

export function ResetPassword() {
  const { L } = usePrefs();
  const signedIn = useSignedIn();
  const { token, link } = useEmailLink("reset");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  const reset = useMutation({
    mutationFn: () => api.reset(token, password),
    onSuccess: (me) => signedIn(me),
    onError: (failure) => {
      if (failure instanceof ApiError && failure.status === 400) setGone(true);
      else setError(L.genericError);
    },
  });

  if (!token || link.isError || gone) return <Expired kind="reset" />;
  if (!link.data) {
    return (
      <AuthPage>
        <div className="auth-wait">
          <Spinner size={20} />
        </div>
      </AuthPage>
    );
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD) setError(L.passShort);
    else if (password !== confirm) setError(L.mismatch);
    else reset.mutate();
  };

  return (
    <AuthPage>
      <h1>{L.resetTitle}</h1>
      <p className="auth-sub">{fill(L.resetFor, { email: link.data.email })}</p>
      {error && <Notice tone="bad">{error}</Notice>}
      <form className="auth-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="reset-password">{L.newPassword}</label>
          <input
            id="reset-password"
            className="input tall latin"
            type="password"
            required
            autoComplete="new-password"
            aria-describedby="reset-password-hint"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <PasswordHint id="reset-password-hint" />
        </div>
        <div className="field">
          <label htmlFor="reset-confirm">{L.confirm}</label>
          <input
            id="reset-confirm"
            className="input tall latin"
            type="password"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </div>
        <button type="submit" className="btn primary tall" disabled={reset.isPending}>
          {L.saveAndLogin}
        </button>
      </form>
    </AuthPage>
  );
}
