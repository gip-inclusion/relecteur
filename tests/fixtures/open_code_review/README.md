# open-code-review outputs

Outputs of `ocr review --format json` for open-code-review 1.12.11. `tool-rounds-exhausted.json`
was recorded from a real run against Albert (`deepseek-v4-flash-0731`). The others were written
from the output types of its source (`cmd/opencodereview/output.go`,
`internal/session/manifest.go`, `internal/llm/retry_report.go`): replace them with recorded
outputs as real runs make them available.

| File | Run |
| --- | --- |
| `with-comments.json` | Complete review with a single-line and a multi-line comment. |
| `silent.json` | Complete review without any comment (`comments` is `null`, as in the recorded run). |
| `no-supported-files.json` | Pull request without any file the engine reviews. |
| `rate-limited.json` | One file of two not reviewed: the model answered 429 after retries (exit code 0). |
| `overloaded.json` | No file reviewed: the model answered 503 after retries (exit code 1). |
| `tool-rounds-exhausted.json` | Recorded: the model never called the engine's tools, and both files ran out of rounds (exit code 1). |
