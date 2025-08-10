import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Play, Database, TrendingUp, Clock } from 'lucide-react';
import axios from 'axios';

const Dashboard: React.FC = () => {
  const [companies, setCompanies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCompanies();
  }, []);

  const fetchCompanies = async () => {
    try {
      const response = await axios.get('/results/companies');
      setCompanies(response.data.companies);
    } catch (error) {
      console.error('Error fetching companies:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="px-4 py-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Trading Analysis Dashboard</h1>
        <p className="mt-2 text-gray-600">
          Execute trading analysis and view historical results for stock predictions
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <Link
          to="/run-analysis"
          className="bg-primary-600 hover:bg-primary-700 text-white p-6 rounded-lg shadow-md transition-colors"
        >
          <div className="flex items-center">
            <Play className="h-8 w-8 mr-4" />
            <div>
              <h3 className="text-xl font-semibold">Run New Analysis</h3>
              <p className="text-primary-100">Execute trading pipeline for any stock symbol</p>
            </div>
          </div>
        </Link>

        <Link
          to="/results"
          className="bg-success-600 hover:bg-success-700 text-white p-6 rounded-lg shadow-md transition-colors"
        >
          <div className="flex items-center">
            <Database className="h-8 w-8 mr-4" />
            <div>
              <h3 className="text-xl font-semibold">View Agent Outputs</h3>
              <p className="text-success-100">Browse historical analysis results</p>
            </div>
          </div>
        </Link>
      </div>

      {/* Recent Results */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Recent Analysis Results</h2>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
              <p className="mt-2 text-gray-500">Loading results...</p>
            </div>
          ) : companies.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {companies.slice(0, 6).map((company) => (
                <div key={company.symbol} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold text-gray-900">{company.symbol}</h3>
                    <TrendingUp className="h-4 w-4 text-success-500" />
                  </div>
                  <div className="text-sm text-gray-600">
                    <div className="flex items-center mb-1">
                      <Clock className="h-3 w-3 mr-1" />
                      Latest: {company.latest_analysis}
                    </div>
                    <div>Total analyses: {company.total_analyses}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <Database className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-500">No analysis results found</p>
              <Link
                to="/run-analysis"
                className="mt-2 inline-flex items-center text-primary-600 hover:text-primary-500"
              >
                Run your first analysis
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
