# TradingAgents Dashboard

A modern, interactive dashboard for the TradingAgents system built with Streamlit and Plotly.

## Features

- 📊 **Real-time Charts**: Interactive price and volume visualizations
- 🤖 **Agent Monitoring**: Track multi-agent activity and performance
- 📝 **Comprehensive Logging**: Real-time activity logs with filtering
- 💼 **Trade Tracking**: Monitor executed trades and profitability
- 🎛️ **Control Panel**: Interactive controls for simulation parameters

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Run the dashboard:

```bash
streamlit run app.py
```

The dashboard will open in your browser at `http://localhost:8501`

## Components

### Main Dashboard
- Price charts with technical indicators
- Volume analysis
- Agent activity visualization
- Recent trades table

### Control Panel (Sidebar)
- Ticker selection
- Agent activation/deactivation
- Time range configuration
- Quick statistics

### Activity Log
- Real-time logging of all system activities
- Filterable by log level (INFO, WARNING, ERROR, SUCCESS)
- Color-coded entries for easy identification

## Architecture

The dashboard uses:
- **Streamlit**: For the reactive UI framework
- **Plotly**: For interactive data visualizations
- **Pandas/Numpy**: For data manipulation and analysis
- **Python logging**: For comprehensive activity tracking

## Testing

UI tests are located in `/workspace/tests/test_dashboard_ui.py`

Run tests with:
```bash
pytest tests/test_dashboard_ui.py -v
```
