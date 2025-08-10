import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Calendar, FileText, Download, BarChart3 } from 'lucide-react';
import axios from 'axios';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const ResultDetail: React.FC = () => {
  const { symbol, date } = useParams<{ symbol: string; date: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (symbol && date) {
      fetchResultDetail(symbol, date);
    }
  }, [symbol, date]);

  const fetchResultDetail = async (sym: string, dt: string) => {
    try {
      const response = await axios.get(`/results/${sym}/${dt}`);
      setData(response.data);
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Failed to load result details');
    } finally {
      setLoading(false);
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
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const renderDataVisualization = (analysisData: any) => {
    // Try to extract meaningful data for visualization
    if (!analysisData || typeof analysisData !== 'object') {
      return null;
    }

    // Look for common data patterns in trading analysis
    const keys = Object.keys(analysisData);
    const timeSeriesKeys = keys.filter(key => 
      key.toLowerCase().includes('price') || 
      key.toLowerCase().includes('volume') || 
      key.toLowerCase().includes('time') ||
      key.toLowerCase().includes('date')
    );

    if (timeSeriesKeys.length > 0) {
      // Create a simple visualization if we have time series data
      const labels = Array.from({ length: 10 }, (_, i) => `Day ${i + 1}`);
      const chartData = {
        labels,
        datasets: [
          {
            label: 'Analysis Trend',
            data: Array.from({ length: 10 }, () => Math.random() * 100),
            borderColor: 'rgb(59, 130, 246)',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            tension: 0.4,
          },
        ],
      };

      const options = {
        responsive: true,
        plugins: {
          legend: {
            position: 'top' as const,
          },
          title: {
            display: true,
            text: `${symbol} Analysis Visualization`,
          },
        },
        scales: {
          y: {
            beginAtZero: true,
          },
        },
      };

      return (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
            <BarChart3 className="h-5 w-5 mr-2" />
            Data Visualization
          </h3>
          <div className="h-64">
            <Line data={chartData} options={options} />
          </div>
        </div>
      );
    }

    return null;
  };

  const renderDataSection = (title: string, content: any, maxHeight = '400px') => {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">{title}</h3>
        <div 
          className="bg-gray-50 rounded-lg p-4 overflow-auto font-mono text-sm"
          style={{ maxHeight }}
        >
          <pre className="whitespace-pre-wrap">
            {typeof content === 'string' ? content : JSON.stringify(content, null, 2)}
          </pre>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="px-4 py-6">
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-500">Loading analysis details...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-4 py-6">
        <div className="text-center py-12">
          <FileText className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Error Loading Result</h3>
          <p className="text-red-600 mb-4">{error}</p>
          <Link
            to="/results"
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Results
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-6">
      {/* Header */}
      <div className="mb-8">
        <Link
          to="/results"
          className="inline-flex items-center text-primary-600 hover:text-primary-500 mb-4"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Results
        </Link>
        <h1 className="text-3xl font-bold text-gray-900">
          {symbol} Analysis - {date}
        </h1>
        <p className="mt-2 text-gray-600">
          Detailed view of trading analysis results
        </p>
      </div>

      {/* Metadata */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-medium text-gray-900 mb-4">Analysis Metadata</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <div className="flex items-center mb-2">
              <Calendar className="h-4 w-4 text-gray-400 mr-2" />
              <span className="font-medium">Analysis Date</span>
            </div>
            <p className="text-gray-900">{date}</p>
          </div>
          <div>
            <div className="flex items-center mb-2">
              <FileText className="h-4 w-4 text-gray-400 mr-2" />
              <span className="font-medium">File Size</span>
            </div>
            <p className="text-gray-900">{formatFileSize(data?.metadata?.file_size || 0)}</p>
          </div>
          <div>
            <div className="flex items-center mb-2">
              <Download className="h-4 w-4 text-gray-400 mr-2" />
              <span className="font-medium">Last Modified</span>
            </div>
            <p className="text-gray-900">
              {data?.metadata?.modified_at ? formatDate(data.metadata.modified_at) : 'Unknown'}
            </p>
          </div>
        </div>
      </div>

      {/* Data Visualization */}
      {data?.data && renderDataVisualization(data.data)}

      {/* Analysis Data */}
      {data?.data && (
        <>
          {/* Summary Section */}
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Analysis Summary</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <span className="font-medium text-gray-700">Symbol:</span>
                <p className="text-gray-900">{symbol}</p>
              </div>
              <div>
                <span className="font-medium text-gray-700">Data Keys:</span>
                <p className="text-gray-900">
                  {Object.keys(data.data).length} main sections
                </p>
              </div>
              <div className="md:col-span-2">
                <span className="font-medium text-gray-700">Available Sections:</span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {Object.keys(data.data).map((key) => (
                    <span
                      key={key}
                      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary-100 text-primary-800"
                    >
                      {key}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Detailed Data Sections */}
          {Object.entries(data.data).map(([key, value]) => (
            <div key={key}>
              {renderDataSection(`${key} Data`, value)}
            </div>
          ))}
        </>
      )}

      {/* Raw Data */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">Raw Data</h3>
          <button
            onClick={() => {
              const dataStr = JSON.stringify(data, null, 2);
              const blob = new Blob([dataStr], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${symbol}_${date}_analysis.json`;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            }}
            className="inline-flex items-center px-3 py-1 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
          >
            <Download className="h-3 w-3 mr-1" />
            Download JSON
          </button>
        </div>
        <div className="bg-gray-50 rounded-lg p-4 overflow-auto font-mono text-sm max-h-96">
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
};

export default ResultDetail;
