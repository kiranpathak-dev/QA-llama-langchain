# -*- coding: utf-8 -*-
"""Question-Answering on Your Own Data.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1B5kjsxBg0tRXzcK05NzKb0B6tMNyqB6Q

# Using LLaMA 2.0, FAISS and LangChain for Question-Answering on Your Own Data
Question-Answering (QA) chatbot using Llama-2–7b-chat model with LangChain framework and FAISS library over the documents fetched online from Databricks documentation website.

* LLaMA 2 model is one of the powerful open source models.
* LangChain is a powerful, open-source framework designed to help you develop applications powered by a language model, particularly a large language model (LLM).
* FAISS (Facebook AI Similarity Search) is a library for efficient similarity search and clustering of dense vectors.

# Process Flow
* **Initialize model pipeline**: initializing text-generation pipeline with Hugging Face transformers for the pretrained Llama-2-7b-chat-hf model.

* **Ingest data**: loading the data from arbitrary sources in the form of text into the document loader.

* **Split into chunks**: splitting the loaded text into smaller chunks. It is necessary to create small chunks of text because language models can handle limited amount of text.

* **Create embeddings**: converting the chunks of text into numerical values, also known as embeddings. These embeddings are used to search and retrieve similar or relevant documents quickly in large databases, as they represent the semantic meaning of the text.

* **Load embeddings into vector store**: loading the embeddings into a vector store i.e. “FAISS” in this case. Vector stores perform extremely well in similarity search using text embeddings compared to the traditional databases.

* **Enable memory**: combing chat history with a new question and turn them into a single standalone question is quite important to enable the ability to ask follow up questions.

* **Query data**: searching for the relevant information stored in vector store using the embeddings.

* **Generate answer**: passing the standalone question and the relevant information to the question-answering chain where the language model is used to generate an answer.

# Getting Started
You can use the open source Llama-2-7b-chat model in both Hugging Face transformers and LangChain. However, you have to first request access to Llama 2 models via [Meta website](https://ai.meta.com/resources/models-and-libraries/llama-downloads) and also accept to share your account details with Meta on [Hugging Face website](https://huggingface.co/meta-llama/Llama-2-7b-chat-hf). It typically takes a few minutes or hours to get the access.

🚨 Note that your Hugging Face account email MUST match the email you provided on the Meta website, or your request will not be approved.

If you’re using Google Colab to run the code. In your notebook, go to Runtime > Change runtime type > Hardware accelerator > GPU > GPU type > T4. You will need ~8GB of GPU RAM for inference and running on CPU is practically impossible.

# Installing the Libraries
First of all, let’s start by installing all required libraries using pip install.
"""

!pip install accelerate==0.21.0 transformers==4.31.0 tokenizers==0.13.3
!pip install bitsandbytes==0.40.0 einops==0.6.1
!pip install xformers==0.0.22.post7
!pip install langchain==0.1.4
!pip install faiss-gpu==1.7.1.post3
!pip install sentence_transformers

"""# Initializing the Hugging Face Pipeline
You have to initialize a text-generation pipeline with Hugging Face transformers. The pipeline requires the following three things that you must initialize:

* A LLM, in this case it will be meta-llama/Llama-2-7b-chat-hf.
*  respective tokenizer for the model.
* A stopping criteria object.

You have to initialize the model and move it to CUDA-enabled GPU. Using Colab, this can take 5–10 minutes to download and initialize the model.

Also, you need to generate an access token to allow downloading the model from Hugging Face in your code. For that, go to your Hugging Face Profile > Settings > Access Token > New Token > Generate a Token. Just copy the token and add it in the below code.
"""

from torch import cuda, bfloat16
import transformers

model_id = 'meta-llama/Llama-2-7b-chat-hf'

device = f'cuda:{cuda.current_device()}' if cuda.is_available() else 'cpu'

# set quantization configuration to load large model with less GPU memory
# this requires the `bitsandbytes` library
bnb_config = transformers.BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type='nf4',
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=bfloat16
)

# begin initializing HF items, you need an access token
hf_auth = hf_auth
model_config = transformers.AutoConfig.from_pretrained(
    model_id,
    use_auth_token=hf_auth
)

model = transformers.AutoModelForCausalLM.from_pretrained(
    model_id,
    trust_remote_code=True,
    config=model_config,
    quantization_config=bnb_config,
    device_map='auto',
    use_auth_token=hf_auth
)

# enable evaluation mode to allow model inference
model.eval()

print(f"Model loaded on {device}")

"""The pipeline requires a tokenizer which handles the translation of human readable plaintext to LLM readable token IDs. The Llama 2 7B models were trained using the Llama 2 7B tokenizer, which can be initialized with this code:"""

tokenizer = transformers.AutoTokenizer.from_pretrained(
    model_id,
    use_auth_token=hf_auth
)

"""Now, we need to define the stopping criteria of the model. The stopping criteria allows us to specify when the model should stop generating text. If we don’t provide a stopping criteria the model just goes on a bit tangent after answering the initial question."""

stop_list = ['\nHuman:', '\n```\n']

stop_token_ids = [tokenizer(x)['input_ids'] for x in stop_list]
stop_token_ids

"""You have to convert these stop token ids into LongTensor objects."""

import torch

stop_token_ids = [torch.LongTensor(x).to(device) for x in stop_token_ids]
stop_token_ids

"""You can do a quick spot check that no <unk> token IDs (0) appear in the stop_token_ids — there are none so we can move on to building the stopping criteria object that will check whether the stopping criteria has been satisfied — meaning whether any of these token ID combinations have been generated."""

from transformers import StoppingCriteria, StoppingCriteriaList

