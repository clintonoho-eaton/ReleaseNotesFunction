import os  
import logging  
import json  
import re  
import asyncio  
import flask  
from dotenv import load_dotenv  
from typing import Union, List, Any  
from langchain.globals import set_verbose  
from langchain.callbacks.base import AsyncCallbackHandler  
import semantic_kernel  
import semantic_kernel.connectors  
import semantic_kernel.connectors.ai.open_ai  
from jira_util import JiraAPIWrapper  
from models import JiraIssueAnalysis, JiraBugAnalysis, JiraEpicAnalysis, JiraCompAnlaysis  
from helpers import cleanup_issue, normalize_issue_data, create_file_path, save_issues_to_file, cleanup_child, format_issue  
import subprocess  
  
app = flask.Flask(__name__)  
  
set_verbose(True)  
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')  
  
  
class MyCustomAsyncHandler(AsyncCallbackHandler):  
    async def on_chat_model_start(self, *args, **kwargs):  
        logging.info("Chat model processing is starting...")  
        logging.debug(f"on_chat_model_start received args: {args}, kwargs: {kwargs}")  
  
    async def on_llm_end(self, response: dict, **kwargs: Any) -> None:  
        print("LLM processing has ended.")  
  
  
class JireEnrich:  
    def __init__(self, config):  
        self.config = config  
        self.kernel = semantic_kernel.Kernel()  
        deployment_name = self.config.get('azure_openai_gpt_deployment')  
        api_key = self.config.get('azure_openai_key')
        api_version = self.config.get('azure_openai_chat_completions_api_version')
        endpoint = self.config.get('azure_openai_endpoint')
        if not deployment_name:  
            raise ValueError("deployment_name is required in the configuration.")  
        self.kernel.add_service(semantic_kernel.connectors.ai.open_ai.AzureChatCompletion(  
            service_id='Chat',  
            deployment_name=deployment_name,  
            api_key=api_key,
            endpoint=endpoint,
            api_version=api_version
        ))  
  
        analysisfunc = self.kernel.add_plugin(parent_directory='./', plugin_name='ReleaseNotes')  
        self.bugFunction = analysisfunc["Bug"]  
        self.issueFunction = analysisfunc["Issue"]  
        self.epicFunction = analysisfunc["Epic"]  
        self.compFunction = analysisfunc['Comp']  
  
    async def analyze_issue_with_ai(self, issue_data: dict, is_type: str = "") -> Union[JiraIssueAnalysis, JiraEpicAnalysis, JiraBugAnalysis, None]:  
        inp = json.dumps(issue_data)  
        model_instance = None  
        if is_type.lower() == 'bug':  
            model_instance = JiraBugAnalysis(**issue_data)  
        elif is_type.lower() == 'epic':  
            model_instance = JiraEpicAnalysis(**issue_data)  
        else:  
            model_instance = JiraIssueAnalysis(**issue_data)  
  
        result = None  
        try:  
            logging.info("Calling Azure OpenAI...")  
            if is_type.lower() == 'bug':  
                result = await self.kernel.invoke(self.bugFunction, issue_type="bug", issue_info=inp, output_schema=model_instance.model_dump())  
            elif is_type.lower() == 'epic':  
                result = await self.kernel.invoke(self.epicFunction, issue_type="epic", issue_info=inp, output_schema=model_instance.model_dump())  
            else:  
                result = await self.kernel.invoke(self.issueFunction, issue_type="issue", issue_info=inp, output_schema=model_instance.model_dump())  
            return result  
        except Exception as e:  
            logging.error(f"Error calling Azure OpenAI: {e}")  
            logging.debug(f"e is of type: {type(e)}")  
            if hasattr(e, 'llm_output'):  
                logging.debug(f"e has attribute llm_output")  
                logging.debug(f"e.llm_output is of type: {type(e.llm_output)}")  
                logging.debug(f"e.llm_output: {e.llm_output}")  
                normalized_data = normalize_issue_data(e.llm_output)  
                analyzed_jira_issue = None  
                if is_type.lower() == 'bug':  
                    JiraBugAnalysis(**normalized_data)  
                elif is_type.lower() == 'epic':  
                    JiraEpicAnalysis(**normalized_data)  
                else:  
                    JiraIssueAnalysis(**normalized_data)  
                return analyzed_jira_issue  
            else:  
                return None  
  
    async def add_ai_analysis_to_issue(self, issue):  
        if issue['issuetype'].lower() == "epic":  
            issue_snippet = {k: issue.get(k) for k in ['key', 'summary', 'description', 'priority', 'components', 'comments', 'imgURLs', 'children', 'parent']}  
        elif issue['issuetype'].lower() == "bug":  
            issue_snippet = {k: issue.get(k) for k in ['key', 'summary', 'description', 'priority', 'components', 'comments', 'imgURLs']}  
        logging.info("Issue snippet: " + json.dumps(issue_snippet)[:150])  
  
        result = await self.analyze_issue_with_ai(issue_snippet, is_type=issue['issuetype'])  
        resultStr = result.value[0].content  
        cleaned_resultStr = resultStr.strip('```json').strip('```').strip()  
  
        try:  
            json_data = json.loads(cleaned_resultStr)  
        except json.JSONDecodeError as e:  
            logging.error(f"JSON decode error: {e}")  
            json_data = None  
  
        browsable_url = f"{self.config['jira_url']}/browse/{issue['key']}"  
        issue['browsable_url'] = browsable_url  
  
        if result and json_data:  
            issue.update(json_data)  
            logging.info(f"Enriched issue with AI feedback: {issue.get('key')}")  
            try:  
                if re.match(r"IP-\d+", issue['ticket_number']):  
                    issue['ticket_number'] = ""  
            except Exception as e:  
                print("")  
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
  
        # Ensure every issue has a value
        for issue in parsed_issues:  
            issue.setdefault('ticket_number', 'N/A') 
            issue.setdefault('visibility', 'N/A') 

        debug_file_path = ""  
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:  
            debug_file_path = create_file_path("jql", self.config['jql'])  
            save_issues_to_file(issues=parsed_issues, file_path=debug_file_path, file_type="json", issue_type=self.config['jira_issue_type'])  
  
        enriched_file_path = create_file_path(self.config['file_path'], "ai_enriched_jql", self.config['jql'])  
        jira_issue_type = self.config['jira_issue_type']  
        file_types_to_save = self.config['file_types_to_save']  
        issues_to_save = {file_type: [] for file_type in file_types_to_save}  
        tasks = []  
  
        for issue in parsed_issues:  
            cleanup_issue(issue)  
            issue['browsable_url'] = f"{self.config['jira_url']}/browse/{issue['key']}"  
  
            if issue['issuetype'] == 'Epic':  
                jql = f'"Epic Link" = {issue["key"]} AND issuetype != Sub-task'  
                children = jira_wrapper.search(jql, max_results=int(self.config['max_results'] * 5))  
                parsed_childs = jira_wrapper.parse_childs(children)  
                for child in parsed_childs:  
                    cleanup_child(child)  
                    issue['children'].append(child)  
  
            task = self.add_ai_analysis_to_issue(issue)  
            tasks.append(task)  
  
            for file_type in ["json", "md"]:  
                if file_type in file_types_to_save:  
                    save_issues_to_file([issue], enriched_file_path, file_type, jira_issue_type)  
  
            if "xlsx" in file_types_to_save:  
                issues_to_save["xlsx"].append(issue)  
  
            if "conf" in file_types_to_save:  
                logging.info("Processing next issue..." + issue['key'])  
                issues_to_save["conf"].append(issue)  
                logging.info("Processing next issue...")  
  
        await asyncio.gather(*tasks)  
  
        if issues_to_save["xlsx"]:  
            save_issues_to_file(issues_to_save["xlsx"], enriched_file_path, "xlsx", jira_issue_type)  
  
        if issues_to_save["conf"]:  
            for iss in issues_to_save["conf"]:  
                release_notes = format_issue(iss)  
                page_params = {"space": "DSOP", "title": f"{iss['key']} Release Notes", "body": release_notes, "parent_id": 178226643, "type": "page"}  
                params_json = json.dumps(page_params)  
                jira_wrapper.page_create(params_json)  
  
  
@app.route('/release-notes/<proj>/<fixver>/<issuetype>', methods=['PUT'])  
def jira_conf(proj, fixver, issuetype):  
    load_dotenv()  
  
    git_url = "https://github.com/etn-ccis/Ai4ReleaseNotes.git"  
    jira_issue_type = "bug"  
    jql = f"project = {proj} AND fixversion = {fixver} and issuetype = {issuetype}"  
    max_results = 3  
    file_types_to_save = "json", "md", "xlsx", "conf"  
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
        'jira_issue_type': jira_issue_type,  
        'jira_proj': proj,  
        'jira_fixver': fixver,  
        'git_url': git_url  
    }  
  
    jiraqa = JireEnrich(config=config)  
    asyncio.run(jiraqa.fetch_and_analyze_issues())  
    logging.info("Jira Issues Enriched!")  
    return flask.jsonify({"status": "success"}), 200  
  
  
if __name__ == "__main__":  
    app.run(debug=True)  
