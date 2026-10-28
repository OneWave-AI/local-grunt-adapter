"""Mac memory admission and conservative context sizing. No model-generated commands."""
import os
import psutil

GIB = 1024 ** 3


def memory_snapshot():
    m = psutil.virtual_memory()
    return {"total_gib": round(m.total / GIB, 3), "available_gib": round(m.available / GIB, 3)}


def context_size(prompt_bytes, output_tokens):
    # UTF-8 bytes conservatively bound byte-fallback tokenizer input tokens.
    # Include chat template overhead rather than relying on characters / 4.
    needed = prompt_bytes + output_tokens + 768
    for size in (4096, 8192, 16384, 32768):
        if size >= needed:
            return size
    raise ValueError("Task cannot fit the maximum local context; split the source")


def admit_model(model, installed, loaded, context_tokens):
    memory = memory_snapshot()
    reserve = float(os.environ.get("LOCAL_GRUNT_RESERVE_GIB", max(2, memory["total_gib"] * 0.1)))
    if not 0 < reserve < memory["total_gib"]:
        raise ValueError("LOCAL_GRUNT_RESERVE_GIB must be positive and below total RAM")
    current = next((m for m in loaded if m.get("name") == model or m.get("model") == model), None)
    size = next((m.get("size", 0) for m in installed if m["name"] == model), 0)
    # This is a heuristic, not a guarantee of peak model/KV-cache memory.
    extra = (0 if current.get("context_length", 0) >= context_tokens else context_tokens / 32768) if current else size / GIB * 1.15 + context_tokens / 32768
    required = reserve + extra
    if memory["available_gib"] < required:
        raise RuntimeError(f"Memory guard: {memory['available_gib']:.1f} GiB available; estimated {required:.1f} GiB needed including reserve. Close applications or select a smaller model.")
    return memory
