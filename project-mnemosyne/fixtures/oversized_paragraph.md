# Architecture Decision Record

## Context

This section describes the reasoning behind the chosen approach.

## Decision

We chose to implement the scoring pipeline as a series of independent Python subprocesses rather than a monolithic service because this approach provides several significant advantages that outweigh the overhead of subprocess invocation. First, each subprocess can be tested, upgraded, and replaced independently without affecting the rest of the pipeline. Second, Python's scientific ecosystem provides mature libraries for text analysis, graph algorithms, and statistical scoring that would be difficult to replicate in TypeScript. Third, the subprocess model naturally enforces the contract boundaries defined in the IPC protocol document, making it impossible for one module to access the internal state of another. Fourth, process isolation means that a crash in the Mermaid rendering subprocess cannot corrupt the in-memory state of the TypeScript orchestrator. Fifth, the approach aligns with the Unix philosophy of small, composable tools. Sixth, it simplifies future parallelization because independent subprocesses can be run concurrently without shared-memory synchronization primitives. Seventh, it enables mixing of language runtimes so that future modules could be written in Go or Rust without changing the orchestration layer. Eighth, the JSON-over-file-system IPC mechanism is trivially inspectable and debuggable by developers who can simply read the intermediate output files. Finally, the approach keeps the TypeScript orchestrator thin and focused on coordination rather than computation.

## Consequences

The main drawback is subprocess startup latency, which adds approximately 100-200ms per module invocation. This is acceptable for a local-first tool where analysis runs are infrequent.
