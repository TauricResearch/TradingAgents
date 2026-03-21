import time
import pandas as pd
import numpy as np

# Let's see how much time it takes to create DataFrame columns using list comprehension vs pandas vectorized string methods

cols = [f"Col_{i}" for i in range(1000000)]
df = pd.DataFrame(columns=cols)

start = time.time()
new_cols_list = [str(c).lower() for c in df.columns]
t1 = time.time() - start

start = time.time()
new_cols_str = df.columns.astype(str).str.lower()
t2 = time.time() - start

print(f"List comprehension: {t1:.6f} s")
print(f"Pandas str.lower(): {t2:.6f} s")

# Maybe "DataFrame creation from iteration" isn't this list comprehension. Let me check the issue.
# Oh, "data = yf.download(...).reset_index()"
