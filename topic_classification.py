import re
import time
import os
from typing import List
from data_stores.mongodb import thoughts_db
from bson.objectid import ObjectId
import utils
import openai
from anthropic import (
    Anthropic,
    HUMAN_PROMPT,
    AI_PROMPT,
    APIStatusError as AnthropicAPIStatusError,
)

from langchain.document_loaders import YoutubeLoader
import youtube_transcript_api
from pprint import pprint

# TODO: LATER: fetch topics from db so this is always up-to-date
from constants import topics as master_topics


anthropic = Anthropic()
openai.api_key = os.environ["OPENAI_API_KEY"]


def generate_summary(content: str, title: str):
    human_prompt = f"""
        Write a 50-300 word summary of the following article, make sure to keep important names. 
        Keep it professional and concise.

        title: {title}
        article content: {content}
    """

    retries = 5
    for i in range(retries):
        try:
            prompt = f"{HUMAN_PROMPT}: You are a frequent contributor to Wikipedia. \n\n{human_prompt}\n\n{AI_PROMPT}:\n\nSummary:\n\n"
            completion = anthropic.completions.create(
                prompt=prompt,
                model="claude-instant-v1-100k",
                max_tokens_to_sample=100000,
                temperature=0,
            )
            response = completion.completion.strip(" \n")
            break
        except AnthropicAPIStatusError:
            print(
                f"Anthropic API service unavailable. Retrying again... ({i+1}/{retries})"
            )
            time.sleep(1)
    return response


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

        Here are some notes regarding topics which are identical but might be called different names: 
        - If you choose "Mathematics" as a topic, please just call it "Math".
        - If you choose "Health" as a topic, please call it "Medicine or Health."
        - If you choose "Film" as a topic, please just call it "Culture".

        Article title: {title}
        Article summary: {content}
    """

    retries = 5
    for i in range(retries):
        try:
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
            break
        except openai.error.ServiceUnavailableError:
            print(f"OpenAI service unavailable. Retrying again... ({i+1}/{retries})")
            time.sleep(1)

    response = completion.choices[0].message

    parsed_topics = []
    rejected_topics = []
    for topic in response.content.split("\n"):
        stripped_topic = topic.replace("-", "").strip()
        if stripped_topic in master_topics:
            parsed_topics.append(stripped_topic)
        else:
            print("Rejected this topic: ", stripped_topic)
            rejected_topics.append(stripped_topic)
    return {"accepted_topics": parsed_topics, "rejected_topics": rejected_topics}


def summary_seems_incomplete(summary: str):
    regExp = r"[^.?]$"  # A regular expression that matches for end-of-strings which do NOT end in a period or question mark.
    if re.search(regExp, summary):
        return True
    return False


# TODO: LATER: something more robust down the road...possibly tapping into our existing rules db collection
def thought_should_be_processed(thought, parsedContent):
    """
    Determine if thought should be processed according to simple filter rules.
    """
    # Tyler Cowen
    if "assorted links" in thought["title"]:
        return False
    if "appeared first on Marginal REVOLUTION" in parsedContent[-250:]:
        return False
    # Content too short
    if len(parsedContent) < 450:
        return False
    # Content is already truncated
    if "read more" in parsedContent[-250:]:
        return False
    # Ignore content from voice "Public"
    if ObjectId("64505e4c509cac9a8e7e226d") in thought["voicesInContent"]:
        return False
    return True


def store_transcript(thought_pointer, transcript):
    # thought_collection = thought_pointer["collection"]
    thought_id = thought_pointer["_id"]

    # update_op = thoughts_db[thought_collection].update_one(
    #     {"_id": thought_id}, {"$set": {"content_transcript": transcript}}
    # )

    # TEST
    update_op = thoughts_db["test_topic_classification"].update_one(
        {"_id": thought_id}, {"$set": {"content_transcript": transcript}}
    )

    return update_op.modified_count


def collect_thoughts_for_classification(limit=1000):
    # print("active thought collections: ", os.environ["ACTIVE_THOUGHT_COLLECTIONS"])
    thoughts_to_classify = []
    thoughts_to_skip = []
    # for collection in os.environ["ACTIVE_THOUGHT_COLLECTIONS"].split(","):
    # for thought in thoughts_db[collection].find(
    for thought in thoughts_db["test_topic_classification"].find(
        {
            "valuable": True,
            "reviewed": True,
            "title": {"$ne": None},
            # TODO: LATER: Do we want to filter for thoughts that have already been topic-classified?
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
            "voicesInContent": 1,
        },
        limit=limit,
    ):
        parsedContent = ""
        if thought.get("vid") != None:
            try:
                loader = YoutubeLoader.from_youtube_url(thought.get("url"))
                transcript = loader.load()
                if len(transcript) > 0:
                    parsedContent = transcript[0].page_content
                    documents_modified = store_transcript(
                        {
                            # "collection": "yt",
                            "_id": thought["_id"]
                        },
                        parsedContent,
                    )
                    if documents_modified == 0:
                        # throw some warning about "transcript not saved"
                        pass
            except youtube_transcript_api._errors.NoTranscriptFound:
                print(f"No transcript found for youtube video {thought['url']}")
                continue
        elif thought.get("content_text") != None:
            parsedContent = thought["content_text"]
        else:
            continue

        # Only the fields necessary for performing summarization/topic classification.
        lean_thought_for_processing = {
            # "collection": collection,
            # "collection": thought["collection"],
            "_id": thought["_id"],
            "content": parsedContent,
            "title": thought["title"],
        }
        if thought_should_be_processed(thought, parsedContent):
            thoughts_to_classify.append(lean_thought_for_processing)
        else:
            thoughts_to_skip.append(lean_thought_for_processing)

    return {
        "thoughts_to_classify": thoughts_to_classify,
        "thoughts_to_classify_count": len(thoughts_to_classify),
        "thoughts_to_skip": thoughts_to_skip,
        "thoughts_to_skip_count": len(thoughts_to_skip),
    }


def main(limit=1000):
    # TODO: LATER: Clean up this function from all this job mgmt logic
    job_id = utils.create_job()

    classification_candidates = collect_thoughts_for_classification(limit)
    thoughts_classified: List[ObjectId] = []
    all_incomplete_summaries = []
    all_rejected_topics = {}

    for thought in classification_candidates["thoughts_to_classify"]:
        now = utils.get_now()

        generated_summary = generate_summary(thought["content"], thought["title"])
        if summary_seems_incomplete(generated_summary):
            all_incomplete_summaries.append(
                {
                    "_id": thought["_id"],
                    "title": thought["title"],
                    "generated_summary": generated_summary,
                }
            )

        generated_topics = generate_topics(generated_summary, thought["title"])

        # compile all rejected topics for later analysis. Don't need to include
        # reference to the original thought, because we'll write both accepted and rejected topics
        # to the thought in the final write operation (see below)
        for topic in generated_topics["rejected_topics"]:
            if hasattr(all_rejected_topics, topic):
                all_rejected_topics[topic] += 1
            else:
                all_rejected_topics[topic] = 1

        workflows_completed = [
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
        ]

        update_op = thoughts_db["test_topic_classification"].update_one(
            {"_id": thought["_id"]},
            {
                "$set": {
                    "llm_generated_summary": generated_summary,
                    "llm_generated_topics": generated_topics,  # This includes both accepted and rejected topics.
                    "llm_processing_metadata": {
                        "workflows_completed": workflows_completed,
                        "fields_written": [
                            "llm_generated_summary",
                            "llm_generated_topics",
                        ],
                    },
                }
            },
        )

        if update_op.modified_count == 1:
            thoughts_classified.append(thought["_id"])

    utils.update_job(
        job_id,
        {
            "status": "complete",
            "last_updated": utils.get_now(),
            "workflows_completed": workflows_completed,
            "thoughts_updated": thoughts_classified,
            "thoughts_updated_count": len(thoughts_classified),
            "job_metadata": {
                "incomplete_summaries": all_incomplete_summaries,
                "rejected_topics": all_rejected_topics,
            },
        },
    )

    return dict(
        {
            "quantity_thoughts_modified": len(thoughts_classified),
        }
    )


if __name__ == "__main__":
    tic = time.perf_counter()
    x = main(limit=10)
    # x = main()
    toc = time.perf_counter()
    pprint(x)
    print(f"Time elapsed: {toc-tic:0.4f}")

# TODO: add back db -> collection for loop
# TODO: add back if_thought_should_be_classified filter
# TODO: clean up
# TODO: collect the "omitted topics" to later analyze for good additions to our topics list!
