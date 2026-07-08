import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv(override=True)

class JiraClient:
    """
    A dedicated client for communicating with Atlassian's REST API.
    Used by the Agents to fetch live customer tickets and post AI-generated resolutions.
    """
    def __init__(self):
        self.url = os.environ.get("JIRA_URL", "").rstrip("/")
        self.email = os.environ.get("JIRA_EMAIL")
        self.api_token = os.environ.get("JIRA_API_TOKEN")
        
        if not self.url or not self.email or not self.api_token:
            raise ValueError("Missing Jira Credentials in .env")
            
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def verify_connection(self) -> dict:
        """
        Pings the Jira API to verify authentication status.
        """
        endpoint = f"{self.url}/rest/api/3/myself"
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        
        if response.status_code == 200:
            return {"status": "success", "user": response.json().get("displayName")}
        else:
            return {"status": "error", "code": response.status_code, "message": response.text}

    def fetch_unresolved_tickets(self, project_key: str, limit: int = 5) -> list:
        """
        Fetches the most recent unresolved tickets from a specific Jira project using JQL.
        """
        endpoint = f"{self.url}/rest/api/3/search/jql"
        jql = f"project = {project_key} AND resolution = Unresolved ORDER BY created DESC"
        
        query = {
            "jql": jql,
            "maxResults": limit,
            "fields": "summary,description,status,creator"
        }
        
        response = requests.get(endpoint, headers=self.headers, auth=self.auth, params=query)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("issues", [])
        else:
            raise Exception(f"Failed to fetch tickets: {response.text}")
            
    def post_comment(self, issue_key: str, comment_text: str) -> dict:
        """
        Posts an automated response back to the specific Jira ticket.
        """
        endpoint = f"{self.url}/rest/api/3/issue/{issue_key}/comment"
        
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"text": comment_text, "type": "text"}
                        ]
                    }
                ]
            }
        }
        
        response = requests.post(endpoint, headers=self.headers, auth=self.auth, json=payload)
        
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to post comment: {response.text}")
            
    def create_ticket(self, project_key: str, summary: str, description: str) -> dict:
        """
        Creates a new customer support ticket (Issue) in Jira.
        """
        endpoint = f"{self.url}/rest/api/3/issue"
        
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description}]
                        }
                    ]
                },
                "issuetype": {"id": "10001"} # [System] Incident
            }
        }
        
        response = requests.post(endpoint, headers=self.headers, auth=self.auth, json=payload)
        
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to create ticket: {response.status_code} - {response.text}")
            
    def resolve_ticket(self, issue_key: str) -> dict:
        """
        Transitions the ticket to a 'Done' or 'Completed' status.
        """
        transitions_endpoint = f"{self.url}/rest/api/3/issue/{issue_key}/transitions"
        resp = requests.get(transitions_endpoint, headers=self.headers, auth=self.auth)
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch transitions: {resp.text}")
            
        transitions = resp.json().get("transitions", [])
        
        # Look for a transition where the destination status belongs to the 'done' category
        target_id = None
        available_transitions = []
        for t in transitions:
            available_transitions.append(t.get("name"))
            status_category = t.get("to", {}).get("statusCategory", {}).get("key", "")
            if status_category == "done":
                target_id = t.get("id")
                break
                
        if not target_id:
            return {"status": "success", "message": f"Ticket {issue_key} was commented on. No 'Completed' transition was available for the API user, so it was left in its current state."}
            
        payload = {
            "transition": {
                "id": target_id
            }
        }
        
        post_resp = requests.post(transitions_endpoint, headers=self.headers, auth=self.auth, json=payload)
        
        # Jira returns 204 No Content on successful transition
        if post_resp.status_code == 204:
            return {"status": "success", "message": f"Ticket {issue_key} transitioned to resolved state."}
        else:
            raise Exception(f"Failed to resolve ticket: {post_resp.text}")
