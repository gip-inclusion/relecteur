# open-code-review outputs

Outputs of `ocr review --format json` for open-code-review 1.12.11, on pull request 3390 of
rdv-insertion unless stated otherwise. Recorded outputs come from real runs against Albert; the
others were written from the output types of the engine's source (`cmd/opencodereview/output.go`,
`internal/session/manifest.go`, `internal/llm/retry_report.go`) and should be replaced by
recorded outputs as real runs make them available.

| File | Origin | Run |
| --- | --- | --- |
| `with-comments.json` | recorded, `gpt-oss-120b` | Complete review with two multi-line comments. |
| `silent.json` | recorded, `deepseek-v4-flash-0731` | Complete review without any comment. |
| `tool-rounds-exhausted.json` | recorded, `deepseek-v4-flash-0731` | The model never called the engine's tools: both files ran out of rounds (exit code 1). |
| `no-supported-files.json` | written | Pull request without any file the engine reviews. |
| `rate-limited.json` | written | One file of two not reviewed: the model answered 429 after retries (exit code 0). |
| `overloaded.json` | written | No file reviewed: the model answered 503 after retries (exit code 1). |
