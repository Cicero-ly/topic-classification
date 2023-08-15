import sys
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
            rejected_topics.append(stripped_topic)
    return {"accepted_topics": parsed_topics, "rejected_topics": rejected_topics}


def summary_seems_incomplete(summary: str):
    terminated_sentence_pattern = r"[.?!][\"\']?$"
    if not re.search(terminated_sentence_pattern, summary):
        return True
    return False


# TODO: LATER: something more robust down the road...possibly tapping into our existing rules db collection
def thought_should_be_processed(thought, parsed_content):
    """
    Determine if thought should be processed according to simple filter rules.
    """
    # Tyler Cowen
    if "assorted links" in thought["title"]:
        return False
    if "appeared first on Marginal REVOLUTION" in parsed_content[-250:]:
        return False
    # Content too short
    if len(parsed_content) < 450:
        return False
    # Content is already truncated
    if "read more" in parsed_content[-250:]:
        return False
    # Ignore content from voice "Public"
    if ObjectId("64505e4c509cac9a8e7e226d") in thought["voicesInContent"]:
        return False
    return True


def store_transcript(thought_pointer, transcript):
    thought_collection = thought_pointer["collection"]
    thought_id = thought_pointer["_id"]

    update_op = thoughts_db[thought_collection].update_one(
        {"_id": thought_id}, {"$set": {"content_transcript": transcript}}
    )

    return update_op.modified_count


def collect_thoughts_for_classification(single_collection_find_limit=1000):
    active_thought_collections = os.environ["ACTIVE_THOUGHT_COLLECTIONS"].split(",")
    print("Active thought collections: ", active_thought_collections)
    thoughts_to_classify = []
    thoughts_to_skip = []

    for collection in active_thought_collections:
        for thought in thoughts_db[collection].find(
            {
                "valuable": True,
                "reviewed": True,
                "title": {"$exists": True},
                "llm_generated_topics": None,
                "url": {"$exists": True},
                "$or": [
                    # If it's an article, it will have "content_text". If it's a youtube video, it will have "vid".
                    {"content_text": {"$exists": True}},
                    {"vid": {"$exists": True}},
                ],
            },
            # Projections
            {
                "_id": 1,
                "url": 1,
                "vid": 1,
                "title": 1,
                "content_text": 1,
                # Used for filtering out certain voices to prevent classification
                "voicesInContent": 1,
            },
            limit=single_collection_find_limit,
        ):
            parsed_content = ""
            # TODO: Refactor this out
            if thought.get("vid") != None:
                try:
                    loader = YoutubeLoader.from_youtube_url(thought.get("url"))
                    document_list = loader.load()
                    if len(document_list) > 0:
                        transcript = document_list[0].page_content
                        parsed_content = transcript
                        documents_modified = store_transcript(
                            {
                                "collection": collection,
                                "_id": thought["_id"],
                            },
                            transcript,
                        )
                        if documents_modified == 0:
                            # TODO: LATER: throw some warning about "transcript not saved"
                            pass
                except youtube_transcript_api._errors.NoTranscriptFound:
                    print(f"No transcript found for youtube video {thought['url']}")
                    continue
            elif thought.get("content_text") != None:
                parsed_content = thought["content_text"]
            else:
                continue

            # Return only the fields necessary for performing summarization/topic classification.
            lean_thought_for_processing = {
                "collection": collection,
                "_id": thought["_id"],
                "content": parsed_content,
                "title": thought["title"],
            }
            if thought_should_be_processed(thought, parsed_content):
                thoughts_to_classify.append(lean_thought_for_processing)
            else:
                thoughts_to_skip.append(lean_thought_for_processing)

    return {
        "thoughts_to_classify": thoughts_to_classify,
        "thoughts_to_classify_count": len(thoughts_to_classify),
        "thoughts_to_skip": thoughts_to_skip,
        "thoughts_to_skip_count": len(thoughts_to_skip),
    }


def main(single_collection_find_limit=1000):
    # Setup/init
    job_id = utils.create_job()

    # Collate thoughts
    classification_candidates = collect_thoughts_for_classification(
        single_collection_find_limit
    )
    thoughts_classified: List[ObjectId] = []
    all_incomplete_summaries = []
    all_rejected_topics = {}

    # Summarize + classify each thought
    for thought in classification_candidates["thoughts_to_classify"]:
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

        # Here we compile all rejected topics for later analysis. We don't need to include
        # reference to the original thought, because the thought itself will contain its own list of
        # accepted and rejected topics.
        for topic in generated_topics["rejected_topics"]:
            if hasattr(all_rejected_topics, topic):
                all_rejected_topics[topic] += 1
            else:
                all_rejected_topics[topic] = 1

        now = utils.get_now()

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

        update_op = thoughts_db[thought["collection"]].update_one(
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
            thoughts_classified.append(
                {"collection": thought["collection"], "_id": thought["_id"]}
            )

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
                "incomplete_summaries_count": len(all_incomplete_summaries),
                "rejected_topics": all_rejected_topics,
            },
        },
    )

    return {
        "quantity_thoughts_classified": len(thoughts_classified),
    }


if __name__ == "__main__":
    try:
        tic = time.perf_counter()
        single_collection_find_limit = int(sys.argv[1])
        print(
            "Limit for querying each collection has been set to: ",
            single_collection_find_limit,
        )
        x = main(single_collection_find_limit=single_collection_find_limit)
        toc = time.perf_counter()
        pprint(x)
        print(f"Time elapsed: {toc-tic:0.4f}")
    except IndexError:
        raise SystemExit(
            f"Missing required positional argument. Usage: {sys.argv[0]} <integer_that_limits_per-collection_find operation>"
        )
