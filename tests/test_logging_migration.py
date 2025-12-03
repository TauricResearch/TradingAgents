import ast
import os
import pytest


class TestLoggingMigration:
    def test_no_print_statements_in_interface_py(self):
        file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "tradingagents",
            "dataflows",
            "interface.py",
        )
        with open(file_path, "r") as f:
            content = f.read()

        tree = ast.parse(content)

        print_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    print_calls.append(node.lineno)

        assert len(print_calls) == 0, f"Found print statements at lines: {print_calls}"

    def test_no_print_statements_in_brave_py(self):
        file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "tradingagents",
            "dataflows",
            "brave.py",
        )
        with open(file_path, "r") as f:
            content = f.read()

        tree = ast.parse(content)

        print_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    print_calls.append(node.lineno)

        assert len(print_calls) == 0, f"Found print statements at lines: {print_calls}"

    def test_no_print_statements_in_tavily_py(self):
        file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "tradingagents",
            "dataflows",
            "tavily.py",
        )
        with open(file_path, "r") as f:
            content = f.read()

        tree = ast.parse(content)

        print_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    print_calls.append(node.lineno)

        assert len(print_calls) == 0, f"Found print statements at lines: {print_calls}"

    def test_no_print_statements_in_migrated_dataflow_files(self):
        dataflow_files = [
            "alpha_vantage_news.py",
            "y_finance.py",
            "local.py",
            "yfin_utils.py",
            "googlenews_utils.py",
            "utils.py",
            "alpha_vantage_common.py",
            "alpha_vantage_indicator.py",
        ]

        dataflows_dir = os.path.join(
            os.path.dirname(__file__),
            "..",
            "tradingagents",
            "dataflows",
        )

        all_print_calls = {}

        for filename in dataflow_files:
            file_path = os.path.join(dataflows_dir, filename)
            if not os.path.exists(file_path):
                continue

            with open(file_path, "r") as f:
                content = f.read()

            tree = ast.parse(content)

            print_calls = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "print":
                        print_calls.append(node.lineno)

            if print_calls:
                all_print_calls[filename] = print_calls

        assert len(all_print_calls) == 0, f"Found print statements in: {all_print_calls}"

    def test_logger_import_exists_in_interface_py(self):
        file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "tradingagents",
            "dataflows",
            "interface.py",
        )
        with open(file_path, "r") as f:
            content = f.read()

        assert "import logging" in content, "interface.py should import logging"
        assert "logger = logging.getLogger(__name__)" in content, "interface.py should define logger"
