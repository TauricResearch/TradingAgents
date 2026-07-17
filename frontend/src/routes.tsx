import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "./app/AppShell";
import { SkeletonCard } from "./components/ui/skeleton";

const HomePage = lazy(() => import("./features/home/HomePage"));
const WorkspacePage = lazy(() => import("./features/workspace/WorkspacePage"));
const DecisionsPage = lazy(() => import("./features/decisions/DecisionsPage"));
const PortfolioPage = lazy(() => import("./features/portfolio/PortfolioPage"));
const TrackRecordPage = lazy(
  () => import("./features/track-record/TrackRecordPage"),
);
const IntelPage = lazy(() => import("./features/intelligence/IntelPage"));
const SettingsPage = lazy(() => import("./features/settings/SettingsPage"));
const ReportPage = lazy(() => import("./features/report/ReportPage"));

const page = (element: React.ReactNode) => (
  <Suspense fallback={<SkeletonCard lines={6} />}>{element}</Suspense>
);

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: page(<HomePage />) },
      { path: "trade", element: <Navigate to="/trade/BTC-USD" replace /> },
      { path: "trade/:symbol", element: page(<WorkspacePage />) },
      { path: "decisions", element: page(<DecisionsPage />) },
      { path: "decisions/:runId", element: page(<DecisionsPage />) },
      { path: "portfolio", element: page(<PortfolioPage />) },
      { path: "track-record", element: page(<TrackRecordPage />) },
      { path: "intel", element: page(<IntelPage />) },
      { path: "settings", element: page(<SettingsPage />) },
      { path: "report", element: page(<ReportPage />) },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
