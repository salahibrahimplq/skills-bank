---
id: weekly-digest
name: Weekly Digest
type: workflow
project: shared
tags: [reporting, example]
schedule: "Mon 08:00"
uses: [research-assistant, summarise-document]
version: 1
---
1. research-assistant: "what changed this week in <topic>"
2. summarise-document: audience = me
3. deliver: email / Slack
