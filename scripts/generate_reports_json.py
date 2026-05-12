import os
import json
import re

def parse_report(report_path, report_id):
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract title
        title_match = re.search(r'^# (.*)', content)
        title = title_match.group(1) if title_match else report_id
        
        # Extract date
        date_match = re.search(r'Generated: (.*)', content)
        date = date_match.group(1).split(' ')[0] if date_match else "Unknown"
        
        # Extract rating
        rating_match = re.search(r'Rating: (.*)', content)
        rating = rating_match.group(1).strip() if rating_match else "Unknown"
        
        # Extract summary (from Portfolio Manager or Research Manager)
        summary = ""
        pm_match = re.search(r'### Portfolio Manager\n(.*?)\n', content, re.DOTALL)
        if pm_match:
            summary = pm_match.group(1).strip()
        else:
            rm_match = re.search(r'### Research Manager\n(.*?)\n', content, re.DOTALL)
            if rm_match:
                summary = rm_match.group(1).strip()
        
        if not summary:
            # Fallback to first paragraph after header
            paragraphs = content.split('\n\n')
            if len(paragraphs) > 1:
                summary = paragraphs[1][:200] + "..."
        
        return {
            "id": report_id,
            "title": title,
            "date": date,
            "type": "Trading",
            "author": "Portfolio Manager",
            "summary": summary[:300] if summary else "No summary available.",
            "rating": rating,
            "content": content
        }
    except Exception as e:
        print(f"Error parsing {report_path}: {e}")
        return None

def main():
    reports_dir = '/Users/alexanderpolyakov/PycharmProjects/TradingAgents/reports'
    output_path = '/Users/alexanderpolyakov/PycharmProjects/TradingAgents/dashboard/src/data/reports.json'
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    reports_list = []
    for entry in os.listdir(reports_dir):
        entry_path = os.path.join(reports_dir, entry)
        if os.path.isdir(entry_path):
            report_file = os.path.join(entry_path, 'complete_report.md')
            if os.path.exists(report_file):
                report_data = parse_report(report_file, entry)
                if report_data:
                    reports_list.append(report_data)
    
    # Sort by date descending
    reports_list.sort(key=lambda x: x['date'], reverse=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(reports_list, f, indent=2)
    
    print(f"Successfully generated {len(reports_list)} reports at {output_path}")

if __name__ == "__main__":
    main()
