from lime.lime_text import LimeTextExplainer

def explain_prediction(text, model, vectorizer, num_features=6):
    explainer = LimeTextExplainer(class_names=['negative', 'positive'])

    def predict_fn(texts):
        return model.predict_proba(vectorizer.transform(texts))

    exp = explainer.explain_instance(
        text, predict_fn, num_features=num_features, num_samples=300
    )
    return [
        {"token": word, "weight": round(float(weight), 4)}
        for word, weight in exp.as_list()
    ]