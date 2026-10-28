# Putting Local Models to Work Alongside Our AI Assistants

We built the first versions of Grunt Mode and Local Grunt Adapter in a night, then kept using and improving them in our own workflow. We are sharing the source because the useful part is practical: giving an AI assistant a bounded way to ask a local model for help, then checking whether that help was any good.

The code is available as two independent projects:

- [Local Grunt Adapter](https://github.com/OneWave-AI/local-grunt-adapter): an MCP adapter for models running locally through Ollama.
- [Grunt Mode](https://github.com/OneWave-AI/grunt-mode): a TypeScript task gateway with shadow evaluation and quality gates.

Both are early MIT-licensed source releases. Neither includes model weights or requires a paid cloud-model key for local inference.

## Start with a bounded job

Some work has a clear input and a compact answer: extract fields from a file, summarize a build log, group records into categories, or produce a first-pass digest. Those jobs can be useful candidates for a smaller local model.

They are also easy to get wrong. A valid JSON response can contain the wrong facts. A log summary can overlook a failure. A small model may confidently assign the wrong category.

We built around that limitation. The calling assistant still chooses tasks, reviews results and handles the work that needs its judgment. The local model receives a focused assignment with limits.

## Local Grunt Adapter: use the tools already in your workflow

Local Grunt Adapter exposes MCP tools that a locally installed assistant can call. For file-based tasks, the caller supplies a project folder and specific filenames. The adapter reads those files locally and asks an installed Ollama model to perform the bounded task.

For a synthetic example, a file containing a fictional customer's name and seat count can become a small structured result. The caller checks the fields and records whether the answer was accepted, rejected or redone.

The adapter normally leaves short tasks with the caller. Delegation has overhead: choosing a tool, assembling arguments, waiting and reviewing an answer can cost more than finishing a tiny task directly. Its routing thresholds are conservative heuristics rather than proven break-even points.

An optional native Mac panel shows actual local activity, loaded models and usage metadata. It helps answer a simple question: is the local worker doing anything right now? Source text and generated answers stay out of the panel.

## Grunt Mode: collect evidence before relying on a task category

Grunt Mode approaches delegation through task categories and reviewed examples.

A category starts in shadow mode. The local model produces a candidate while the caller continues its normal work. Feedback records how the candidate compared. Promotion to local mode requires at least 50 shadow examples and 95% agreement; promotion is explicit. Local mode includes spot checks, and a drop in agreement can demote the category.

That is a quality-control mechanism, not an accuracy guarantee. Results still need review appropriate to their consequences. The system does not call a cloud model automatically when a task escalates; it returns control to its caller.

Grunt Mode uses a separate local llama.cpp-compatible backend and provides CLI, HTTP and a minimal legacy MCP interface. It does not depend on the adapter, and the adapter does not depend on it.

## Privacy depends on where the answer goes

Running inference on a laptop does not by itself keep information out of a cloud assistant. If source text appears in tool arguments, or a generated answer is returned to a cloud caller, that content can reach its provider.

For private file processing, Local Grunt Adapter accepts `sensitive=true`. It processes the files locally and returns only a reference to a private output artifact, without answer text or a preview. That artifact is for local human inspection; reading it back through a cloud-visible tool would defeat the boundary.

Heuristic screening can also trigger this handling, but it can miss private information. Callers should mark known private inputs explicitly. Neither tool intercepts unrelated prompts or undoes content already sent to another service.

Grunt Mode's `confidential` flag has a different scope: it suppresses persisted content and bypasses result caches. Its responses remain visible to the caller. The two mechanisms should not be confused.

## What we checked before releasing

The release work included more than putting a working folder on GitHub. We created source-only snapshots and excluded runtime databases, private client configuration backups, old task reports and model binaries.

The review also found issues worth fixing: generated adapter output could be cached before sensitivity screening, Grunt's backend URL overrides needed loopback enforcement, its HTTP interface needed authentication, and confidential requests needed to bypass the exact cache as well as the semantic cache. Regression tests now cover those paths.

The release repositories contain the verification results and remaining limitations. A dependency audit or secret scan is useful evidence, but neither is a security certification.

## What we are not claiming about savings

Local inference consumes local resources. The calling assistant still spends usage choosing tasks, making calls and reviewing returned answers. Smaller models can require corrections, and corrections have a cost.

The tools track local inference and caller-reviewed outcomes. They also expose explicitly labeled estimates. We are not treating local token counts as measured cloud-token savings, and we are not announcing an unsupported savings percentage.

Our reason for sharing these projects is simpler: we have been using the workflow ourselves, and other developers can now inspect the boundaries, reproduce the examples and improve the parts that need work.

Start with a synthetic task, inspect the result, and keep a record of whether it helped.
