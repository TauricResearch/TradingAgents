import pandas as pd
import time

# Let's create a large dataframe and compare
# df.columns = [str(c).lower() for c in df.columns]
# vs
# df.columns = df.columns.astype(str).str.lower()

# Wait, the task says:
# "Missing optimization on DataFrame creation from iteration"
# "It's generally recommended to pass data structures optimally when generating Pandas dataframes to avoid overhead."
# Wait, look at the code:
# It's in tradingagents/dataflows/stockstats_utils.py:52
