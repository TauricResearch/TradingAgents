import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

export interface TransformedAnalysis {
  filename: string;
  date: string;
  modified_at: string;
  file_size: number;
  preview?: {
    final_recommendation: string;
    confidence_level: string;
    current_price: number;
  };
  error?: string;
  symbol: string;
  displayName: string;
}

export interface TransformedData {
  metadata: {
    company_ticker: string;
    analysis_date: string;
    final_recommendation: string;
    confidence_level: string;
    current_price: number;
    target_price: number;
    risk_level: string;
    time_horizon: string;
  };
  financial_data: {
    current_price: number;
    target_price: number;
    price_change_1d: number;
    price_change_1w: number;
    price_change_1m: number;
    market_cap: number;
    volume: number;
    pe_ratio: number;
    revenue: number;
    profit_margin: number;
    debt_to_equity: number;
    roe: number;
    dividend_yield: number;
  };
  technical_indicators: {
    rsi: number;
    macd: number;
    moving_avg_20: number;
    moving_avg_50: number;
    bollinger_upper: number;
    bollinger_lower: number;
    support_level: number;
    resistance_level: number;
  };
  investment_strategy: {
    position_size: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    holding_period: string;
    risk_reward_ratio: number;
  };
  debate_summary: {
    bull_case: {
      key_points: string[];
      strength_score: number;
    };
    bear_case: {
      key_points: string[];
      strength_score: number;
    };
    consensus: string;
  };
  text_content: {
    executive_summary: string;
    key_takeaways: string[];
    detailed_analysis: string;
    risk_factors: string[];
    catalysts: string[];
  };
  widgets_config: {
    charts_enabled: string[];
    priority_widgets: string[];
    display_preferences: Record<string, any>;
  };
}

class TransformedDataService {
  private baseUrl = API_BASE_URL; 
  private cachedFiles: TransformedAnalysis[] | null = null;
  private cachedData: Map<string, TransformedData> = new Map();

  async getAvailableFiles(): Promise<TransformedAnalysis[]> {
    if (this.cachedFiles) {
      return this.cachedFiles;
    }

    try {
      const companiesResponse = await axios.get(`${this.baseUrl}/results/companies`);
      const companiesData = companiesResponse.data;
      const companies = companiesData.companies || [];
      
      const files: TransformedAnalysis[] = [];
      
      for (const company of companies) {
        if (company.transformed_analyses > 0) {
          try {
            const resultsResponse = await axios.get(`${this.baseUrl}/transformed-results/${company.symbol}`);
            const resultsData = resultsResponse.data;
            const results = resultsData.results || [];
            
            for (const result of results) {
              files.push({
                filename: result.filename,
                date: result.date,
                modified_at: result.modified_at,
                file_size: result.file_size,
                preview: result.preview,
                error: result.error,
                symbol: company.symbol,
                displayName: `${company.symbol} - ${result.date}`
              });
            }
          } catch (error) {
            console.warn(`Failed to fetch transformed results for ${company.symbol}:`, error);
          }
        }
      }
      
      this.cachedFiles = files;
    } catch (error) {
      console.warn('Could not load transformed data files:', error);
      this.cachedFiles = [];
    }

    return this.cachedFiles;
  }

  async loadTransformedData(filename: string): Promise<TransformedData> {
    if (this.cachedData.has(filename)) {
      return this.cachedData.get(filename)!;
    }

    try {
      const match = filename.match(/full_states_log_(.+)_transformed\.json/);
      if (!match) {
        throw new Error(`Invalid filename format: ${filename}`);
      }
      const date = match[1];
      
      const files = await this.getAvailableFiles();
      const fileEntry = files.find(f => f.filename === filename);
      if (!fileEntry) {
        throw new Error(`File not found in index: ${filename}`);
      }
      
      const response = await axios.get(`${this.baseUrl}/transformed-results/${fileEntry.symbol}/${date}`);
      const responseData = response.data;
      const data: TransformedData = responseData.data;
      
      this.validateTransformedData(data);
      
      this.cachedData.set(filename, data);
      
      return data;
    } catch (error) {
      console.error(`Error loading transformed data from ${filename}:`, error);
      throw error;
    }
  }

