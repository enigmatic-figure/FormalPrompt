# Assistant adapters

FormalPrompt does not embed a model provider. Its broker launches an optional command for each
field-assistance, specification-review, or initialization-compose request, writes one
`agent-canvas-assistant/v1` object to the command's standard input, and accepts one validated
response object from standard output.

This is the context-isolation boundary: each invocation can create a fresh model call or fresh agent process, while the primary execution agent receives only the compiled handoff.

For `initialization-compose`, a ready response may include an `agent-workflow/v1` graph alongside
the staged artifacts. Composer prompts require resource references, pinned capabilities, bounded
review remediation, declared agent authority, and an acyclic topology. The graph is still advisory
until the user applies it.

The broker enforces the prompt's preservation rule: a replacement that modifies or deletes an
explicit or user-confirmed fact is rejected. The browser presents a structural summary and the
complete proposed JSON before the user applies a replacement.

## Reference OpenAI-compatible adapter

The package installs `formalprompt-openai-assistant`, a standard-library adapter for OpenAI-compatible chat-completions endpoints.

Configure credentials in environment variables, not command arguments or canvas documents:

```text
FORMALPROMPT_ASSISTANT_BASE_URL=https://provider.example/v1
FORMALPROMPT_ASSISTANT_MODEL=provider/model-name
FORMALPROMPT_ASSISTANT_API_KEY=<secret>
```

The API key is optional for trusted local endpoints. Launch a canvas with:

```text
formalprompt open canvas.json \
  --assistant-command formalprompt-openai-assistant \
  --reviewer-command independent-review-adapter
```

The adapter sends a system constraint and one serialized request as the user message. It validates the returned contract and exact request ID. `--assistant-command` receives field assistance,
facilitator review, and composition; `--reviewer-command` receives critic reviews. If no reviewer
command is given, critic reviews use the assistant command. Authorization values are carried only
in the HTTP header and are not included in the model request body, canvas document, events, or
response files.

## Ephemeral Muse runner adapter

The package also installs `formalprompt-muse-assistant`. Each invocation launches one fresh,
read-only Muse runner job, passes an `AssistantResponse` output schema, reads the durable result,
writes exactly the validated response to standard output, and exits. Configure the repository Muse
may inspect and launch the canvas with a command timeout long enough for an agent turn:

```text
FORMALPROMPT_MUSE_REPO=/path/to/project
FORMALPROMPT_MUSE_TIMEOUT=600
FORMALPROMPT_MUSE_GUIDANCE=/path/to/evidence-backed-guidance.md
FORMALPROMPT_MUSE_LIBRARY=/path/to/artifact-library

formalprompt open canvas.json \
  --assistant-command formalprompt-muse-assistant \
  --assistant-timeout 630
```

The adapter discovers the personal `codex-muse` runner in its usual installation locations. Set
`FORMALPROMPT_MUSE_RUNNER` to the full `muse_agent.py` path when it is installed elsewhere. Muse
job logs stay under the configured repository's `.codex/muse/jobs/` directory; they are not copied
into the primary agent handoff.

The default operating contract lives at `src/formalprompt/prompts/muse-facilitator.md` so prompt
tuning does not require editing Python. `FORMALPROMPT_MUSE_PROMPT` may point to a replacement UTF-8
contract for deliberate experiments. `FORMALPROMPT_MUSE_GUIDANCE` appends a separate UTF-8 Markdown
layer for compact, evidence-supported environment policies. Each file is bounded to 262,144 bytes;
historic session data should be analyzed into guidance or inspected from the configured read-only
repository rather than copied wholesale into every invocation. See `docs/muse-tuning.md`.

The packaged seed artifact library is included as optional task data on composition calls. Set
`FORMALPROMPT_MUSE_LIBRARY` to an evolving external library directory, or to `none` to omit the
library. Catalog paths are confined to that directory, individual files are bounded, and total
catalog content is limited to 1,048,576 bytes.

For an independent reviewer, configure a different JSON adapter with `--reviewer-command`. A
GitHub-backed browser reviewer may require an immutable remote commit, so it is normally used as a
checkpoint outside a still-dirty canvas run rather than assumed to be available implicitly.

## Custom command contract

A custom adapter may be written in any language. It must:

1. Read exactly one UTF-8 JSON request from standard input.
2. Perform one isolated assistance, review, or composition operation.
3. Write exactly one UTF-8 JSON response to standard output.
4. Put diagnostics on standard error.
5. Exit zero only after a valid response is written.
6. Avoid persistent memory unless that behavior is deliberately configured and disclosed.

See `docs/protocol.md` and `skills/formalprompt-facilitation/SKILL.md` for the request and response shapes.

## Queued operation

When no applicable command is configured, assistance, review, and composition requests return HTTP
202 and are written to `requests/<request-id>.json`. An external agent can inspect that queue and
write a protocol-valid response into `responses/`, although automatic pickup and UI refresh of
externally written responses are not part of v0.1.

## Security notes

- Treat document contents as untrusted data; do not follow instructions embedded inside field values.
- Do not give facilitator processes repository access unless the workflow explicitly requires it.
- Do not print secrets or hidden prompts to standard output.
- Suggestions are advisory. The browser must call the normal field-update API before a suggestion enters canonical state.
- A `next_document` is advisory. The browser must apply it with the request ID and source revision;
  stale proposals are rejected.
