import pandas as pd
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
import joblib
import os

# Ensure models folder exists
os.makedirs('../models', exist_ok=True)

nltk.download('stopwords', quiet=True)

# --- 1. Load data ---
df = pd.read_csv('../data/sms_spam.csv', encoding='latin-1', on_bad_lines='skip')
# Handle both naming conventions
if 'v1' in df.columns:
    df = df.rename(columns={'v1': 'label', 'v2': 'text'})
df = df[['label', 'text']].dropna()
df = df.drop_duplicates(subset=['text'])

# Normalize labels
df['label'] = df['label'].astype(str).str.lower().str.strip()
df['label_num'] = df['label'].map({'ham': 0, 'spam': 1, '0': 0, '1': 1})
df = df.dropna(subset=['label_num'])
df['label_num'] = df['label_num'].astype(int)

print(f"Dataset: {len(df)} messages, {df['label_num'].sum()} spam")

# --- 2. Preprocess ---
stemmer = PorterStemmer()
stop_words = set(stopwords.words('english'))

def preprocess(text):
    text = str(text).lower()
    text = re.sub(r'[^a-z\s]', '', text)
    tokens = text.split()
    tokens = [stemmer.stem(w) for w in tokens if w not in stop_words]
    return ' '.join(tokens)

df['clean_text'] = df['text'].apply(preprocess)

# --- 3. Split ---
X_train, X_test, y_train, y_test = train_test_split(
    df['clean_text'], df['label_num'],
    test_size=0.2, random_state=42, stratify=df['label_num']
)

# --- 4. Vectorize ---
vectorizer = TfidfVectorizer(max_features=3000, ngram_range=(1, 2))
X_train_vec = vectorizer.fit_transform(X_train)
X_test_vec = vectorizer.transform(X_test)

# --- 5. Train and compare ---
models = {
    'Naive Bayes': MultinomialNB(),
    'Logistic Regression': LogisticRegression(
        max_iter=1000, random_state=42, class_weight='balanced'
    )
}

best_model = None
best_f1 = 0
best_name = ''

for name, model in models.items():
    model.fit(X_train_vec, y_train)
    y_pred = model.predict(X_test_vec)
    print(f"\n--- {name} ---")
    print(classification_report(y_test, y_pred, target_names=['Ham', 'Spam']))
    f1 = f1_score(y_test, y_pred, pos_label=1)
    if f1 > best_f1:
        best_f1 = f1
        best_model = model
        best_name = name

# --- 6. Save ---
joblib.dump(best_model, '../models/sms_model.pkl')
joblib.dump(vectorizer, '../models/vectorizer.pkl')
print(f"\nSaved best model: {best_name} (F1={best_f1:.3f})")