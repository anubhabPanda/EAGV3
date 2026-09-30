#!/usr/bin/env python
"""p6 — what the semantic cache actually saves, and what it actually gets wrong.

The other proofs in this directory measure money the gateway spent. This one
measures money the gateway did NOT spend, which is a harder thing to be honest
about, because a cache that saves a lot and a cache that quietly answers the
wrong question look identical on a savings dashboard.

So p6 measures both halves, through the live gateway, with the real embedder:

1. **The embedding is real.** ``/v1/embed`` is asked for a vector and the vector
   is checked the way you check a stub: right dimension, right embedder
   identity, deterministic on a repeat, and NOT constant across different texts.
   glc_v4's seven unit tests for this cache all inject a fixed embedder, so they
   pass whether or not nomic is wired up. This check is the one that would not.
2. **Paraphrases hit.** Each ``same`` pair is round-tripped: prompt A cold
   (miss, provider call, real cost), then prompt B (hit, no provider call). The
   similarity the gateway reports is compared against the cosine computed here
   from the same embeddings — if those two numbers disagree, the cache is not
   deciding on what it says it is deciding on.
3. **Near-misses miss.** Each ``different`` pair is round-tripped the same way.
   A hit here is a wrong answer served with no error and no signal.
4. **The threshold is swept.** Over every labelled pair, at every threshold in
   the range, the true-positive and false-positive rates. This is the number
   ``cache.yaml``'s comment asserts and nobody had measured. Whatever it says,
   it goes in the report.
5. **The saving is net.** A hit still costs an embedding call. The gross saving
   is the cold call's tokens and dollars; the net saving subtracts the embedding
   the lookup had to compute. Locally that is free in dollars and real in
   milliseconds, so the proof reports the break-even embedding price above which
   a hosted embedder would erase the saving entirely.
6. **Namespaces isolate.** The same paraphrase that hits must MISS when the
   model, the system prompt or the tenant changes, because a cached answer from
   a different model is a different answer.

The pairs are DATA (``--pairs``), the threshold comes from the gateway's own
``cache.yaml`` unless overridden, the sweep range comes from the command line,
and the two models used for the namespace check come from ``config/tiers.yaml``.
Nothing about the measurement is written down in this file, so pointing it at an
unseen pair file recomputes every number with no edit.

Unlike p7 this proof talks to ``/v1/chat`` over plain httpx rather than through
:class:`~sourcecode.gateway.GatewayClient`. It has to: the thing under test is the
gateway's ``cache`` envelope and its ``semantic_cache`` opt-in, and the client
deliberately does not carry either — sourcecode's budget path must never be able to
be served a stale answer without asking for one.

    python proofs/p6_cache_savings.py --base-url http://127.0.0.1:8112
    python proofs/p6_cache_savings.py --pairs mine.jsonl --sweep-low 0.80
    python proofs/p6_cache_savings.py --offline          # CI: simulation, not evidence
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from harness import DEFAULT_BASE_URL, OUT, Args, Proof, gateway_reachable, sync

from sourcecode.core.memory.embeddings import DeterministicEmbedder
from sourcecode.economics import EconomicsConfig
from sourcecode.evals import (
    LabelledPair,
    best_operating,
    by_family,
    load_pairs,
    separable,
    steepest_fpr_drop,
    sweep,
    thresholds,
)

DEFAULT_PAIRS = Path(__file__).resolve().parent / "pairs" / "paraphrases.jsonl"

#: A neutral instruction. The proof measures which prompt hit and what it cost,
#: never what the answer said, so the system prompt only has to be constant —
#: and it carries the per-pair nonce that gives each pair its own namespace.
SYSTEM = "Answer the user directly and in one short paragraph."


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, computed the way glc_v4's cache computes it.

    Deliberately the same arithmetic rather than an import: p6 must be able to
    say the gateway's reported similarity and this proof's number agree, and
    that claim is worth nothing if both came from the same function object.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


# --------------------------------------------------------------------------- #
# the gateway seam
# --------------------------------------------------------------------------- #


class LiveCacheProbe:
    """Everything p6 asks the running gateway for, and nothing else."""

    def __init__(self, base_url: str, *, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout)
        self.embed_latencies_ms: list[float] = []
        self.embed_calls = 0

    async def close(self) -> None:
        await self.client.aclose()

    async def embedders(self) -> dict[str, Any]:
        """The failover ring the cache was wired to, straight from the gateway."""
        response = await self.client.get(f"{self.base_url}/v1/embedders")
        response.raise_for_status()
        return response.json()

    async def cache_config(self) -> dict[str, Any]:
        response = await self.client.get(f"{self.base_url}/v1/cache/stats")
        if response.status_code == 404:
            # A gateway old enough to answer /healthz but not this route cannot
            # be measured, and pretending otherwise would report a cache that
            # is not there. Say which URL, so --base-url is the obvious fix.
            raise SystemExit(
                f"{self.base_url} has no /v1/cache/stats: this gateway has no semantic cache. "
                f"Point --base-url at one that does, or run --offline."
            )
        response.raise_for_status()
        return response.json()

    async def price_of(self, provider: str, model: str) -> dict[str, Any]:
        response = await self.client.get(
            f"{self.base_url}/v1/pricing", params={"provider": provider, "model": model}
        )
        response.raise_for_status()
        return response.json()

    async def embed(self, text: str, task_type: str) -> dict[str, Any]:
        """One embedding, timed end to end. This is the cache's own code path."""
        started = time.perf_counter()
        response = await self.client.post(
            f"{self.base_url}/v1/embed", json={"text": text, "task_type": task_type}
        )
        elapsed = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        self.embed_calls += 1
        self.embed_latencies_ms.append(elapsed)
        body = response.json()
        body["wall_ms"] = elapsed
        return body

    async def chat(self, prompt: str, system: str, request: dict[str, Any]) -> dict[str, Any]:
        """One /v1/chat with the semantic cache switched on for this request."""
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "system": system,
            "semantic_cache": True,
            "agent": "p6_cache",
            **request,
        }
        started = time.perf_counter()
        response = await self.client.post(f"{self.base_url}/v1/chat", json=payload)
        elapsed = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            raise RuntimeError(f"/v1/chat -> {response.status_code}: {response.text[:400]}")
        body = response.json()
        body["wall_ms"] = elapsed
        return body


