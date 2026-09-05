# Policy: Write-scope isolation and concurrency

## Invariant
An agent or operation may write only inside its declared `write_scope`. Parallel writers must have disjoint scopes or an explicit must-happen-before ordering.

## Grammar (repository-relative)
- Segments are literal, `*` (whole segment), or trailing `**`.
- Allowed: `src/**`, `src/providers/*`, `docs/**`, `tests/unit/**`.
- Rejected: `../escape`, `/absolute`, `.\win\sep`, `.git/**`, `.formalprompt/**`, `src/*.py`, `src/**/*.py?`, `src/{a,b}`.

## Checks
1. Validate scopes against the grammar at composition time.
2. Compute scope intersections with the same grammar; if intersection cannot be proven empty and no ordering edge orders the writers, create a dependency edge or reduce parallelism.
3. Treat empty `write_scope: []` as read-only. `report`/`materialize`/`handoff` require non-empty scope; `checkpoint` must use a pinned `git-checkpoint` capability, not a scope.
4. `any` joins: writers on distinct branches are treated as potentially concurrent with descendants unless common to every input branch.

## Failure mode
Overlapping concurrent scopes → validation error, blocked approval. Fix by adding ordering edges, splitting scopes, or lowering `maximum_parallel_nodes`.

This policy should be included as an `execution-policy` artifact and referenced by implementation/verification nodes whenever parallelism is used.
