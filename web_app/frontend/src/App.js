import React, { useState, useEffect } from 'react';
import axios from 'axios';
import AnalysisDataAdapter from './components/AnalysisDataAdapter.tsx';
import TransformedDataAdapter from './components/TransformedDataAdapter.tsx';
import transformedDataService from './services/transformedDataService.ts';

function App() {
  const [backendStatus, setBackendStatus] = useState('checking');
  const [companies, setCompanies] = useState([]);
  const [stats, setStats] = useState({ totalAnalyses: 0, companies: 0 });
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [showResultsModal, setShowResultsModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showWidgetsView, setShowWidgetsView] = useState(false);
  const [showTransformedDataModal, setShowTransformedDataModal] = useState(false);
  const [analysisForm, setAnalysisForm] = useState({ symbol: '', date: '' });
  const [isRunningAnalysis, setIsRunningAnalysis] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [companyResults, setCompanyResults] = useState([]);
  const [selectedResult, setSelectedResult] = useState(null);
  const [resultDetail, setResultDetail] = useState(null);
  
  // New state for transformed data
  const [transformedDataFiles, setTransformedDataFiles] = useState([]);
  const [transformedDataSummary, setTransformedDataSummary] = useState(null);
  const [selectedTransformedData, setSelectedTransformedData] = useState(null);
  const [isLoadingTransformedData, setIsLoadingTransformedData] = useState(false);
  const [transformedDataError, setTransformedDataError] = useState(null);

  useEffect(() => {
    checkBackendStatus();
    fetchCompanies();
    loadTransformedDataSummary();
  }, []);

  const checkBackendStatus = async () => {
    try {
      await axios.get('/health');
      setBackendStatus('connected');
    } catch (error) {
      setBackendStatus('disconnected');
    }
  };

  const fetchCompanies = async () => {
    try {
      const response = await axios.get('/results/companies');
      const companiesData = response.data.companies || [];
      setCompanies(companiesData);
      
      const totalAnalyses = companiesData.reduce((sum, company) => sum + company.total_analyses, 0);
      setStats({
        totalAnalyses,
        companies: companiesData.length
      });
    } catch (error) {
      console.error('Error fetching companies:', error);
    }
  };

  const loadTransformedDataSummary = async () => {
    try {
      const [files, summary] = await Promise.all([
        transformedDataService.getAvailableFiles(),
        transformedDataService.getDataSummary()
      ]);
      setTransformedDataFiles(files);
      setTransformedDataSummary(summary);
    } catch (error) {
      console.error('Error loading transformed data summary:', error);
      setTransformedDataError('Failed to load transformed data');
    }
  };

  const fetchCompanyResults = async (symbol) => {
    try {
      const response = await axios.get(`/results/${symbol}`);
      setCompanyResults(response.data.results || []);
      setSelectedCompany(symbol);
    } catch (error) {
      console.error('Error fetching company results:', error);
      alert('Error loading company results');
    }
  };

  const openDetailModal = async (result) => {
    try {
      const response = await axios.get(`/results/${selectedCompany}/${result.date}`);
      setResultDetail(response.data);
      setSelectedResult({ ...result, company: selectedCompany });
      setShowDetailModal(true);
    } catch (error) {
      console.error('Error fetching result detail:', error);
      alert('Error loading result details');
    }
  };

  const openWidgetsView = async (result) => {
    try {
      const response = await axios.get(`/results/${selectedCompany}/${result.date}`);
      setResultDetail(response.data);
      setSelectedResult({ ...result, company: selectedCompany });
      setShowWidgetsView(true);
    } catch (error) {
      console.error('Error fetching result detail:', error);
      alert('Error loading analysis dashboard');
    }
  };

  const openTransformedWidgetsView = async (file) => {
    setIsLoadingTransformedData(true);
    setTransformedDataError(null);
    
    try {
      const transformedData = await transformedDataService.loadTransformedData(file.filename);
      setSelectedTransformedData(transformedData);
      setShowWidgetsView(true);
    } catch (error) {
      console.error('Error loading transformed data:', error);
      setTransformedDataError(`Failed to load ${file.filename}: ${error.message}`);
    } finally {
      setIsLoadingTransformedData(false);
    }
  };

  const handleStartAnalysis = () => {
    if (backendStatus !== 'connected') {
      alert('Backend is not connected. Please ensure the backend server is running.');
      return;
    }
    setShowAnalysisModal(true);
  };

  const handleViewResults = () => {
    if (backendStatus !== 'connected') {
      alert('Backend is not connected. Please ensure the backend server is running.');
      return;
    }
    setShowResultsModal(true);
    setSelectedCompany(null);
    setCompanyResults([]);
  };

  const handleViewTransformedData = () => {
    setShowTransformedDataModal(true);
    setTransformedDataError(null);
  };

  const runAnalysis = async () => {
    setIsRunningAnalysis(true);
    try {
      const response = await axios.post('/run-analysis', analysisForm);
      alert('Analysis completed successfully!');
      setShowAnalysisModal(false);
      setAnalysisForm({ symbol: '', date: '' });
      fetchCompanies(); // Refresh the companies list
    } catch (error) {
      console.error('Error running analysis:', error);
      alert('Error running analysis. Please try again.');
    } finally {
      setIsRunningAnalysis(false);
    }
  };

  const closeAllModals = () => {
    setShowAnalysisModal(false);
    setShowResultsModal(false);
    setShowDetailModal(false);
    setShowWidgetsView(false);
    setShowTransformedDataModal(false);
    setSelectedResult(null);
    setResultDetail(null);
    setSelectedTransformedData(null);
    setTransformedDataError(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <div className="bg-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <h1 className="text-3xl font-bold text-gray-900">TradingAgents</h1>
              </div>
              <div className="ml-4">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  backendStatus === 'connected' 
                    ? 'bg-green-100 text-green-800' 
                    : backendStatus === 'disconnected'
                    ? 'bg-red-100 text-red-800'
                    : 'bg-yellow-100 text-yellow-800'
                }`}>
                  {backendStatus === 'connected' ? '● Connected' : 
                   backendStatus === 'disconnected' ? '● Disconnected' : '● Checking...'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-blue-500 rounded-md flex items-center justify-center">
                      <span className="text-white font-semibold">📊</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">Total Analyses</dt>
                      <dd className="text-lg font-medium text-gray-900">{stats.totalAnalyses}</dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-green-500 rounded-md flex items-center justify-center">
                      <span className="text-white font-semibold">🏢</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">Companies</dt>
                      <dd className="text-lg font-medium text-gray-900">{stats.companies}</dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-purple-500 rounded-md flex items-center justify-center">
                      <span className="text-white font-semibold">🔄</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">Transformed Data</dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {transformedDataSummary ? transformedDataSummary.totalFiles : '---'}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <button
              onClick={handleStartAnalysis}
              className="group relative w-full flex justify-center py-8 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150 ease-in-out"
            >
              <span className="absolute left-0 inset-y-0 flex items-center pl-3">
                <span className="text-2xl">🚀</span>
              </span>
              <div className="text-center">
                <div className="text-lg font-semibold">Run New Analysis</div>
                <div className="text-sm opacity-90">Execute TradingAgents pipeline</div>
              </div>
            </button>

            <button
              onClick={handleViewResults}
              className="group relative w-full flex justify-center py-8 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition duration-150 ease-in-out"
            >
              <span className="absolute left-0 inset-y-0 flex items-center pl-3">
                <span className="text-2xl">📈</span>
              </span>
              <div className="text-center">
                <div className="text-lg font-semibold">View Results</div>
                <div className="text-sm opacity-90">Browse analysis results</div>
              </div>
            </button>

            <button
              onClick={handleViewTransformedData}
              className="group relative w-full flex justify-center py-8 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 transition duration-150 ease-in-out"
            >
              <span className="absolute left-0 inset-y-0 flex items-center pl-3">
                <span className="text-2xl">🔄</span>
              </span>
              <div className="text-center">
                <div className="text-lg font-semibold">Transformed Data</div>
                <div className="text-sm opacity-90">View enhanced analyses</div>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Transformed Data Modal */}
      {showTransformedDataModal && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-11/12 max-w-4xl shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-medium text-gray-900">Transformed Analysis Data</h3>
                <button
                  onClick={closeAllModals}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <span className="sr-only">Close</span>
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {transformedDataError && (
                <div className="mb-4 bg-red-50 border border-red-200 rounded-md p-4">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                      </svg>
                    </div>
                    <div className="ml-3">
                      <p className="text-sm text-red-800">{transformedDataError}</p>
                    </div>
                  </div>
                </div>
              )}

              {transformedDataSummary && (
                <div className="mb-6 bg-blue-50 border border-blue-200 rounded-md p-4">
                  <h4 className="text-sm font-medium text-blue-900 mb-2">Data Summary</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <span className="text-blue-600 font-medium">Total Files:</span>
                      <span className="ml-1 text-blue-900">{transformedDataSummary.totalFiles}</span>
                    </div>
                    <div>
                      <span className="text-blue-600 font-medium">Companies:</span>
                      <span className="ml-1 text-blue-900">{transformedDataSummary.companies.join(', ')}</span>
                    </div>
                    <div>
                      <span className="text-blue-600 font-medium">Date Range:</span>
                      <span className="ml-1 text-blue-900">
                        {transformedDataSummary.dateRange.earliest} to {transformedDataSummary.dateRange.latest}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <div className="max-h-96 overflow-y-auto">
                {transformedDataFiles.length === 0 ? (
                  <div className="text-center py-8">
                    <div className="text-gray-500 mb-2">No transformed data files found</div>
                    <div className="text-sm text-gray-400">
                      Run the data transformation agent to generate transformed analyses
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {transformedDataFiles.map((file, index) => (
                      <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100">
                        <div>
                          <div className="font-medium text-gray-900">{file.displayName}</div>
                          <div className="text-sm text-gray-500">{file.filename}</div>
                        </div>
                        <button
                          onClick={() => openTransformedWidgetsView(file)}
                          disabled={isLoadingTransformedData}
                          className="inline-flex items-center px-3 py-1 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
                        >
                          {isLoadingTransformedData ? 'Loading...' : 'View Dashboard'}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Widgets View Modal */}
      {showWidgetsView && (
        <div className="fixed inset-0 bg-gray-900 bg-opacity-75 z-50">
          <div className="min-h-screen flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-7xl max-h-screen overflow-hidden">
              <div className="flex justify-between items-center p-4 border-b">
                <h2 className="text-xl font-semibold text-gray-900">
                  Analysis Dashboard
                  {selectedResult && ` - ${selectedResult.company} (${selectedResult.date})`}
                  {selectedTransformedData && ` - ${selectedTransformedData.metadata.company_ticker} (${selectedTransformedData.metadata.analysis_date})`}
                </h2>
                <button
                  onClick={closeAllModals}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="overflow-y-auto max-h-[calc(100vh-100px)]">
                {selectedTransformedData ? (
                  <TransformedDataAdapter analysisData={selectedTransformedData} />
                ) : resultDetail ? (
                  <AnalysisDataAdapter tradingResult={resultDetail} />
                ) : (
                  <div className="p-8 text-center">
                    <div className="text-gray-500">Loading analysis data...</div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Analysis Modal */}
      {showAnalysisModal && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-medium text-gray-900">Start New Analysis</h3>
                <button
                  onClick={closeAllModals}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <span className="sr-only">Close</span>
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Stock Symbol
                  </label>
                  <input
                    type="text"
                    value={analysisForm.symbol}
                    onChange={(e) => setAnalysisForm({...analysisForm, symbol: e.target.value})}
                    placeholder="e.g., AAPL, TSLA, NVDA"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Analysis Date
                  </label>
                  <input
                    type="date"
                    value={analysisForm.date}
                    onChange={(e) => setAnalysisForm({...analysisForm, date: e.target.value})}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div className="flex space-x-3 pt-4">
                  <button
                    onClick={runAnalysis}
                    disabled={isRunningAnalysis}
                    className="flex-1 bg-indigo-600 text-white py-2 px-4 rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isRunningAnalysis ? 'Starting...' : 'Start Analysis'}
                  </button>
                  <button
                    onClick={closeAllModals}
                    className="flex-1 bg-gray-300 text-gray-700 py-2 px-4 rounded-md hover:bg-gray-400"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Results Modal */}
      {showResultsModal && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-11/12 max-w-6xl shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-medium text-gray-900">
                  {selectedCompany ? `${selectedCompany} Analysis Results` : "Analysis Results"}
                </h3>
                <button
                  onClick={closeAllModals}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <span className="sr-only">Close</span>
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="max-h-96 overflow-y-auto">
                {!selectedCompany ? (
                  // Company list view
                  companies.length > 0 ? (
                    <div className="space-y-2">
                      {companies.map((company) => (
                        <div 
                          key={company.symbol} 
                          className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100 cursor-pointer"
                          onClick={() => fetchCompanyResults(company.symbol)}
                        >
                          <div>
                            <div className="font-medium text-gray-900">{company.symbol}</div>
                            <div className="text-sm text-gray-500">{company.total_analyses} analyses</div>
                          </div>
                          <div className="text-sm text-gray-400">
                            {company.latest_analysis}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <div className="text-gray-500 mb-2">No analysis results available</div>
                      <div className="text-sm text-gray-400">Start your first analysis to see results here</div>
                    </div>
                  )
                ) : (
                  // Company results view
                  <div>
                    <div className="flex items-center mb-4">
                      <button
                        onClick={() => {setSelectedCompany(null); setCompanyResults([]);}}
                        className="flex items-center text-indigo-600 hover:text-indigo-800 mr-4"
                      >
                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                        Back
                      </button>
                      <h4 className="text-lg font-semibold">{selectedCompany} Results</h4>
                    </div>
                    
                    {companyResults.length > 0 ? (
                      <div className="space-y-2">
                        {companyResults.map((result, index) => (
                          <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100">
                            <div>
                              <div className="font-medium text-gray-900">{result.filename}</div>
                              <div className="text-sm text-gray-500">
                                {new Date(result.timestamp).toLocaleString()}
                              </div>
                            </div>
                            <div className="flex space-x-2">
                              <button
                                onClick={() => openWidgetsView(result)}
                                className="inline-flex items-center px-3 py-1 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                              >
                                View Dashboard
                              </button>
                              <button
                                onClick={() => openDetailModal(result)}
                                className="inline-flex items-center px-3 py-1 border border-gray-300 text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                              >
                                View Details
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <div className="text-gray-500">No results found for {selectedCompany}</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {showDetailModal && (
        <div className="fixed inset-0 bg-gray-900 bg-opacity-75 z-50">
          <div className="min-h-screen flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-screen overflow-hidden">
              <div className="flex justify-between items-center p-4 border-b">
                <h2 className="text-xl font-semibold text-gray-900">
                  {selectedResult?.company} Analysis Details
                </h2>
                <button
                  onClick={closeAllModals}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="overflow-y-auto max-h-[calc(100vh-100px)] p-6">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="font-semibold mb-2">Analysis Data</h3>
                  <pre className="text-sm overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(resultDetail, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
