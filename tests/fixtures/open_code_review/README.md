# open-code-review outputs

Outputs of `ocr review --format json` for open-code-review 1.12.11, written from the output
types of its source (`cmd/opencodereview/output.go`, `internal/session/manifest.go`,
`internal/llm/retry_report.go`) rather than recorded from a run. Replace them with recorded
outputs once runs against a real model are available.

| File | Run |
| --- | --- |
| `with-comments.json` | Complete review with a single-line and a multi-line comment. |
| `silent.json` | Complete review without any comment. |
| `no-supported-files.json` | Pull request without any file the engine reviews. |
| `rate-limited.json` | One file of two not reviewed: the model answered 429 after retries (exit code 0). |
| `overloaded.json` | No file reviewed: the model answered 503 after retries (exit code 1). |
