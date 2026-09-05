# Report synthesis

You produce a narrow, evidence-backed report from inspected state. The report is the node's deliverable; it is not execution history.

Steps:
1. Load the instruction resource and any input artifacts declared on the operation node's `artifact` or `evidence` ports.
2. Inspect the repository or predecessor outputs required by the node's description. Capture file paths, command outputs, and hashes that support each statement.
3. Write the report inside `write_scope` (e.g., `reports/<name>.md` or `docs/<topic>.md`). Keep it <2k words unless the acceptance criteria require more.
4. End with a verdict against the node's acceptance criteria: `pass` (with evidence) / `fail` (with reproduction) / `needs-input` (with the missing decision).

Do not diagnose the generating system, propose upstream policy changes, or claim authority beyond the report scope.
