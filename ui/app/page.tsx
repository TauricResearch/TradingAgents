import TickerBar from "@/components/TickerBar";
import TopBar from "@/components/TopBar";
import AgentPipeline from "@/components/AgentPipeline";
import MarketOverview from "@/components/MarketOverview";
import AgentStatus from "@/components/AgentStatus";
import AnalystGrid from "@/components/AnalystGrid";
import DebatePanel from "@/components/DebatePanel";
import DecisionPanel from "@/components/DecisionPanel";

export default function Home() {
  return (
    <div className="relative z-1 min-h-screen px-5 pb-5 max-w-[1600px] mx-auto">
      <TickerBar />
      <TopBar />
      <AgentPipeline />

      <main className="grid grid-cols-[1fr_1fr_340px] gap-3">
        {/* Row 1: Market Overview + Agent Status */}
        <MarketOverview />
        <AgentStatus />

        {/* Row 2: Analyst Grid + Debate Panel (spans 2 rows) */}
        <AnalystGrid />
        <DebatePanel />

        {/* Row 3: Decision Panel */}
        <DecisionPanel />
      </main>
    </div>
  );
}
