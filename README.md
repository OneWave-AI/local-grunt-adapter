# Local Grunt Adapter

An MCP adapter that lets Codex, Claude and other local MCP clients delegate bounded text work to models running on the same computer through Ollama. MIT licensed; early release, version 0.5.1.

It handles substantial file summaries, structured extraction, classification, rewrites, focused code drafts and long-log digestion. The calling assistant chooses tasks and reviews results. A native Mac panel shows actual local activity and usage metadata.

## How it fits

- **Local Grunt Adapter** connects existing assistants to Ollama workers, with conservative routing and private-result artifacts.
- **[Grunt Mode](https://github.com/OneWave-AI/grunt-mode)** is a separate TypeScript task gateway with shadow evaluation and per-task quality gates, using a local llama.cpp-compatible backend.
- **[Crest](https://github.com/OneWave-AI/Crest)** is a separate desktop coding app with its own local coding API and permissions.

These projects can be used independently. The adapter does not require Grunt Mode or Crest and does not automatically reroute every prompt in an AI app.

## Quick start

Requirements: Python 3.11+, Ollama, installed local text-generation models, and a local MCP-capable client. macOS is the primary target; the worker can run without the panel. The native panel requires Xcode Command Line Tools. Model suitability depends on your machine and workload.

```sh
git clone https://github.com/OneWave-AI/local-grunt-adapter.git
cd local-grunt-adapter
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
ollama pull granite4.2:3b
ollama pull qwen3.5:9b
.venv/bin/python build_panel.py
.venv/bin/python adapter.py --doctor
```

Model downloads are explicit. Check memory and model licenses first. Smaller installed models can be selected explicitly; quality can vary substantially.

Configure your MCP client to launch the absolute path to `.venv/bin/python`, with the absolute path to `adapter.py` as its argument. Set `LOCAL_GRUNT_ROOTS` to a narrow folder of sample files, `LOCAL_GRUNT_STATE` to a private state folder, and the client tool timeout to 240 seconds where supported.

The optional installer registers supported installed clients and backs up their configuration:

```sh
.venv/bin/python install_clients.py --roots /absolute/path/to/sample-project
# Add --desktop to also register Claude Desktop.
```

It preserves unrelated entries and refuses to overwrite a different existing `local-grunt` entry. Its private backups may contain credentials; never share `.state/`. Restart existing client sessions to discover the tools. `sh setup.sh --roots /absolute/path/to/sample-project` combines dependency installation, optional panel build, doctor and registration.

## Try a synthetic task

This repository includes `example-source.txt`, containing a fictional customer and seat count. Example `local_run` arguments:

```json
{
  "task": "extract",
  "instructions": "Extract customer and seats. Return only those fields.",
  "project_path": "/absolute/path/to/local-grunt-adapter",
  "files": ["example-source.txt"],
  "force_local": true,
  "max_output_tokens": 128,
  "schema": {
    "type": "object",
    "properties": {"customer": {"type": "string"}, "seats": {"type": "integer"}},
    "required": ["customer", "seats"],
    "additionalProperties": false
  }
}
```

The expected fields are `customer: River Labs` and `seats: 12`. This small example uses `force_local` deliberately; normal routing keeps small tasks with the caller. Review the result, then record `local_outcome` using its `call_id` and `accepted`, `rejected` or `redone`.

## Tools and routing

| Tool | Purpose |
| --- | --- |
| `local_models` | Local availability, loaded models and configured file roots |
| `local_run` | Bounded summary, extraction, classification, rewrite or code draft |
| `local_digest_log` | Diagnostic/head/tail log digest with explicit omitted-line counts |
| `local_outcome` | Record a caller-reviewed result |
| `local_stats` | Local usage, review outcomes and labeled ROI estimates |
| `local_cloud_usage` | Record actual paired cloud measurements supplied by the caller |

Routing normally keeps file inputs under 12 KB, short inline tasks, code/review and unsuitable output sizes with the calling assistant. A task category with at least five reviewed results and less than 80% acceptance is paused. These thresholds are heuristics, not measured break-even points. Respect `decision=keep_with_caller`.

Default tiers are Granite 3B for routine tasks and Qwen 9B for classification/code/review. The memory guard keeps a reserve of at least 2 GiB or 10% of RAM. A smaller-model fallback requires `allow_smaller_model=true`; explicit model requests are never substituted. The adapter never downloads models or calls a cloud fallback.

Limits: 12 UTF-8 files, 18,000 source characters including line numbers, 24,000 total prompt bytes, 64–2,048 output tokens, a 180-second inference timeout and 2 MB log input. Larger logs are sampled and can omit failures. Model outputs can be incorrect even when schema-valid.

## Privacy and security boundaries

Inference requests use only loopback HTTP, bypass proxy environment settings, refuse redirects and reject remote/cloud model metadata. The adapter does not execute model-generated commands or change source files.

**Ordinary returned answers are visible to the calling assistant and may reach its cloud provider.** Passing source text in tool arguments also exposes it to that caller. For private inputs, pass file paths with neutral names and set `sensitive=true` before source content is read into the caller's context.

The adapter screens input files and generated output using heuristics. A detected or explicitly marked private task returns only a private artifact reference with no answer body or preview, and bypasses cache writes. The caller must never read that artifact through cloud-visible tools or retry the private job with a cloud model. Open it locally for human review. File paths, instructions and runtime metadata can still be visible to the caller.

Detection can miss names, addresses, credentials or other private information. The adapter cannot intercept unrelated app prompts or undo content already sent to the cloud. Treat local model runtimes and the host account as trusted. File-root checks are not an OS sandbox against malicious processes running as the same user.

Normal cached outputs live in `.state/cache.sqlite3` for up to 24 hours, capped at 200 entries on successful uncached writes. Artifacts live in `.state/drafts` and are cleaned after 24 hours when new artifacts are created. Historical state is not retroactively scrubbed. Stop clients before deleting state. The usage ledger stores metadata and review outcomes; the panel shows labels and metadata rather than source text or result bodies. Use neutral labels.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| `LOCAL_GRUNT_HOST` | `http://127.0.0.1:11434`; loopback HTTP only |
| `LOCAL_GRUNT_ROOTS` | Working directory; installer accepts explicit roots separated by `:` |
| `LOCAL_GRUNT_STATE` | `.state` beside the adapter |
| `LOCAL_GRUNT_FAST` | `granite4.2:3b` |
| `LOCAL_GRUNT_QUALITY` | `qwen3.5:9b` |
| `LOCAL_GRUNT_PANEL` | `1` on macOS; use `0` for headless operation |
| `LOCAL_GRUNT_RESERVE_GIB` | Override the default memory reserve |

The optional panel binds an ephemeral port on `127.0.0.1`, requires a per-process token and checks Host/Origin. It stays open after work finishes until closed; a warm model does not imply active generation.

## Verify

```sh
.venv/bin/python -m pytest -q
LOCAL_GRUNT_PANEL=0 .venv/bin/python smoke_test.py
```

The unit suite uses synthetic data and fake model responses. The smoke test uses the real MCP connection and an installed local model, in temporary state, to verify extraction, cache, artifacts and feedback. It does not run paid cloud calls. See [release review](SECURITY-REVIEW.md).

## Usage claims

Local inference counts are not measured cloud savings. The caller still spends usage selecting tasks, invoking tools and reviewing results. Modeled ROI uses explicit assumptions and can be negative. Actual paired cloud measurements must include all input and output from both runs; never invent a baseline. No savings percentage is claimed here.

## Uninstall

Remove only the `local-grunt` entry from each client's MCP configuration, restart the clients, and then remove the checkout and private state if desired. Ollama models are shared with other apps and are not removed automatically.
