import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            TradingAgents
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Multi-Agents LLM Financial Trading Framework
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
          <Link
            href="/analysis/new"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <h2 className="text-2xl font-semibold mb-2">New Analysis</h2>
            <p className="text-gray-600">
              Start a new trading analysis with your selected ticker and configuration
            </p>
          </Link>

          <Link
            href="/history"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <h2 className="text-2xl font-semibold mb-2">View History</h2>
            <p className="text-gray-600">
              Browse and review your previous trading analyses
            </p>
          </Link>
        </div>

        <div className="mt-12 text-center text-gray-500">
          <p>Workflow: Analyst Team → Research Team → Trader → Risk Management → Portfolio Management</p>
        </div>
      </div>
    </div>
  );
}
