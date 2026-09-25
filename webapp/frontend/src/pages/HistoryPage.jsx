import { HistoryTape } from "../components/HistoryTape";

export function HistoryPage() {
  return (
    <main className="app-main app-main--single">
      <div className="card">
        <HistoryTape limit={50} showFilters title="full tape" />
      </div>
    </main>
  );
}
