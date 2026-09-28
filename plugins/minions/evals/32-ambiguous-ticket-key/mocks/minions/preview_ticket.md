---
expect:
  ticket: string
---
{"ok":false,"code":"ambiguous","message":"DEMO-4201 matches more than one connected Jira board: Primary board (jira.example), Secondary board (jira.example). Paste the ticket's URL so the board is unambiguous.","candidates":[{"boardId":1,"name":"Primary board","host":"jira.example"},{"boardId":2,"name":"Secondary board","host":"jira.example"}]}
