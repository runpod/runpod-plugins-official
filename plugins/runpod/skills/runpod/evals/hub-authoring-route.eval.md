# Distinguish Hub listing authoring from existing-listing operations

## Prompt

Evaluate these independently:

1. "Prepare this worker for a Runpod Hub listing. Write the required project files
   locally; do not publish or deploy."
2. "Find and deploy an existing vLLM worker from the Hub." The connected MCP exposes
   Hub browsing and deployment, and the requested deployment is authorized.
3. "Give me reproducible terminal commands to deploy an existing Hub worker."

## Expected behavior

The first request routes to runpod-build-template and preserves the local authoring
scope. The second uses the router's existing Hub capability choice after consulting
its applicable deployment example. The third uses runpodctl for the requested commands.
Repeat the first request when entering through runpod-mcp or runpodctl directly.

## Assertions

- Listing authoring produces app-specific project/listing artifacts; it does not
  substitute deployment of another worker or require cloud credentials to write files.
- Existing-listing operations do not trigger new Dockerfiles or Hub metadata authoring.
- Connected, capable MCP handles the second request; the agent does not declare Hub
  CLI-only or install a CLI merely to perform that supported operation.
- Tool names and parameters come from the current tool schema or CLI help.
- The terminal request retains its reproducible-command deliverable.
- Preparation alone does not authorize publication or provision billable resources.
