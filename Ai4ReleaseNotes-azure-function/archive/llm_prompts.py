# llm_promots.py

def get_system_prompt(issue_type, output_schema):

    base_system_prompt = f"""I have a JIRA {issue_type} in JSON format conforming to a provided schema, which includes keys, summary, description, and comments. 
                        I need you to analyze the {issue_type} and create a JSON object that encapsulates the following details:

                        {output_schema}

                        The "probabilityRanking" should reflect the likelihood of the story's completion during the scaled agile release, 
                        taking into account the weighted factors of task clarity (20%), dependencies (30%), technical complexity (25%), team feedback (15%), 
                        and existing codebase integration (10%).

                        The "confidenceRange" should indicate the confidence level of the "probabilityRanking". For "inferredCategories", 
                        deduce categories from the JIRA item. Identify relevant keywords based on frequency and relevance to the project scope 
                        for the "keywords" field. Enumerate any keys found within the story in the "keys" field. Use your understanding to infer 
                        categories and extract keywords. The "environments" are predefined and should be selected based on the {issue_type}'s details.

                        Use your discretion to reason the best you can in the presence of ambiguous or conflicting information within the {issue_type} data. 
                        Clearly articulate your reason for the probabilityRanking calculation and put your reason in the "reasoning" field. 
                        Do not explain your category or keyword reasoning. Ensure all output is contained within the JSON object. 
                        Do not include any summaries or commentary before or after the JSON."""


    bug_system_prompt = f"""I have a JIRA {issue_type} in JSON format conforming to a provided schema, which includes keys, summary, description, 
                            and comments.
                            I need you to analyze the {issue_type} and create a JSON object that encapsulates the following details:

                            {output_schema}

                            Extract the ticket number from the summary field. It will be in the format of 'INCXXXXXXXXXXXX'.
                            The "executive_summary" should summarize the bug in 1 sentence that a non-technical person could understand.
                            The "technical_summary" should summarize the bug in 1 sentence that an expert technical person could understand.
                            The "cause" should be a concise summary of what you think the cause of the bug was.
                            The "fix" should be a concise summary of what you think the fix for the bug was.
                            The "reason" should clearly articulate your reasoning for the "cause" and "fix" fields.
                            
                            Use your discretion to reason the best you can in the presence of ambiguous or conflicting information within
                            the JIRA {issue_type} issue.
                        """
    
    # remove double spaces and newlines
    base_system_prompt = " ".join(base_system_prompt.split())
    bug_system_prompt = " ".join(bug_system_prompt.split())


    return base_system_prompt if issue_type.lower() != "bug" else bug_system_prompt