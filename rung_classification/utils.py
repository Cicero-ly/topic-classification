from langchain.chains import LLMChain
from langchain import PromptTemplate

    
def decouple_rung(x):
    
  # This is to extract the reason and Rung class from the LLM Response;
  # Still under testing to tackle all types of text output strcuture.

    try:
      
      # Handling the formats of:
      # Class:
      # Reason:

      if '<class>' in x:

        class_point = x[x.index('<class>')+1:]
        rung_class = class_point[class_point.index('>') + 1: class_point.index('<')].strip().lower()
        reason_point = x[x.index('<reason>')+1:]
        rung_reason = reason_point[reason_point.index('>') + 1: reason_point.index('<')].strip()

      else:

        class_point = x[x.lower().index('class'):]

        rung_class = class_point[class_point.replace('-', ':').index(':') + 1: class_point.index('\n')].strip().lower()

        reason_point = x[x.lower().index('score'):]

        rung_reason = reason_point[reason_point.replace('-', ':').index(':') + 1:]
        if 'scratchpad' in rung_reason:
          rung_reason = rung_reason[:rung_reason.index('\n')]

      if 'high' in rung_class:
        rung_class = "high"
      elif "between" in rung_class:
        rung_class = "medium"
      else:
        rung_class = "low"
      els = [rung_class, rung_reason.strip()]

    except Exception as e:

      els = [x, e]
    return els

def identify_rung(source, model):


    prompt = PromptTemplate(
            input_variables=[ "source"], template = """Please read the following source content and follow the instructions given.

    <source>
      {source}
    <source>

    Now, based on the source you’ve just read, please follow these instrcutions:
    <instruction>
    Your primary responsibility is to classify a source's quality.
    A source can be identified as a High rung or a Low Rung or in Between.
    Use the following definitions:
    ### **High Rung Definition**

High rung content is characterized by its depth, nuance, and intellectual rigor. It’s truth seeking and dialectic focused, rather than debate focused and concerned with winning or owning the other side. It aims to inform us about the world in a good faith way. It often requires a significant investment of time and cognitive effort to fully understand. This type of content is usually well-researched, thoroughly cited, and aims to provide a comprehensive understanding of a subject.

### **Low Rung Definition**

Low rung content, on the other hand, is designed for quick consumption and immediate emotional impact. It often relies on sensationalism, clickbait headlines, or superficial analysis. Low rung is all about winning debates, sound bites, and partisan. It falls victim to partisan hackery, ideologically extremism, and logical fallacies.

    You are to present it under 3 separate categories:
    1. Source Title - The title for the article: string
    2. Class - Low Rung or High Rung;
    3. Reason for the score - Give a short and concise reason for the score given.
    <instruction>

    Pull 2-3 relevant quotes from the source that pertain to the instruction and write them inside
    <scratchpad></scratchpad> tags. Then, respond to the instruction.

    Keep your answer direct and don't include your thoughts.
    """)

    chain = LLMChain(llm=model, prompt = prompt)

    rung_scoring = chain.run( source=source,).strip()

    return rung_scoring