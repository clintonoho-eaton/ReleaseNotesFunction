# get_issues_langchain.py

import os  
import logging  
import json
import re
import asyncio 
import semantic_kernel
from dotenv import load_dotenv 
 

# from langchain_openai import AzureChatOpenAI  
# from langchain.chains import create_structured_output_runnable
# from langchain_core.pydantic_v1 import BaseModel
from langchain.globals import set_verbose
# from langchain_core.prompts import ChatPromptTemplate 
from langchain.callbacks.base import AsyncCallbackHandler  

from typing import Union, List, Any

import semantic_kernel.connectors
import semantic_kernel.connectors.ai
import semantic_kernel.connectors.ai.open_ai
import semantic_kernel.core_plugins
import semantic_kernel.kernel
import semantic_kernel.memory
import semantic_kernel.memory.semantic_text_memory
import semantic_kernel.memory.volatile_memory_store
from jira_util import JiraAPIWrapper

from models import JiraIssueAnalysis, JiraBugAnalysis, JiraEpicAnalysis
from helpers import cleanup_issue, normalize_issue_data, create_file_path, save_issues_to_file, cleanup_child, format_issue
from archive.llm_prompts import get_system_prompt

# Configure logging  
set_verbose(True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')  

class MyCustomAsyncHandler(AsyncCallbackHandler):  
    async def on_chat_model_start(self, *args, **kwargs):  
        # Now the method can accept any number of positional and keyword arguments  
        logging.info("Chat model processing is starting...")  
        # You can also log the received arguments to see what is being passed  
        logging.debug(f"on_chat_model_start received args: {args}, kwargs: {kwargs}")  
  
    async def on_llm_end(self, response: dict, **kwargs: Any) -> None:  
        # Logic to run when the LLM finishes processing  
        print("LLM processing has ended.")  

class JireEnrich:  
    def __init__(self, config):  
        self.config = config

        # initiate semantic kernel
        self.kernel = semantic_kernel.Kernel()

        deployment_name = self.config.get('azure_openai_gpt_deployment')
        api_key = self.config.get('azure_openai_key')
        api_version = self.config.get('azure_openai_chat_completions_api_version')
        endpoint = self.config.get('azure_openai_endpoint')
        
        self.kernel.add_service(semantic_kernel.connectors.ai.open_ai.AzureChatCompletion(
            service_id='Chat',
            deployment_name=deployment_name,
            api_key=api_key,
            endpoint=endpoint,
            api_version=api_version
        ))
        embed_gen = semantic_kernel.connectors.ai.open_ai.AzureTextEmbedding(service_id='TextEmbedding')
        self.kernel.add_service(embed_gen)

        self.memory = semantic_kernel.memory.SemanticTextMemory(storage=semantic_kernel.memory.volatile_memory_store.VolatileMemoryStore(), embeddings_generator=embed_gen)
        self.kernel.add_plugin(semantic_kernel.core_plugins.TextMemoryPlugin(self.memory), "TextMemory")

        #add release note plug in which will host analysis functions for types of Jira items
        analysisfunc = self.kernel.add_plugin(parent_directory='./', plugin_name='ReleaseNotes')

        # add functions to the release note plug in
        self.compFunction = analysisfunc["Comp"]

        #TODO: add functions to the releasenotes directory for the other kinds of Jira tickets
    
    async def analyze_issue_with_ai(self):
        # Create an instance of the appropriate class         

        commitFile  = open("commit_compare.txt", "r")
        commitcontents = commitFile.read()
        return await self.kernel.invoke(self.compFunction, commits=commitcontents)
        # print("the message is ", len(commitcontents.encode('utf-8')), " bytes")
        # await self.memory.save_information(collection="commits", id="log", text=commitcontents)
        #     # result = await asyncio.to_thread(runnable.invoke, {"input": inp})  
        # question = "Summarize the differences between the current and previous commit and write what you infer from these changes?"
        # return await self.memory.search("commits", question)

    async def add_ai_analysis_to_issue(self, response):  
    
            # Since analyze_issue_with_ai is a coroutine, you must await it to get the result  
            
            result = await self.analyze_issue_with_ai() 

            # print(result)
    
            if result:  
                response += result.__str__()
                print(response)

            else:  
                logging.error("No result from AI feedback, skipping issue.")  

    async def fetch_and_analyze_issues(self):  

        # Call the AI to analyze the issue if the issue has labels or if the summary contains a ServiceNow ticket number pattern (INC\d{12})
        response = ""
        task = self.add_ai_analysis_to_issue(response)
        await asyncio.gather(task)



def main():  
    load_dotenv() 


    config = {  
        'azure_openai_key': os.getenv('AZURE_OPENAI_KEY'),  
        'azure_openai_chat_completions_api_version': os.getenv('AZURE_OPENAI_CHAT_COMPLETIONS_API_VERSION'),  
        'azure_openai_gpt_deployment': os.getenv('AZURE_OPENAI_GPT_DEPLOYMENT'),  
        'jira_url': os.getenv("ATLASSIAN_URL"),  
        'jira_username': os.getenv("ATLASSIAN_USERNAME"),  
        'jira_api_key': os.getenv("ATLASSIAN_API_KEY"),  
        'file_path': os.getenv("ATLASSIAN_DEFAULT_PATH", "None")
    }  
  
    # Initialize JireEnrich 
    jiraqa = JireEnrich(config=config)  
    asyncio.run(jiraqa.fetch_and_analyze_issues())
    logging.info("Jira Issues Enriched!")  
 
      
if __name__ == "__main__":  
    main()  