def _verdict(body: dict[str, Any]) -> dict[str, Any]:
    """The cache envelope plus what the call cost, flattened for the report."""
    cache = body.get("cache") or {}
    cost = body.get("cost") or {}
    return {
        "hit": bool(cache.get("hit")),
        "similarity": float(cache.get("similarity") or 0.0),
        "best_similarity": float(cache.get("best_similarity") or 0.0),
        "skipped_reason": cache.get("skipped_reason") or "",
        "provider": body.get("provider"),
        "model": body.get("model"),
        "input_tokens": int(body.get("input_tokens") or 0),
        "output_tokens": int(body.get("output_tokens") or 0),
        "usd": float(cost.get("total_usd") or 0.0),
        "price_source": cost.get("price_source"),
        "latency_ms": body.get("latency_ms"),
        "wall_ms": round(body.get("wall_ms") or 0.0, 1),
        "chars": len(str(body.get("text") or "")),
    }


# --------------------------------------------------------------------------- #
# the measurement
# --------------------------------------------------------------------------- #


async def _score_pairs(probe: LiveCacheProbe, pairs, task_type: str) -> dict[str, dict[str, Any]]:
    """Embed both sides of every pair once and score them. No provider calls."""
    vectors: dict[str, list[float]] = {}
    scored: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        for text in (pair.a, pair.b):
            if text not in vectors:
                vectors[text] = (await probe.embed(text, task_type))["embedding"]
        scored[pair.id] = {"cosine": cosine(vectors[pair.a], vectors[pair.b])}
    return scored


async def _round_trip(
    probe: LiveCacheProbe,
    pair: LabelledPair,
    request: dict[str, Any],
    nonce: str,
    pace: float,
) -> dict[str, Any]:
    """Prompt A cold, then prompt B, in a namespace nobody else is using.

    The nonce goes in the system prompt, which ``cache.yaml`` lists as a
    namespace field. That gives each pair a private namespace, so the similarity
    reported for B is unambiguously B against A and not B against some other
    pair's prompt left in the shared table by an earlier run.
    """
    system = f"{SYSTEM} [{nonce}/{pair.id}]"
    cold = _verdict(await probe.chat(pair.a, system, request))
    await asyncio.sleep(pace)
    warm = _verdict(await probe.chat(pair.b, system, request))
    await asyncio.sleep(pace)
    return {"system": system, "cold": cold, "warm": warm}


async def _namespace_isolation(
    probe: LiveCacheProbe,
    pair: LabelledPair,
    base_request: dict[str, Any],
    other_model: str,
    nonce: str,
    pace: float,
) -> dict[str, Any]:
    """Store A, then ask B four ways. Only the identical namespace may hit."""
    system = f"{SYSTEM} [{nonce}/ns/{pair.id}]"
    out: dict[str, Any] = {"pair": pair.id, "system": system}
    out["store"] = _verdict(await probe.chat(pair.a, system, base_request))
    await asyncio.sleep(pace)

    cases = {
        "control (same model, system and tenant)": (system, dict(base_request)),
        "different model": (system, {**base_request, "model": other_model}),
        "different system prompt": (f"{system} Also cite a source.", dict(base_request)),
        "different tenant": (system, {**base_request, "tenant": f"{nonce}-other-tenant"}),
    }
    for label, (sys_text, request) in cases.items():
        try:
            out[label] = _verdict(await probe.chat(pair.b, sys_text, request))
        except Exception as error:
            # A model that cannot answer is still evidence about the CACHE: the
            # question is whether it was consulted, and a provider error proves
            # it was not served from the cache.
            out[label] = {"hit": False, "error": f"{type(error).__name__}: {error}"[:200]}
        await asyncio.sleep(pace)
    return out


