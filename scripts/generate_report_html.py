import sys
import json
import markdown
from pathlib import Path

# Add project root to sys.path to allow importing tradingagents
current_dir = Path(__file__).parent
sys.path.append(str(current_dir.parent))

try:
    from tradingagents.utils.anonymizer import TickerAnonymizer
    ANONYMIZER_AVAILABLE = True
except ImportError:
    ANONYMIZER_AVAILABLE = False

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Agent Report - {ticker} - {date}</title>
    <style>
        :root {
            --bg-color: #0d1117;
            --text-color: #c9d1d9;
            --border-color: #30363d;
            --accent-color: #58a6ff;
            --sidebar-bg: #161b22;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 0;
            display: flex;
            height: 100vh;
        }

        /* Sidebar Navigation */
        .sidebar {
            width: 250px;
            background-color: var(--sidebar-bg);
            border-right: 1px solid var(--border-color);
            padding: 20px;
            display: flex;
            flex-direction: column;
        }

        .logo {
            font-size: 1.2rem;
            font-weight: bold;
            color: var(--accent-color);
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
        }

        .nav-item {
            padding: 10px 15px;
            margin-bottom: 8px;
            cursor: pointer;
            border-radius: 6px;
            color: var(--text-color);
            transition: background 0.2s;
        }

        .nav-item:hover {
            background-color: #21262d;
        }

        .nav-item.active {
            background-color: #1f2937;
            color: var(--accent-color);
            border-left: 3px solid var(--accent-color);
        }

        /* Main Content */
        .main-content {
            flex: 1;
            padding: 40px;
            overflow-y: auto;
        }

        .markdown-body {
            max-width: 900px;
            margin: 0 auto;
            line-height: 1.6;
        }

        /* Markdown Styles (GitHub Dark Theme approximation) */
        h1, h2, h3 { color: #f0f6fc; border-bottom: 1px solid var(--border-color); padding-bottom: 0.3em; }
        h1 { font-size: 2em; }
        h2 { font-size: 1.5em; margin-top: 24px; }
        a { color: var(--accent-color); text-decoration: none; }
        a:hover { text-decoration: underline; }
        
        code {
            background-color: rgba(110, 118, 129, 0.4);
            padding: 0.2em 0.4em;
            border-radius: 6px;
            font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
        }
        
        pre {
            background-color: #161b22;
            padding: 16px;
            border-radius: 6px;
            overflow: auto;
        }
        
        pre code {
            background-color: transparent;
            padding: 0;
        }

        blockquote {
            border-left: 0.25em solid #30363d;
            color: #8b949e;
            padding: 0 1em;
            margin: 0;
        }

        table {
            border-collapse: collapse;
            width: 100%;
            margin-top: 20px;
        }
        
        table th, table td {
            border: 1px solid var(--border-color);
            padding: 8px 12px;
        }
        
        table th {
            background-color: #161b22;
            font-weight: 600;
        }

        table tr:nth-child(2n) {
            background-color: #0d1117;
        }
        
        hr {
            border: 0;
            border-bottom: 1px solid var(--border-color);
            margin: 24px 0;
        }

        /* Helper for replacing content */
        .hidden { display: none; }
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="logo">
            🤖 Trading Agents<br>
            <span style="font-size: 0.8em; color: #8b949e">{ticker} | {date}</span>
        </div>
        <div id="nav-container">
            <!-- Nav text will be inserted here -->
        </div>
    </div>

    <div class="main-content">
        <div id="content" class="markdown-body">
            <!-- Rendered Markdown will appear here -->
        </div>
    </div>

    <script>
        // Start: Embedded Markdown Content
        const reportData = {json_data};
        // End: Embedded Markdown Content

        const navContainer = document.getElementById('nav-container');
        const contentDiv = document.getElementById('content');

        function renderReport(key) {
            // Update Active Nav
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            document.getElementById(`nav-${key}`).classList.add('active');
            
            // Render Content
            contentDiv.innerHTML = reportData[key];
            window.scrollTo(0, 0);
        }

        // Initialize Navigation
        const keys = Object.keys(reportData);
        keys.forEach((key, index) => {
            const navItem = document.createElement('div');
            navItem.className = 'nav-item';
            navItem.id = `nav-${key}`;
            navItem.innerText = key.replace(/_/g, ' ').toUpperCase();
            navItem.onclick = () => renderReport(key);
            navContainer.appendChild(navItem);
        });

        // Load first report by default
        if (keys.length > 0) {
            renderReport(keys[0]);
        }
    </script>

</body>
</html>
"""

def generate_report(report_dir):
    path = Path(report_dir)
    if not path.exists():
        print(f"Error: Directory {report_dir} not found.")
        return

    # Extract info from path structure: results/TICKER/DATE/reports
    try:
        data_parts = path.parts
        # Assuming structure .../TICKER/DATE/reports
        date = data_parts[-2]
        ticker = data_parts[-3]
    except IndexError:
        date = "Unknown Date"
        ticker = "Unknown Ticker"

    anonymizer = None
    if ANONYMIZER_AVAILABLE:
        anonymizer = TickerAnonymizer()
        real_ticker = anonymizer.deanonymize_ticker(ticker)
        if real_ticker:
            ticker = f"{real_ticker} ({ticker})"

    reports = {}
    
    # Read all markdown files
    for file in path.glob("*.md"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Deanonymize content if possible
                if anonymizer:
                    content = anonymizer.deanonymize_text(content)
                
                # Convert Markdown to HTML server-side
                html_content = markdown.markdown(content, extensions=['tables', 'fenced_code'])
                reports[file.stem] = html_content
        except Exception as e:
            print(f"Failed to read {file}: {e}")

    if not reports:
        print("No markdown files found to generate report.")
        return

    # Sort keys to ensure consistent order (e.g. Investment Plan first if possible, or alphabetical)
    # Let's prioritize investment_plan.md
    sorted_keys = sorted(reports.keys(), key=lambda x: (0 if "plan" in x else 1, x))
    sorted_reports = {k: reports[k] for k in sorted_keys}

    # Generate HTML
    html_content = TEMPLATE.replace("{ticker}", ticker).replace("{date}", date)
    html_content = html_content.replace("{json_data}", json.dumps(sorted_reports))

    output_path = path / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ Generated Dashboard: {output_path}")
    return str(output_path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_report_html.py <report_dir>")
        sys.exit(1)
    
    generate_report(sys.argv[1])
