import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, FileText, TrendingUp, Clock, Eye } from 'lucide-react';
import axios from 'axios';

interface Company {
  symbol: string;
  latest_analysis: string;
  total_analyses: number;
}

interface Result {
  date: string;
  filename: string;
  file_size: number;
  modified_at: string;
  preview?: {
    keys: string[];
    size: number;
  };
  error?: string;
}

const ViewResults: React.FC = () => {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<string>('');
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);

  useEffect(() => {
    fetchCompanies();
  }, []);

  useEffect(() => {
    if (selectedCompany) {
      fetchCompanyResults(selectedCompany);
    }
  }, [selectedCompany]);

  const fetchCompanies = async () => {
    try {
      const response = await axios.get('/results/companies');
      setCompanies(response.data.companies);
      if (response.data.companies.length > 0) {
        setSelectedCompany(response.data.companies[0].symbol);
      }
    } catch (error) {
      console.error('Error fetching companies:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchCompanyResults = async (symbol: string) => {
    setLoadingResults(true);
    try {
      const response = await axios.get(`/results/${symbol}`);
      setResults(response.data.results);
    } catch (error) {
      console.error('Error fetching results:', error);
      setResults([]);
    } finally {
      setLoadingResults(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="px-4 py-6">
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-500">Loading analysis results...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Analysis Results</h1>
        <p className="mt-2 text-gray-600">
          Browse and view historical trading analysis results
        </p>
      </div>

      {companies.length === 0 ? (
        <div className="text-center py-12">
          <FileText className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Results Found</h3>
          <p className="text-gray-500 mb-4">No analysis results are available yet.</p>
          <Link
            to="/run-analysis"
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
          >
            Run Your First Analysis
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Company Selector */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Companies</h3>
              <div className="space-y-2">
                {companies.map((company) => (
                  <button
                    key={company.symbol}
                    onClick={() => setSelectedCompany(company.symbol)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors ${
                      selectedCompany === company.symbol
                        ? 'bg-primary-50 border-primary-200 text-primary-900'
                        : 'bg-gray-50 border-gray-200 hover:bg-gray-100'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{company.symbol}</span>
                      <TrendingUp className="h-4 w-4" />
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      {company.total_analyses} analyses
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Results List */}
          <div className="lg:col-span-3">
            <div className="bg-white rounded-lg shadow">
              <div className="px-6 py-4 border-b border-gray-200">
                <h3 className="text-lg font-medium text-gray-900">
                  Results for {selectedCompany}
                </h3>
              </div>
              <div className="p-6">
                {loadingResults ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
                    <p className="mt-2 text-gray-500">Loading results...</p>
                  </div>
                ) : results.length === 0 ? (
                  <div className="text-center py-8">
                    <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-500">No results found for {selectedCompany}</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {results.map((result) => (
                      <div
                        key={result.date}
                        className="border rounded-lg p-4 hover:shadow-md transition-shadow"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center">
                            <Calendar className="h-4 w-4 text-gray-400 mr-2" />
                            <span className="font-medium text-gray-900">
                              Analysis: {result.date}
                            </span>
                          </div>
                          <Link
                            to={`/results/${selectedCompany}/${result.date}`}
                            className="inline-flex items-center px-3 py-1 border border-transparent text-sm font-medium rounded-md text-primary-700 bg-primary-100 hover:bg-primary-200"
                          >
                            <Eye className="h-3 w-3 mr-1" />
                            View Details
                          </Link>
                        </div>
                        
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-gray-600">
                          <div>
                            <span className="font-medium">File Size:</span>
                            <div>{formatFileSize(result.file_size)}</div>
                          </div>
                          <div>
                            <span className="font-medium">Modified:</span>
                            <div>{formatDate(result.modified_at)}</div>
                          </div>
                          {result.preview && (
                            <>
                              <div>
                                <span className="font-medium">Data Keys:</span>
                                <div>{result.preview.keys.length} keys</div>
                              </div>
                              <div>
                                <span className="font-medium">Data Size:</span>
                                <div>{result.preview.size} chars</div>
                              </div>
                            </>
                          )}
                          {result.error && (
                            <div className="col-span-2 md:col-span-4">
                              <span className="font-medium text-red-600">Error:</span>
                              <div className="text-red-600">{result.error}</div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ViewResults;