  async loadByCompanyAndDate(company: string, date: string): Promise<TransformedData> {
    const files = await this.getAvailableFiles();
    const entry = files.find(f => f.symbol === company && f.date === date);
    if (entry) {
      return this.loadTransformedData(entry.filename);
    }

    const response = await axios.get(`${this.baseUrl}/transformed-results/${company}/${date}`);
    const data: TransformedData = response.data.data;
    this.validateTransformedData(data);
    return data;
  }

  async getLatestForCompany(company: string): Promise<TransformedData | null> {
    const files = await this.getAvailableFiles();
    const companyFiles = files
      .filter(f => f.symbol === company)
      .sort((a, b) => b.date.localeCompare(a.date)); 
    
    if (companyFiles.length === 0) {
      return null;
    }
    
    return this.loadTransformedData(companyFiles[0].filename);
  }

  async getAvailableCompanies(): Promise<string[]> {
    const files = await this.getAvailableFiles();
    const companies = [...new Set(files.map(f => f.symbol))].sort();
    return companies;
  }

  async getAvailableDatesForCompany(company: string): Promise<string[]> {
    const files = await this.getAvailableFiles();
    const dates = files
      .filter(f => f.symbol === company)
      .map(f => f.date)
      .sort((a, b) => b.localeCompare(a)); 
    
    return dates;
  }

  private validateTransformedData(data: any): void {
    // Core sections that must exist
    const requiredSections = [
      'metadata',
      'financial_data',
      'technical_indicators',
      'investment_strategy'
    ];
    for (const section of requiredSections) {
      if (!(section in data)) {
        throw new Error(`Missing required section: ${section}`);
      }
    }

    // Normalize legacy singular widget_config to widgets_config, if present
    if (!('widgets_config' in data) && ('widget_config' in data)) {
      data.widgets_config = data.widget_config;
    }

    // widgets_config is optional; UI will supply a sensible default if absent
  }

  clearCache(): void {
    this.cachedFiles = null;
    this.cachedData.clear();
  }

  async generateManifest(): Promise<{ files: TransformedAnalysis[] }> {
    const files = await this.getAvailableFiles();
    return { files };
  }

  async searchAnalyses(criteria: {
    company?: string;
    dateFrom?: string;
    dateTo?: string;
    recommendation?: 'BUY' | 'SELL' | 'HOLD';
  }): Promise<TransformedAnalysis[]> {
    const files = await this.getAvailableFiles();
    
    return files.filter(file => {
      if (criteria.company && file.symbol !== criteria.company) {
        return false;
      }
      
      if (criteria.dateFrom && file.date < criteria.dateFrom) {
        return false;
      }
      
      if (criteria.dateTo && file.date > criteria.dateTo) {
        return false;
      }
      
      return true;
    });
  }

  async getDataSummary(): Promise<{
    totalFiles: number;
    companies: string[];
    dateRange: { earliest: string; latest: string };
    companyCounts: Record<string, number>;
  }> {
    const files = await this.getAvailableFiles();
    
    const companies = [...new Set(files.map(f => f.symbol))].sort();
    const dates = files.map(f => f.date).sort();
    
    const companyCounts: Record<string, number> = {};
    files.forEach(file => {
      const company = file.symbol;
      companyCounts[company] = (companyCounts[company] || 0) + 1;
    });
    
    return {
      totalFiles: files.length,
      companies,
      dateRange: {
        earliest: dates[0] || '',
        latest: dates[dates.length - 1] || ''
      },
      companyCounts
    };
  }
}

export const transformedDataService = new TransformedDataService();
export default transformedDataService;
