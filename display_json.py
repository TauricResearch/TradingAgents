#!/usr/bin/env python3
"""
JSON Pretty Display Script for Trading Analysis Data
Displays trading strategy logs with color coding and formatting
"""

import json
import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime
import argparse

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_header(text: str, color: str = Colors.HEADER):
    """Print a formatted header"""
    print(f"\n{color}{'='*80}")
    print(f"{text.center(80)}")
    print(f"{'='*80}{Colors.END}\n")

def print_section(text: str, color: str = Colors.BLUE):
    """Print a section header"""
    print(f"\n{color}{'─'*60}")
    print(f"  {text}")
    print(f"{'─'*60}{Colors.END}")

def print_key_value(key: str, value: str, max_width: int = 100):
    """Print a key-value pair with formatting"""
    if len(value) > max_width:
        # Truncate and add ellipsis
        truncated = value[:max_width-3] + "..."
        print(f"{Colors.CYAN}{key}:{Colors.END} {truncated}")
        print(f"{Colors.YELLOW}    (truncated - full text available in raw JSON){Colors.END}")
    else:
        print(f"{Colors.CYAN}{key}:{Colors.END} {value}")

def format_text_block(text: str, indent: int = 2, max_width: int = 80) -> str:
    """Format a long text block with proper wrapping"""
    if not text:
        return ""
    
    # Split by newlines and format each paragraph
    paragraphs = text.split('\n\n')
    formatted_paragraphs = []
    
    for paragraph in paragraphs:
        if not paragraph.strip():
            continue
            
        # Handle markdown headers
        if paragraph.startswith('###'):
            formatted_paragraphs.append(f"{Colors.GREEN}{paragraph}{Colors.END}")
        elif paragraph.startswith('**') and paragraph.endswith('**'):
            formatted_paragraphs.append(f"{Colors.BOLD}{paragraph}{Colors.END}")
        else:
            # Simple text wrapping
            words = paragraph.split()
            lines = []
            current_line = " " * indent
            
            for word in words:
                if len(current_line + word) < max_width:
                    current_line += word + " "
                else:
                    lines.append(current_line.strip())
                    current_line = " " * indent + word + " "
            
            if current_line.strip():
                lines.append(current_line.strip())
            
            formatted_paragraphs.append('\n'.join(lines))
    
    return '\n\n'.join(formatted_paragraphs)

def display_trading_data(data: Dict[str, Any]):
    """Display the trading analysis data in a formatted way"""
    
    # Get the main date key (assuming it's the first key)
    date_key = list(data.keys())[0]
    trading_data = data[date_key]
    
    print_header(f"Trading Analysis Report - {date_key}", Colors.HEADER)
    
    # Basic information
    print_section("Basic Information")
    print_key_value("Company", trading_data.get("company_of_interest", "N/A"))
    print_key_value("Trade Date", trading_data.get("trade_date", "N/A"))
    
    # Market Report
    print_section("Market Analysis Report")
    market_report = trading_data.get("market_report", "")
    if market_report:
        print(format_text_block(market_report))
    else:
        print(f"{Colors.RED}No market report available{Colors.END}")
    
    # Sentiment Report
    print_section("Sentiment Analysis")
    sentiment_report = trading_data.get("sentiment_report", "")
    if sentiment_report:
        print(format_text_block(sentiment_report))
    else:
        print(f"{Colors.RED}No sentiment report available{Colors.END}")
    
    # News Report
    print_section("News Analysis")
    news_report = trading_data.get("news_report", "")
    if news_report:
        print(format_text_block(news_report))
    else:
        print(f"{Colors.RED}No news report available{Colors.END}")
    
    # Fundamentals Report
    print_section("Fundamentals Analysis")
    fundamentals_report = trading_data.get("fundamentals_report", "")
    if fundamentals_report:
        print(format_text_block(fundamentals_report))
    else:
        print(f"{Colors.RED}No fundamentals report available{Colors.END}")
    
    # Investment Decision
    print_section("Investment Decision")
    investment_decision = trading_data.get("trader_investment_decision", "")
    if investment_decision:
        print(format_text_block(investment_decision))
    else:
        print(f"{Colors.RED}No investment decision available{Colors.END}")
    
    # Investment Plan
    print_section("Investment Plan")
    investment_plan = trading_data.get("investment_plan", "")
    if investment_plan:
        print(format_text_block(investment_plan))
    else:
        print(f"{Colors.RED}No investment plan available{Colors.END}")
    
    # Final Trade Decision
    print_section("Final Trade Decision")
    final_decision = trading_data.get("final_trade_decision", "")
    if final_decision:
        print(format_text_block(final_decision))
    else:
        print(f"{Colors.RED}No final trade decision available{Colors.END}")
    
    # Debate States
    if "investment_debate_state" in trading_data:
        print_section("Investment Debate Analysis")
        debate_state = trading_data["investment_debate_state"]
        
        if "judge_decision" in debate_state:
            print(f"{Colors.BOLD}Judge Decision:{Colors.END}")
            print(format_text_block(debate_state["judge_decision"]))
    
    if "risk_debate_state" in trading_data:
        print_section("Risk Management Debate")
        risk_state = trading_data["risk_debate_state"]
        
        if "judge_decision" in risk_state:
            print(f"{Colors.BOLD}Risk Judge Decision:{Colors.END}")
            print(format_text_block(risk_state["judge_decision"]))

