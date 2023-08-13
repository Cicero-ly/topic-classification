import time
import datetime
import os
from data_stores.mongodb import thoughts_db
from langchain.chat_models import ChatOpenAI, ChatAnthropic
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.document_loaders import YoutubeLoader
from pprint import pprint

# TODO: fetch topics from db so this is always up-to-date
from constants import topics as master_topics

# Ramsis has custom class for Claude. Why?
# It seems that in the Colab, he's instantiating with the default vars that are already set in a
# vanilla instantiation of ChatAnthropic(). Only one I'm unsure of: stop_sequences (which technically isn't available in https://api.python.langchain.com/en/latest/chat_models/langchain.chat_models.anthropic.ChatAnthropic.html#langchain.chat_models.anthropic.ChatAnthropic)
# also his custom class sets up the right prompt format ({HUMAN_PROMPT}\n{prompt}\n\n{AI_PROMPT}\n) which ChatAnthropic() already does
claude = ChatAnthropic(
    model="claude-instant-v1-100k", anthropic_api_key=os.environ["ANTHROPIC_API_KEY"]
)
chatgpt = ChatOpenAI(temperature=0, model="gpt-3.5-turbo")


def call_chat_model(llm, messages):
    """
    This is called "call_chat_model" because it accepts an array of messages (as opposed to a string, which would be
    a simple completion for any LLM, not necessarily a chat LLM.)
    """
    try:
        response = llm(messages)
        return response
    except Exception as e:
        print(e)


def generate_summary(content, title):
    system_message_prompt = SystemMessagePromptTemplate.from_template(
        template="""
            You are a frequent contributor to Wikipedia.
        """
    )

    human_message_prompt = HumanMessagePromptTemplate.from_template(
        template="""
            Write a short summary of the following article, make sure to keep important names. Keep it professional and concise.
            I only want you to return the summary itself. Do not include any announcements like "Here is the summary" in your response.
            Most importantly, please make sure finish your thoughts—do not leave any sentences or thoughts incomplete!
            
            Article title: {title}
            Article content: {content}
        """
    )

    chat_prompt = ChatPromptTemplate.from_messages(
        [system_message_prompt, human_message_prompt]
    )

    chat_messages = chat_prompt.format_prompt(
        title=title, content=content
    ).to_messages()

    response = call_chat_model(claude, chat_messages)
    response = response.content.replace("\n", "").strip()
    return response


def generate_topics(content, title):
    system_message_prompt = SystemMessagePromptTemplate.from_template(
        template="""
            You are a frequent contributor to Wikipedia and have a deep understanding of its taxonomy.
        """
    )

    human_message_prompt = HumanMessagePromptTemplate.from_template(
        template="""
            Pick three topics that properly match the article summary below, based on the topics list provided.
            Your response format should be:
            - TOPIC_1
            - TOPIC_2
            - TOPIC_3

            Do not add a topic that isn't in this list of topics: {topics}
            Feel free to use less than three topics if you can't find three topics from the list that are a good fit.

            Article title: {title}
            Article summary: {content}
        """
    )

    chat_prompt = ChatPromptTemplate.from_messages(
        [system_message_prompt, human_message_prompt]
    )
    chat_messages = chat_prompt.format_prompt(
        topics=master_topics, title=title, content=content
    ).to_messages()

    response = call_chat_model(chatgpt, chat_messages)

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
            # TODO: Do we want to re-classify thoughts that have been classified?
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
            # TODO: handle NoTranscriptFound exception
            except Exception as e:
                print(e)
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
        # print("collection", thought["collection"])
        # print("_id", thought["_id"])
        # print("title: ", thought["title"])

        now = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
        generated_summary = generate_summary(thought["content"], thought["title"])
        # print("generated_summary: ", generated_summary)
        generated_topics = generate_topics(generated_summary, thought["title"])
        # print("generated_topics: ", generated_topics)

        updateOp = thoughts_db["test_topic_classification"].update_one(
            {"_id": thought["_id"]},
            {
                "$set": {
                    "summary": generated_summary,
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
                        "fields_written": ["summary", "llm_generated_topics"],
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
                }
            )

    return thoughts_classified


if __name__ == "__main__":
    tic = time.perf_counter()
    x = topic_classification(limit=1)
    # x = topic_classification()
    toc = time.perf_counter()
    pprint(x)
    print(f"Finished topic classification in {toc - tic:0.4f} seconds")
