import pandas as pd
csv = r'C:\Users\Vaishnavi\.cache\kagglehub\datasets\abdallahwagih\movies\versions\1\movies.csv'
df = pd.read_csv(csv)

with open('_inspection_output2.txt', 'w', encoding='utf-8') as f:
    f.write(f"SHAPE: {df.shape}\n\n")
    
    # Show just the key columns we care about
    cols_of_interest = ['title', 'genres', 'vote_average', 'vote_count', 'release_date', 'overview', 'director']
    for col in cols_of_interest:
        if col in df.columns:
            f.write(f"\n--- {col} (first 5) ---\n")
            for i, val in enumerate(df[col].head(5)):
                f.write(f"  [{i}] {val}\n")
    
    f.write(f"\n\nAll columns: {list(df.columns)}\n")
    f.write(f"Missing values:\n")
    for col in df.columns:
        nulls = df[col].isnull().sum()
        if nulls > 0:
            f.write(f"  {col}: {nulls}\n")
            
print("Done -> _inspection_output2.txt")
