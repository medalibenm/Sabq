// The frame around every signed-in screen: top bar, navigation, filter rail, drawer, live link.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Me } from "../api/client";
import { LiveProvider, useLive } from "../live";
import { initials } from "../lib/text";
import { useFilters } from "../lib/useFilters";
import { usePrefs } from "../prefs";
import type { ThemeChoice } from "../prefs";
import { rememberWilayas, Segmented } from "./bits";
import { Drawer } from "./Drawer";
import { FilterRail, FilterSheet } from "./FilterRail";
import { Funnel, Logo, Logout, Radar, Feed, Search, Spinner, Team, User } from "./icons";
import { ViewSwitch } from "./ViewSwitch";

const SEARCH_DELAY_MS = 250;

export const roleLabel = (L: ReturnType<typeof usePrefs>["L"], role: string) =>
  ({ owner: L.roleOwner, admin: L.roleAdmin, editor: L.roleEditor, viewer: L.roleViewer })[role] ??
  role;

export const canManageTeam = (me: Me) => me.role === "owner" || me.role === "admin";

export function useLogout() {
  const client = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      client.clear();
      navigate("/login", { replace: true });
    },
  });
}

function LiveIndicator() {
  const { L } = usePrefs();
  const { up } = useLive();
  if (up) {
    return (
      <div role="status" title={L.liveTitle} className="live">
        <span className="live-dot" aria-hidden="true" />
        <span className="live-label">{L.live}</span>
      </div>
    );
  }
  return (
    <div role="status" className="live down">
      <Spinner size={14} />
      <span>{L.reconnecting}</span>
      <button type="button" className="link" onClick={() => window.location.reload()}>
        {L.reload}
      </button>
    </div>
  );
}

function SearchBox({ inputId }: { inputId: string }) {
  const { L } = usePrefs();
  const { filters, setQuery } = useFilters();
  const [value, setValue] = useState(filters.q);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => setValue(filters.q), [filters.q]); // "clear search" from the empty state

  useEffect(() => {
    if (value === filters.q) return;
    const timer = setTimeout(() => setQuery(value), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [value, filters.q, setQuery]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !/INPUT|TEXTAREA/.test(target.tagName)) {
        event.preventDefault();
        input.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="search">
      <label htmlFor={inputId} className="sr-only">
        {L.search}
      </label>
      <Search className="search-icon" />
      <input
        ref={input}
        id={inputId}
        type="search"
        placeholder={L.search}
        value={value}
        maxLength={200}
        onChange={(event) => setValue(event.target.value)}
      />
      <kbd>/</kbd>
    </div>
  );
}

function UserMenu({ me }: { me: Me }) {
  const { L, lang, setLang, themeChoice, theme, setTheme } = usePrefs();
  const logout = useLogout();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const name = me.display_name || me.email;

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="user" ref={root}>
      <button
        type="button"
        className={open ? "user-button open" : "user-button"}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
      >
        <span className="avatar" aria-hidden="true">
          {initials(name)}
        </span>
        <span className="user-names">
          <span className="strong">{name}</span>
          <span className="soft">{me.organisation.name}</span>
        </span>
      </button>
      {open && (
        <div className="menu">
          <div className="menu-who">
            <span className="strong">{name}</span>
            <span className="soft email" dir="ltr">
              {me.email}
            </span>
            <span className="soft">
              {me.organisation.name} · {roleLabel(L, me.role)}
            </span>
          </div>
          <div className="menu-group">
            <span className="menu-label">{L.language}</span>
            <Segmented
              label={L.language}
              value={lang}
              onChange={setLang}
              options={[
                { value: "ar", label: "العربية", lang: "ar" },
                { value: "fr", label: "Français", lang: "fr" },
              ]}
            />
          </div>
          <div className="menu-group divided">
            <span className="menu-label">{L.theme}</span>
            <Segmented<ThemeChoice>
              label={L.theme}
              value={themeChoice === "system" ? theme : themeChoice}
              onChange={setTheme}
              options={[
                { value: "light", label: L.light },
                { value: "dark", label: L.dark },
              ]}
            />
          </div>
          <Link className="menu-item" to="/account" onClick={() => setOpen(false)}>
            <User />
            {L.account}
          </Link>
          <button type="button" className="menu-item" onClick={() => logout.mutate()}>
            <Logout />
            {L.logout}
          </button>
        </div>
      )}
    </div>
  );
}

