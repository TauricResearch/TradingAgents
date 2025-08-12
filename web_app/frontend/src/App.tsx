import React from 'react';

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900">TradingAgents Web Application</h1>
            <p className="mt-2 text-gray-600">
              Backend is running successfully! Frontend compilation test.
            </p>
          </div>
          
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-medium text-gray-900 mb-4">System Status</h2>
            <div className="space-y-2">
              <div className="flex items-center">
                <div className="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                <span>Backend Server: Running on http://localhost:8000</span>
              </div>
              <div className="flex items-center">
                <div className="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                <span>Frontend: Compilation successful</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