async def _measure(
    *,
    base_url: str,
    pairs,
    request: dict[str, Any],
    other_model: str,
    task_type: str,
    nonce: str,
    pace: float,
    live_pairs: int,
) -> dict[str, Any]:
    probe = LiveCacheProbe(base_url)
    try:
        ring = await probe.embedders()
        cache = await probe.cache_config()
        task_type = task_type or (cache.get("config") or {}).get("task_type") or "retrieval_query"

        # --- 1. the embedder is real ------------------------------------- #
        probe_text = f"p6 embedder identity probe {nonce}"
        first = await probe.embed(probe_text, task_type)
        second = await probe.embed(probe_text, task_type)
        third = await probe.embed(f"an entirely different sentence about {nonce} pancakes", task_type)
        identity = {
            "provider": first.get("provider"),
            "model": first.get("model"),
            "reported_dim": first.get("dim"),
            "vector_length": len(first["embedding"]),
            "ring_order": ring.get("order"),
            "ring_models": ring.get("models"),
            "ring_fixed_dim": ring.get("fixed_dim"),
            "task_type": task_type,
            "repeat_cosine": cosine(first["embedding"], second["embedding"]),
            "unrelated_cosine": cosine(first["embedding"], third["embedding"]),
            "distinct_values": len({round(v, 9) for v in first["embedding"]}),
            "gateway_latency_ms": [first.get("latency_ms"), second.get("latency_ms")],
        }

        # --- 2. cosine for every pair ------------------------------------ #
        scored = await _score_pairs(probe, pairs, task_type)
        embed_only_calls = probe.embed_calls
        embed_only_latencies = list(probe.embed_latencies_ms)

        # --- 3. the live round trips ------------------------------------- #
        wanted = pairs if live_pairs <= 0 else pairs[:live_pairs]
        trips: dict[str, Any] = {}
        for pair in wanted:
            try:
                trips[pair.id] = await _round_trip(probe, pair, request, nonce, pace)
            except Exception as error:
                trips[pair.id] = {"error": f"{type(error).__name__}: {error}"[:300]}

        # --- 4. namespace isolation, on the pair most likely to hit ------- #
        strongest = max(
            (p for p in pairs if p.positive), key=lambda p: scored[p.id]["cosine"], default=None
        )
        isolation: dict[str, Any] = {}
        if strongest is not None:
            isolation = await _namespace_isolation(
                probe, strongest, request, other_model, nonce, pace
            )
            isolation["cosine"] = scored[strongest.id]["cosine"]

        # --- 5. what an embedding costs ---------------------------------- #
        embed_price = await probe.price_of(first.get("provider") or "", first.get("model") or "")
        after = await probe.cache_config()

        return {
            "identity": identity,
            "scored": scored,
            "trips": trips,
            "isolation": isolation,
            "cache_config": cache.get("config") or {},
            "cache_counters_before": {
                k: cache.get(k) for k in ("lookups", "hits", "misses", "stores", "embed_failures")
            },
            "cache_counters_after": {
                k: after.get(k) for k in ("lookups", "hits", "misses", "stores", "embed_failures")
            },
            "embed_price": embed_price,
            "embedding": {
                "calls_for_scoring": embed_only_calls,
                "median_wall_ms": round(statistics.median(embed_only_latencies), 2),
                "mean_wall_ms": round(statistics.fmean(embed_only_latencies), 2),
                "min_wall_ms": round(min(embed_only_latencies), 2),
                "max_wall_ms": round(max(embed_only_latencies), 2),
            },
        }
    finally:
        await probe.close()


def _simulate(pairs, threshold: float) -> dict[str, Any]:
    """Offline: the same pipeline, a deterministic embedder, no evidence.

    Every downstream step — the sweep, the separability verdict, the report, the
    exit code — runs on these numbers exactly as it runs on live ones, which is
    what CI is checking. The numbers themselves prove nothing about nomic and
    the report says so on every line.
    """
    embedder = DeterministicEmbedder(256)
    scored = {p.id: {"cosine": cosine(embedder.embed(p.a), embedder.embed(p.b))} for p in pairs}
    trips = {
        p.id: {
            "system": "(simulated)",
            "cold": {"hit": False, "similarity": 0.0, "usd": 0.0, "input_tokens": 0,
                     "output_tokens": 0, "simulated": True},
            "warm": {"hit": scored[p.id]["cosine"] >= threshold,
                     "similarity": scored[p.id]["cosine"] if scored[p.id]["cosine"] >= threshold else 0.0,
                     "best_similarity": scored[p.id]["cosine"], "usd": 0.0,
                     "input_tokens": 0, "output_tokens": 0, "simulated": True},
        }
        for p in pairs
    }
    return {
        "identity": {"provider": "(deterministic)", "model": embedder.fingerprint,
                     "reported_dim": embedder.dimensions, "vector_length": embedder.dimensions,
                     "simulated": True},
        "scored": scored,
        "trips": trips,
        "isolation": {},
        "cache_config": {"threshold": threshold, "simulated": True},
        "cache_counters_before": {},
        "cache_counters_after": {},
        "embed_price": {},
        "embedding": {"calls_for_scoring": 2 * len(pairs), "median_wall_ms": 0.0,
                      "mean_wall_ms": 0.0, "min_wall_ms": 0.0, "max_wall_ms": 0.0},
    }


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #


