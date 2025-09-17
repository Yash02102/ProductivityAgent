from app.agent.graph import agent

#Example runs on the agent

if __name__ == "__main__":
    
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