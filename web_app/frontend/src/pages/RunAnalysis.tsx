import React, { useState } from 'react';
import { Play, Settings, AlertCircle, CheckCircle } from 'lucide-react';
import axios from 'axios';
import toast from 'react-hot-toast';

const RunAnalysis: React.FC = () => {
  const [formData, setFormData] = useState({
    symbol: '',
    date: new Date().toISOString().split('T')[0],
  });
  const [isRunning, setIsRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<any>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.symbol.trim()) {
      toast.error('Please enter a stock symbol');
      return;
    }

    setIsRunning(true);
    try {
      const response = await axios.post('/analysis/start', {
        symbol: formData.symbol.toUpperCase(),
        date: formData.date,
      });
      
      setJobId(response.data.job_id);
      toast.success('Analysis started successfully!');
      pollJobStatus(response.data.job_id);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to start analysis');
      setIsRunning(false);
    }
  };

  const pollJobStatus = async (id: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`/analysis/status/${id}`);
        setJobStatus(response.data);
        
        if (response.data.status === 'completed') {
          clearInterval(interval);
          setIsRunning(false);
          toast.success('Analysis completed successfully!');
        } else if (response.data.status === 'failed') {
          clearInterval(interval);
          setIsRunning(false);
          toast.error(`Analysis failed: ${response.data.error}`);
        }
      } catch (error) {
        clearInterval(interval);
        setIsRunning(false);
        toast.error('Error checking job status');
      }
    }, 2000);
  };

  return (
    <div className="px-4 py-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Run Trading Analysis</h1>
        <p className="mt-2 text-gray-600">
          Execute the TradingAgents pipeline to generate predictions for any stock symbol
        </p>
      </div>

      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-md p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="symbol" className="block text-sm font-medium text-gray-700 mb-2">
                Stock Symbol
              </label>
              <input
                type="text"
                id="symbol"
                value={formData.symbol}
                onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
                placeholder="e.g., NVDA, AAPL, TSLA"
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                disabled={isRunning}
              />
            </div>

            <div>
              <label htmlFor="date" className="block text-sm font-medium text-gray-700 mb-2">
                Analysis Date
              </label>
              <input
                type="date"
                id="date"
                value={formData.date}
                onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                disabled={isRunning}
              />
            </div>

            <button
              type="submit"
              disabled={isRunning}
              className="w-full flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRunning ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Running Analysis...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Start Analysis
                </>
              )}
            </button>
          </form>

          {/* Job Status */}
          {jobStatus && (
            <div className="mt-6 p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center mb-2">
                {jobStatus.status === 'completed' && <CheckCircle className="h-5 w-5 text-success-500 mr-2" />}
                {jobStatus.status === 'failed' && <AlertCircle className="h-5 w-5 text-danger-500 mr-2" />}
                {jobStatus.status === 'running' && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary-600 mr-2"></div>
                )}
                <span className="font-medium capitalize">{jobStatus.status}</span>
              </div>
              {jobStatus.progress && (
                <p className="text-sm text-gray-600 mb-2">{jobStatus.progress}</p>
              )}
              {jobStatus.result && (
                <div className="mt-4 p-3 bg-white rounded border">
                  <h4 className="font-medium mb-2">Analysis Result:</h4>
                  <pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto">
                    {JSON.stringify(jobStatus.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RunAnalysis;
