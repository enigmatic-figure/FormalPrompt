# Policy: Intent-preserving deviation

## Principle
Preserve the user-approved intended outcome when physical reality (existing code, tool output, missing capability) invalidates an implementation detail.

## Decision ladder
1. **Narrow adaptation allowed** (`workflow.policy.deviation: allow-narrow` or node-local allowance): change the minimal detail that lets the node still satisfy its `acceptance_criteria` (e.g., rename a function to match existing conventions, adjust a path inside `write_scope`, choose the next compatible library version). Record the adaptation in the commit message and session log.
2. **Consequential adaptation**: any change that alters intent, authority, model assignment, completion criteria, write scope, or resource bindings. This follows the declared user-decision path (typically a `gate: user-approval` node). Do not silently proceed.
3. **Intervention marker**: when the adaptation required a local intervention worth later examination (violated expectation, not ordinary work), emit one `formalprompt-intervention` marker with the active node ID, then continue.

## What not to do
- Do not rewrite the approved graph to make history look planned.
- Do not promote a local repair into a reusable library policy during execution.
- Do not ask the execution agent for root-cause or upstream recommendations.

Include this as an `execution-policy` artifact when the workflow permits adaptive repair.