# define custom stopping criteria object
class StopOnTokens(StoppingCriteria):
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        for stop_ids in stop_token_ids:
            if torch.eq(input_ids[0][-len(stop_ids):], stop_ids).all():
                return True
        return False

stopping_criteria = StoppingCriteriaList([StopOnTokens()])

"""You are ready to initialize the Hugging Face pipeline. There are a few additional parameters that we must define here."""

generate_text = transformers.pipeline(
    model=model,
    tokenizer=tokenizer,
    return_full_text=True,  # langchain expects the full text
    task='text-generation',
    # we pass model parameters here too
    stopping_criteria=stopping_criteria,  # without this model rambles during chat
    temperature=0.1,  # 'randomness' of outputs, 0.0 is the min and 1.0 the max
    max_new_tokens=512,  # max number of tokens to generate in the output
    repetition_penalty=1.1  # without this output begins repeating
)

res = generate_text("Explain me the difference between Data Lakehouse and Data Warehouse.")
print(res[0]["generated_text"])

"""# Implementing HF Pipeline in LangChain

Now, you have to implement the Hugging Face pipeline in LangChain. You will still get the same output as nothing different is being done here. However, this code will allow you to use LangChain’s advanced agent tooling, chains, etc, with Llama 2.
"""

from langchain.llms import HuggingFacePipeline

llm = HuggingFacePipeline(pipeline=generate_text)

# checking again that everything is working fine
llm(prompt="Explain me the difference between Data Lakehouse and Data Warehouse.")

"""# Ingesting Data using Document Loader

You have to ingest data using WebBaseLoader document loader which collects data by scraping webpages. In this case, you will be collecting data from Databricks documentation website.
"""

from langchain.document_loaders import WebBaseLoader

web_links = ["https://www.databricks.com/","https://help.databricks.com","https://databricks.com/try-databricks","https://help.databricks.com/s/","https://docs.databricks.com","https://kb.databricks.com/","http://docs.databricks.com/getting-started/index.html","http://docs.databricks.com/introduction/index.html","http://docs.databricks.com/getting-started/tutorials/index.html","http://docs.databricks.com/release-notes/index.html","http://docs.databricks.com/ingestion/index.html","http://docs.databricks.com/exploratory-data-analysis/index.html","http://docs.databricks.com/data-preparation/index.html","http://docs.databricks.com/data-sharing/index.html","http://docs.databricks.com/marketplace/index.html","http://docs.databricks.com/workspace-index.html","http://docs.databricks.com/machine-learning/index.html","http://docs.databricks.com/sql/index.html","http://docs.databricks.com/delta/index.html","http://docs.databricks.com/dev-tools/index.html","http://docs.databricks.com/integrations/index.html","http://docs.databricks.com/administration-guide/index.html","http://docs.databricks.com/security/index.html","http://docs.databricks.com/data-governance/index.html","http://docs.databricks.com/lakehouse-architecture/index.html","http://docs.databricks.com/reference/api.html","http://docs.databricks.com/resources/index.html","http://docs.databricks.com/whats-coming.html","http://docs.databricks.com/archive/index.html","http://docs.databricks.com/lakehouse/index.html","http://docs.databricks.com/getting-started/quick-start.html","http://docs.databricks.com/getting-started/etl-quick-start.html","http://docs.databricks.com/getting-started/lakehouse-e2e.html","http://docs.databricks.com/getting-started/free-training.html","http://docs.databricks.com/sql/language-manual/index.html","http://docs.databricks.com/error-messages/index.html","http://www.apache.org/","https://databricks.com/privacy-policy","https://databricks.com/terms-of-use"]

loader = WebBaseLoader(web_links)
documents = loader.load()

"""**Splitting in Chunks using Text Splitters**

You have to make sure to split the text into small pieces. You will need to initialize RecursiveCharacterTextSplitter and call it by passing the documents.

"""

from langchain.text_splitter import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=20)
all_splits = text_splitter.split_documents(documents)

"""**Creating Embeddings and Storing in Vector Store**

You have to create embeddings for each small chunk of text and store them in the vector store (i.e. FAISS). You will be using all-mpnet-base-v2 Sentence Transformer to convert all pieces of text in vectors while storing them in the vector store
"""

from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS


model_name = "sentence-transformers/all-mpnet-base-v2"
model_kwargs = {"device": "cuda"}

embeddings = HuggingFaceEmbeddings(model_name=model_name, model_kwargs=model_kwargs)

# storing embeddings in the vector store
vectorstore = FAISS.from_documents(all_splits, embeddings)

"""**Initializing Chain**

You have to initialize `ConversationalRetrievalChain`. This chain allows you to have a chatbot with memory while relying on a vector store to find relevant information from your document.

Additionally, you can return the source documents used to answer the question by specifying an optional parameter i.e. `return_source_documents=True` when constructing the chain.
"""

from langchain.chains import ConversationalRetrievalChain

chain = ConversationalRetrievalChain.from_llm(llm, vectorstore.as_retriever(), return_source_documents=True)

"""Now, it’s time to do some Question-Answering on your own data!"""

chat_history = []

query = "What is Data lakehouse architecture in Databricks?"
result = chain({"question": query, "chat_history": chat_history})

print(result['answer'])

"""This time your previous question and answer will be included as a chat history which will enable the ability to ask follow up questions."""

chat_history = [(query, result["answer"])]

query = "What are Data Governance and Interoperability in it?"
result = chain({"question": query, "chat_history": chat_history})

print(result['answer'])

"""You can also see the source of the information used to generate the answer."""

print(result['source_documents'])

"""Finally…
Et voilà! You have now the capability to do question-answering on your on data using a powerful language model. Additionally, we can further develop it into a chatbot application using Streamlit.
"""