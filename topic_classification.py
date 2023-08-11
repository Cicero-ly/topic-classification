import datetime
import os
from data_stores.mongodb import thoughts_db
from langchain import LLMChain, PromptTemplate
from langchain.chat_models import ChatOpenAI, ChatAnthropic
from langchain.document_loaders import YoutubeLoader
from pprint import pprint

# TODO: fetch topics from db so this is always up-to-date
from constants import topics

# Ramsis has custom class for Claude. Why?
# It seems that in the Colab, he's instantiating with the default vars that are already set in a
# vanilla instantiation of ChatAnthropic(). Only one I'm unsure of: stop_sequences (which technically isn't available in https://api.python.langchain.com/en/latest/chat_models/langchain.chat_models.anthropic.ChatAnthropic.html#langchain.chat_models.anthropic.ChatAnthropic)
# also his custom class sets up the right prompt format ({HUMAN_PROMPT}\n{prompt}\n\n{AI_PROMPT}\n) which ChatAnthropic() already does
claude = ChatAnthropic(
    model="claude-instant-v1-100k", anthropic_api_key=os.environ["ANTHROPIC_API_KEY"]
)
chatgpt = ChatOpenAI(temperature=0, model="gpt-3.5-turbo")


def generate_summary(content, title, llm):
    prompt = PromptTemplate(
        input_variables=["content", "title"],
        template="""
        Write a 50-300 word summary of the following article, make sure to keep important names. Keep it professional and concise.
        title: {title}
        article content: {content}
        """,
    )
    try:
        chain = LLMChain(llm=llm, prompt=prompt)
        response = chain.run(content=content, title=title)
        response = response.replace("\n", "").strip()
    except Exception as e:
        print(e)
        response = e
    return response


def generate_topics(content, title, llm):
    if llm is None:
        llm = chatgpt

    prompt = PromptTemplate(
        input_variables=["question", "docs", "topics", "title"],
        template="""
      You are a WikiPedia assistant that that can identify main topics about the given video transcript or article.
      You will pick topics that may be included for the article based on the topics list provided.
      The format should be:
      - TOPIC_1
      - TOPIC_2
      - TOPIC_3

      Answer the following question: {question}

      article title: {title}
      By analyzing the following summary: {docs}

      Make sure to always pick topics only from these following ones: {topics}
      Never invent topics and if you can't find 3 topics englobing the article, you can use less.


      """,
    )

    try:
        chain = LLMChain(llm=llm, prompt=prompt)
        response = chain.run(
            question="identify 3 topics from the list provided only.",
            docs=content,
            topics=", ".join(topics),
            title=title,
        )
    except Exception as e:
        print(e)

    returned_topics = [topic.replace("-", "").strip() for topic in response.split("\n")]
    return returned_topics


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


def topic_classification(limit=10):
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
            loader = YoutubeLoader.from_youtube_url(thought.get("url"))
            transcript = loader.load()
            content = transcript
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

        summarization_llm = claude
        topic_generation_llm = chatgpt

        now = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
        generated_summary = generate_summary(
            thought["content"], thought["title"], llm=summarization_llm
        )
        # print("generated_summary: ", generated_summary)
        generated_topics = generate_topics(
            generated_summary, thought["title"], llm=topic_generation_llm
        )
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
    x = topic_classification(limit=2)
    pprint(x)
