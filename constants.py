youtube_thought_collection = "yt"

workflows = {
    "summarization": {
        "name": "summarization",
        "model": "claude-instant-v1-100k",
        "fields_written": "llm_generated_summary",
    },
    "rungness": {
        "name": "rung_classification",
        "model": "claude-instant-v1-100k",
        "fields_written": ["level", "reason"],
    },
    "topic_classification": {
        "name": "topic_classification",
        "model": "chatgpt-3.5-turbo",
        "fields_written": "llm_generated_legacy_topics",
    },
}

rung_classes = [
    "High",
    "In Between",
    "Low"
]
