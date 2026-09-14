import polars as pl
df1 = pl.DataFrame({"RRN": ["1", "1", "2"], "amount_our": [10, 20, 30], "date_our": ["d1", "d2", "d3"]})
df2 = pl.DataFrame({"RRN": ["1", "3"], "amount_bank": [100, 200], "date_bank": ["d4", "d5"]})
res = df1.join(df2, on="RRN", how="full", coalesce=True)
print(res)
