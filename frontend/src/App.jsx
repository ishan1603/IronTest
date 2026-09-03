import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
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
import Integrations from "./pages/Integrations";

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

const protect = (element) => <RequireAuth>{element}</RequireAuth>;

/** Cross-fades between routes; a hair of vertical travel, no layout jump. */
function AnimatedRoutes() {
  const location = useLocation();
  const reduce = useReducedMotion();

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={reduce ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
      >
        <Routes location={location}>
          <Route path="/" element={<Landing />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/r/:token" element={<PublicReport />} />
          <Route path="/dashboard" element={protect(<Dashboard />)} />
          <Route path="/runs" element={protect(<Analytics />)} />
          <Route path="/runs/:runId" element={protect(<RunDetail />)} />
          <Route path="/integrations" element={protect(<Integrations />)} />
          <Route path="/repo/:repoId" element={protect(<RepoRun />)} />
          <Route path="/chat/:chatId" element={protect(<Chat />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AnimatedRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
