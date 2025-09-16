from agent.graph import agent
from clients.jira_client import JiraClient

if __name__ == "__main__":
    
    # JiraClient().ensure_test_plan("QSE", "DSA_Quote_Shipping_and_Estimates", "FY25FW20-0603")
    # JiraClient().link_tests_to_plan("QSE-5502", ["QSE-894","QSE-893"])
    
    res = agent.invoke({
        "jira_key": "MAV-269293",
        "gitlab_project_id": "8259",
        "gitlab_mr_id": "2912",
        "messages": []
    })
    
    # res = agent.invoke({
    #     "jira_key": "MAV-323698",
    #     "gitlab_project_id": "8259",
    #     "gitlab_mr_id": "2932",
    #     "messages": []
    # })
    
    # res = agent.invoke({
    #     "jira_key": "MAV-334403",
    #     "gitlab_project_id": "4048",
    #     "gitlab_mr_id": "2551",
    #     "messages": []
    # })
    
    # res = agent.invoke({
    #     "jira_key": "MAV-165844",
    #     "gitlab_project_id": "4048",
    #     "gitlab_mr_id": "2508",
    #     "messages": []
    # })
    
    print(res.get("jira_comment_body", "No report generated."))