---
id: example-tools
name: Example Tool Specs
type: tool
project: shared
tags: [tools, function-calling, example]
version: 1
---
```json
[{"name":"web_search","description":"Search the web","parameters":{"type":"object","properties":{"q":{"type":"string"}},"required":["q"]}},
 {"name":"web_fetch","description":"Fetch a URL as text","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}}]
```
