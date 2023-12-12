youtube_thought_collection = "yt"

workflows = {
    "summarization": {
        "name": "summarization",
        "model": "claude-instant-v1-100k",
        "fields_written": "llm_generated_summary",
    },
    "rung_classification": {
        "name": "rung_classification",
        "model": "claude-instant-v1-100k",
        "fields_written": ["llm_rung"],
    },
    "topic_classification": {
        "name": "topic_classification",
        "model": "chatgpt-3.5-turbo",
        "fields_written": "llm_generated_legacy_topics",
    },
}

rung_levels = [
    "high",
    "medium",
    "low"
]

topics = [
    "Anthropology",
    "Archeology",
    "Artificial Intelligence",
    "Biology",
    "Business",
    "Climate",
    "Computer Science",
    "Critical Thinking",
    "Culture",
    "Current Events",
    "Economics",
    "Education",
    "Engineering",
    "Environmental Studies",
    "Evolution",
    "Geology",
    "Geopolitics",
    "Green Energy",
    "History",
    "Investing",
    "Journalism",
    "Law",
    "Leadership",
    "Linguistics",
    "Math",
    "Medicine or Health",
    "Military",
    "Neuroscience",
    "Philosophy",
    "Philosophy of Science",
    "Physics",
    "Political Science",
    "Politics",
    "Psychology",
    "Public Policy",
    "Religion",
    "Social Justice",
    "Sociology",
    "Space",
    "Technology",
]
