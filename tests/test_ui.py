import subprocess
import sys
from unittest.mock import patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_ui_importable():
    """Ensure cli.ui can be imported without syntax or import errors."""
    import cli.ui

    assert hasattr(cli.ui, "init_session_state")


def test_cli_ui_help():
    """Verify `tradingagents ui --help` output."""
    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Launch the TradingAgents Streamlit UI web application" in result.output
    assert "--port" in result.output
    assert "--host" in result.output


@patch("subprocess.run")
def test_cli_ui_command_execution(mock_subproc_run):
    """Test `tradingagents ui` invokes streamlit run with specified host and port."""
    result = runner.invoke(app, ["ui", "--port", "8502", "--host", "127.0.0.1"])
    assert result.exit_code == 0
    mock_subproc_run.assert_called_once()
    cmd = mock_subproc_run.call_args[0][0]
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-m", "streamlit", "run"]
    assert "--server.port" in cmd
    assert "8502" in cmd
    assert "--server.address" in cmd
    assert "127.0.0.1" in cmd
