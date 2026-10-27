import joblib
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from pathlib import Path

nltk.download('stopwords', quiet=True)
stemmer = PorterStemmer()
stop_words = set(stopwords.words('english'))

BASE_DIR = Path(__file__).resolve().parent.parent

_sms_model = None
_sms_vectorizer = None
_email_model = None
_email_vectorizer = None

def load_sms():
    global _sms_model, _sms_vectorizer
    if _sms_model is None:
        _sms_model = joblib.load(BASE_DIR / 'models' / 'sms_model.pkl')
        _sms_vectorizer = joblib.load(BASE_DIR / 'models' / 'vectorizer.pkl')

def load_email():
    global _email_model, _email_vectorizer
    if _email_model is None:
        _email_model = joblib.load(BASE_DIR / 'models' / 'email_model.pkl')
        _email_vectorizer = joblib.load(BASE_DIR / 'models' / 'email_vectorizer.pkl')

def preprocess(text, is_email=False):
    text = str(text).lower()
    if is_email:
        text = re.sub(r'http\S+|www\.\S+', ' url_token ', text)
    text = re.sub(r'[^a-z\s]', ' ', text)
    tokens = text.split()
    tokens = [stemmer.stem(w) for w in tokens if w not in stop_words]
    return ' '.join(tokens)

def predict(text: str, message_type: str = "sms"):
    is_email = message_type == "email"

    if is_email:
        load_email()
        model, vectorizer = _email_model, _email_vectorizer
        pos_label, neg_label = "phishing", "legitimate"
    else:
        load_sms()
        model, vectorizer = _sms_model, _sms_vectorizer
        pos_label, neg_label = "spam", "ham"

    clean = preprocess(text, is_email)
    vec = vectorizer.transform([clean])
    proba = model.predict_proba(vec)[0]
    pred = model.predict(vec)[0]

    label = pos_label if pred == 1 else neg_label
    confidence = float(proba[1] if pred == 1 else proba[0])
    return label, confidence, clean, model, vectorizer