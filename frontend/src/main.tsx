import "@fontsource/ibm-plex-sans-arabic/arabic-400.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-500.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-600.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-700.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-700.css";
import "@fontsource/ibm-plex-sans/latin-ext-400.css";
import "./styles.css";

import { QueryCache, QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { api, ApiError } from "./api/client";
import type { Me } from "./api/client";
import { Spinner } from "./components/icons";
import { canManageTeam, Shell } from "./components/Shell";
import { Account } from "./pages/Account";
import { AcceptInvite, ForgotPassword, Login, ResetPassword } from "./pages/Auth";
import { Radar } from "./pages/Radar";
import { Sources } from "./pages/Sources";
import { Team } from "./pages/Team";
import { PrefsProvider } from "./prefs";

const client: QueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failures, error) =>
        !(error instanceof ApiError && error.status < 500) && failures < 2,
    },
  },
  queryCache: new QueryCache({
    onError: (error) => {
      // the session ended while the app was open
      if (error instanceof ApiError && error.status === 401) client.setQueryData(["me"], null);
    },
  }),
});

async function currentUser(): Promise<Me | null> {
  try {
    return await api.me();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: currentUser, staleTime: 60_000 });
}

function Waiting() {
  return (
    <div className="full-wait">
      <Spinner size={22} />
    </div>
  );
}

/** The old addresses, and "/": filters in the query string come along. */
function ToRadar({ view }: { view?: "events" }) {
  const params = new URLSearchParams(useLocation().search);
  if (view) params.set("view", view);
  return <Navigate to={{ pathname: "/radar", search: params.toString() }} replace />;
}

function SignedIn() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <Waiting />;
  if (!me.data) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={location.pathname === "/" ? "/login" : `/login?next=${next}`} replace />;
  }
  const user = me.data;
  return (
    <Routes>
      <Route element={<Shell me={user} />}>
        <Route index element={<ToRadar />} />
        <Route path="radar" element={<Radar me={user} />} />
        <Route path="stories" element={<ToRadar view="events" />} />
        <Route path="sources" element={<Sources me={user} />} />
        <Route
          path="team"
          element={canManageTeam(user) ? <Team me={user} /> : <Navigate to="/" replace />}
        />
        <Route path="account" element={<Account me={user} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function SignedOut({ page }: { page: React.ReactNode }) {
  const me = useMe();
  if (me.isPending) return <Waiting />;
  return me.data ? <Navigate to="/" replace /> : page;
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <PrefsProvider>
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<SignedOut page={<Login />} />} />
            <Route path="/forgot-password" element={<SignedOut page={<ForgotPassword />} />} />
            <Route path="/accept-invite" element={<AcceptInvite />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/*" element={<SignedIn />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </PrefsProvider>
  </StrictMode>,
);
