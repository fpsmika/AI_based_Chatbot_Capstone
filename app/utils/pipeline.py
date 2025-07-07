import pandas as pd

def ingest_large_csv(file_path, chunksize=10000):
    """
    Load large CSV file in chunks and combine into one DataFrame.
    """
    chunks = []
    for chunk in pd.read_csv(file_path, chunksize=chunksize):
        chunks.append(chunk)
    df = pd.concat(chunks, ignore_index=True)
    return df
