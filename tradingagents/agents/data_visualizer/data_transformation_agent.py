import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import openai
from pathlib import Path

@dataclass
class TransformationConfig:
    """Configuration for the data transformation agent"""
    openai_api_key: str = os.environ.get("OPENAI_API_KEY")
    model: str = "gpt-4o-mini"
    eval_results_path: str = "scripts/eval_results/AVAH/TradingAgentsStrategy_logs"
    output_path: str = "scripts/eval_results/AVAH/TradingAgentsStrategy_transformed_logs"
    backend_url: str = "https://api.openai.com/v1"
    
class DataTransformationAgent:
    """Agent that transforms TradingAgents output into widget-friendly JSON format"""
    
    def __init__(self, config: TransformationConfig):
        self.config = config
        self.client = openai.OpenAI(
            api_key=config.openai_api_key,
            base_url=config.backend_url
        )
        
        # Ensure output directory exists
        os.makedirs(self.config.output_path, exist_ok=True)
    
    def get_transformation_prompt(self) -> str:
        """Returns the comprehensive transformation prompt"""
        return """
You are a data transformation specialist. Take the provided investment analysis JSON and restructure it into a widget-friendly format that separates visual data from text content for easy frontend consumption.

## Input Format
The input JSON contains investment analysis data with the following structure:
- `company_of_interest`: Stock ticker
- `trade_date`: Analysis date
- `market_report`: Technical analysis text
- `sentiment_report`: Company sentiment analysis text
- `news_report`: Macroeconomic news text
- `fundamentals_report`: Financial metrics and company data text
- `investment_debate_state`: Object containing bull/bear/neutral arguments
- `risk_debate_state`: Object containing risk analysis discussions
- `investment_plan`: Final investment strategy text
- `trader_investment_decision`: Final decision rationale text
- `final_trade_decision`: Ultimate trade recommendation text

## Output Requirements
Transform the input into a structured JSON with the following sections:

### 1. Widget Data Structure
```json
{
  "metadata": {
    "company_ticker": "string",
    "company_name": "string", 
    "analysis_date": "YYYY-MM-DD",
    "final_recommendation": "BUY|SELL|HOLD",
    "confidence_level": "HIGH|MEDIUM|LOW"
  },
  
  "financial_data": {
    "current_price": number,
    "price_change": number,
    "price_change_percent": number,
    "market_cap": "string",
    "enterprise_value": "string",
    "shares_outstanding": "string",
    "trading_range": {
      "high": number,
      "low": number,
      "open": number
    },
    "volume": number,
    "valuation_ratios": {
      "current_ps_ratio": number,
      "fair_value_ps_ratio": number,
      "forward_pe": number,
      "forward_ps": number,
      "forward_pcf": number,
      "forward_pocf": number
    },
    "ownership": {
      "insider_percent": number,
      "institutional_percent": number
    },
    "analyst_data": {
      "consensus_rating": "string",
      "price_target": number,
      "forecast_price": number
    }
  },

  "technical_indicators": {
    "sma_50": number,
    "sma_200": number,
    "ema_10": number,
    "macd": number,
    "macd_signal": number,
    "rsi": number,
    "atr": number,
    "trend_directions": {
      "sma_50": "BULLISH|BEARISH|NEUTRAL",
      "sma_200": "BULLISH|BEARISH|NEUTRAL",
      "ema_10": "BULLISH|BEARISH|NEUTRAL",
      "macd": "BULLISH|BEARISH|NEUTRAL",
      "rsi_condition": "OVERSOLD|OVERBOUGHT|NEUTRAL"
    }
  },

  "investment_strategy": {
    "position_sizing": {
      "total_allocation_percent": "string",
      "entry_strategy": "string",
      "tranche_1_percent": "string",
      "tranche_2_percent": "string"
    },
    "risk_management": {
      "initial_stop_loss": number,
      "stop_loss_percent": number,
      "breakeven_strategy": "string"
    },
    "profit_targets": [
      {
        "target_price": number,
        "action": "string",
        "rationale": "string"
      }
    ],
    "monitoring_points": [
      "string"
    ]
  },

  "debate_summary": {
    "bull_key_points": [
      "string"
    ],
    "bear_key_points": [
      "string"
    ],
    "neutral_perspective": "string",
    "final_decision_rationale": "string"
  },

  "text_content": {
    "market_report": {
      "title": "Technical Analysis Report",
      "content": "string",
      "key_takeaways": [
        "string"
      ]
    },
    "sentiment_report": {
      "title": "Company Sentiment Analysis", 
      "content": "string",
      "recent_developments": [
        "string"
      ]
    },
    "fundamentals_report": {
      "title": "Fundamental Analysis",
      "content": "string",
      "financial_highlights": [
        "string"
      ]
    },
    "news_report": {
      "title": "Macroeconomic Context",
      "content": "string",
      "key_developments": [
        {
          "date": "string",
          "event": "string",
          "impact": "string"
        }
      ]
    },
    "investment_plan_full": {
      "title": "Complete Investment Strategy",
      "content": "string"
    },
    "debate_transcripts": {
      "bull_analysis": "string",
      "bear_analysis": "string",
      "neutral_analysis": "string",
      "risk_discussion": "string"
    }
  },

  "widgets_config": {
    "charts_needed": [
      {
        "type": "price_chart",
        "data_source": "financial_data.current_price",
        "timeframe": "30_days"
      },
      {
        "type": "technical_indicators",
        "data_source": "technical_indicators"
      }
    ],
    "text_widgets": [
      {
        "type": "expandable_report",
        "title": "Technical Analysis",
        "content_source": "text_content.market_report"
      }
    ]
  }
}
```

## Extraction Instructions

1. **Parse Financial Metrics**: Extract all numerical values from the fundamentals_report, including current price, ratios, market cap, etc.

2. **Extract Technical Data**: Pull technical indicator values and trend directions from the market_report text

3. **Summarize Debates**: Create concise bullet points from the lengthy bull/bear arguments, focusing on key investment themes

4. **Structure Investment Plan**: Break down the investment strategy into actionable components (sizing, stops, targets)

5. **Organize Text Content**: Preserve full text reports while also extracting key highlights for quick reference

6. **Identify Key Dates**: Extract important dates like earnings calls, trade dates, and catalyst events

7. **Classify Sentiment**: Determine overall sentiment scores and confidence levels based on the analysis

## Data Validation
- Ensure all numerical values are properly typed (numbers vs strings)
- Validate date formats are consistent
- Check that all required fields are populated
- Verify that text content is properly escaped for JSON

## Output Optimization
- Structure data for easy consumption by frontend frameworks (React, Vue, Angular)
- Separate frequently-accessed data (current price, recommendation) from detailed reports
- Include metadata for widget configuration and rendering preferences
- Provide fallback values for any missing data points

Transform the input JSON following this structure to create a comprehensive, widget-ready dataset that maintains all original information while making it easily accessible for dashboard creation.

IMPORTANT: Return ONLY the transformed JSON, no additional text or explanations.
"""

    def extract_numerical_value(self, text: str, pattern: str, default: float = 0.0) -> float:
        """Extract numerical values from text using regex patterns"""
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '').replace('$', '').replace('%', '')
                return float(value_str)
        except (ValueError, AttributeError):
            pass
        return default

    def transform_single_file(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single TradingAgents JSON file using LLM"""
        try:
            # Prepare the input data as a JSON string
            input_json = json.dumps(input_data, indent=2)
            
            # Create the prompt with the input data
            full_prompt = f"{self.get_transformation_prompt()}\n\nInput JSON to transform:\n{input_json}"
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "You are a data transformation specialist. Transform the provided JSON exactly as specified."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.1,
                max_tokens=16384
            )
            
            # Parse the response
            transformed_json_str = response.choices[0].message.content.strip()
            
            # Clean up the response (remove any markdown formatting)
            if transformed_json_str.startswith('```json'):
                transformed_json_str = transformed_json_str[7:]
            if transformed_json_str.endswith('```'):
                transformed_json_str = transformed_json_str[:-3]
            
            transformed_data = json.loads(transformed_json_str)
            
            # Add fallback values if transformation missed anything
            self._add_fallback_values(transformed_data, input_data)
            
            
        except Exception as e:
            print(f"Error transforming data: {e}")
            # Return a basic fallback structure
            transformed_data = self._create_fallback_structure(input_data)
        
        return transformed_data
    
    def _add_fallback_values(self, transformed_data: Dict[str, Any], original_data: Dict[str, Any]):
        """Add fallback values for any missing required fields"""
        
        # Ensure metadata exists
        if 'metadata' not in transformed_data:
            transformed_data['metadata'] = {}
        
        metadata = transformed_data['metadata']
        if 'company_ticker' not in metadata:
            metadata['company_ticker'] = original_data.get('company_of_interest', 'UNKNOWN')
        if 'analysis_date' not in metadata:
            metadata['analysis_date'] = original_data.get('trade_date', datetime.now().strftime('%Y-%m-%d'))
        if 'final_recommendation' not in metadata:
            metadata['final_recommendation'] = 'HOLD'
        if 'confidence_level' not in metadata:
            metadata['confidence_level'] = 'MEDIUM'

        # Ensure all required sections exist
        required_sections = [
            'financial_data', 'technical_indicators', 'investment_strategy',
            'debate_summary', 'text_content', 'widgets_config'
        ]
        
        for section in required_sections:
            if section not in transformed_data:
                transformed_data[section] = {}

    def _create_fallback_structure(self, original_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a basic fallback structure when transformation fails"""
        return {
            "metadata": {
                "company_ticker": original_data.get('company_of_interest', 'UNKNOWN'),
                "company_name": original_data.get('company_of_interest', 'Unknown Company'),
                "analysis_date": original_data.get('trade_date', datetime.now().strftime('%Y-%m-%d')),
                "final_recommendation": "HOLD",
                "confidence_level": "LOW"
            },
            "financial_data": {
                "current_price": 0.0,
                "price_change": 0.0,
                "price_change_percent": 0.0,
                "market_cap": "N/A",
                "enterprise_value": "N/A",
                "shares_outstanding": "N/A",
                "trading_range": {"high": 0.0, "low": 0.0, "open": 0.0},
                "volume": 0,
                "valuation_ratios": {
                    "current_ps_ratio": 0.0,
                    "fair_value_ps_ratio": 0.0,
                    "forward_pe": 0.0,
                    "forward_ps": 0.0,
                    "forward_pcf": 0.0,
                    "forward_pocf": 0.0
                },
                "ownership": {"insider_percent": 0.0, "institutional_percent": 0.0},
                "analyst_data": {
                    "consensus_rating": "N/A",
                    "price_target": 0.0,
                    "forecast_price": 0.0
                }
            },
            "technical_indicators": {
                "sma_50": 0.0,
                "sma_200": 0.0,
                "ema_10": 0.0,
                "macd": 0.0,
                "macd_signal": 0.0,
                "rsi": 50.0,
                "atr": 0.0,
                "trend_directions": {
                    "sma_50": "NEUTRAL",
                    "sma_200": "NEUTRAL",
                    "ema_10": "NEUTRAL",
                    "macd": "NEUTRAL",
                    "rsi_condition": "NEUTRAL"
                }
            },
            "investment_strategy": {
                "position_sizing": {
                    "total_allocation_percent": "0%",
                    "entry_strategy": "N/A",
                    "tranche_1_percent": "0%",
                    "tranche_2_percent": "0%"
                },
                "risk_management": {
                    "initial_stop_loss": 0.0,
                    "stop_loss_percent": 0.0,
                    "breakeven_strategy": "N/A"
                },
                "profit_targets": [],
                "monitoring_points": []
            },
            "debate_summary": {
                "bull_key_points": [],
                "bear_key_points": [],
                "neutral_perspective": "No analysis available",
                "final_decision_rationale": "No decision rationale available"
            },
            "text_content": {
                "market_report": {
                    "title": "Technical Analysis Report",
                    "content": original_data.get('market_report', 'No market report available'),
                    "key_takeaways": []
                },
                "sentiment_report": {
                    "title": "Company Sentiment Analysis",
                    "content": original_data.get('sentiment_report', 'No sentiment report available'),
                    "recent_developments": []
                },
                "fundamentals_report": {
                    "title": "Fundamental Analysis",
                    "content": original_data.get('fundamentals_report', 'No fundamentals report available'),
                    "financial_highlights": []
                },
                "news_report": {
                    "title": "Macroeconomic Context",
                    "content": original_data.get('news_report', 'No news report available'),
                    "key_developments": []
                },
                "investment_plan_full": {
                    "title": "Complete Investment Strategy",
                    "content": original_data.get('investment_plan', 'No investment plan available')
                },
                "debate_transcripts": {
                    "bull_analysis": "",
                    "bear_analysis": "",
                    "neutral_analysis": "",
                    "risk_discussion": ""
                }
            },
            "widgets_config": {
                "charts_needed": [
                    {"type": "price_chart", "data_source": "financial_data.current_price", "timeframe": "30_days"},
                    {"type": "technical_indicators", "data_source": "technical_indicators"}
                ],
                "text_widgets": [
                    {"type": "expandable_report", "title": "Technical Analysis", "content_source": "text_content.market_report"}
                ]
            }
        }

    def process_all_files(self) -> Dict[str, List[str]]:
        """Process all JSON files in the eval_results directory"""
        results = {"success": [], "failed": []}
        
        eval_results_path = Path(self.config.eval_results_path)
        
        if not eval_results_path.exists():
            print(f"Eval results path does not exist: {eval_results_path}")
            return results
        
        # Process each company directory
        for company_dir in eval_results_path.iterdir():
            if not company_dir.is_dir():
                continue
            
            company_ticker = company_dir.name
            logs_dir = company_dir / "TradingAgentsStrategy_logs"
            transformed_dir = company_dir / "TradingAgentsStrategy_transformed_logs"
            transformed_dir.mkdir(parents=True, exist_ok=True)
            
            # Process each JSON file in the logs directory
            for json_file in logs_dir.glob("*.json"):
                try:
                    print(f"Processing {json_file}")
                    
                    # Process the file
                    success = self.process_single_file(str(json_file), str(transformed_dir / json_file.name))
                    
                    if success:
                        results["success"].append(str(transformed_dir / json_file.name))
                        print(f"Successfully transformed and saved: {transformed_dir / json_file.name}")
                    else:
                        results["failed"].append(str(json_file))
                        print(f"Failed to process {json_file}")
                    
                except Exception as e:
                    print(f"Failed to process {json_file}: {e}")
                    results["failed"].append(str(json_file))
        
        return results

    def process_single_file(self, input_file_path: str, output_file_path: str = None) -> bool:
        """Process a single JSON file"""
        try:
            input_path = Path(input_file_path)
            
            if not input_path.exists():
                print(f"Input file does not exist: {input_path}")
                return False
            
            # Load the original data
            with open(input_path, 'r') as f:
                original_data = json.load(f)
            
            # Transform the data
            transformed_data = self.transform_single_file(original_data)
            
            # Determine output path
            if output_file_path is None:
                output_file_path = Path(self.config.output_path) / f"{input_path.stem}_transformed.json"
            else:
                output_file_path = Path(output_file_path)
            
            # Save the transformed data
            with open(output_file_path, 'w') as f:
                json.dump(transformed_data, f, indent=2)
            
            print(f"Successfully transformed and saved: {output_file_path}")
            return True
            
        except Exception as e:
            print(f"Failed to process {input_file_path}: {e}")
            return False


def main():
    """Main function to run the transformation agent"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Transform TradingAgents output to widget-friendly format")
    parser.add_argument("--api-key", help="OpenAI API key")
    parser.add_argument("--input-file",  default="scripts/eval_results/AVAH/TradingAgentsStrategy_logs/full_states_log_2025-07-26.json", help="Process a single input file")
    parser.add_argument("--output-file", default="scripts/eval_results/AVAH/TradingAgentsStrategy_transformed_logs/full_states_log_2025-07-26.json", help="Output file path (for single file processing)")
    parser.add_argument("--eval-results-path", default="scripts/eval_results", help="Path to eval_results directory")
    parser.add_argument("--output-path", default="scripts/eval_results/AVAH/TradingAgentsStrategy_transformed_logs/", help="Output directory path")
    
    args = parser.parse_args()
    
    # Create configuration
    config = TransformationConfig(
        openai_api_key=args.api_key,
        eval_results_path=args.eval_results_path,
        output_path=args.output_path
    )
    
    # Create agent
    agent = DataTransformationAgent(config)
    
    if args.input_file:
        # Process single file
        success = agent.process_single_file(args.input_file, args.output_file)
        if success:
            print("Single file processing completed successfully")
        else:
            print("Single file processing failed")
    else:
        # Process all files
        results = agent.process_all_files()
        print(f"\nProcessing completed:")
        print(f"Success: {len(results['success'])} files")
        print(f"Failed: {len(results['failed'])} files")
        
        if results['success']:
            print("\nSuccessfully processed files:")
            for file_path in results['success']:
                print(f"  - {file_path}")
        
        if results['failed']:
            print("\nFailed to process files:")
            for file_path in results['failed']:
                print(f"  - {file_path}")


if __name__ == "__main__":
    main()
