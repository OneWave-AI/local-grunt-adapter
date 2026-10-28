# Release security review — Local Grunt Adapter 0.5.1

The source release passed 41 automated tests and a real stdio MCP-to-Ollama smoke test. No unresolved high-severity issue was identified in this review; that is not proof of absence.

## Findings fixed

| ID | Severity | Finding and resolution | Evidence |
| --- | --- | --- | --- |
| A1 | High | Sensitive generated output could enter the result cache before the response was screened. Raw output and parsed output are now screened before cache writes and validation errors; private output is artifact-only. The exact input snapshot is also screened before cache access. | `adapter.py:198`, `adapter.py:254`, `_generate` output-screening block; regression tests for sensitive output, validation errors and zero cache entries |
| A2 | Medium | Artifact content could briefly be created using ambient file permissions before chmod. Files are now opened exclusively with mode 0600; existing state directories are tightened to 0700. | `adapter.py` artifact creation; permissions regression |
| A3 | Medium | The optional panel's backend HTTP client followed redirects. It now refuses redirects and rejects credential/query/fragment URL variants. | `dashboard.py:28`; local redirect regression |
| A4 | Low | Installer-written configuration did not explicitly set private permissions. Codex and Desktop configuration writes now set mode 0600. | `install_clients.py` configuration write paths |

## Verification

- 41 Python tests passed using mocked inference and synthetic data.
- Real stdio MCP smoke passed: initialization, catalog, schema extraction, cache, review outcomes, private artifact mechanics and error propagation. This smoke input was synthetic and non-sensitive.
- Gitleaks 8.30.1 reported no secrets in the release source tree.
- pip-audit reported no known vulnerabilities for all pinned entries in `requirements-lock.txt`, using `--no-deps --disable-pip`. The lock lists transitive dependencies; the audit did not resolve a new environment. Known-advisory coverage is not a supply-chain guarantee.
- Python compilation and shell syntax checks passed.
- Bandit results were reviewed. Its medium SQL-construction flag in `jobs.py:36` is constrained by a fixed column-name allowlist and parameterized values. Its URL-open flag is in a test against a local ephemeral server. Neither was treated as an exploitable finding in this context.

## Operational limits

Heuristic screening can miss private information. Use file arguments and `sensitive=true` for known private data, and never read private artifacts into a cloud caller. Ordinary returned answers remain visible to the caller. Existing caches and artifacts from earlier versions are not retroactively scrubbed. Caller labels and metadata can be visible; use neutral labels. Local root checks are not an OS sandbox against same-account filesystem races.

The native panel source is included; this release did not repeat a live native-window UI test. The panel's backend protections are covered by local tests. No paid cloud calls were used for verification.

## Scope and remaining limits

This was a source review and local release verification on October 27, 2026, not an independent penetration test or security certification. Automated detection can miss secrets and vulnerabilities. The trust boundary is one user on a trusted computer; malicious processes with the same account, compromised model runtimes and arbitrary client plugins are outside the isolation provided here.

No runtime data, client configuration backups, private output artifacts, model weights or private Git history are included. Examples and regression inputs are synthetic. Dependencies and models retain their own licenses.
