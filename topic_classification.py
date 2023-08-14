import time
import datetime
import os
from data_stores.mongodb import thoughts_db
import openai
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT

from langchain.document_loaders import YoutubeLoader
import youtube_transcript_api
from pprint import pprint

# TODO: fetch topics from db so this is always up-to-date
from constants import topics as master_topics

# TODO: openai.error.ServiceUnavailableError: The server is overloaded or not ready yet.
# Need a simple for loop retry for any openai requests to handle the above

anthropic = Anthropic()
openai.api_key = os.environ["OPENAI_API_KEY"]


def generate_summary(content: str, title: str):
    # MODIFIED PROMPT
    # human_prompt = f"""
    #     Write a short summary of the following article, and make sure to keep important names. Keep it professional and concise.
    #     I only want you to return the summary itself, as if it would be published on Wikipedia. Let's assume that your initial response is perfect, and that it doesn't need to be modified in any way.
    #     Most importantly, please make sure finish your thoughts. Do not leave any sentences or thoughts incomplete!
    #     Feel free to make your response shorter if you feel like you cannot capture the entire summary in the number of words you are allowed to provide.

    #     Article title: {title}
    #     Article content: {content}
    # """

    # ORIGINAL PROMPT
    human_prompt = f"""
        Write a 50-300 word summary of the following article, make sure to keep important names. 
        Keep it professional and concise.

        title: {title}
        article content: {content}
    """

    # response = call_chat_model(claude, chat_messages)
    prompt = f"{HUMAN_PROMPT}: You are a frequent contributor to Wikipedia. \n\n{human_prompt}\n\n{AI_PROMPT}:\n\nSummary:\n\n"
    completion = anthropic.completions.create(
        prompt=prompt,
        model="claude-instant-v1-100k",
        max_tokens_to_sample=100000,
        temperature=0,
    )
    response = completion.completion.strip(" \n")
    return response


# def clean_up_claude_summary(content: str):
#     human_prompt = f"""
#         Below is a short summary of an article or video that an assistant of mine created, which they sent to me via email.
#         I want to you to identify any comments that my assistant included and cut them out, such that all that's left is the summary itself.
#         Sometimes, my assistant didn't include any comments, in which case—leave it alone.

#         Original summary from my assistant: {content}
#         New summary:
#     """
#     completion = openai.ChatCompletion.create(
#         model="gpt-3.5-turbo",
#         # TODO: temperature=0
#         messages=[
#             {
#                 "role": "system",
#                 "content": "You are a frequent contributor to Wikipedia.",
#             },
#             {"role": "user", "content": human_prompt},
#         ],
#     )

#     response = completion.choices[0].message
#     return response.content


def generate_topics(content: str, title: str):
    human_prompt = f"""
        Pick three topics that properly match the article summary below, based on the topics list provided.
        Your response format should be:
        - TOPIC_1
        - TOPIC_2
        - TOPIC_3

        Do not add a topic that isn't in this list of topics: {master_topics}
        Feel free to use less than three topics if you can't find three topics from the list that are a good fit.
        If you pick a topic that is two words or more, make sure every word is capitalized (not just the first word).

        Article title: {title}
        Article summary: {content}
    """

    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are a frequent contributor to Wikipedia, and have a deep understanding of Wikipedia's categories and topics.",
            },
            {"role": "user", "content": human_prompt},
        ],
    )

    # print(completion.choices[0].message)
    response = completion.choices[0].message

    parsed_topics = []
    for topic in response.content.split("\n"):
        stripped_topic = topic.replace("-", "").strip()
        if stripped_topic in master_topics:
            parsed_topics.append(stripped_topic)
        else:
            print("Omitted this topic: ", stripped_topic)
    return parsed_topics


# TODO: something more robust down the road...possibly tapping into our existing rules db collection
def thought_should_be_processed(content, title):
    """
    Determine if thought should be processed according to simple filter rules.
    """
    if "assorted links" in title:
        return False
    if len(content) < 450:
        return False
    if "read more" in content[-250:]:
        return False
    if "appeared first on Marginal REVOLUTION" in content[-250:]:
        return False

    return True


def topic_classification(limit=1000):
    # print("active thought collections: ", os.environ["ACTIVE_THOUGHT_COLLECTIONS"])
    thoughts_to_classify = []
    # for collection in os.environ["ACTIVE_THOUGHT_COLLECTIONS"].split(","):
    # for thought in thoughts_db[collection].find(
    for thought in thoughts_db["test_topic_classification"].find(
        {
            "valuable": True,
            "title": {"$ne": None},
            # TODO: Do we want to filter for thoughts that have already been topic-classified?
            # If so, remove this
            "llm_generated_topics": None,
            "url": {"$ne": None},
            "$or": [
                # conditionally find content_text if articles only
                {"content_text": {"$ne": None}},
                {"vid": {"$ne": None}},
            ],
        },
        {
            "_id": 1,
            "url": 1,
            "vid": 1,
            "title": 1,
            "content_text": 1,
        },
        limit=limit,
    ):
        content = ""
        if thought.get("vid") != None:
            try:
                loader = YoutubeLoader.from_youtube_url(thought.get("url"))
                transcript = loader.load()
                content = transcript
            except youtube_transcript_api._errors.NoTranscriptFound:
                print(f"No transcript found for youtube video {thought['url']}")
                continue
        elif thought.get("content_text") != None:
            content = thought["content_text"]
        else:
            continue

        # if thought_should_be_processed(content, title):
        thoughts_to_classify.append(
            {
                # "collection": collection,
                # "collection": thought["collection"],
                "_id": thought["_id"],
                "title": thought["title"],
                "content": content,
            }
        )

    print("thoughts_to_classify length:", len(thoughts_to_classify))

    thoughts_classified = []
    for thought in thoughts_to_classify:
        now = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
        claude_generated_summary = generate_summary(
            thought["content"], thought["title"]
        )
        # final_generated_summary = clean_up_claude_summary(claude_generated_summary)
        final_generated_summary = claude_generated_summary
        # TODO: throw a warning if summary doesn't end in "." or "?" (summary seems incomplete).
        generated_topics = generate_topics(final_generated_summary, thought["title"])

        updateOp = thoughts_db["test_topic_classification"].update_one(
            {"_id": thought["_id"]},
            {
                "$set": {
                    "llm_generated_summary": final_generated_summary,
                    "llm_generated_topics": generated_topics,
                    "llm_processing_metadata": {
                        "workflows_performed": [
                            {
                                "name": "summarization",
                                "model": "claude-instant-v1-100k",
                                "last_performed": now,
                            },
                            {
                                "name": "topic_classification",
                                "model": "chatgpt-3.5-turbo",
                                "last_performed": now,
                            },
                        ],
                        "fields_written": [
                            "llm_generated_summary",
                            "llm_generated_topics",
                        ],
                    },
                }
            },
        )

        if updateOp.modified_count == 1:
            thoughts_classified.append(
                {
                    "_id": thought["_id"],
                    "title": thought["title"],
                    "llm_topics": generated_topics,
                    "claude_summary": claude_generated_summary,
                    # "chatgpt_cleaned_summary": final_generated_summary,
                }
            )

    return thoughts_classified


if __name__ == "__main__":
    tic = time.perf_counter()
    x = topic_classification(limit=100)
    # x = topic_classification()
    toc = time.perf_counter()
    pprint(x)
    print(f"Time elapsed: {toc-tic:0.4f}")

# TODO: add back db -> collection for loop
# TODO: add back if_thought_should_be_classified filter
# TODO: clean up
# TODO: collect the "omitted topics" to later analyze for good additions to our topics list!
