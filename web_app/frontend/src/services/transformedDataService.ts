import { TransformedAnalysisData } from '../components/TransformedDataAdapter.tsx';

export interface TransformedDataFile {
  filename: string;
  company: string;
  date: string;
  displayName: string;
}

class TransformedDataService {
  private baseUrl = '/transformed_data';
  private cachedFiles: TransformedDataFile[] | null = null;
  private cachedData: Map<string, TransformedAnalysisData> = new Map();

  /**
   * Get list of available transformed data files
   */
  async getAvailableFiles(): Promise<TransformedDataFile[]> {
    if (this.cachedFiles) {
      return this.cachedFiles;
    }

    try {
      // In a real implementation, you might have an API endpoint that lists files
      // For now, we'll try to load a manifest file or use a predefined list
      const response = await fetch(`${this.baseUrl}/manifest.json`);
      
      if (response.ok) {
        const manifest = await response.json();
        this.cachedFiles = manifest.files || [];
      } else {
        // Fallback: try to load some common files
        this.cachedFiles = await this.discoverFiles();
      }
    } catch (error) {
      console.warn('Could not load transformed data manifest, using fallback discovery:', error);
      this.cachedFiles = await this.discoverFiles();
    }

    return this.cachedFiles;
  }

  /**
   * Discover available files by trying common patterns
   */
  private async discoverFiles(): Promise<TransformedDataFile[]> {
    const companies = ['AVAH', 'PLTR', 'RDDT'];
    const dates = [
      '2025-07-26', '2025-08-05', '2025-08-06', '2025-08-07'
    ];
    
    const files: TransformedDataFile[] = [];
    
    for (const company of companies) {
      for (const date of dates) {
        const filename = `${company}_full_states_log_${date}_transformed.json`;
        
        try {
          const response = await fetch(`${this.baseUrl}/${filename}`, { method: 'HEAD' });
          if (response.ok) {
            files.push({
              filename,
              company,
              date,
              displayName: `${company} - ${date}`
            });
          }
        } catch (error) {
          // File doesn't exist, skip
        }
      }
    }
    
    return files;
  }

  /**
   * Load a specific transformed data file
   */
  async loadTransformedData(filename: string): Promise<TransformedAnalysisData> {
    // Check cache first
    if (this.cachedData.has(filename)) {
      return this.cachedData.get(filename)!;
    }

    try {
      const response = await fetch(`${this.baseUrl}/${filename}`);
      
      if (!response.ok) {
        throw new Error(`Failed to load ${filename}: ${response.status} ${response.statusText}`);
      }
      
      const data: TransformedAnalysisData = await response.json();
      
      // Validate the data structure
      this.validateTransformedData(data);
      
      // Cache the data
      this.cachedData.set(filename, data);
      
      return data;
    } catch (error) {
      console.error(`Error loading transformed data file ${filename}:`, error);
      throw error;
    }
  }

  /**
   * Load transformed data by company and date
   */
  async loadByCompanyAndDate(company: string, date: string): Promise<TransformedAnalysisData> {
    const filename = `${company}_full_states_log_${date}_transformed.json`;
    return this.loadTransformedData(filename);
  }

  /**
   * Get the most recent analysis for a company
   */
  async getLatestForCompany(company: string): Promise<TransformedAnalysisData | null> {
    const files = await this.getAvailableFiles();
    const companyFiles = files
      .filter(f => f.company === company)
      .sort((a, b) => b.date.localeCompare(a.date)); // Sort by date descending
    
    if (companyFiles.length === 0) {
      return null;
    }
    
    return this.loadTransformedData(companyFiles[0].filename);
  }

  /**
   * Get all available companies
   */
  async getAvailableCompanies(): Promise<string[]> {
    const files = await this.getAvailableFiles();
    const companies = [...new Set(files.map(f => f.company))];
    return companies.sort();
  }

  /**
   * Get available dates for a specific company
   */
  async getAvailableDatesForCompany(company: string): Promise<string[]> {
    const files = await this.getAvailableFiles();
    const dates = files
      .filter(f => f.company === company)
      .map(f => f.date)
      .sort((a, b) => b.localeCompare(a)); // Sort by date descending
    
    return dates;
  }

  /**
   * Validate that the loaded data conforms to the expected structure
   */
  private validateTransformedData(data: any): void {
    const requiredSections = [
      'metadata',
      'financial_data',
      'technical_indicators',
      'investment_strategy',
      'debate_summary',
      'text_content',
      'widgets_config'
    ];

    for (const section of requiredSections) {
      if (!data[section]) {
        throw new Error(`Missing required section: ${section}`);
      }
    }

    // Validate metadata
    const metadata = data.metadata;
    if (!metadata.company_ticker || !metadata.analysis_date) {
      throw new Error('Invalid metadata: missing company_ticker or analysis_date');
    }

    // Validate that dates are in correct format
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (!dateRegex.test(metadata.analysis_date)) {
      throw new Error('Invalid date format in metadata.analysis_date');
    }
  }

  /**
   * Clear all cached data
   */
  clearCache(): void {
    this.cachedFiles = null;
    this.cachedData.clear();
  }

  /**
   * Create a manifest file content for available transformed data
   * This can be used to generate a manifest.json file
   */
  async generateManifest(): Promise<{ files: TransformedDataFile[] }> {
    const files = await this.discoverFiles();
    return { files };
  }

  /**
   * Search for analyses by various criteria
   */
  async searchAnalyses(criteria: {
    company?: string;
    dateFrom?: string;
    dateTo?: string;
    recommendation?: 'BUY' | 'SELL' | 'HOLD';
  }): Promise<TransformedDataFile[]> {
    const files = await this.getAvailableFiles();
    
    return files.filter(file => {
      if (criteria.company && file.company !== criteria.company) {
        return false;
      }
      
      if (criteria.dateFrom && file.date < criteria.dateFrom) {
        return false;
      }
      
      if (criteria.dateTo && file.date > criteria.dateTo) {
        return false;
      }
      
      // For recommendation filtering, we'd need to load the actual data
      // This is left as a future enhancement
      
      return true;
    });
  }

  /**
   * Get summary statistics about available data
   */
  async getDataSummary(): Promise<{
    totalFiles: number;
    companies: string[];
    dateRange: { earliest: string; latest: string };
    companyCounts: Record<string, number>;
  }> {
    const files = await this.getAvailableFiles();
    
    const companies = [...new Set(files.map(f => f.company))].sort();
    const dates = files.map(f => f.date).sort();
    
    const companyCounts: Record<string, number> = {};
    files.forEach(file => {
      companyCounts[file.company] = (companyCounts[file.company] || 0) + 1;
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

// Export a singleton instance
export const transformedDataService = new TransformedDataService();
export default transformedDataService;