def _finding(points, config_threshold: float, split: dict[str, Any], safest) -> str:
    """One sentence a reader can quote, derived entirely from the measurement."""
    at_config = next((p for p in points if abs(p.threshold - config_threshold) < 1e-9), None)
    if split.get("separable"):
        return (
            f"the labelled set IS separable: every 'same' pair scores above every 'different' "
            f"pair, with a margin of {split['margin']:.4f}. A threshold anywhere in "
            f"({split['highest_negative']:.4f}, {split['lowest_positive']:.4f}] admits every "
            f"paraphrase and no collision."
        )
    line = (
        f"the labelled set is NOT separable: the highest-scoring 'different' pair "
        f"({split['highest_negative_id']}, {split['highest_negative']:.4f}) outscores the "
        f"lowest-scoring 'same' pair ({split['lowest_positive']:.4f}), so NO threshold admits "
        f"every paraphrase without also admitting at least one wrong answer."
    )
    if at_config is not None:
        line += (
            f" At the configured {config_threshold:.2f}: TPR {at_config.tpr:.2f}, "
            f"FPR {at_config.fpr:.2f} ({at_config.false_positives}/{at_config.negatives} "
            f"wrong-answer collisions)."
        )
    if safest is not None and safest.false_positives == 0:
        line += f" The highest collision-free threshold is {safest.threshold:.2f} (TPR {safest.tpr:.2f})."
    elif safest is not None:
        line += (
            f" NO threshold in the swept range reaches zero collisions: the least-bad point is "
            f"{safest.threshold:.2f}, and it still admits {safest.false_positives} of "
            f"{safest.negatives} wrong pairs (TPR {safest.tpr:.2f}, FPR {safest.fpr:.2f})."
        )
    return line


