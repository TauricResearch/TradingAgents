import pandas as pd
df = pd.DataFrame({"A": [1,2,3]})
df.to_csv("test_cache.csv", index=False)
try:
    pd.read_csv("test_cache.csv", engine="pyarrow", on_bad_lines="skip")
    print("Success")
except Exception as e:
    print("Error:", e)
