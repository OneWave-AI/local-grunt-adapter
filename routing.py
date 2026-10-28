"""Conservative delegation admission. Heuristics, not a learned cost predictor."""


def decide(task, source_bytes, has_files, output_tokens, output_mode, feedback, force=False):
    if force:
        return {"route": "local", "reason": "Caller explicitly requested local processing"}
    if task in {"code", "review"}:
        return {"route": "caller", "reason": "Code judgment and review stay with the cloud assistant by default; local drafts require force_local=true"}
    history = feedback.get("by_task", {}).get(task, {})
    if history.get("reviewed", 0) >= 5 and history.get("accepted", 0) / history["reviewed"] < 0.8:
        return {"route": "caller", "reason": "Recent caller-reviewed results for this task are below the 80% acceptance threshold"}
    if not has_files:
        if output_mode == "artifact" and output_tokens >= 1024:
            return {"route": "local", "reason": "Large draft can stay on disk with a compact return value"}
        return {"route": "caller", "reason": "Source text is already in cloud context; delegation overhead likely outweighs this bounded task"}
    if source_bytes < 12000:
        return {"route": "caller", "reason": "File input is below the conservative 12 KB offload threshold"}
    if output_mode != "artifact" and source_bytes < output_tokens * 4 * 4:
        return {"route": "caller", "reason": "Requested output is too large relative to the source; ask for a shorter result or a saved draft"}
    return {"route": "local", "reason": "Substantial file input stays local and the requested return value is compact"}