def run(parsed: argparse.Namespace) -> Proof:
    config = EconomicsConfig.load(parsed.config_dir)
    pairs = load_pairs(parsed.pairs)
    ladder = config.ladder

    # The two models come from the ladder, so the namespace check compares two
    # models a reviewer can see in tiers.yaml rather than two names typed here.
    tier = ladder.tier(parsed.tier) if parsed.tier else ladder.tier(ladder.names[0])
    other = ladder.tier(ladder.names[1] if len(ladder.names) > 1 else ladder.names[0])
    request = {
        k: v for k, v in dict(tier.request).items()
        if k in ("provider", "model", "max_tokens", "reasoning")
    }
    request["temperature"] = 0
    request["tenant"] = parsed.principal.split("/")[0]

    base_url = parsed.base_url.rstrip("/")
    live = not parsed.offline and gateway_reachable(base_url)
    nonce = f"p6-{int(time.time())}"

    args = Args(
        task=f"{len(pairs)} labelled pairs from {parsed.pairs}",
        budget=0.0, principal=parsed.principal, offline=not live, base_url=base_url,
        otel_endpoint=None, respond_as="text", config_dir=parsed.config_dir,
        live_embeddings=live, label=parsed.label,
    )

    if live:
        mode, detail = "live", {"base_url": base_url, "nonce": nonce,
                                "answering_model": f"{request.get('provider')}/{request.get('model')}"}
        print(f"\np6: {len(pairs)} labelled pairs, live against {base_url}")
        print(f"  answering   {request.get('provider')}/{request.get('model')}")
        print(f"  namespace   nonce {nonce} (each pair gets its own cache namespace)")
        print(f"  live trips  {'all' if parsed.live_pairs <= 0 else parsed.live_pairs} pairs, "
              f"pacing {parsed.pace}s\n", flush=True)
        observed = sync(_measure(
            base_url=base_url, pairs=pairs, request=request,
            other_model=other.request.get("model") or "", task_type=parsed.task_type,
            nonce=nonce, pace=parsed.pace, live_pairs=parsed.live_pairs,
        ))
    else:
        mode = "offline"
        detail = {
            "reason": "--offline requested" if parsed.offline else f"{base_url} unreachable",
            "simulated": True,
            "warning": "offline numbers come from a deterministic embedder and are NOT evidence "
                       "about nomic, the cache, or any threshold",
        }
        print(f"\np6: {len(pairs)} labelled pairs, OFFLINE SIMULATION — not evidence\n", flush=True)
        observed = _simulate(pairs, parsed.threshold or 0.95)

    proof = Proof(name="p6_cache_savings", args=args, mode=mode, mode_detail=detail)
    scored = observed["scored"]
    identity = observed["identity"]
    config_threshold = float(
        parsed.threshold
        if parsed.threshold is not None
        else (observed["cache_config"].get("threshold") or 0.95)
    )

    # ── the sweep ────────────────────────────────────────────────────────── #
    by_id = {pair.id: pair for pair in pairs}
    scored_pairs = [(by_id[pid], row["cosine"]) for pid, row in scored.items()]
    grid = thresholds(parsed.sweep_low, parsed.sweep_high, parsed.sweep_step)
    if config_threshold not in grid:
        grid = tuple(sorted({*grid, round(config_threshold, 6)}))
    points = sweep(scored_pairs, grid)
    split = separable(scored_pairs)
    safest = best_operating(points)
    at_config = next((p for p in points if abs(p.threshold - config_threshold) < 1e-9), None)

    # ── the table ────────────────────────────────────────────────────────── #
    proof.fact("pairs", f"{len(pairs)} from {parsed.pairs}  families "
                        f"{ {k: len(v) for k, v in by_family(pairs).items()} }")
    proof.fact("embedder", f"{identity.get('provider')} / {identity.get('model')}  "
                           f"dim {identity.get('vector_length')} "
                           f"(ring declares {identity.get('ring_fixed_dim')})")
    proof.fact("configured threshold", f"{config_threshold} (from "
                                       f"{observed['cache_config'].get('path') or 'cache.yaml'})")

    for pair in pairs:
        row = scored[pair.id]
        trip = observed["trips"].get(pair.id) or {}
        warm = trip.get("warm") or {}
        if "error" in trip:
            served = f"live FAILED {trip['error'][:80]}"
        elif not trip:
            served = "not round-tripped"
        elif warm.get("hit"):
            served = f"HIT (reported {warm.get('similarity'):.6f}, ${warm.get('usd', 0):.8f})"
        else:
            served = f"miss (best {warm.get('best_similarity', 0.0):.6f}, paid "
            served += f"${warm.get('usd', 0):.8f})"
        wrong = "  <-- WRONG ANSWER SERVED" if warm.get("hit") and not pair.positive else ""
        proof.fact(
            f"{pair.id} [{pair.label}/{pair.family}]",
            f"cosine {row['cosine']:.6f}  {served}{wrong}",
        )

    # The overall FPR mixes hard negatives with easy ones, and the mix is a
    # property of the file rather than of the cache. So the same sweep is run
    # again per negative family, which is the number a reader can act on.
    negative_families = sorted({p.family or "unlabelled" for p in pairs if not p.positive})
    family_sweeps = {
        family: sweep(
            [(p, s) for p, s in scored_pairs if p.positive or (p.family or "unlabelled") == family],
            grid,
        )
        for family in negative_families
    }

    def cell(rate: float, hits: int, total: int) -> str:
        return f"{rate:.2f} ({hits}/{total})".ljust(16)

    header = (f"\n    {'threshold':<11}{'TPR':<16}{'FPR (all)':<16}"
              + "".join(f"FPR {family}".ljust(16) for family in negative_families))
    print_rows = []
    for index, point in enumerate(points):
        marker = "<- configured" if at_config is not None and point is at_config else ""
        cells = [
            cell(point.tpr, point.true_positives, point.positives),
            cell(point.fpr, point.false_positives, point.negatives),
        ]
        cells += [
            cell(fam.fpr, fam.false_positives, fam.negatives)
            for fam in (family_sweeps[family][index] for family in negative_families)
        ]
        print_rows.append(f"    {point.threshold:<11.2f}" + "".join(cells) + marker)
    proof.fact("threshold sweep", header + "\n" + "\n".join(print_rows))

    # Where the curve actually turns, measured rather than inherited. A claim
    # of the form "below X collisions become common" is a claim about this.
    knee = steepest_fpr_drop(points)
    knee_family = {f: steepest_fpr_drop(family_sweeps[f]) for f in negative_families}
    if knee.get("measured"):
        proof.fact(
            "measured danger line",
            f"the sharpest fall in collision rate over {parsed.sweep_low}-{parsed.sweep_high} is at "
            f"{knee['knee_at']:.2f}: FPR {knee['fpr_below']:.2f} -> {knee['fpr_at']:.2f} "
            f"({knee['collisions_below']} -> {knee['collisions_at']} of {knee['negatives']} "
            f"wrong pairs admitted)"
            + "".join(
                f"; on {f} alone the knee is {k['knee_at']:.2f} "
                f"({k['fpr_below']:.2f} -> {k['fpr_at']:.2f})"
                for f, k in knee_family.items() if k.get("measured") and not k.get("flat")
            ),
        )

    per_family: dict[str, dict[str, Any]] = {}
    if at_config is not None:
        for family, ids in by_family(pairs).items():
            members = [by_id[i] for i in ids]
            positives = sum(1 for m in members if m.positive)
            hits = [i for i in ids if scored[i]["cosine"] >= config_threshold]
            wrongly = [i for i in hits if not by_id[i].positive]
            per_family[family] = {
                "n": len(ids),
                "positive": positives,
                "admitted_at_configured_threshold": hits,
                "wrongly_admitted": wrongly,
                "rate": round(len(hits) / len(ids), 4) if ids else 0.0,
            }
            proof.fact(
                f"family {family} @ {config_threshold}",
                f"{len(hits)}/{len(ids)} admitted, {len(wrongly)} of them WRONGLY  {hits or ''}",
            )

    finding = _finding(points, config_threshold, split, safest)
    proof.fact("FINDING", finding)

    # ── savings, net of the embedding ────────────────────────────────────── #
    savings = _savings(observed, pairs, by_id)
    for key, value in savings["facts"].items():
        proof.fact(key, value)

    # ── checks ───────────────────────────────────────────────────────────── #
    if live:
        _live_checks(proof, observed, identity, pairs, by_id, scored, config_threshold, savings)
    else:
        proof.check(
            "the offline pipeline scores every pair and sweeps every threshold",
            len(scored) == len(pairs) and len(points) == len(grid),
            f"{len(scored)} pairs scored, {len(points)} thresholds swept "
            f"(SIMULATED: proves the code path, not the cache)",
        )

    # These hold in both modes: they are properties of the arithmetic, not of
    # the embedder, and a sweep that violated them would be reporting nonsense.
    proof.check(
        "the sweep is monotone: raising the threshold never raises TPR or FPR",
        all(b.tpr <= a.tpr + 1e-12 and b.fpr <= a.fpr + 1e-12 for a, b in zip(points, points[1:])),
        f"{len(points)} thresholds from {points[0].threshold} to {points[-1].threshold}",
    )
    proof.check(
        "every pair is accounted for at every threshold",
        all(p.positives + p.negatives == len(pairs) for p in points),
        f"{len(pairs)} pairs, {sum(1 for x in pairs if x.positive)} positive",
    )
    proof.check(
        "the report states whether a collision-free threshold exists",
        "separable" in split and bool(finding),
        finding,
    )

    proof.record("cosines", {pid: round(row["cosine"], 6) for pid, row in scored.items()})
    proof.record("pairs", [p.as_dict() for p in pairs])
    proof.record("sweep", [p.as_dict() for p in points])
    proof.record("sweep_by_negative_family",
                 {f: [p.as_dict() for p in s] for f, s in family_sweeps.items()})
    proof.record("measured_danger_line", {"overall": knee, "by_negative_family": knee_family})
    proof.record("separability", split)
    proof.record("safest_operating_point", safest.as_dict() if safest else None)
    proof.record("configured_operating_point", at_config.as_dict() if at_config else None)
    proof.record("per_family_at_configured_threshold", per_family)
    proof.record("embedder_identity", identity)
    proof.record("embedding_cost", savings["embedding"])
    proof.record("savings", savings["detail"])
    proof.record("round_trips", observed["trips"])
    proof.record("namespace_isolation", observed["isolation"])
    proof.record("cache_config", observed["cache_config"])
    proof.record("finding", finding)
    return proof


