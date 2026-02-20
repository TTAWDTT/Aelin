import React, { Suspense } from "react";
import { SWRConfig } from "swr";
import { BrowserRouter, HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { fetchJson } from "./api";
import { ThemeProvider } from "./theme";
import { ToastProvider } from "./contexts/ToastContext";
import { isNativeMobileShell } from "./mobile/runtime";

const Aelin = React.lazy(() => import("./components/Aelin"));
const Settings = React.lazy(() => import("./components/Settings"));
const NotFound = React.lazy(() => import("./components/NotFound"));

function RouteLoadingFallback() {
  return (
    <Box display="flex" alignItems="center" justifyContent="center" minHeight="100vh">
      <CircularProgress size={28} />
    </Box>
  );
}

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <Suspense fallback={<RouteLoadingFallback />}>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Aelin />} />
          <Route path="/chat" element={<Navigate to="/" replace />} />
          <Route path="/desk" element={<Navigate to="/?panel=desk" replace />} />
          <Route path="/dashboard" element={<Navigate to="/?panel=desk" replace />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AnimatePresence>
    </Suspense>
  );
}

export default function App() {
  const RouterComponent = isNativeMobileShell() ? HashRouter : BrowserRouter;
  return (
    <ThemeProvider>
      <ToastProvider>
        <ErrorBoundary>
          <SWRConfig
            value={{
              fetcher: (key: string) => fetchJson(key),
              shouldRetryOnError: true,
              errorRetryCount: 3,
              errorRetryInterval: 2000,
              revalidateOnFocus: true,
              focusThrottleInterval: 10000,
            }}
          >
            <RouterComponent>
              <AnimatedRoutes />
            </RouterComponent>
          </SWRConfig>
        </ErrorBoundary>
      </ToastProvider>
    </ThemeProvider>
  );
}
