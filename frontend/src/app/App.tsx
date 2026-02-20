import React, { Suspense } from "react";
import { BrowserRouter, HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { SWRConfig } from "swr";
import { isNativeMobileShell } from "./env";
import { fetchJson } from "../api/client";
import { Shell } from "./layout/Shell";
import { PageLoading } from "./layout/PageLoading";

const ChatPage = React.lazy(() => import("../pages/ChatPage").then((m) => ({ default: m.ChatPage })));
const SignalsPage = React.lazy(() => import("../pages/SignalsPage").then((m) => ({ default: m.SignalsPage })));
const ContactThreadPage = React.lazy(() => import("../pages/SignalsThreadPage").then((m) => ({ default: m.SignalsThreadPage })));
const MessagePage = React.lazy(() => import("../pages/MessagePage").then((m) => ({ default: m.MessagePage })));
const TrackingPage = React.lazy(() => import("../pages/TrackingPage").then((m) => ({ default: m.TrackingPage })));
const TrackingTargetPage = React.lazy(() => import("../pages/TrackingTargetPage").then((m) => ({ default: m.TrackingTargetPage })));
const SettingsPage = React.lazy(() => import("../pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const NotFound = React.lazy(() => import("../pages/NotFound").then((m) => ({ default: m.NotFound })));

export function App() {
  const Router = isNativeMobileShell() ? HashRouter : BrowserRouter;
  return (
    <SWRConfig
      value={{
        fetcher: (key: string) => fetchJson(key),
        shouldRetryOnError: true,
        errorRetryCount: 2,
        errorRetryInterval: 1200,
        revalidateOnFocus: true,
        focusThrottleInterval: 10000,
      }}
    >
      <Router>
        <Suspense fallback={<PageLoading />}>
          <Routes>
            <Route element={<Shell />}>
              <Route path="/" element={<ChatPage />} />
              <Route path="/chat" element={<Navigate to="/" replace />} />
              <Route path="/signals" element={<SignalsPage />} />
              <Route path="/signals/contact/:contactId" element={<ContactThreadPage />} />
              <Route path="/message/:messageId" element={<MessagePage />} />
              <Route path="/tracking" element={<TrackingPage />} />
              <Route path="/tracking/target/:targetId" element={<TrackingTargetPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </Suspense>
      </Router>
    </SWRConfig>
  );
}
