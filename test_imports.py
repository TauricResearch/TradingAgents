#!/usr/bin/env python
"""Test imports to find slow modules."""

import time
import sys

def time_import(module_name, import_statement):
    """Time an import statement."""
    start = time.time()
    try:
        exec(import_statement)
        elapsed = time.time() - start
        print(f"✓ {module_name}: {elapsed:.2f}s")
        return True
    except Exception as e:
        print(f"✗ {module_name}: {e}")
        return False

print("Testing imports...")
print("-" * 40)

imports_to_test = [
    ("os", "import os"),
    ("datetime", "from datetime import datetime"),
    ("typing", "from typing import Annotated"),
    ("unittest.mock", "from unittest.mock import Mock"),
    ("pandas", "import pandas"),
    ("numpy", "import numpy"),
    ("yfinance", "import yfinance"),
    ("openai", "from openai import OpenAI"),
    ("langchain_core.messages", "from langchain_core.messages import HumanMessage"),
    ("langchain_core.prompts", "from langchain_core.prompts import ChatPromptTemplate"),
    ("langchain_core.tools", "from langchain_core.tools import tool"),
]

total_start = time.time()
for name, stmt in imports_to_test:
    time_import(name, stmt)

print("-" * 40)
print(f"Total time: {time.time() - total_start:.2f}s")