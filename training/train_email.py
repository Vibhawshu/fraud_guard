import pandas as pd
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
import joblib
import os

os.makedirs('../models', exist_ok=True)
nltk.download('stopwords', quiet=True)
stemmer = PorterStemmer()
stop_words = set(stopwords.words('english'))

# --- 1. Load ---
df = pd.read_csv('../data/phishing_email.csv', on_bad_lines='skip')
df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
df = df.loc[:, ~df.columns.str.startswith('Unnamed')]
print(f"Raw columns found: {list(df.columns)}")

# Auto-detect text column
text_candidates = ['text_combined', 'text', 'Text', 'Email Text', 'body', 'message', 'Email']
text_col = next((c for c in text_candidates if c in df.columns), None)
if text_col is None:
    text_col = df.columns[1]
    print(f"Fallback: using second column '{text_col}' as text")

# Auto-detect label column
label_candidates = ['label', 'Label', 'class', 'Class', 'target', 'phishing']
label_col = next((c for c in label_candidates if c in df.columns), None)
if label_col is None:
    label_col = df.columns[0]
    print(f"Fallback: using first column '{label_col}' as label")

print(f"Using label='{label_col}', text='{text_col}'")

df = df.rename(columns={label_col: 'label', text_col: 'text'})
df = df[['text', 'label']].dropna()
df = df.drop_duplicates(subset=['text'])

# Normalize labels
def to_int(x):
    s = str(x).lower().strip()
    if s in ['1', '1.0', 'phishing', 'spam', 'true', 'yes']: return 1
    if s in ['0', '0.0', 'legitimate', 'ham', 'false', 'no', 'safe']: return 0
    return None

df['label'] = df['label'].apply(to_int)
df = df.dropna(subset=['label'])
df['label'] = df['label'].astype(int)

print(f"Dataset: {len(df)} emails, {df['label'].sum()} phishing, {(df['label'] == 0).sum()} legitimate")

if len(df) == 0:
    raise ValueError("No rows loaded — check CSV column names")

# --- 2. Preprocess ---
def preprocess_email(text):
    text = str(text).lower()
    text = re.sub(r'http\S+|www\.\S+', ' url_token ', text)
    text = re.sub(r'[^a-z\s]', ' ', text)
    tokens = text.split()
    tokens = [stemmer.stem(w) for w in tokens if w not in stop_words]
    return ' '.join(tokens)

df['clean_text'] = df['text'].apply(preprocess_email)

# --- 3. Split ---
X_train, X_test, y_train, y_test = train_test_split(
    df['clean_text'], df['label'],
    test_size=0.2, random_state=42, stratify=df['label']
)

# --- 4. Vectorize ---
vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
X_train_vec = vectorizer.fit_transform(X_train)
X_test_vec = vectorizer.transform(X_test)

# --- 5. Train ---
model = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced')
model.fit(X_train_vec, y_train)

y_pred = model.predict(X_test_vec)
print("\n--- Logistic Regression (Email) ---")
print(classification_report(y_test, y_pred, target_names=['Legitimate', 'Phishing']))

# --- 6. Save ---
joblib.dump(model, '../models/email_model.pkl')
joblib.dump(vectorizer, '../models/email_vectorizer.pkl')
print("Saved: email_model.pkl, email_vectorizer.pkl")