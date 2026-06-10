#!/usr/bin/env python3
"""Benchmark de modelos Grok para classificação taxonômica.

Compara candidatos (modelo + reasoning_effort) contra o baseline real de produção
(job 94ed87ee de 2026-06-09, grok-4.3 low effort via redirect, 8,6% fallback),
usando o MESMO caminho de prompt de produção (src.llm_classifier._call_openai_api).

Métricas por candidato:
  - latência por batch de 100 itens
  - tokens cobrados (input / output / reasoning / cached) e custo estimado por 1k itens
  - modelo realmente servido (campo `model` da resposta — detecta redirects)
  - taxa de fallback ("Não Identificado")
  - concordância com o baseline (N1 e caminho completo N1>N2>N3>N4)
  - validade de hierarquia (caminho existe na árvore do projeto)

Uso (requer créditos xAI ativos e GROK_API_KEY no local.settings.json ou env):
  python3 scripts/benchmark_models.py                          # candidatos default
  python3 scripts/benchmark_models.py --sample 300 \
      --candidates "grok-4.3:low,grok-4.3:none,grok-4.20-0309-non-reasoning:-"

NUNCA roda em CI/testes — chamadas reais, custo real (~$0.05-0.15 por candidato
com sample=200).
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = REPO_ROOT / ".benchmark-data"

# Preços xAI vigentes (jun/2026) — $/1M tokens
PRICE_INPUT = 1.25
PRICE_OUTPUT = 2.50
PRICE_CACHED = 0.20

DEFAULT_CANDIDATES = (
    "grok-4.3:low,grok-4.3:none,grok-4.3:medium,grok-4.20-0309-non-reasoning:-"
)

INCOMPLETE = {"", "não identificado", "nao identificado", "n/a", "none", "null"}


def _norm(v):
    return str(v or "").strip().lower()


def is_fallback(item):
    return all(_norm(item.get(lv)) in INCOMPLETE for lv in ("N1", "N2", "N3", "N4"))


def load_data(sample_size, seed):
    config = json.loads((DATA_DIR / "project_config.json").read_text())
    baseline = json.loads((DATA_DIR / "baseline_result.json").read_text())["items"]
    hierarchy = config.get("custom_hierarchy") or []
    valid_paths = {
        tuple(_norm(h.get(lv)) for lv in ("N1", "N2", "N3", "N4")) for h in hierarchy
    }
    # Apenas itens com descrição e classificados no baseline (régua de concordância)
    pool = [
        it
        for it in baseline
        if it.get("description")
        and str(it["description"]).strip()
        and not is_fallback(it)
    ]
    random.Random(seed).shuffle(pool)
    sample = pool[:sample_size]
    return config, hierarchy, valid_paths, sample


def get_api_key():
    key = os.getenv("GROK_API_KEY", "")
    if not key:
        ls = REPO_ROOT / "local.settings.json"
        if ls.exists():
            key = json.loads(ls.read_text()).get("Values", {}).get("GROK_API_KEY", "")
    if not key:
        sys.exit("GROK_API_KEY não encontrada (env ou local.settings.json)")
    return key


def run_candidate(
    model, effort, sample, hierarchy, client_context, api_key, batch_size
):
    """Roda um candidato pelo caminho de prompt de produção, capturando raw responses."""
    import requests as requests_mod

    import src.llm_classifier as llm

    # Circuit breaker limpo por candidato (estado é global no módulo)
    llm._CIRCUIT_BREAKER = llm.CircuitBreaker(failure_threshold=5, recovery_timeout=60)

    captured = []  # (elapsed_s, raw_json) por chamada HTTP
    original_post = requests_mod.post

    def shim(url, **kwargs):
        if effort and effort != "-" and "json" in kwargs:
            kwargs["json"]["reasoning_effort"] = effort
        t0 = time.monotonic()
        resp = original_post(url, **kwargs)
        elapsed = time.monotonic() - t0
        try:
            captured.append((elapsed, resp.json()))
        except Exception:
            captured.append((elapsed, {"_http_status": resp.status_code}))
        return resp

    config = {
        "endpoint": os.getenv("GROK_API_ENDPOINT", "https://api.x.ai/v1"),
        "api_key": api_key,
        "deployment": model,
    }
    descriptions = [str(it["description"]) for it in sample]

    results = []
    requests_mod.post = shim
    # llm_classifier importa requests no módulo — patch lá também
    llm.requests.post = shim
    try:
        for i in range(0, len(descriptions), batch_size):
            batch = descriptions[i : i + batch_size]
            batch_results, _usage = llm._call_openai_api(
                batch,
                config,
                sector="Alimentação - Camarão e Peixes",
                client_context=client_context,
                custom_hierarchy=hierarchy,
            )
            results.extend(batch_results)
    finally:
        requests_mod.post = original_post
        llm.requests.post = original_post

    return results, captured


def summarize(model, effort, sample, results, captured, valid_paths):
    n = len(sample)
    usage = {"input": 0, "output": 0, "reasoning": 0, "cached": 0}
    served_models = set()
    latencies = []
    for elapsed, raw in captured:
        latencies.append(elapsed)
        if "model" in raw:
            served_models.add(raw["model"])
        u = raw.get("usage") or {}
        usage["input"] += u.get("prompt_tokens", 0)
        usage["output"] += u.get("completion_tokens", 0)
        usage["reasoning"] += (u.get("completion_tokens_details") or {}).get(
            "reasoning_tokens", 0
        )
        usage["cached"] += (u.get("prompt_tokens_details") or {}).get(
            "cached_tokens", 0
        )

    fallback = sum(1 for r in results if is_fallback(r))
    agree_n1 = agree_full = valid = comparable = 0
    for ref, got in zip(sample, results):
        if is_fallback(got):
            continue
        got_path = tuple(_norm(got.get(lv)) for lv in ("N1", "N2", "N3", "N4"))
        if got_path in valid_paths:
            valid += 1
        comparable += 1
        if _norm(got.get("N1")) == _norm(ref.get("N1")):
            agree_n1 += 1
        ref_path = tuple(_norm(ref.get(lv)) for lv in ("N1", "N2", "N3", "N4"))
        if got_path == ref_path:
            agree_full += 1

    fresh_input = usage["input"] - usage["cached"]
    cost = (
        fresh_input * PRICE_INPUT
        + usage["cached"] * PRICE_CACHED
        + usage["output"] * PRICE_OUTPUT
    ) / 1e6
    cost_per_1k = cost / n * 1000 if n else 0

    return {
        "candidate": f"{model}"
        + (f" (effort={effort})" if effort and effort != "-" else ""),
        "served_by": sorted(served_models),
        "items": n,
        "latency_per_batch_s": round(sum(latencies) / len(latencies), 1)
        if latencies
        else None,
        "fallback_pct": round(fallback / n * 100, 1) if n else None,
        "agree_n1_pct": round(agree_n1 / comparable * 100, 1) if comparable else None,
        "agree_full_path_pct": round(agree_full / comparable * 100, 1)
        if comparable
        else None,
        "valid_hierarchy_pct": round(valid / comparable * 100, 1)
        if comparable
        else None,
        "tokens": usage,
        "est_cost_usd_per_1k_items": round(cost_per_1k, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--candidates",
        default=DEFAULT_CANDIDATES,
        help="lista model:effort separada por vírgula (effort '-' = não enviar)",
    )
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(DATA_DIR / "benchmark_results.json"))
    args = ap.parse_args()

    api_key = get_api_key()
    config, hierarchy, valid_paths, sample = load_data(args.sample, args.seed)
    client_context = config.get("client_context", "")
    print(f"Golden set: {len(sample)} itens (baseline 94ed87ee, fallback excluído)")
    print(f"Árvore: {len(hierarchy)} combos | candidatos: {args.candidates}\n")

    reports = []
    for cand in args.candidates.split(","):
        model, _, effort = cand.strip().partition(":")
        print(f"→ {cand.strip()} ...", flush=True)
        t0 = time.monotonic()
        results, captured = run_candidate(
            model, effort, sample, hierarchy, client_context, api_key, args.batch_size
        )
        report = summarize(model, effort, sample, results, captured, valid_paths)
        report["wall_time_s"] = round(time.monotonic() - t0, 1)
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))

    Path(args.out).write_text(json.dumps(reports, ensure_ascii=False, indent=2))
    print(f"\nRelatório salvo em {args.out}")


if __name__ == "__main__":
    main()
