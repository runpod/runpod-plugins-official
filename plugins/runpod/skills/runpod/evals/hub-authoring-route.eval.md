# Distinguish Hub listing authoring from existing-listing operations

## Prompt

"Prepare this worker for a Runpod Hub listing. Write the required project files
locally; do not publish or deploy."

Repeat when entering through the router, runpod-mcp or runpodctl directly.

## Expected behavior

The request routes to runpod-build-template and preserves the local authoring scope.
The agent distinguishes creating listing files from operating an existing listing.

## Assertions

- Listing authoring produces app-specific project/listing artifacts; it does not
  substitute deployment of another worker or require cloud credentials to write files.
- Existing-listing operations do not trigger new Dockerfiles or Hub metadata authoring.
- Tool names and parameters come from the current tool schema or CLI help.
- Preparation alone does not authorize publication or provision billable resources.