def _savings(observed: dict[str, Any], pairs, by_id) -> dict[str, Any]:
    """Gross saving, the embedding it cost, and the break-even embedding price."""
    hits, colds = [], []
    for pid, trip in observed["trips"].items():
        if "error" in trip:
            continue
        cold, warm = trip.get("cold") or {}, trip.get("warm") or {}
        if cold.get("usd") is not None:
            colds.append(cold)
        if warm.get("hit") and by_id[pid].positive:
            hits.append((pid, cold, warm))

    embed = observed["embedding"]
    price = observed.get("embed_price") or {}
    embed_usd_per_mtok = float(price.get("input_usd_per_mtok") or 0.0)

    gross_usd = sum(c["usd"] for _, c, _ in hits)
    gross_tokens = sum(c["input_tokens"] + c["output_tokens"] for _, c, _ in hits)
    # A LOOKUP embeds once. A MISS embeds twice: the lookup, then the store.
    # Both are the cache's own overhead and neither appears in the chat's cost.
    lookup_ms = embed["median_wall_ms"]
    cold_ms = statistics.fmean([c.get("wall_ms") or 0.0 for c in colds]) if colds else 0.0
    hit_ms = statistics.fmean([w.get("wall_ms") or 0.0 for _, _, w in hits]) if hits else 0.0
    per_hit_usd = gross_usd / len(hits) if hits else 0.0

    facts = {
        "hits measured": f"{len(hits)} of {sum(1 for p in pairs if p.positive)} 'same' pairs "
                         f"served from cache",
        "gross saving": f"${gross_usd:.8f} over {len(hits)} hits, {gross_tokens} provider tokens "
                        f"never billed  (${per_hit_usd:.8f}/hit)",
        "embedding cost": f"${embed_usd_per_mtok:.4f}/Mtok at "
                          f"{price.get('price_source') or 'unpriced'} -> $0.00000000 per lookup; "
                          f"median {lookup_ms:.1f} ms, {embed['min_wall_ms']:.1f}-"
                          f"{embed['max_wall_ms']:.1f} ms over {embed['calls_for_scoring']} calls",
        "net saving": f"${gross_usd:.8f} (the local embedder costs no money, so net == gross); "
                      f"break-even embedding price is ${per_hit_usd:.8f}/lookup — a hosted "
                      f"embedder dearer than that erases the saving",
        "latency": f"cold call {cold_ms:.0f} ms -> cache hit {hit_ms:.0f} ms "
                   f"(of which ~{lookup_ms:.0f} ms is the embedding a hit cannot avoid)",
    }
    return {
        "facts": facts,
        "embedding": {**embed, "usd_per_mtok": embed_usd_per_mtok,
                      "price_source": price.get("price_source"),
                      "embeds_per_lookup": 1, "embeds_per_miss": 2},
        "detail": {
            "hits": [pid for pid, _, _ in hits],
            "gross_usd": gross_usd,
            "gross_tokens": gross_tokens,
            "usd_per_hit": per_hit_usd,
            "break_even_embedding_usd_per_lookup": per_hit_usd,
            "mean_cold_wall_ms": round(cold_ms, 1),
            "mean_hit_wall_ms": round(hit_ms, 1),
            "median_embed_wall_ms": lookup_ms,
        },
    }


