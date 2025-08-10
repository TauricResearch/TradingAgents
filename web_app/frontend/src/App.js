import React, { useState, useEffect, useMemo } from 'react';
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
  const [transformedDataSummary, setTransformedDataSummary] = useState(null);
  const [selectedTransformedData, setSelectedTransformedData] = useState(null);
  const [isLoadingTransformedData, setIsLoadingTransformedData] = useState(false);
  const [transformedDataError, setTransformedDataError] = useState(null);
  const [selectedTransformedCompany, setSelectedTransformedCompany] = useState(null);
  const [transformedCompanyFiles, setTransformedCompanyFiles] = useState([]);
  const [activeDetailTab, setActiveDetailTab] = useState(null);

  // Fields to display as pretty cards in the Details modal
  const detailFields = useMemo(() => ([
    'market_report',
    'sentiment_report',
    'news_report',
    'fundamentals_report',
    'trader_investment_decision',
    'investment_plan',
    'final_trade_decision',
    'investment_debate_state.bull_history',
    'investment_debate_state.bear_history',
    'investment_debate_state.history',
    'investment_debate_state.current_response',
    'investment_debate_state.judge_decision',
    'risk_debate_state.risky_history',
    'risk_debate_state.safe_history',
    'risk_debate_state.neutral_history',
    'risk_debate_state.history',
    'risk_debate_state.judge_decision',
    'company_of_interest',
    'trade_date',
  ]), []);

  const fieldLabelMap = {
    market_report: 'Market Report',
    sentiment_report: 'Sentiment Report',
    news_report: 'News Report',
    fundamentals_report: 'Fundamentals Report',
    trader_investment_decision: 'Trader Investment Decision',
    investment_plan: 'Investment Plan',
    final_trade_decision: 'Final Trade Decision',
    'investment_debate_state.bull_history': 'Investment Debate - Bull History',
    'investment_debate_state.bear_history': 'Investment Debate - Bear History',
    'investment_debate_state.history': 'Investment Debate - History',
    'investment_debate_state.current_response': 'Investment Debate - Current Response',
    'investment_debate_state.judge_decision': 'Investment Debate - Judge Decision',
    'risk_debate_state.risky_history': 'Risk Debate - Risky History',
    'risk_debate_state.safe_history': 'Risk Debate - Safe History',
    'risk_debate_state.neutral_history': 'Risk Debate - Neutral History',
    'risk_debate_state.history': 'Risk Debate - History',
    'risk_debate_state.judge_decision': 'Risk Debate - Judge Decision',
    company_of_interest: 'Company of Interest',
    trade_date: 'Trade Date',
  };

  // Helpers
  const getNested = (obj, path) => {
    if (!obj || !path) return undefined;
    return path.split('.').reduce((acc, key) => (acc != null ? acc[key] : undefined), obj);
  };

  const prettyValue = (val) => {
    if (val === null || val === undefined) return '';
    if (typeof val === 'string') return val;
    try { return JSON.stringify(val, null, 2); } catch { return String(val); }
  };

  // Close only the topmost open modal on Escape, preserving underlying modals
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (showDetailModal) {
          setShowDetailModal(false);
          return;
        }
        if (showWidgetsView) {
          setShowWidgetsView(false);
          return;
        }
        if (showTransformedDataModal) {
          setShowTransformedDataModal(false);
          return;
        }
        if (showResultsModal) {
          setShowResultsModal(false);
          return;
        }
        if (showAnalysisModal) {
          setShowAnalysisModal(false);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showDetailModal, showWidgetsView, showTransformedDataModal, showResultsModal, showAnalysisModal]);

  useEffect(() => {
    checkBackendStatus();
    fetchCompanies();
    loadTransformedDataSummary();
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (showDetailModal) {
          setShowDetailModal(false);
          return;
        }
        if (showWidgetsView) {
          setShowWidgetsView(false);
          return;
        }
        if (showTransformedDataModal) {
          setShowTransformedDataModal(false);
          return;
        }
        if (showResultsModal) {
          setShowResultsModal(false);
          return;
        }
        if (showAnalysisModal) {
          setShowAnalysisModal(false);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showDetailModal, showWidgetsView, showTransformedDataModal, showResultsModal, showAnalysisModal]);

  // Keep the active details tab in sync with available fields for the selected result
  useEffect(() => {
    const baseData = resultDetail?.data?.[selectedResult?.date];
    if (!baseData) {
      setActiveDetailTab(null);
      return;
    }
    const available = (detailFields || []).filter((path) => {
      const val = path.split('.').reduce((acc, k) => (acc != null ? acc[k] : undefined), baseData);
      if (val === undefined || val === null) return false;
      if (typeof val === 'object') {
        if (Array.isArray(val)) return val.length > 0;
        return Object.keys(val).length > 0;
      }
      return true;
    });
    if (available.length === 0) {
      setActiveDetailTab(null);
    } else if (!activeDetailTab || !available.includes(activeDetailTab)) {
      setActiveDetailTab(available[0]);
    }
  }, [resultDetail, selectedResult, detailFields, activeDetailTab]);

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
      const summary = await transformedDataService.getDataSummary();
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
      // Load by company and date to avoid relying on cached index
      const transformedData = await transformedDataService.loadByCompanyAndDate(selectedTransformedCompany, file.date);
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

  const handleViewTransformedData = async () => {
    setShowTransformedDataModal(true);
    setTransformedDataError(null);
    setSelectedTransformedCompany(null);
    setTransformedCompanyFiles([]);
    try {
      transformedDataService.clearCache();
      const summary = await transformedDataService.getDataSummary();
      setTransformedDataSummary(summary);
    } catch (e) {
      console.error('Failed to load transformed data on open:', e);
      setTransformedDataError('Failed to load transformed data');
    }
  };

  const runAnalysis = async () => {
    setIsRunningAnalysis(true);
    try {
      await axios.post('/analysis/start', analysisForm);
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

  const fetchTransformedCompanyFiles = async (symbol) => {
    try {
      const response = await axios.get(`/transformed-results/${symbol}`);
      setTransformedCompanyFiles(response.data.results || []);
      setSelectedTransformedCompany(symbol);
    } catch (error) {
      console.error('Error fetching transformed company files:', error);
      setTransformedDataError('Error loading transformed company files');
    }
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
                <div className="text-lg font-semibold">View Agent Outputs</div>
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
                <div className="text-lg font-semibold">Visualize Output Data</div>
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
                <h3 className="text-lg font-medium text-gray-900">
                  {selectedTransformedCompany ? `${selectedTransformedCompany} Transformed Analyses` : 'Transformed Analysis Data'}
                </h3>
                <div className="flex items-center gap-2">
                  {selectedTransformedCompany && (
                    <button
                      onClick={() => {
                        setSelectedTransformedCompany(null);
                        setTransformedCompanyFiles([]);
                      }}
                      className="text-sm px-3 py-1 rounded-md border text-gray-700 hover:bg-gray-50"
                    >
                      Back
                    </button>
                  )}
                  <button
                    onClick={async () => {
                      try {
                        transformedDataService.clearCache();
                        const summary = await transformedDataService.getDataSummary();
                        setTransformedDataSummary(summary);
                        setTransformedDataError(null);
                      } catch (e) {
                        console.error('Refresh failed:', e);
                        setTransformedDataError('Refresh failed');
                      }
                    }}
                    className="text-sm px-3 py-1 rounded-md border text-gray-700 hover:bg-gray-50"
                  >
                    Refresh
                  </button>
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
                {!selectedTransformedCompany ? (
                  // Company list view (only companies with transformed analyses)
                  companies && companies.filter(c => (c.transformed_analyses || 0) > 0).length > 0 ? (
                    <div className="space-y-2">
                      {companies.filter(c => (c.transformed_analyses || 0) > 0).map((company) => (
                        <div 
                          key={company.symbol} 
                          className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100 cursor-pointer"
                          onClick={() => fetchTransformedCompanyFiles(company.symbol)}
                        >
                          <div>
                            <div className="font-medium text-gray-900">{company.symbol}</div>
                            <div className="text-sm text-gray-500">Transformed analyses: {company.transformed_analyses}</div>
                          </div>
                          <div className="text-sm text-gray-400">
                            View Files
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <div className="text-gray-500 mb-2">No companies with transformed data found</div>
                      <div className="text-sm text-gray-400">Run the data transformation agent to generate transformed analyses</div>
                    </div>
                  )
                ) : (
                  // File list for selected transformed company
                  transformedCompanyFiles.length > 0 ? (
                    <div className="space-y-2">
                      {transformedCompanyFiles.map((file, index) => (
                        <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100">
                          <div>
                            <div className="font-medium text-gray-900">{selectedTransformedCompany} - {file.date}</div>
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
                  ) : (
                    <div className="text-center py-8">
                      <div className="text-gray-500 mb-2">No transformed files found for {selectedTransformedCompany}</div>
                    </div>
                  )
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
                {/* Dropdown selector */}
                {(() => {
                  const baseData = resultDetail?.data?.[selectedResult?.date];
                  if (!baseData) return null;
                  const available = detailFields
                    .map((path) => ({ path, val: getNested(baseData, path) }))
                    .filter(({ val }) => {
                      if (val === undefined || val === null) return false;
                      if (typeof val === 'object') {
                        if (Array.isArray(val)) return val.length > 0;
                        return Object.keys(val).length > 0;
                      }
                      return true;
                    });
                  if (available.length === 0) return null;
                  const current = available.find(({ path }) => path === activeDetailTab) || available[0];
                  const activePath = current.path;
                  const activeVal = current.val;
                  return (
                    <div className="mb-6">
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Select section</label>
                        <select
                          className="block w-full md:max-w-sm border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                          value={activePath}
                          onChange={(e) => setActiveDetailTab(e.target.value)}
                        >
                          {available.map(({ path }) => (
                            <option key={path} value={path}>
                              {fieldLabelMap[path] || path}
                            </option>
                          ))}
                        </select>
                      </div>
                      {/* Content */}
                      <div className="bg-white border rounded-lg p-4 shadow-sm">
                        <h4 className="font-semibold mb-2 text-gray-900">{fieldLabelMap[activePath] || activePath}</h4>
                        <pre className="text-sm text-gray-800 whitespace-pre-wrap overflow-x-auto">{prettyValue(activeVal)}</pre>
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
