import polars as pl
df1 = pl.DataFrame({"RRN": ["1", "1", "1", "2"], "v1": [10, 20, 30, 40]})
df2 = pl.DataFrame({"RRN": ["1", "1", "3"], "v2": [100, 200, 300]})

df1 = df1.with_columns(pl.int_range(0, pl.len()).over("RRN").alias("dup_idx"))
df2 = df2.with_columns(pl.int_range(0, pl.len()).over("RRN").alias("dup_idx"))

res = df1.join(df2, on=["RRN", "dup_idx"], how="full", coalesce=True)
print(res)
