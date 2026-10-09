---
id: model-guide
name: Model Selection Guide
type: model
project: shared
tags: [models, cost]
version: 1
---
| Task | Model | Why |
|---|---|---|
| Bulk screening, summaries, classification | claude-haiku-5-5 | cheapest, fast |
| Drafting, matching, most app features | claude-sonnet-5-5 | best price/quality |
| Legal/contract drafting, Arabic formal letters, complex reasoning | claude-opus-5-5 | accuracy matters |
| Long agentic runs | claude-fable-5-1 | strongest reasoning |

Rules: default Sonnet; drop to Haiku when output is structured and low-stakes; go Opus when a mistake
costs money or reputation. Check current pricing at docs.claude.com before committing a budget.