def display_raw_json(data: Dict[str, Any], indent: int = 2):
    """Display the raw JSON with proper formatting"""
    print_header("Raw JSON Data", Colors.YELLOW)
    print(json.dumps(data, indent=indent, ensure_ascii=False))

def interactive_menu(data: Dict[str, Any]):
    """Provide an interactive menu for exploring the data"""
    while True:
        print(f"\n{Colors.CYAN}Interactive Menu:{Colors.END}")
        print("1. View formatted trading analysis")
        print("2. View raw JSON data")
        print("3. Search for specific content")
        print("4. Export to formatted text file")
        print("5. Exit")
        
        choice = input(f"\n{Colors.YELLOW}Enter your choice (1-5): {Colors.END}").strip()
        
        if choice == "1":
            display_trading_data(data)
        elif choice == "2":
            display_raw_json(data)
        elif choice == "3":
            search_content(data)
        elif choice == "4":
            export_to_file(data)
        elif choice == "5":
            print(f"{Colors.GREEN}Goodbye!{Colors.END}")
            break
        else:
            print(f"{Colors.RED}Invalid choice. Please try again.{Colors.END}")

def search_content(data: Dict[str, Any]):
    """Search for specific content in the data"""
    search_term = input(f"{Colors.YELLOW}Enter search term: {Colors.END}").strip().lower()
    
    if not search_term:
        return
    
    print(f"\n{Colors.CYAN}Searching for '{search_term}'...{Colors.END}\n")
    
    found = False
    date_key = list(data.keys())[0]
    trading_data = data[date_key]
    
    for key, value in trading_data.items():
        if isinstance(value, str) and search_term in value.lower():
            print_section(f"Found in: {key}")
            # Find the context around the search term
            words = value.split()
            for i, word in enumerate(words):
                if search_term in word.lower():
                    start = max(0, i-5)
                    end = min(len(words), i+6)
                    context = " ".join(words[start:end])
                    print(f"...{context}...")
                    found = True
                    break
    
    if not found:
        print(f"{Colors.RED}No matches found for '{search_term}'{Colors.END}")

def export_to_file(data: Dict[str, Any]):
    """Export the formatted data to a text file"""
    filename = input(f"{Colors.YELLOW}Enter filename (default: trading_analysis.txt): {Colors.END}").strip()
    if not filename:
        filename = "trading_analysis.txt"
    
    if not filename.endswith('.txt'):
        filename += '.txt'
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            # Redirect stdout to capture the formatted output
            import io
            import contextlib
            
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                display_trading_data(data)
            
            f.write(output.getvalue())
        
        print(f"{Colors.GREEN}Data exported to {filename}{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}Error exporting file: {e}{Colors.END}")

def main():
    parser = argparse.ArgumentParser(description="Pretty display JSON trading analysis data")
    parser.add_argument("json_file", help="Path to the JSON file to display")
    parser.add_argument("--raw", action="store_true", help="Display raw JSON only")
    parser.add_argument("--interactive", action="store_true", help="Start interactive mode")
    parser.add_argument("--export", help="Export formatted data to specified file")
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.json_file):
        print(f"{Colors.RED}Error: File '{args.json_file}' not found{Colors.END}")
        sys.exit(1)
    
    try:
        with open(args.json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"{Colors.RED}Error: Invalid JSON file - {e}{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Error reading file: {e}{Colors.END}")
        sys.exit(1)
    
    # Handle different display modes
    if args.raw:
        display_raw_json(data)
    elif args.interactive:
        interactive_menu(data)
    elif args.export:
        try:
            with open(args.export, 'w', encoding='utf-8') as f:
                import io
                import contextlib
                
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    display_trading_data(data)
                
                f.write(output.getvalue())
            print(f"{Colors.GREEN}Data exported to {args.export}{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}Error exporting file: {e}{Colors.END}")
    else:
        # Default: display formatted data
        display_trading_data(data)

if __name__ == "__main__":
    main() 