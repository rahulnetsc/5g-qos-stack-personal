"""Scenario-level workload transforms: committed load, and survival time.

Both exist because the same knob was wanted in four places and built in one
(`committed_mult` lived only in `sim/scenarios/g12.py`; `survival_time_ms`
existed on `FlowConfig` and was never non-zero anywhere). Both DERIVE the
set of flows they act on from the flows themselves rather than listing it,
and both refuse a traffic kind they cannot account for instead of silently
skipping it -- an enumerator that reports "scaled" over a set it cannot
reach is this project's most-repeated defect.

Must not import the driver or any scheduler.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Iterable

from scheduler.flow import FlowConfig

#: Which `traffic_params` key carries the OFFERED BYTES for each traffic kind
#: (`sim/traffic.py::TrafficModel._gen`'s own dispatch). A rate key scales the
#: same way a size key does -- both are "bytes per unit time" once the period
#: is held fixed, which is what `committed_mult` means.
#: `sim/tests/test_workload.py` asserts this covers every kind `_gen`
#: dispatches on, so a new kind fails loudly here rather than being skipped.
LOAD_PARAMS: dict[str, tuple[str, ...]] = {
    "deterministic": ("bytes_per_period",),
    "poisson": ("rate_bps",),
    "adaptive": ("initial_rate_bps", "max_rate_bps", "min_rate_bps"),
    "video_frame": ("avg_bytes",),
    "xr_video": ("avg_bytes",),
    "periodic_control": ("bytes_per_period",),
    "condition_monitor": ("bytes_per_period",),
    "aperiodic_event": ("burst_bytes",),
    "machine_vision": ("burst_bytes",),
    "none": (),
}

#: Which key carries the TRANSFER INTERVAL, where the kind has one. A kind
#: absent here is aperiodic: it has no "anticipated message", so TS 22.261's
#: survival-time definition does not apply and the value stays 0.
INTERVAL_PARAMS: dict[str, str] = {
    "deterministic": "period_ms",
    "video_frame": "period_ms",
    "xr_video": "period_ms",
    "periodic_control": "period_ms",
    "condition_monitor": "period_ms",
}

#: The contract fields that must move WITH the offered load: scaling demand
#: without scaling the guarantee would silently change what is being promised,
#: which is the confound `sim/scenarios/g12.py`'s own `committed_mult` avoids
#: by scaling `video_tier` (bytes) and `gfbr_bps` together.
CONTRACT_FIELDS: tuple[str, ...] = ("gfbr_bps", "mfbr_bps", "pbr_bps")

#: Committed traffic is GBR and Delay -- the classes the network promised
#: something about. PF is best-effort filler and belongs to `load_mult`.
#: DERIVED from `flow_class`, never a list of QFIs.
COMMITTED_CLASSES: frozenset[str] = frozenset({"GBR", "Delay"})


def _scaled_params(kind: str, params: dict[str, Any], mult: float) -> dict[str, Any]:
    if kind not in LOAD_PARAMS:
        raise ValueError(
            f"traffic kind {kind!r} has no entry in workload.LOAD_PARAMS -- add "
            f"the key that carries its offered bytes rather than letting it "
            f"pass through unscaled")
    out = dict(params)
    for key in LOAD_PARAMS[kind]:
        if key in out:
            out[key] = type(out[key])(out[key] * mult) if isinstance(out[key], int) \
                else out[key] * mult
    # `periodic_control`'s optional per-stream form carries its own sizes.
    streams = out.get("streams")
    if streams:
        out["streams"] = [{**s, "bytes": type(s["bytes"])(s["bytes"] * mult)}
                          if "bytes" in s else dict(s) for s in streams]
    return out


def scale_committed_load(scenario, mult: float):
    """Scale every COMMITTED flow's offered load and its contract together.

    This is the load axis an operator experiences: more work promised to the
    cell. `load_mult` is a different knob -- it scales the best-effort filler
    only -- and the two are deliberately separable.

    `mult == 1.0` returns the scenario unchanged (identity, not a rebuild), so
    a campaign can pass the axis unconditionally.
    """
    if mult == 1.0:
        return scenario
    if mult <= 0.0:
        raise ValueError(f"committed_mult must be > 0 (got {mult})")
    flows = []
    for f in scenario.flows:
        if f.flow_class not in COMMITTED_CLASSES or getattr(f, "is_srb", False):
            flows.append(f)
            continue
        changes: dict[str, Any] = {
            "traffic_params": _scaled_params(f.traffic_kind, f.traffic_params or {}, mult)
        }
        for field in CONTRACT_FIELDS:
            value = getattr(f, field, 0.0)
            if value:
                changes[field] = value * mult
        flows.append(dataclasses.replace(f, **changes))
    # The name carries the axis value: two points that differ only in
    # committed_mult must not share a scenario name, or a ledger keyed on it
    # (regime_sweep.RunLedger) silently merges them.
    name = f"{scenario.name}_cm{mult:g}"
    return dataclasses.replace(scenario, flows=flows, name=name)


def survival_time_ms_for(flow: FlowConfig, intervals: float) -> float:
    """TS 22.261 V17.11.0 §3.1: *"survival time: the time that an application
    consuming a communication service may continue without an anticipated
    message."*

    For periodic deterministic traffic the anticipated messages arrive one
    transfer interval apart, so the time an application may continue without
    `n` of them IS `n x transfer_interval` -- the value is DERIVED from the
    flow's own configured period, not assigned per 5QI from memory.

    `intervals` (how many consecutive messages the application tolerates) is
    the CHOSEN part and is swept by the campaign. **TS 22.104's per-use-case
    survival-time table would replace it and could not be obtained on this
    machine** (ETSI returns 403; no copy in `~/Documents/.../3gpp/`), and
    reconstructing that table from memory is precisely what CLAUDE.md's
    spec-table rule forbids -- so it is requested, like the SRB capture,
    rather than invented.

    Aperiodic kinds have no anticipated message and get 0.0.
    """
    if intervals < 0:
        raise ValueError(f"intervals must be >= 0 (got {intervals})")
    key = INTERVAL_PARAMS.get(flow.traffic_kind)
    if key is None:
        return 0.0
    params = flow.traffic_params or {}
    streams = params.get("streams")
    if streams:
        # The flow's own shortest anticipated-message interval bounds it.
        periods = [float(s["period_ms"]) for s in streams if "period_ms" in s]
        return intervals * min(periods) if periods else 0.0
    if key not in params:
        return 0.0
    return intervals * float(params[key])


def with_survival_times(scenario, intervals: float = 1.0):
    """Populate `survival_time_ms` on every flow that has a transfer interval.

    Opt-in at the scenario level rather than resolved in
    `FlowConfig.__post_init__`: the regression corpus stores
    `FlowRecord.survival_time_ms`, so defaulting it non-zero would move 462
    baseline values as a side effect of a scoring change. Campaigns that want
    TS 22.261's availability threshold call this; everything else is
    untouched.
    """
    return dataclasses.replace(scenario, flows=[
        dataclasses.replace(f, survival_time_ms=survival_time_ms_for(f, intervals))
        for f in scenario.flows
    ])
