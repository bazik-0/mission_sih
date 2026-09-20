
import joblib
import pandas as pd

model = joblib.load("model.joblib")

FEATURES = [
    "latitude",
    "longitude",
    "scan",
    "track",
    "track_scan",
    "frp",
    "radiation",
    "brightness",
    "bright_t31",
    "final_bright",
    "acq_time",
    "daynight",
    "confidence",
    "type",
    "match_dist_m"
]

def predict(data):
    X = pd.DataFrame([data])[FEATURES]
    return model.predict(X)[0]

def predict_proba(data):
    X = pd.DataFrame([data])[FEATURES]
    return model.predict_proba(X)[0].tolist()
