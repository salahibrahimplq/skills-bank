---
id: summarise-document
name: Summarise Document
type: prompt
project: shared
tags: [summary, example]
model: claude-haiku-5-5
inputs: [document, audience]
version: 1
---
Summarise the document below for {{audience}}. 5 bullets, then one line on the single most important decision or deadline it contains.

{{document}}
