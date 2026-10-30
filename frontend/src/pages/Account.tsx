import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { api } from "../api/client";
import type { Me } from "../api/client";
import { Segmented } from "../components/bits";
import { Logout } from "../components/icons";
import { roleLabel, useLogout } from "../components/Shell";
import { usePrefs } from "../prefs";
import type { ThemeChoice } from "../prefs";

export function Account({ me }: { me: Me }) {
  const { L, lang, setLang, themeChoice, setTheme } = usePrefs();
  const client = useQueryClient();
  const logout = useLogout();
  const [name, setName] = useState(me.display_name);
  const save = useMutation({
    mutationFn: () => api.updateMe(name.trim()),
    onSuccess: (updated) => client.setQueryData(["me"], updated),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim()) save.mutate();
  };

  return (
    <main className="main page">
      <div className="account">
        <h1>{L.accountHeading}</h1>

        <section aria-labelledby="account-profile" className="panel">
          <h2 id="account-profile">{L.profile}</h2>
          <div className="panel-body">
            <form className="field" onSubmit={submit}>
              <label htmlFor="account-name">{L.displayName}</label>
              <div className="inline-field">
                <input
                  id="account-name"
                  className="input"
                  type="text"
                  maxLength={200}
                  value={name}
                  onChange={(event) => {
                    setName(event.target.value);
                    save.reset();
                  }}
                />
                <button type="submit" className="btn primary" disabled={save.isPending}>
                  {save.isSuccess ? L.saved : L.save}
                </button>
              </div>
              {save.isError && (
                <p role="alert" className="form-error">
                  {L.genericError}
                </p>
              )}
            </form>
            <dl className="profile-facts">
              <div>
                <dt>{L.email}</dt>
                <dd dir="ltr" className="latin email">
                  {me.email}
                </dd>
              </div>
              <div>
                <dt>{L.role}</dt>
                <dd>{roleLabel(L, me.role)}</dd>
              </div>
              <div>
                <dt>{L.organisation}</dt>
                <dd>{me.organisation.name}</dd>
              </div>
            </dl>
            <p className="timezone-note">{L.emailNote}</p>
          </div>
        </section>

        <section aria-labelledby="account-prefs" className="panel">
          <h2 id="account-prefs">{L.preferences}</h2>
          <div className="panel-body">
            <div className="pref">
              <div>
                <strong>{L.interfaceLanguage}</strong>
                <span>{L.languageHint}</span>
              </div>
              <Segmented
                label={L.interfaceLanguage}
                value={lang}
                onChange={setLang}
                options={[
                  { value: "ar", label: "العربية", lang: "ar" },
                  { value: "fr", label: "Français", lang: "fr" },
                ]}
              />
            </div>
            <div className="pref">
              <div>
                <strong>{L.theme}</strong>
                <span>{L.themeHint}</span>
              </div>
              <Segmented<ThemeChoice>
                label={L.theme}
                value={themeChoice}
                onChange={setTheme}
                options={[
                  { value: "light", label: L.light },
                  { value: "dark", label: L.dark },
                  { value: "system", label: L.system },
                ]}
              />
            </div>
          </div>
        </section>

        <section aria-labelledby="account-session" className="panel session">
          <div>
            <h2 id="account-session">{L.session}</h2>
            <span>{L.sessionHint}</span>
          </div>
          <button type="button" className="btn ghost" onClick={() => logout.mutate()}>
            <Logout />
            {L.logout}
          </button>
        </section>
      </div>
    </main>
  );
}