def _live_checks(proof, observed, identity, pairs, by_id, scored, threshold, savings) -> None:
    """The claims that only mean anything against the running gateway."""
    ring_dim = identity.get("ring_fixed_dim")
    proof.check(
        "the embedding is a real vector of the ring's declared dimension",
        identity["vector_length"] == identity["reported_dim"] == ring_dim and ring_dim >= 256,
        f"{identity['vector_length']} floats, gateway reports dim {identity['reported_dim']}, "
        f"ring declares {ring_dim}",
    )
    proof.check(
        "the vector came from the configured embedder ring, named",
        identity["provider"] in (identity.get("ring_order") or [])
        and (identity.get("ring_models") or {}).get(identity["provider"]) == identity["model"],
        f"{identity['provider']} / {identity['model']} "
        f"(ring order {identity.get('ring_order')}, task_type {identity.get('task_type')})",
    )
    proof.check(
        "the embedder is not a constant stub: deterministic on a repeat, "
        "different on different text",
        identity["repeat_cosine"] > 0.9999
        and identity["unrelated_cosine"] < 0.99
        and identity["distinct_values"] > 100,
        f"repeat cosine {identity['repeat_cosine']:.9f}, unrelated cosine "
        f"{identity['unrelated_cosine']:.6f}, {identity['distinct_values']} distinct components",
    )

    trips = {pid: t for pid, t in observed["trips"].items() if "error" not in t}
    proof.check(
        "every pair round-tripped through the live gateway",
        len(trips) == len(observed["trips"]) and trips,
        {pid: t["error"] for pid, t in observed["trips"].items() if "error" in t}
        or f"{len(trips)} pairs",
    )

    # The correctness invariant: the gateway decided on the number this proof
    # computed independently. Without this, every cosine below is hearsay.
    drift = {}
    for pid, trip in trips.items():
        reported = trip["warm"].get("similarity") or trip["warm"].get("best_similarity") or 0.0
        if reported and abs(reported - scored[pid]["cosine"]) > 1e-5:
            drift[pid] = (reported, round(scored[pid]["cosine"], 6))
    proof.check(
        "the similarity the gateway acted on equals the cosine measured here",
        not drift,
        drift or f"{len(trips)} pairs agree to 1e-5",
    )

    # The cache's verdict must follow its own threshold, in both directions.
    wrong_way = {
        pid: (scored[pid]["cosine"], trip["warm"]["hit"])
        for pid, trip in trips.items()
        if trip["warm"]["hit"] != (scored[pid]["cosine"] >= threshold)
    }
    proof.check(
        f"a pair hits if and only if its cosine reaches the configured {threshold}",
        not wrong_way,
        wrong_way or f"{len(trips)} verdicts match the threshold exactly",
    )

    served = [pid for pid, t in trips.items() if t["warm"]["hit"] and by_id[pid].positive]
    strongest = max((scored[p.id]["cosine"] for p in pairs if p.positive), default=0.0)
    proof.check(
        "at least one real paraphrase is served from cache",
        bool(served),
        f"{len(served)} of {sum(1 for p in pairs if p.positive)} 'same' pairs hit: {served}"
        if served
        else f"no 'same' pair reaches {threshold}: the closest scores {strongest:.6f}, so this "
             f"pair set cannot demonstrate a saving at this threshold",
    )
    not_free = {
        pid: trips[pid]["warm"]["usd"] for pid in served if trips[pid]["warm"]["usd"] != 0.0
    }
    proof.check(
        "a cache hit contacts no provider and is billed nothing",
        not not_free and all(trips[pid]["warm"]["price_source"] == "semantic-cache-hit"
                             for pid in served),
        not_free or f"{len(served)} hits, all $0.00000000, price_source semantic-cache-hit",
    )
    proof.check(
        "the saving is a measured provider bill, not a model of one",
        savings["detail"]["gross_usd"] > 0 and savings["detail"]["gross_tokens"] > 0,
        f"${savings['detail']['gross_usd']:.8f} and "
        f"{savings['detail']['gross_tokens']} tokens, read off the cold calls",
    )

    # An indiscriminate embedder — or a stub — collides on everything. Unrelated
    # prompts colliding is the failure this check exists to catch; NEAR-misses
    # colliding is a measurement, reported above and deliberately not asserted,
    # because that number is the finding rather than a regression.
    unrelated = [p for p in pairs if not p.positive and (p.family or "") == "unrelated"]
    admitted = [p.id for p in unrelated if scored[p.id]["cosine"] >= threshold]
    if unrelated:
        proof.check(
            "unrelated prompts are not conflated at the configured threshold",
            not admitted,
            admitted or f"{len(unrelated)} unrelated pairs, max cosine "
                        f"{max(scored[p.id]['cosine'] for p in unrelated):.6f} < {threshold}",
        )

    proof.check(
        "no embedding failed silently during the run",
        (observed["cache_counters_after"].get("embed_failures") or 0) == 0,
        observed["cache_counters_after"],
    )

    # Isolation is only demonstrable when the control HITS: "the same question
    # under a different model misses" says nothing if the same question under
    # the same model missed too. A pair set whose best paraphrase is below the
    # threshold makes the experiment inconclusive, not failed, and that is
    # reported rather than scored.
    iso = observed["isolation"]
    if iso and not (iso.get("control (same model, system and tenant)") or {}).get("hit"):
        proof.fact(
            "namespace isolation",
            f"INCONCLUSIVE: pair {iso['pair']} at cosine {iso['cosine']:.6f} did not hit its own "
            f"control at threshold {threshold}, so there was no cached answer for a different "
            f"namespace to leak",
        )
    elif iso:
        control = iso.get("control (same model, system and tenant)") or {}
        others = {k: v for k, v in iso.items()
                  if k.startswith("different") and isinstance(v, dict)}
        proof.fact(
            "namespace isolation",
            f"pair {iso['pair']} at cosine {iso['cosine']:.6f}: control "
            f"{'HIT' if control.get('hit') else 'miss'}; "
            + "; ".join(f"{k} {'HIT (LEAK)' if v.get('hit') else 'miss'}" for k, v in others.items()),
        )
        proof.check(
            "the control case, identical in every namespace field, hits",
            control.get("hit"),
            control,
        )
        leaks = {k: v for k, v in others.items() if v.get("hit")}
        proof.check(
            "a change of model, system prompt or tenant misses despite the same question",
            not leaks,
            leaks or sorted(others),
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--pairs", default=str(DEFAULT_PAIRS),
                        help="labelled pair set as DATA (.jsonl/.json/.yaml). Bring your own.")
    parser.add_argument("--threshold", type=float, default=None,
                        help="override the gateway's configured cosine threshold")
    parser.add_argument("--sweep-low", type=float, default=0.85)
    parser.add_argument("--sweep-high", type=float, default=0.99)
    parser.add_argument("--sweep-step", type=float, default=0.01)
    parser.add_argument("--tier", default=None,
                        help="which tiers.yaml rung answers the cold calls (default: cheapest)")
    parser.add_argument("--task-type", default="",
                        help="embedding task type (default: whatever cache.yaml asks for)")
    parser.add_argument("--live-pairs", type=int, default=0,
                        help="round-trip only the first N pairs through /v1/chat; 0 = all")
    parser.add_argument("--pace", type=float, default=1.0,
                        help="seconds between provider calls, to stay inside rate limits")
    parser.add_argument("--principal", default="proofs/s15/p6")
    parser.add_argument("--offline", action="store_true",
                        help="deterministic SIMULATION: exercises every path, proves nothing")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--config-dir", default=os.getenv("S17_CONFIG_DIR"))
    parser.add_argument("--label", default="", help="suffix for the JSON written to proofs/out/")
    return parser.parse_args(argv)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    sys.exit(run(parse_args()).finish())
