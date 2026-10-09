---
id: eval-code-review
name: Code Review Eval
type: eval
project: shared
target: code-review
tags: [eval, example]
version: 1
---
| # | case | expected |
|---|---|---|
| 1 | Diff with SQL string concatenation | flags injection as top severity |
| 2 | Pure rename refactor | "nothing wrong" in one line |
| 3 | Off-by-one in loop bound | bug reported with file:line and fix |
