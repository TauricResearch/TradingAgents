import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppProvider, useApp } from "./context/AppContext";
import { Navbar } from "./components/Navbar";
import { WelcomePage } from "./pages/WelcomePage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { WatchlistPage } from "./pages/WatchlistPage";
import { ProfilePage } from "./pages/ProfilePage";

function RequireKey({ children }) {
  const { api } = useApp();
  return api.apiKey ? children : <WelcomePage />;
}

function Shell() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route
          path="/"
          element={
            <RequireKey>
              <DashboardPage />
            </RequireKey>
          }
        />
        <Route
          path="/history"
          element={
            <RequireKey>
              <HistoryPage />
            </RequireKey>
          }
        />
        <Route
          path="/watchlist"
          element={
            <RequireKey>
              <WatchlistPage />
            </RequireKey>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireKey>
              <ProfilePage />
            </RequireKey>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <footer className="app-footer">
        Research output only. TradingAgents places no trades and gives no investment advice.
      </footer>
    </>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Shell />
      </AppProvider>
    </BrowserRouter>
  );
}
