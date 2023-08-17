import os
import time
from pprint import pprint
from typing import List

import openai
import pymongo
from anthropic import AI_PROMPT, HUMAN_PROMPT, Anthropic
from anthropic import APIStatusError as AnthropicAPIStatusError
from bson.objectid import ObjectId
from langchain.document_loaders import YoutubeLoader
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptAvailable,
    NoTranscriptFound,
)

import utils

# TODO: LATER: fetch topics from db so this is always up-to-date
from constants import topics as master_topics
from constants import workflows
from data_stores.mongodb import thoughts_db

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
        - If you choose "Film", "Music", or "Art" as a topic, please just call it "Culture".

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
    errors = []

    for collection in active_thought_collections:
        for thought in thoughts_db[collection].find(
            {
                "valuable": True,
                "reviewed": True,
                "voicesInContent": {"$exists": True},
                "title": {"$exists": True},
                "url": {"$exists": True},
                "llm_generated_legacy_topics": {"$exists": False},
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
                # in thought_should_be_processed()
                "voicesInContent": 1,
            },
            limit=single_collection_find_limit,
            sort=[("_id", pymongo.DESCENDING)],
        ):
            parsed_content = ""
            # TODO: LATER: Refactor this out
            if thought.get("vid") != None:
                try:
                    # Right now, we are fetching fresh transcripts even if a youtube thought
                    # already has a transcript in `content_transcript`, since it was alluded to
                    # previously that those were quite poor
                    loader = YoutubeLoader.from_youtube_url(thought.get("url"))
                    document_list = loader.load()
                    if len(document_list) > 0:
                        transcript = document_list[0].page_content
                        parsed_content = transcript
                        store_transcript(
                            {
                                "collection": collection,
                                "_id": thought["_id"],
                            },
                            transcript,
                        )
                except (
                    NoTranscriptFound
                    or NoTranscriptAvailable
                    or CouldNotRetrieveTranscript
                ):
                    # Handling these exceptions separately, because the error message
                    # is egregiously long (contains information about all the languages that
                    # are and aren't available)
                    transcript_not_found_error = f"Error getting transcript for Youtube video at {thought['url']} due to NoTranscriptFound, NoTranscriptAvaialble, or CouldNotRetrieveTranscript."
                    errors.append(transcript_not_found_error)
                except Exception as e:
                    print(
                        f"Misc. error getting transcript for Youtube video at {thought['url']}—see below:"
                    )
                    print(e)
                    errors.append(str(e))
            elif thought.get("content_text") != None:
                parsed_content = thought["content_text"]
            else:
                continue

            # Return only the fields necessary for performing summarization/topic classification.
            if thought_should_be_processed(thought, parsed_content):
                thoughts_to_classify.append(
                    {
                        "collection": collection,
                        "_id": thought["_id"],
                        "content": parsed_content,
                        "title": thought["title"],
                    }
                )
            else:
                thoughts_to_skip.append(
                    {
                        "collection": collection,
                        "_id": thought["_id"],
                    }
                )

    return {
        "active_thought_collections": active_thought_collections,
        "thoughts_to_classify": thoughts_to_classify,
        "thoughts_to_classify_count": len(thoughts_to_classify),
        "thoughts_to_skip": thoughts_to_skip,
        "thoughts_to_skip_count": len(thoughts_to_skip),
        "errors": errors,
    }


def main(single_collection_find_limit=10000):
    # Setup/init
    job_id = utils.create_job()
    collected_thought_data = {}
    thoughts_classified: List[ObjectId] = []
    all_rejected_topics = {}
    data_collection_errors = []
    ai_processing_errors = []

    # Collect thoughts
    collected_thought_data = collect_thoughts_for_classification(
        single_collection_find_limit
    )
    data_collection_errors.extend(collected_thought_data["errors"])

    # Summarize + classify each thought
    for thought in collected_thought_data["thoughts_to_classify"]:
        try:
            generated_summary = generate_summary(thought["content"], thought["title"])
            generated_topics = generate_topics(generated_summary, thought["title"])

            # Here we compile all rejected topics for later analysis. We don't need to include
            # reference to the original thought, because the thought itself will contain its own list of
            # accepted and rejected topics.
            for topic in generated_topics["rejected_topics"]:
                if all_rejected_topics.get(topic) is not None:
                    all_rejected_topics[topic] += 1
                else:
                    all_rejected_topics[topic] = 1

            update_op = thoughts_db[thought["collection"]].update_one(
                {"_id": thought["_id"]},
                {
                    "$set": {
                        "llm_generated_summary": generated_summary,
                        "llm_generated_legacy_topics": generated_topics,  # This includes both accepted and rejected topics.
                        "llm_processing_metadata": {
                            "workflows_completed": [
                                workflows["summarization"],
                                workflows["topic_classification"],
                            ],
                            "fields_written": [
                                workflows["summarization"]["fields_written"],
                                workflows["topic_classification"]["fields_written"],
                            ],
                        },
                    }
                },
            )

            if update_op.modified_count == 1:
                thoughts_classified.append(
                    {"collection": thought["collection"], "_id": thought["_id"]}
                )
        except Exception as e:
            ai_processing_errors.append(str(e))
            print(e)

    # Finish up, log the job
    utils.update_job(
        job_id,
        {
            "status": "complete",
            "last_updated": utils.get_now(),
            "workflows_completed": [
                workflows["summarization"],
                workflows["topic_classification"],
            ],
            "job_metadata": {
                "collections_queried": collected_thought_data[
                    "active_thought_collections"
                ],
                "thoughts_updated": thoughts_classified,
                "thoughts_updated_count": len(thoughts_classified),
                "thoughts_skipped": collected_thought_data["thoughts_to_skip"],
                "thoughts_skipped_count": collected_thought_data[
                    "thoughts_to_skip_count"
                ],
                "rejected_topics": all_rejected_topics,
                "errors": {
                    "data_collection_errors": data_collection_errors,
                    "ai_processing_errors": ai_processing_errors,
                },
            },
        },
    )

    return {
        "quantity_thoughts_classified": len(thoughts_classified),
    }


if __name__ == "__main__":
    tic = time.perf_counter()

    python_env = os.environ.get("PYTHON_ENV", "development")
    if python_env == "production":
        single_collection_find_limit = os.environ["SINGLE_COLLECTION_FIND_LIMIT"]
    elif python_env == "data_analysis":
        # A larger `n` for testing AI performance and performing more substantive data analysis.
        single_collection_find_limit = 100
    else:
        # A small `n` for operational testing/container testing.
        single_collection_find_limit = 3
    print(
        "Limit for querying each collection has been set to: ",
        single_collection_find_limit,
    )
    x = main(single_collection_find_limit=single_collection_find_limit)

    toc = time.perf_counter()

    pprint(x)
    print(f"Time elapsed: {toc-tic:0.4f}")
