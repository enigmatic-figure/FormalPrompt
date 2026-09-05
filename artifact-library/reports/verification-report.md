# Report template: Verification result

## Heading
`Verification — <node title> — <timestamp>`

## Body
1. **Criterion**: quoted from `acceptance_criteria`
2. **Check**: exact command or inspection performed
3. **Observed result**: full stdout/stderr tail, file path, or UI screenshot path
4. **Verdict**: `pass` | `fail` | `unverifiable`

## Example
- Criterion: "Export produces identical bytes for fixture `examples/large-dataset`"
  - Check: `uv run pytest tests/test_export.py -k test_large_fixture --tb=short`
  - Result: `1 passed in 2.41s` — output hash `sha256: ab...`
  - Verdict: `pass`

## Evidence
Attach log files or artifact hashes. Do not infer a pass from file presence.

This template is a `report-template` artifact. Operation nodes that produce reports should reference it and satisfy its acceptance criteria.
