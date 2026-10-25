"""Original deterministic implementation for Resource Optimization (plotxyz-resource-optimization-agent)."""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict, deque


class LogicError(ValueError):
    """Raised when supplied input cannot be processed."""


def _text(payload, key, min_len=1, max_len=20000):
    value = payload.get(key)
    if not isinstance(value, str):
        raise LogicError(f"'{key}' must be a string")
    value = value.strip()
    if len(value) < min_len:
        raise LogicError(f"'{key}' is required")
    if len(value) > max_len:
        raise LogicError(f"'{key}' exceeds {max_len} characters")
    return value


def _num(payload, key, default=None, lo=None, hi=None):
    value = payload.get(key, default)
    if value is None or value == "":
        if default is None:
            raise LogicError(f"'{key}' is required")
        return default
    if isinstance(value, bool):
        raise LogicError(f"'{key}' must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LogicError(f"'{key}' must be numeric")
    if lo is not None and number < lo:
        raise LogicError(f"'{key}' must be at least {lo}")
    if hi is not None and number > hi:
        raise LogicError(f"'{key}' must be at most {hi}")
    return number


def _json(payload, key, expected=None, max_len=200000):
    raw = payload.get(key)
    if isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        if len(raw) > max_len:
            raise LogicError(f"'{key}' exceeds {max_len} characters")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LogicError(f"'{key}' is not valid JSON: {exc.msg} at line {exc.lineno}")
    else:
        raise LogicError(f"'{key}' must be JSON")
    if expected is not None and not isinstance(data, expected):
        name = expected.__name__ if hasattr(expected, "__name__") else str(expected)
        raise LogicError(f"'{key}' must be a JSON {name}")
    return data


def _csv(payload, key, max_rows=5000):
    text = _text(payload, key, max_len=2000000)
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise LogicError(f"'{key}' must include a header row")
        columns = [str(c).strip() for c in reader.fieldnames if c and str(c).strip()]
        if not columns:
            raise LogicError(f"'{key}' must include named columns")
        rows = []
        for index, raw in enumerate(reader):
            if index >= max_rows:
                raise LogicError(f"'{key}' exceeds {max_rows} rows")
            rows.append({col: (raw.get(col) or "").strip() for col in columns})
    except csv.Error as exc:
        raise LogicError(f"'{key}' is not valid CSV: {exc}")
    if not rows:
        raise LogicError(f"'{key}' must include at least one data row")
    return columns, rows


STOPWORDS = {'will', 'they', 'was', 'your', 'than', 'that', 'on', 'be', 'then', 'do', 'our', 'with', 'he', 'is', 'about', 'had', 'were', 'as', 'may', 'we', 'their', 'are', 'did', 'at', 'she', 'a', 'by', 'the', 'if', 'might', 'it', 'into', 'have', 'from', 'should', 'not', 'over', 'can', 'for', 'and', 'an', 'you', 'does', 'to', 'this', 'could', 'would', 'under', 'of', 'no', 'its', 'in', 'i', 'or', 'has'}


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower()) if w not in STOPWORDS]


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 2]


def provider_status():
    """Report which optional model providers are configured (never exposes secrets)."""
    ollama = bool(os.getenv("OLLAMA_BASE_URL"))
    openai = bool(os.getenv("OPENAI_BASE_URL") and os.getenv("OPENAI_MODEL"))
    return {"ollama_compatible": ollama, "openai_compatible": openai}


def _llm(messages, temperature=0.2):
    """Call an explicitly configured OpenAI-compatible endpoint; return None when unavailable."""
    base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "")
    if not base or not model:
        ollama = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        if not ollama:
            return None
        base = f"{ollama}/v1"
        model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        return None
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        key = os.getenv("OPENAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "temperature": temperature},
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


def _result(summary, result, warnings=None):
    return {"summary": summary, "result": result, "warnings": warnings or []}


def agent_resource_optimization(payload):
    cores = _num(payload, "cpu_cores", lo=1, hi=512)
    ram = _num(payload, "ram_gb", lo=1, hi=4096)
    workload = str(payload.get("workload", "api")).lower()
    if workload not in {"api", "batch", "ml"}:
        raise LogicError("workload must be api, batch, or ml")
    current_workers = int(_num(payload, "current_workers", default=1, lo=1, hi=1024))
    target_latency = _num(payload, "target_latency_ms", default=300, lo=10, hi=60000)
    if workload == "api":
        workers = max(2, int(cores * 2))
        batch = max(1, int(ram / 4))
        cache = min(4096, int(ram * 128))
        reason = "I/O-bound API work benefits from roughly two workers per core."
    elif workload == "batch":
        workers = max(1, int(cores))
        batch = max(8, int(ram * 2))
        cache = min(2048, int(ram * 64))
        reason = "CPU-bound batch work is kept near one worker per core."
    else:
        workers = max(1, int(cores // 2))
        batch = max(1, int(ram / 16))
        cache = min(8192, int(ram * 192))
        reason = "ML workloads reserve memory for model weights and avoid oversubscription."
    if target_latency < 100:
        workers = min(cores * 4, workers * 2)
        reason += " Tight latency targets increase concurrency."
    table = {
        "columns": ["Setting", "Current", "Recommended", "Rationale"],
        "rows": [
            ["Workers", current_workers, workers, reason],
            ["Batch size", "-", batch, "Derived from available RAM and workload type."],
            ["Cache (MB)", "-", cache, "Leaves headroom for the operating system and model."],
        ],
    }
    findings = []
    if current_workers > workers * 2:
        findings.append({"title": "Possible worker oversubscription", "severity": "medium", "detail": f"{current_workers} workers is more than twice the recommended {workers}; expect context-switch overhead."})
    if ram < 8 and workload == "ml":
        findings.append({"title": "Low memory for ML", "severity": "high", "detail": "Under 8 GB RAM is unlikely to support local model inference comfortably."})
    if current_workers < workers // 2:
        findings.append({"title": "Underutilized capacity", "severity": "low", "detail": "More concurrency may improve throughput if the workload is not memory-bound."})
    return _result(
        f"Recommended {workers} workers, batch size {batch}, and {cache} MB cache for the {workload} workload.",
        {
            "metrics": {"recommended_workers": workers, "batch_size": batch, "cache_mb": cache, "cpu_cores": cores, "ram_gb": ram},
            "table": table,
            "findings": findings,
            "items": ["Load-test with production-like payloads before applying changes.", "Watch p95 latency and memory pressure after the change."],
        },
    )


run = agent_resource_optimization
