---
description: Manage the MCP servers Minions agents can use
argument-hint: "[server name or what you want to do]"
---
Use the Minions skill's "Agent MCP servers" section for `$ARGUMENTS`.
Start with `list_agent_mcp_servers` (view in_use, then catalog if the user is looking for one) and report the live result: each server's status, roles and missing credentials. Change nothing until the user confirms the specific change.
- To turn on a catalog server, confirm the roles (only ones the server allows) and the repositories, then call `turn_on_agent_mcp_server`. No approval is needed. Report the `missingCredentials` it returns: agents get the server once those are set.
- To add a credential, call `get_agent_mcp_server` to see its preset fields, ask the user where the value lives (an environment variable, file or OS keychain entry), and pass `env:NAME`, `file:PATH` or `keychain:SERVICE/ACCOUNT` as the value of `set_agent_mcp_credential`; the plugin resolves it locally. Never ask the user to paste a credential into chat. Remind them that agents in the server's roles can read it, so a least-privilege token is best.
- To change roles or repositories, use `set_agent_mcp_server_access`; to clear or remove a credential, `delete_agent_mcp_credential`; to stop using a server, `stop_agent_mcp_server` with `confirm: true` only after the user confirms its credentials will be deleted.
- For one repository, read `get_repo_agent_mcp` and change it with `set_repo_agent_mcp_change` (off, roles or inherit); this needs Edit on the repository.
- If the server isn't in the catalog, offer `request_new_agent_mcp_server` with the server's name, where to find it, what agents would use it for, optionally which pipeline agents need it (`roles`), and the credential NAMES it needs, never values. A Minions super admin adds it to the catalog or declines it; `list_agent_mcp_requests` follows the organization's requests.
