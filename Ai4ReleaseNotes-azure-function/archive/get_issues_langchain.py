# get_issues_langchain.py

import os  
import logging  
import json  
import re  
import asyncio  
from dotenv import load_dotenv  
from typing import Union, List, Any  
  
from pydantic import BaseModel  # Updated based on deprecation warning  
from langchain_openai.chat_models.azure import AzureChatOpenAI  
from langchain.chains import create_structured_output_runnable  
from langchain.globals import set_verbose  
from langchain.prompts import ChatPromptTemplate  
from langchain.callbacks.base import AsyncCallbackHandler  
  
from jira_util import JiraAPIWrapper  
from models import JiraIssueAnalysis, JiraBugAnalysis  
from helpers import cleanup_issue, normalize_issue_data, create_file_path, save_issues_to_file  
from archive.llm_prompts import get_system_prompt  
  
# Configure logging  
set_verbose(True)  
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')  
  
  
class MyCustomAsyncHandler(AsyncCallbackHandler):  
    async def on_chat_model_start(self, *args, **kwargs):  
        logging.info("Chat model processing is starting...")  
        logging.debug(f"on_chat_model_start received args: {args}, kwargs: {kwargs}")  
  
    async def on_llm_end(self, response: dict, **kwargs: Any) -> None:  
        logging.info("LLM processing has ended.")  
  
  
class JiraEnrich:  
    def __init__(self, config):  
        self.config = config  
        self.llm = AzureChatOpenAI(  
            temperature=0.0,  
            api_key=config['azure_openai_key'],  
            api_version=config['azure_openai_chat_completions_api_version'],  
            deployment_name=config['azure_openai_gpt_deployment'],  
            callbacks=[MyCustomAsyncHandler()],  
        )  
  
    async def analyze_issue_with_ai(self, issue_data: dict, is_bug: bool = False) -> Union[JiraIssueAnalysis, JiraBugAnalysis, None]:  
        inp = json.dumps(issue_data)  
        system_prompt = self.config['system_prompt']  
        prompt = ChatPromptTemplate.from_messages(  
            [("system", system_prompt), ("human", "{input}")]  
        )  
  
        model_instance = JiraBugAnalysis(**issue_data) if is_bug else JiraIssueAnalysis(**issue_data)  
        runnable = create_structured_output_runnable(  
            model_instance.model_dump(),  
            self.llm,  
            mode="openai-json",  
            prompt=prompt,  
            enforce_function_usage=False,  
        )  
  
        try:  
            logging.info("Calling Azure OpenAI...")  
            result = await asyncio.to_thread(runnable.invoke, {"input": inp})  
            return result  
        except Exception as e:  
            logging.error(f"Error calling Azure OpenAI: {e}")  
            logging.debug(f"Error type: {type(e)}")  
  
            if hasattr(e, 'llm_output'):  
                logging.debug("Exception has attribute llm_output")  
                logging.debug(f"llm_output: {e.llm_output}")  
                normalized_data = normalize_issue_data(e.llm_output)  
                analyzed_jira_issue = (JiraBugAnalysis if is_bug else JiraIssueAnalysis)(**normalized_data)  
                return analyzed_jira_issue  
            else:  
                return None  
  
    async def add_ai_analysis_to_issue(self, issue):  
        issue_snippet = {k: issue.get(k) for k in ['key', 'summary', 'description', 'priority', 'components', 'comments']}  
        logging.info("Issue snippet: " + json.dumps(issue_snippet)[:150])  
  
        if self.config['jira_issue_type'].lower() == "bug":  
            result = await self.analyze_issue_with_ai(issue_snippet, is_bug=True)  
        else:  
            result = await self.analyze_issue_with_ai(issue_snippet, is_bug=False)  
  
        if result:  
            issue.update(result)  
            logging.info(f"Enriched issue with AI feedback: {issue.get('key')}")  
  
            if re.match(r"IP-\d+", issue['ticket_number']):  
                issue['ticket_number'] = ""  
  
            browsable_url = f"{self.config['jira_url']}/browse/{issue['key']}"  
            issue['browsable_url'] = browsable_url  
        else:  
            logging.error("No result from AI feedback, skipping issue.")  
  
    async def fetch_and_analyze_issues(self):  
        jira_wrapper = JiraAPIWrapper(  
            jira_username=self.config['jira_username'],  
            jira_api_token=self.config['jira_api_key'],  
            jira_instance_url=self.config['jira_url']  
        )  
  
        logging.info("Querying Jira to get issues...")  
        issues = jira_wrapper.search(self.config['jql'], max_results=self.config['max_results'])  
  
        logging.info("Parsing issues...")  
        parsed_issues = jira_wrapper.parse_issues(issues)  
        logging.info(f"Issues parsed: {len(parsed_issues)}")  
  
        debug_file_path = ""  
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:  
            debug_file_path = create_file_path("jql", self.config['jql'])  
            save_issues_to_file(parsed_issues, debug_file_path)  
  
        enriched_file_path = create_file_path(self.config['file_path'], "ai_enriched_jql", self.config['jql'])  
        jira_issue_type = self.config['jira_issue_type']  
        file_types_to_save = self.config['file_types_to_save']  
        issues_to_save = {file_type: [] for file_type in file_types_to_save}  
  
        tasks = []  
        for issue in parsed_issues:  
            cleanup_issue(issue)  
  
            if len(issue['labels']) > 0 or re.search(r"INC\d{12}", issue['summary']):  
                task = self.add_ai_analysis_to_issue(issue)  
                tasks.append(task)  
  
            for file_type in ["json", "md"]:  
                if file_type in file_types_to_save:  
                    save_issues_to_file([issue], enriched_file_path, file_type, jira_issue_type)  
  
            if "xlsx" in file_types_to_save:  
                issues_to_save["xlsx"].append(issue)  
  
            logging.info("Processing next issue...")  
  
        await asyncio.gather(*tasks)  
  
        if issues_to_save["xlsx"]:  
            save_issues_to_file(issues_to_save["xlsx"], enriched_file_path, "xlsx", jira_issue_type)  
  
  
def main():  
    load_dotenv()  
  
    jira_issue_type = "bug"  
    jql = f"project = IP AND fixversion = PI08-2025-01 and issuetype = {jira_issue_type}"  
    output_schema = "{output_schema}"  
    max_results = 20  
    file_types_to_save = ["json", "md", "xlsx"]  
    system_prompt = get_system_prompt(jira_issue_type, output_schema)  
  
    config = {  
        'azure_openai_key': os.getenv('AZURE_OPENAI_KEY'),  
        'azure_openai_chat_completions_api_version': os.getenv('AZURE_OPENAI_CHAT_COMPLETIONS_API_VERSION'),  
        'azure_openai_gpt_deployment': os.getenv('AZURE_OPENAI_GPT_DEPLOYMENT'),  
        'jira_url': os.getenv("ATLASSIAN_URL"),  
        'jira_username': os.getenv("ATLASSIAN_USERNAME"),  
        'jira_api_key': os.getenv("ATLASSIAN_API_KEY"),  
        'jql': jql,  
        'max_results': max_results,  
        'file_path': os.getenv("ATLASSIAN_DEFAULT_PATH", "None"),  
        'file_types_to_save': file_types_to_save,  
        'system_prompt': system_prompt,  
        'jira_issue_type': jira_issue_type  
    }  
  
    jiraqa = JiraEnrich(config=config)  
    asyncio.run(jiraqa.fetch_and_analyze_issues())  
    logging.info("Jira Issues Enriched!")  
  
  
if __name__ == "__main__":  
    main()  