function TopBar({ me, radar, title }: { me: Me; radar: boolean; title: string }) {
  const { L } = usePrefs();
  const { activeCount } = useFilters();
  const [searching, setSearching] = useState(false);
  const [sheet, setSheet] = useState(false);
  const closeSheet = useRef(() => setSheet(false)).current;

  return (
    <div className="top">
      <header className="topbar">
        <Link to="/radar" aria-label={L.home} className="brand">
          <Logo />
          <span>{L.brand}</span>
        </Link>
        {radar ? (
          <div className="desktop-only search-slot">
            <SearchBox inputId="search" />
          </div>
        ) : (
          <h1 className="page-title">{title}</h1>
        )}
        <span className="grow" />
        <LiveIndicator />
        {radar && (
          <button
            type="button"
            className="icon-btn mobile-only"
            aria-label={L.searchShort}
            aria-expanded={searching}
            onClick={() => setSearching(!searching)}
          >
            <Search size={20} />
          </button>
        )}
        <div className="desktop-only">
          <UserMenu me={me} />
        </div>
      </header>
      {radar && (
        <div className="mobile-tabs mobile-only">
          <ViewSwitch userId={me.id} />
          <button type="button" className="filter-button" onClick={() => setSheet(true)}>
            <Funnel />
            {L.filtersShort}
            {activeCount > 0 && <span className="count-badge">{activeCount}</span>}
          </button>
        </div>
      )}
      {radar && searching && (
        <div className="mobile-search mobile-only">
          <SearchBox inputId="search-mobile" />
        </div>
      )}
      {sheet && <FilterSheet onClose={closeSheet} />}
    </div>
  );
}

function Navigation({ me, className }: { me: Me; className: string }) {
  const { L } = usePrefs();
  const { pathname } = useLocation();
  const inRadar = pathname === "/radar";
  return (
    <nav aria-label={L.mainNav} className={className}>
      <Link to="/radar" className={inRadar ? "active" : undefined} aria-current={inRadar ? "page" : undefined}>
        <span className="nav-icon">
          <Radar size={20} />
        </span>
        {L.radar}
      </Link>
      <NavLink to="/sources">
        <span className="nav-icon">
          <Feed size={20} />
        </span>
        {L.sources}
      </NavLink>
      {canManageTeam(me) && (
        <NavLink to="/team">
          <span className="nav-icon">
            <Team size={20} />
          </span>
          {L.team}
        </NavLink>
      )}
      <NavLink to="/account">
        <span className="nav-icon">
          <User size={20} />
        </span>
        {L.account}
      </NavLink>
    </nav>
  );
}

function Frame({ me }: { me: Me }) {
  const { L } = usePrefs();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const radar = pathname === "/radar";
  const titles: Record<string, string> = {
    "/sources": L.sources,
    "/team": L.team,
    "/account": L.account,
  };
  const wilayas = useQuery({ queryKey: ["wilayas"], queryFn: api.wilayas });
  if (wilayas.data) rememberWilayas(wilayas.data);

  return (
    <div className="app">
      <TopBar me={me} radar={radar} title={titles[pathname] ?? ""} />
      <div className="workspace">
        <Navigation me={me} className="sidenav" />
        {radar && (
          <div className="desktop-only rail-slot">
            <FilterRail />
          </div>
        )}
        <Outlet />
      </div>
      <Navigation me={me} className="bottomnav" />
      {params.has("article") && <Drawer />}
    </div>
  );
}

export function Shell({ me }: { me: Me }) {
  return (
    <LiveProvider>
      <Frame me={me} />
    </LiveProvider>
  );
}
