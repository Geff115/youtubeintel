def verify_prediction(channel_id: str, prediction: str) -> bool:
    # You can hash the input or do sanity checks
    return "views" in prediction.lower() and "subscriber" in prediction.lower()