import constants
import openai
import os

import time

from anthropic import AI_PROMPT, HUMAN_PROMPT, Anthropic
from anthropic import APIStatusError as AnthropicAPIStatusError

anthropic = Anthropic()

# TO-DO: Use langchain wrapper
openai.api_key = os.environ["OPENAI_API_KEY"]

def generate_summary(content: str, title: str):

    human_prompt = f"""
        
            Instruction: Create a introduction to the source then Distill the source into its main arguments or points, and present them in a succinct summary.

            title: {title}
            source content: {content}

            Write the summary directly without including your thoughts.

            Assistant:
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
            if ":" in response:
              response = response[response.index(':')+1:]
            break
        except AnthropicAPIStatusError:
            print(
                f"Anthropic API service unavailable. Retrying again... ({i+1}/{retries})"
            )
            time.sleep(3)
    return response

def generate_short_summary(content: str, title: str):
    human_prompt = f"""

            Instruction: Create a one-sentence summary that can be used as a headline for the source.

            title: {title}
            source content: {content}

            Please follow the instruction details without including any of your thoughts.

            Assistant:
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
            
            if ":" in response:
              response = response[response.index(':')+1:]
            break

        except AnthropicAPIStatusError:
            print(
                f"Anthropic API service unavailable. Retrying again... ({i+1}/{retries})"
            )
            time.sleep(3)
    return response
    
def generate_topics(content: str, title: str):
    human_prompt = f"""
        Pick three topics that properly match the article summary below, based on the topics list provided.
        Your response format should be:
        - TOPIC_1
        - TOPIC_2
        - TOPIC_3

        Do not add a topic that isn't in this list of topics: {constants.topics}
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
            time.sleep(3)

    response = completion.choices[0].message

    parsed_topics = []
    untracked_topics = []
    for topic in response.content.split("\n"):
        stripped_topic = topic.replace("-", "").strip()
        if stripped_topic in constants.topics:
            parsed_topics.append(stripped_topic)

        else:
            
            untracked_topics.append(stripped_topic)

    return {"accepted_topics": parsed_topics, "untracked_topics": untracked_topics}
