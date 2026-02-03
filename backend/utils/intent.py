def is_casual_message(text: str) -> bool:
    casual_keywords = [
        "hi", "hello", "hey", "how are you",
        "what's up", "thanks", "thank you",
        "bye", "good morning", "good evening"
    ]

    t = text.lower().strip()
    return any(k in t for k in casual_keywords)
