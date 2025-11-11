import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import CountVectorizer

def vectorize_csv(csv_path, text_col, *, analyzer="char_wb", ngram_range=(3, 4), max_features=10000, lowercase=False, encoding=None, as_pandas_sparse=False):
  
    read_args = {"usecols": [text_col]}
    
    if encoding is not None:
        read_args["encoding"] = encoding
        
    df = pd.read_csv(csv_path, **read_args)
    
    if text_col not in df.columns:
        raise ValueError((f"Column '{text_col}' not found in CSV: {csv_path}"))
    
    vectorizer = CountVectorizer(analyzer=analyzer, ngram_range=ngram_range, max_features=max_features, lowercase=lowercase)
    
    X = vectorizer.fit_transform(df[text_col])
    
    if not isinstance(X, csr_matrix):
        X = X.tocsr()
    
    feature_names = vectorizer.get_feature_names_out()
        
    if as_pandas_sparse:
        X_df = pd.DataFrame.sparse.from_spmatrix(X, columns=feature_names)
        return X_df, vectorizer
    
    return X, feature_names, vectorizer