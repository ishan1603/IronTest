import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { Spinner } from "./components/ui";
import Landing from "./pages/Landing";
import AuthCallback from "./pages/AuthCallback";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import RepoRun from "./pages/RepoRun";
import Analytics from "./pages/Analytics";
import RunDetail from "./pages/RunDetail";
import PublicReport from "./pages/PublicReport";

function RequireAuth({ children }) {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }
  if (status === "signed-out") return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/r/:token" element={<PublicReport />} />
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/runs"
            element={
              <RequireAuth>
                <Analytics />
              </RequireAuth>
            }
          />
          <Route
            path="/runs/:runId"
            element={
              <RequireAuth>
                <RunDetail />
              </RequireAuth>
            }
          />
          <Route
            path="/repo/:repoId"
            element={
              <RequireAuth>
                <RepoRun />
              </RequireAuth>
            }
          />
          <Route
            path="/chat/:chatId"
            element={
              <RequireAuth>
                <Chat />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
