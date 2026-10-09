---
id: code-review
name: Code Review
type: prompt
project: shared
tags: [engineering, review, example]
model: claude-sonnet-5-5
inputs: [diff, language]
version: 1
---
Review this {{language}} diff. Report only real problems, ordered by severity: bugs, security, data loss, then performance, then style. For each: file:line, what's wrong, a concrete fix. If nothing is wrong, say so in one line.

{{diff}}
