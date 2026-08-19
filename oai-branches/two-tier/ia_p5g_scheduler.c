/*
 * ia_p5g_scheduler.c
 * IA-P5G Two-Tier QoS-Aware MAC Scheduler — STUB (Checkpoint 1)
 *
 * All functions are present with correct signatures and compile cleanly.
 * Stub behaviour at Checkpoint 1:
 *   - ia_p5g_dl_metric()  returns 0.0 → pf_dl() qsort falls back to
 *     has_gbr / pdb_ms ordering (safe, no behavioural regression)
 *   - ia_p5g_ul_metric()  returns 0.0 → same fallback in pf_ul()
 *   - ia_p5g_get_lcid_budget() returns -1 → nr_generate_dlsch_pdu()
 *     uses default RLC pull (no capping, no regression)
 *   - ia_p5g_compute_lcp_budget() sets all budgets to -1 (same effect)
 *   - All VQ update / drain functions are no-ops
 *   - Tier-1 thread sleeps and logs without solving LP
 *
 * Fill-in order after Checkpoint 1 compiles:
 *   Checkpoint 2: ia_p5g_update_vq_dl/ul + ia_p5g_dl/ul_metric
 *   Checkpoint 3: ia_p5g_compute_lcp_budget + ia_p5g_get_lcid_budget
 *                 + ia_p5g_drain_vq_dl/ul
 *   Checkpoint 4: ia_p5g_tier1_thread (LP solve)
 *
 * Save to: openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.c
 */

/* ── OAI headers — must precede ia_p5g_scheduler.h so that the full
 *    struct definitions are in scope when the forward declarations
 *    in the header are resolved.                                          */
#include "mac_proto.h"
#include "common/utils/LOG/log.h"
#include "common/utils/assertions.h"

/* ── Our own header (after OAI headers) ─────────────────────────────── */
#include "ia_p5g_scheduler.h"

/* ── Standard library ────────────────────────────────────────────────── */
#include <stdlib.h>
#include <stdio.h>    /* snprintf() for [P5G-UL-RANK] telemetry */
#include <string.h>
#include <unistd.h>   /* usleep() */
#include <stdatomic.h>
#include <math.h>     /* fabs() */
#include <time.h>     /* clock_gettime() */

/* ── GLPK: LP solver backing the Tier-1 SCA loop (Checkpoint 4).
 *    Link with -lglpk, requires libglpk-dev on the target host.          */
#include <glpk.h>

/* =========================================================================
 * BUILD-TIME CONFIGURATION (hoisted)
 *
 * These macros MUST be defined before their first textual use. The startup
 * banner in ia_p5g_state_init() (below) prints the active build config, and
 * the C preprocessor has no forward declarations -- definitions that sit
 * next to their algorithmic use sites further down the file are not visible
 * at line ~193. (Build failure 2026-08-04: "IA_P5G_VQ_UL_CATCHUP_N
 * undeclared in ia_p5g_state_init".)
 *
 * The full rationale for each value is retained as a block comment at its
 * ALGORITHMIC use site; only the definitions are hoisted here. Override any
 * of them at build time with -D<NAME>=<value>.
 *
 *   IA_P5G_TIER1_PERIOD_S          Tier-1 LP window (s). See ~"tier1_period".
 *   IA_P5G_VQ_UL_CATCHUP_N         UL vq catch-up horizon, in WINDOWS.
 *                                  N=1 reproduces the original clamp.
 *   IA_P5G_UL_FLOOR_ENABLE         Tier-1 UL service-interval floor on/off.
 *                                  A/B arm: -DIA_P5G_UL_FLOOR_ENABLE=0
 *                                  restores pre-floor behaviour exactly.
 *   IA_P5G_UL_FLOOR_PDB_DIV        theta = min-PDB / this.
 *   IA_P5G_UL_FLOOR_ALIVE_MS       delivery-history arming window (ms).
 *   IA_P5G_UL_FLOOR_MIN_SLOTS      theta lower bound, in slots.
 *   IA_P5G_UL_FLOOR_FRUITLESS_MAX  fruitless fires before evidence-based
 *                                  disarm.
 * ========================================================================= */
#ifndef IA_P5G_TIER1_PERIOD_S
#define IA_P5G_TIER1_PERIOD_S          0.1f
#endif
#ifndef IA_P5G_VQ_UL_CATCHUP_N
#define IA_P5G_VQ_UL_CATCHUP_N         5
#endif
#ifndef IA_P5G_UL_FLOOR_ENABLE
#define IA_P5G_UL_FLOOR_ENABLE         1
#endif
#ifndef IA_P5G_UL_FLOOR_PDB_DIV
#define IA_P5G_UL_FLOOR_PDB_DIV        8     /* theta = min-PDB / this      */
#endif
#ifndef IA_P5G_UL_FLOOR_ALIVE_MS
#define IA_P5G_UL_FLOOR_ALIVE_MS       2000  /* delivery-history arm window */
#endif
#ifndef IA_P5G_UL_FLOOR_MIN_SLOTS
#define IA_P5G_UL_FLOOR_MIN_SLOTS      2     /* theta lower bound, in slots */
#endif
#ifndef IA_P5G_UL_FLOOR_FRUITLESS_MAX
#define IA_P5G_UL_FLOOR_FRUITLESS_MAX  3     /* fruitless fires -> forgive  */
#endif
/* ── [FIX A] Fruitless counter: decay + backoff instead of a hard latch.  */
#ifndef IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX
#define IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX 4  /* theta << n, capped (16x)  */
#endif
#ifndef IA_P5G_UL_FLOOR_FRUITLESS_DECAY_MS
#define IA_P5G_UL_FLOOR_FRUITLESS_DECAY_MS 500 /* forgive one step per this */
#endif
/* ── [FIX B] Adequacy trigger: fire for a CANDIDATE stuck on crumb grants. */
#ifndef IA_P5G_UL_FLOOR_ADQ_ENABLE
#define IA_P5G_UL_FLOOR_ADQ_ENABLE     1
#endif
#ifndef IA_P5G_UL_FLOOR_ADQ_CRUMB_RUN
#define IA_P5G_UL_FLOOR_ADQ_CRUMB_RUN  8     /* consecutive min_rb grants   */
#endif

/* =========================================================================
 * [IA-P5G] LOG POLICY — normal telemetry vs exceptions
 *
 * Two classes of output, deliberately separated so a production or A/B run
 * can be built with -DIA_P5G_TELEMETRY=0 and still surface every fault.
 *
 *   NORMAL (per-slot / per-UE / per-window trace)
 *       IA_P5G_LOG_I / IA_P5G_LOG_I_UL / IA_P5G_LOG_I_DL / IA_P5G_LOG_D
 *       -> emitted only when IA_P5G_TELEMETRY (resp. its UL/DL bit) != 0.
 *
 *   EXCEPTION (fault detected, invariant violated, degraded operation)
 *       IA_P5G_LOG_EXC_W / IA_P5G_LOG_EXC_E
 *       -> ALWAYS emitted, independent of IA_P5G_TELEMETRY. These are the
 *          lines the hardware A/B depends on: [P5G-UL-STALL], the two
 *          [P5G-UL-FLOOR] lines, GLPK solve failures, nr_find_nb_rb
 *          rbSize=0, UE_sched overflow and NULL-state aborts.
 *
 *   LIFECYCLE (one-shot: startup banner, LP thread start/exit, teardown)
 *       IA_P5G_LOG_LIFE
 *       -> ALWAYS emitted by default. These are not per-slot, and the
 *          startup banner is the provenance record of which build config
 *          produced a run; silencing it in exactly the runs that set
 *          TELEMETRY=0 would remove the only in-log evidence of which A/B
 *          arm was active. Override with -DIA_P5G_LOG_LIFECYCLE=0 for a
 *          fully silent build.
 *
 * Verify the policy holds after any edit:
 *     grep -n "IA_P5G_LOG_EXC\|IA_P5G_LOG_LIFE" ia_p5g_scheduler.c
 * lists exactly what survives -DIA_P5G_TELEMETRY=0.
 *
 * The gates are `if (constant)` rather than #if so the compiler still parses
 * and format-checks every call -- a -Wformat bug in a compiled-out path is
 * still caught -- and then folds the dead branch away at -O2. Each macro is
 * do{...}while(0), so it stays a single statement and remains safe after a
 * brace-less `if` or before an `else`.
 *
 *   bit 0 (1) = UL telemetry   bit 1 (2) = DL telemetry
 * Default 0 = silent. 1 = UL-only, 2 = DL-only, 3 = both.
 * ========================================================================= */
#ifndef IA_P5G_TELEMETRY
#define IA_P5G_TELEMETRY  3
#endif
#define IA_P5G_TELEMETRY_UL  (IA_P5G_TELEMETRY & 1)
#define IA_P5G_TELEMETRY_DL  (IA_P5G_TELEMETRY & 2)

#ifndef IA_P5G_LOG_LIFECYCLE
#define IA_P5G_LOG_LIFECYCLE 1
#endif

#define IA_P5G_LOG_I(comp, ...) \
    do { if (IA_P5G_TELEMETRY)     LOG_I(comp, __VA_ARGS__); } while (0)
#define IA_P5G_LOG_I_UL(comp, ...) \
    do { if (IA_P5G_TELEMETRY_UL)  LOG_I(comp, __VA_ARGS__); } while (0)
#define IA_P5G_LOG_I_DL(comp, ...) \
    do { if (IA_P5G_TELEMETRY_DL)  LOG_I(comp, __VA_ARGS__); } while (0)
#define IA_P5G_LOG_D(comp, ...) \
    do { if (IA_P5G_TELEMETRY)     LOG_D(comp, __VA_ARGS__); } while (0)
#define IA_P5G_LOG_LIFE(comp, ...) \
    do { if (IA_P5G_LOG_LIFECYCLE) LOG_I(comp, __VA_ARGS__); } while (0)

/* Exceptions — never gated, by design. */
#define IA_P5G_LOG_EXC_W(comp, ...) LOG_W(comp, __VA_ARGS__)
#define IA_P5G_LOG_EXC_E(comp, ...) LOG_E(comp, __VA_ARGS__)

/* =========================================================================
 * Crash context tracker
 * Set before every major operation. Visible in gdb backtraces on SIGSEGV.
 * ========================================================================= */
volatile const char *ia_p5g_crash_ctx = "ia_p5g: not yet entered";

/* =========================================================================
 * Internal helper: compute absolute slot number (frame × spf + slot).
 * Used by VQ update and windowed ceiling functions.
 * ========================================================================= */
static inline uint32_t abs_slot(const gNB_MAC_INST *mac,
                                 frame_t frame, slot_t slot)
{
    return (uint32_t)frame
           * (uint32_t)mac->frame_structure.numb_slots_frame
           + (uint32_t)slot;
}

/* =========================================================================
 * RNTI index helpers
 * Must be called under state->state_lock.
 * ========================================================================= */

int ia_p5g_rnti_get_or_alloc(ia_p5g_state_t *state, uint16_t rnti)
{
    ia_p5g_crash_ctx = "ia_p5g_rnti_get_or_alloc";
    AssertFatal(state != NULL, "[IA-P5G] rnti_get_or_alloc: state is NULL\n");

    /* Fast path: RNTI already in table */
    for (int i = 0; i < IA_P5G_MAX_UE; i++) {
        if (state->rnti_map[i].active && state->rnti_map[i].rnti == rnti)
            return i;
    }

    /* Slow path: allocate a new slot */
    for (int i = 0; i < IA_P5G_MAX_UE; i++) {
        if (!state->rnti_map[i].active) {
            state->rnti_map[i].rnti   = rnti;
            state->rnti_map[i].active = true;
            /* Zero all per-UE state for this slot */
            memset(state->vq_dl[i],           0,  sizeof(state->vq_dl[i]));
            memset(state->vq_ul[i],           0,  sizeof(state->vq_ul[i]));
            memset(state->ul_demand_smooth[i],0,  sizeof(state->ul_demand_smooth[i]));
            memset(state->dl_arrived_hist[i], 0,  sizeof(state->dl_arrived_hist[i]));
            memset(state->dl_delivered_hist[i],0, sizeof(state->dl_delivered_hist[i]));
            memset(state->ul_arrived_hist[i], 0,  sizeof(state->ul_arrived_hist[i]));
            memset(state->ul_delivered_hist[i],0, sizeof(state->ul_delivered_hist[i]));
            /* -1 means "no budget set" — nr_generate_dlsch_pdu uses default pull */
            memset(state->dl_lcid_budget[i], 0xFF, sizeof(state->dl_lcid_budget[i]));

            IA_P5G_LOG_LIFE(NR_MAC, "[IA-P5G] Allocated slot %d for RNTI %04x\n", i, rnti);
            return i;
        }
    }

    IA_P5G_LOG_EXC_E(NR_MAC,
          "[IA-P5G] RNTI table full (>%d UEs). Cannot add RNTI %04x. "
          "Increase IA_P5G_MAX_UE.\n",
          IA_P5G_MAX_UE, rnti);
    return -1;
}

void ia_p5g_rnti_release(ia_p5g_state_t *state, uint16_t rnti)
{
    ia_p5g_crash_ctx = "ia_p5g_rnti_release";
    if (!state) return;

    for (int i = 0; i < IA_P5G_MAX_UE; i++) {
        if (state->rnti_map[i].active && state->rnti_map[i].rnti == rnti) {
            state->rnti_map[i].active = false;
            state->rnti_map[i].rnti  = 0;
            memset(state->vq_dl[i],            0, sizeof(state->vq_dl[i]));
            memset(state->vq_ul[i],            0, sizeof(state->vq_ul[i]));
            memset(state->ul_demand_smooth[i], 0, sizeof(state->ul_demand_smooth[i]));
            memset(state->dl_arrived_hist[i],  0, sizeof(state->dl_arrived_hist[i]));
            memset(state->dl_delivered_hist[i],0, sizeof(state->dl_delivered_hist[i]));
            memset(state->ul_arrived_hist[i],  0, sizeof(state->ul_arrived_hist[i]));
            memset(state->ul_delivered_hist[i],0, sizeof(state->ul_delivered_hist[i]));
            memset(state->dl_lcid_budget[i], 0xFF, sizeof(state->dl_lcid_budget[i]));
            IA_P5G_LOG_LIFE(NR_MAC, "[IA-P5G] Released slot %d for RNTI %04x\n", i, rnti);
            return;
        }
    }
    IA_P5G_LOG_EXC_W(NR_MAC, "[IA-P5G] rnti_release: RNTI %04x not found in table\n", rnti);
}

/* ─────────────────────────────────────────────────────────────────────────
 * Fast lock-free RNTI lookup — hot path (read-only scan).
 * Safe because rnti/active fields are written atomically (single words)
 * and RNTI allocations are rare (only at UE attach/detach).
 * Returns slot index 0..IA_P5G_MAX_UE-1, or -1 if not found.
 * ───────────────────────────────────────────────────────────────────────── */
static int ia_p5g_rnti_lookup(const ia_p5g_state_t *state, uint16_t rnti)
{
    for (int i = 0; i < IA_P5G_MAX_UE; i++) {
        if (state->rnti_map[i].active && state->rnti_map[i].rnti == rnti)
            return i;
    }
    return -1;
}

/* =========================================================================
 * Lifecycle
 * ========================================================================= */

ia_p5g_state_t *ia_p5g_state_init(gNB_MAC_INST *mac)
{
    ia_p5g_crash_ctx = "ia_p5g_state_init";
    AssertFatal(mac != NULL, "[IA-P5G] state_init: mac pointer is NULL\n");

    ia_p5g_state_t *state = calloc(1, sizeof(*state));
    if (!state) {
        IA_P5G_LOG_EXC_E(NR_MAC, "[IA-P5G] Failed to allocate scheduler state (%zu bytes)\n",
              sizeof(*state));
        return NULL;
    }

    /* calloc zeroed everything:
     *   vq_dl, vq_ul                → 0.0
     *   *_hist arrays               → 0
     *   rnti_map[].active           → false
     *   window_start_abs_slot       → 0
     *   t1out.last_solve_abs_slot   → 0  (Tier-2 detects "not yet solved")
     */

    pthread_mutex_init(&state->state_lock, NULL);
    state->mac            = mac;
    /* [IA-P5G] Tier-1 outer-loop (LP re-solve) period. Shortened from 1.0s
     * to 0.1s so per-flow rate targets track demand an order of magnitude
     * faster -- the window math (target_W_bits = r_bps * tier1_period_s and
     * the vq backlog ceiling) all scale off this one value, so shrinking it
     * shrinks the target window consistently; no other change needed. The
     * LP solve itself is cheap (tens of us for ~16 flows), so a 10x higher
     * solve rate is negligible CPU. Override at build with
     * -DIA_P5G_TIER1_PERIOD_S=<seconds> for finer/coarser tracking.
     * [DEFINITION HOISTED to the BUILD-TIME CONFIGURATION block near the
     *  top of this file -- it is used by the startup banner above.]      */
    state->tier1_period_s = IA_P5G_TIER1_PERIOD_S;
    atomic_store(&state->stop, false);

    /* Mark all DL LCID budgets as "no budget" (-1 = 0xFFFFFFFF per int) */
    for (int i = 0; i < IA_P5G_MAX_UE; i++)
        memset(state->dl_lcid_budget[i], 0xFF, sizeof(state->dl_lcid_budget[i]));

    IA_P5G_LOG_LIFE(NR_MAC,
          "[IA-P5G] TwoTier scheduler state initialised. "
          "MAX_UE=%d  LCID=%d  LCG=%d  tier1_period=%.0fms  "
          "vq_ul_catchup_N=%d  ul_floor=%s(v3, theta=pdb/%d, alive=%dms, "
          "fruitless_max=%d/shift<=%d/decay=%dms, adq=%s(run>=%d), "
          "grant=full-avail)\n",
          IA_P5G_MAX_UE, IA_P5G_MAX_LCID, IA_P5G_MAX_LCG,
          state->tier1_period_s * 1000.0f,
          IA_P5G_VQ_UL_CATCHUP_N,
          IA_P5G_UL_FLOOR_ENABLE ? "ON" : "OFF",
          IA_P5G_UL_FLOOR_PDB_DIV, IA_P5G_UL_FLOOR_ALIVE_MS,
          IA_P5G_UL_FLOOR_FRUITLESS_MAX,
          IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX,
          IA_P5G_UL_FLOOR_FRUITLESS_DECAY_MS,
          IA_P5G_UL_FLOOR_ADQ_ENABLE ? "ON" : "OFF",
          IA_P5G_UL_FLOOR_ADQ_CRUMB_RUN);

    return state;
}

void ia_p5g_state_destroy(ia_p5g_state_t *state)
{
    ia_p5g_crash_ctx = "ia_p5g_state_destroy";
    if (!state) return;

    atomic_store(&state->stop, true);
    /* Join Tier-1 thread if it was started */
    pthread_join(state->tier1_thread, NULL);
    pthread_mutex_destroy(&state->state_lock);
    free(state);
    IA_P5G_LOG_LIFE(NR_MAC, "[IA-P5G] Scheduler state destroyed\n");
}

/* =========================================================================
 * Tier-1 LP pthread — full implementation (Checkpoint 4)
 *
 * Algorithm: Sequential Convex Approximation (SCA) wrapping GLPK's simplex
 * solver, per handoff §7.2 — DAMPED variant (alpha=0.2). The undamped
 * (alpha=1.0) version was independently verified to enter a stable 2-cycle
 * under moderate/severe overload (objective alternates between two LP
 * vertices forever, ~20% true-utility loss, exact wrong answer depending on
 * max_iters parity — confirmed by direct binary test, not just theory).
 * Damping was swept against a robust reference solver across 200 randomized
 * factory scenarios (load_factor 0.3–4.0): 200/200 feasible, max objective
 * gap 0.57%, solve time <11ms for 16–51 flows. alpha=0.2/max_iters=150/
 * tol=1e-6 are the resulting defaults — see VERIFICATION_REPORT.md.
 *
 *   maximize   Σ_i w_i·log(r_i+ε)  −  Σ_i p·s_i
 *   subject to Σ_{i∈DL} r_i/se_i ≤ cap_dl,  Σ_{i∈UL} r_i/se_i ≤ cap_ul
 *              r_i + s_i ≥ gfbr_i   (GBR flows; s_i≥0 soft slack)
 *              0 ≤ r_i ≤ demand_i
 * ========================================================================= */

#define IA_P5G_TIER1_EPSILON           1.0
#define IA_P5G_TIER1_GBR_PENALTY       1.0e3
#define IA_P5G_TIER1_SCA_ALPHA         0.2
#define IA_P5G_TIER1_SCA_MAXITERS      150
#define IA_P5G_TIER1_SCA_TOL           1e-6
#define IA_P5G_TIER1_DELAY_PRIO_THRESH 20      /* 3GPP priority ≤ this → "Delay" class */
#define IA_P5G_TIER1_DELAY_WEIGHT      5.0
#define IA_P5G_TIER1_PF_WEIGHT         1.0
#define IA_P5G_TIER1_OVERHEAD_FACTOR   0.80f   /* PDCCH/DMRS/CSI-RS, per §7.3 */
#define IA_P5G_TIER1_MAX_FLOWS         (IA_P5G_MAX_UE * (IA_P5G_MAX_LCID + IA_P5G_MAX_LCG))

/* UL demand EWMA smoothing factor (Change 1).
 * Time constant τ = -1/ln(1-α) ≈ 2.8 s at α=0.3.
 * Chosen to be longer than the TCP congestion-control oscillation period
 * (~1–2 s at the radio RTT of this deployment) so the smoothed estimate
 * tracks the true average offered load rather than each burst/trough.
 * DL does not need smoothing (reads gNB RLC buffer directly — exact).    */
#define IA_P5G_UL_DEMAND_ALPHA         0.3

/* ── BLER-discounted spectral efficiency (Change 3) ──────────────────────
 * effective_se = se(MCS) × max(1 − BLER, FLOOR)
 *
 * When HARQ retransmissions are frequent (high BLER), the scheduler is
 * granting PRBs that do not translate to net delivered bits — a large
 * fraction of each grant is consumed by retransmissions.  By discounting
 * SE by (1 − BLER), Tier-1 sees a realistic capacity and targets a rate
 * that the channel can actually sustain, rather than the theoretical peak.
 *
 * The floor prevents SE collapsing to zero for a UE in a deep fade.
 * At floor=0.20: a UE at 80% BLER still gets 20% of nominal SE — enough
 * for Tier-1 to allocate something and allow the OLLA to recover.
 * The floor also avoids log-utility singularity (log(0)) in the LP.
 *
 * This is the correct fix for OLLA overshoot under channel variability:
 * it creates a second, faster feedback path above the OLLA (which itself
 * updates every BLER_UPDATE_FRAME=10 frames with a BLER_FILTER=0.9 EWMA).
 * The two loops operate at different timescales and do not interfere.    */
#define IA_P5G_UL_BLER_DISCOUNT_FLOOR  0.20
#define IA_P5G_DL_BLER_DISCOUNT_FLOOR  0.20

/* ── PHR-based UL PRB ceiling (Change 4) ─────────────────────────────────
 * N_max_prb = 10^(ph0/10)  where ph0 = power headroom at 1 PRB (dB).
 *
 * UL transmit power scales as P_N = P_1PRB + 10·log10(N_PRB).
 * When P_N exceeds PCMAX, the UE clips its power spectral density,
 * reducing per-PRB SNR and causing BLER spikes.  N_max_prb is the hard
 * physical ceiling: beyond it the UE cannot maintain the required SNR.
 *
 * The 0.85 safety factor (≈ −0.7 dB) absorbs TPC correction lag: the
 * open-loop power target adapts on a slower timescale than the Tier-1
 * solve, so a small margin prevents brief over-allocation.
 *
 * Operational behaviour:
 *   - UE with ph0 >> 0 (good link, bench test): N_max >> n_rb_ul, cap
 *     never binds.  No change in scheduler behaviour.
 *   - UE at cell edge (ph0 = 5 dB): N_max ≈ 3 PRBs.  Tier-1 correctly
 *     caps demand to ~3-PRB worth of rate, preventing power-limited BLER.
 *   - Factory UGV behind a metal shelf (ph0 transient dip): cap activates
 *     for 1–2 Tier-1 cycles then releases as the UE emerges.
 *
 * Only applied when ph0 > 0 (valid PHR CE received).  At startup before
 * the first PHR, ph0 == 0 and the cap is disabled (sentinel value).      */
#define IA_P5G_PHR_PRB_SAFETY_FACTOR   0.8

/* ── [IA-P5G] Composite-metric deadline-urgency constants ────────────────
 * Mirrors two_tier.py: delay_urgency_weight = 4.0, delay_exponent = 2.0.
 *   urgency  = min(1, hol/pdb)^EXP           (grant-age proxy for hol on UL)
 *   coef     = (Σ Q_g + W·urgency·max_q) × SE
 * A recently-served flow has rem_pdb≈pdb → urgency≈0, so the bonus is earned
 * by lateness, not by class: satisfied GBR/bulk flows get ≈0 boost, while a
 * flow approaching its PDB (control-loop or a starved bulk flow after its
 * own PDB elapses) escalates smoothly above bulk backlog.                 */
#define IA_P5G_DELAY_URGENCY_W         4.0f
#define IA_P5G_DELAY_EXP               2.0f

/* ── [IA-P5G] Refined deadline-urgency: priority-weighted scalarization +
 *    barrier functional form ──────────────────────────────────────────────
 *
 * Two changes vs the plain urgency^EXP form above, motivated by mixed
 * hard-deadline + throughput traffic (e.g. a UGV carrying 5QI 3 C2 control
 * alongside 5QI 4 video on the same UE):
 *
 * 1. PRIORITY-WEIGHTED SCALARIZATION. The UE's scalar urgency is no longer
 *    the raw max over its flows' urgency ratios — that discards WHICH flow
 *    is late, so a video flow approaching its (loose) PDB would boost the UE
 *    as much as a C2 flow approaching its (tight) PDB. Instead we take the
 *    max of (urgency_f · prio_weight_f), where prio_weight_f is larger for
 *    stronger 3GPP priority (lower priority number). A late C2 flow now
 *    dominates a late video flow at equal urgency ratio.
 *
 *    prio_weight = IA_P5G_URG_PRIO_W_MIN + (1 - IA_P5G_URG_PRIO_W_MIN) *
 *                  (1 - (priority-1)/(IA_P5G_URG_PRIO_MAX-1)),  clamped [wmin,1]
 *    so priority 1 → weight 1.0, priority 90 → weight ~wmin. Bounded in
 *    [wmin,1] so it can bias but never zero out or explode a flow's urgency.
 *
 * 2. BARRIER on the delay term. urgency^EXP is bounded (caps at 1 when a
 *    flow is at/over PDB), so a flow one slot from its deadline and a flow
 *    already far past it contribute the same. For a hard-deadline C2 loop we
 *    want missing the deadline to dominate the metric, not merely maximize a
 *    bounded term. Replace urgency^EXP with a rational barrier that diverges
 *    as urgency → 1:
 *        Phi(u) = u^EXP / (1 - min(u, U_CAP) + EPS)
 *    Below ~0.8 this closely tracks the old u^EXP (soft, earned-by-lateness).
 *    Approaching 1 it grows sharply; U_CAP bounds the divergence so a single
 *    over-deadline flow cannot overflow the metric or NaN it. Rate-deficit
 *    (base_q) stays additive and linear — the barrier is on the DEADLINE
 *    side only, never on the throughput side.                              */
#define IA_P5G_URG_PRIO_W_MIN          0.35f  /* weight floor for weakest prio */
#define IA_P5G_URG_PRIO_MAX            90.0f  /* 3GPP priority normaliser      */
#define IA_P5G_URG_BARRIER_CAP         0.97f  /* clamp on u inside barrier     */
#define IA_P5G_URG_BARRIER_EPS         0.03f  /* denom floor (1-CAP == EPS)    */

/* ── [IA-P5G] GBR-met urgency release ────────────────────────────────────
 * Stress-test finding: under heavy oversubscription the barrier over-served
 * a protected flow — it escalated on GRANT-AGE (how far behind the flow is
 * on scheduling) regardless of whether its GBR was already met, so a flow
 * with a large backlog kept its urgency pinned high and monopolized the
 * link until its ENTIRE backlog drained, starving the competing flow. That
 * inverts correct QoS: the guarantee is the target, not backlog exhaustion.
 *
 * Fix: scale the deadline-urgency contribution by a GBR-deficit factor
 *   delta = min(1, deficit / window)      (0 = guarantee met, 1 = far behind)
 * so urgency escalates a flow toward its GUARANTEE, then releases: once the
 * GBR deficit collapses, the barrier contribution collapses with it and any
 * remaining backlog competes on normal PF (base_q) terms instead of the
 * deadline barrier. Continuous (no hard switch → no oscillation). A NON-GBR
 * flow has no deficit/window, so delta defaults to 1 (urgency ungated) —
 * its deadline still matters, it simply has no GBR to "meet and release".
 * URG_GBR_FLOOR keeps a small residual urgency even at deficit 0 so a met
 * GBR flow doesn't drop to pure-PF instantly at the boundary.             */
#define IA_P5G_URG_GBR_FLOOR           0.15f  /* residual urgency at deficit 0 */

/* ── [IA-P5G] Per-slot scheduler telemetry gate ──────────────────────────
 * Bitmask controlling the always-on [P5G-UL*]/[P5G-DL*] diagnostic log
 * lines. These fire per-scheduled-UE-per-slot at LOG_I, so at ~hundreds of
 * slots/s they dominate the log and cost cycles -- keep them ON for targeted,
 * short (single-phase, ideally well under a minute) diagnostic captures.
 * For anything longer -- multi-phase soak tests, calibration sweeps, full
 * matrix runs -- turn this OFF (0) and rely on [P5G-UL-SUMMARY] instead
 * (see IA_P5G_SUMMARY_PERIOD_SLOTS below), which is always-on, independent
 * of this gate, and ~1000x lower volume while still catching grant
 * cadence, retransmission activity, HARQ exhaustion, and BSR/deficit
 * trends across the whole run. A 113MB/725k-line log from a single long
 * run is what motivated adding that path -- don't reproduce it.
 *   bit 0 (1) = UL telemetry   bit 1 (2) = DL telemetry
 * Default 3 = both on. Set to 0 to silence all, 1 for UL-only, 2 for DL-only.
 * Compile-time so it costs nothing when disabled (branches fold away).    */
/* NOTE: the definitions themselves are HOISTED to the LOG POLICY block
 * near the top of this file -- they are needed by IA_P5G_LOG_* at line
 * ~150, far above this point, and the preprocessor has no forward
 * declarations. Only the rationale stays here, at the use site.        */

/* ── [IA-P5G] UL virtual-queue catch-up horizon N ────────────────────────
 * The vq_ul ceiling clamp bounds a flow's virtual queue at
 *     min(backlog_bits, N * target_W_bits) - delivered_W_bits
 * where target_W_bits = r_bps * tier1_period_s is ONE Tier-1 window's worth
 * of guaranteed bits. N is that bound expressed in WINDOWS (not slots): it
 * is how many windows of unmet GBR a starved flow may accumulate before the
 * ceiling caps its debt.
 *
 * WHY THIS EXISTS: with N=1 (the original hard cap) a flow starved for many
 * windows looks identical to one starved for a single window — the virtual
 * queue saturates at one window's entitlement and loses the ability to
 * express "this flow has waited far longer." MaxWeight/Lyapunov fairness
 * depends on the queue growing with wait time until it overtakes a
 * high-SE competitor; capping at one window erased that, collapsing the
 * ranking to the SE tiebreak (i.e. greedy spectral-efficiency = baseline
 * behaviour) and serializing contending flows. Raising N restores the
 * accumulation: a longer-starved flow builds a proportionally larger queue
 * and wins on the metric, concurrently, with no external PRB reservation.
 *
 * TRADEOFF being swept: too small (N~1) → serialization returns; too large
 * (N -> infinity) → a flow whose SOURCE went idle for many windows can
 * accumulate a large phantom debt and then monopolize on return to "catch
 * up" a rate commitment it did not need while idle. The right N is the
 * smallest value that gives concurrency under saturated contention without
 * admitting that idle-then-return burst. Swept manually (5, 10, ...) like
 * IA_P5G_TELEMETRY. N=1 reproduces the original clamp exactly.
 *
 * UNIT REMINDER: N counts WINDOWS. One window = tier1_period_s = 0.1s =
 * ~200 slots at numerology 1. So N=5 ≈ 0.5s of catch-up debt, N=10 ≈ 1s.
 * [DEFINITION HOISTED to the BUILD-TIME CONFIGURATION block near the top
 *  of this file -- it is used by the startup banner in state_init().]   */

/* ── [IA-P5G FLOOR] Tier-1 UL service-interval floor ─────────────────────
 * Motivation (UGV MECSTACKQOS run, 2026-08-04): the 5QI-1 MAVLink probe
 * (400pps x 200B = 0.64 Mbps against a 5 Mbps GBR) suffered intermittent
 * 300-400ms TOTAL UL service gaps (recv-CSV service curve: blackout ->
 * ~0.44 Mbps SR-crumb trickle -> blackout -> burst drain), p99 exploding
 * 37ms -> 743ms vs the reservation baseline. Root cause class: the derived
 * buffer estimate B = estimated_ul_buffer - sched_ul_bytes reads 0 while
 * the UE holds data (BSR desync / SR loss on real RF), and the candidacy
 * skip below removes the UE from scheduling entirely -- downstream
 * machinery (deficit targets, CTRL class, FIX-2 GBR PRB reserve) never
 * sees it. The d639 vq patch does not protect small flows because the UL
 * vq ceiling is clamped by the same decaying estimate.
 *
 * The floor is a TIME-domain guarantee (the min_rb mechanisms are
 * PRB-space or request-response): if a GBR-configured UE that shows life
 * on any durable signal (visible BSR, frozen per-LCG deficit, or virtual
 * queue) has delivered NO UL bytes for theta = PDB/IA_P5G_UL_FLOOR_PDB_DIV,
 * it is force-included as if an SR had arrived (do_sched semantics): the
 * existing paths then give it either one min_rb CTRL grant (carries a
 * fresh BSR -> estimate resync) or a deficit-sized DATA grant if
 * ul_has_unfulfilled_gbr. gNB-initiated: needs no SR over PUCCH and no
 * trustworthy buffer estimate.
 *
 * Forgiveness becomes EVIDENCE-BASED: after IA_P5G_UL_FLOOR_FRUITLESS_MAX
 * consecutive floor grants that moved no bytes, the flow is judged idle,
 * its stale deficit is cleared and the floor disarms until backlog
 * reappears -- replacing the old time-based deficit zeroing, which forgave
 * the entitlement exactly when the flow was starved longest.
 *
 * ── v2 REVISION (2026-08-04, post-review) ───────────────────────────────
 * v1 detected and fired correctly but did not RESCUE: it OR-ed the fire
 * into do_sched, which routed the UE to the control-plane class, whose
 * grant is a hardcoded min_rb crumb (~120B at fallback MCS -- it cannot
 * carry even one 200B MAVLink packet, and leaves no padding room for the
 * BSR MAC CE the crumb was supposed to deliver). The measured trickle
 * phase of the UGV stall is itself ~275 consecutive min_rb crumbs that
 * failed to restore service, bounding per-crumb resync probability at
 * <= 0.01 -- so v1's rescue had already been empirically falsified by the
 * run that motivated it. The DATA-class route v1's comment claimed as the
 * alternative is unreachable in this fault: ul_has_unfulfilled_gbr is set
 * only inside a loop gated on the visible per-LCG estimate, i.e. on the
 * very signal the fault destroys.
 *
 * v2 fixes the rescue, not the detection:
 *  (a) ARMING is delivery-history based (floor_rx_lastseen movement within
 *      FLOOR_ALIVE_MS), not estimate-derived. v1 armed on
 *      (B>0 || deficit>0 || vq>0): B==0 defines the fault, vq_ul stops
 *      updating when the per-LCG estimate reads 0, so v1 armed ONLY via
 *      the frozen deficit -- which is non-zero here only because GBR is
 *      provisioned 7.8x above the offered rate. Right-size the GBR and v1
 *      silently stops arming. Delivery history is independent of every
 *      signal the fault corrupts.
 *  (b) The fired grant is the FULL post-power-adaptation allocation, not
 *      a crumb: the floor keeps the DATA class (see sched_inactive below),
 *      and the second loop bypasses nr_find_nb_rb for a floor grant --
 *      because nr_find_nb_rb sizes to B_eff, and every input to B_eff
 *      (ul_total_target_bytes, B, gbr_bytes_slot) is estimate-derived and
 *      reads 0 in this fault. rbSize = available_rb makes the floor path
 *      independent of the demand estimate entirely, which is the point.
 *      available_rb is already bounded by the FIX-2 GBR reserve, so other
 *      GBR UEs keep their floor. Over-allocation is safe AND useful here:
 *      surplus room triggers a padding BSR (38.321), which is the resync
 *      the crumb could not deliver.
 *  (c) Power safety is preserved by RUNNING the adaptation rather than by
 *      hand-sizing the grant: nr_ue_max_mcs_min_rb() decrements Rb (then
 *      MCS) until required tx power fits the reported headroom, so a large
 *      allocation is self-correcting on PSD. Its `tbs` argument is dead
 *      (immediately overwritten from *Rb), so it needs no trustworthy
 *      demand estimate either. v1 could not benefit: that call is gated on
 *      `B > 0`, false by definition of the fault. v2 relaxes the gate to
 *      (B > 0 || floor_fire), keeping the (pcmax||ph) half -- if the UE
 *      never reported headroom, ph_limit==0 would drive Rb down to min_rb
 *      and regenerate the crumb from the other direction.
 *  (d) theta defaults to PDB/8 (was /4): the offline sweep showed theta
 *      dominates arming/grant details (p99 202 -> 47ms), and PDB/4 leaves
 *      most of the available benefit unclaimed.
 *
 * Healthy runs are unaffected either way (floor never fires; verify
 * floor_fires=0 in [P5G-UL-SUMMARY]). A/B: -DIA_P5G_UL_FLOOR_ENABLE=0
 * restores pre-floor behaviour exactly.
 *
 * KNOWN RESIDUAL: after a long silence the PHR is stale, so (c) clamps to
 * the last reported headroom, not present conditions. A moved UGV may
 * still over-power and fail to decode; retx then adapts MCS down. Strictly
 * better than no adaptation, but log-worthy in the A/B.
 *
 * [DEFINITIONS HOISTED to the BUILD-TIME CONFIGURATION block near the top
 *  of this file -- they are used by the startup banner in state_init().
 *  Defaults: ENABLE=1, PDB_DIV=8, ALIVE_MS=2000, MIN_SLOTS=2,
 *  FRUITLESS_MAX=3.]                                                    */

/* ── [IA-P5G] Lightweight ALWAYS-ON periodic UL summary ──────────────────
 * The [P5G-UL*] telemetry above (gated by IA_P5G_TELEMETRY) fires at LOG_I
 * on every scheduled UE, every slot -- at ~hundreds of slots/s that's the
 * right resolution for a short, targeted capture, but it does not scale to
 * a multi-minute soak test: a ~500s multi-phase run at that rate produced
 * a 113MB / 725k-line log that couldn't even be uploaded for analysis,
 * while the one thing actually needed from it (RLF/retransmission/deficit
 * TRENDS across the whole run) got buried under the volume.
 *
 * Fix: accumulate the essential per-UE UL counters every slot (cheap --
 * a few integer adds, no string formatting, no I/O on the hot path) and
 * flush ONE condensed line per active UE every IA_P5G_SUMMARY_PERIOD_SLOTS
 * slots instead of a line (or several) per grant. This path is deliberately
 * NOT gated by IA_P5G_TELEMETRY and is safe to leave on for long runs --
 * it's what you grep instead of the firehose. Recommended usage: set
 * IA_P5G_TELEMETRY=0 for any run longer than a minute or so and rely on
 * [P5G-UL-SUMMARY] for trend visibility; leave IA_P5G_TELEMETRY=3 only for
 * short, targeted single-phase captures where the per-slot detail earns
 * its cost.
 *
 * Deliberately self-contained: keyed by RNTI via a simple linear-scan
 * table private to this translation unit (no changes to NR_UE_sched_ctrl_t
 * or ia_p5g_state_t, no locking -- pf_ul() is called from the single MAC
 * scheduler thread, same assumption the surrounding deficit/BSR code
 * already makes). IA_P5G_MAX_UE-sized, same bound as the existing
 * ia_p5g_rnti_map table, so it never grows unbounded.               */
#ifndef IA_P5G_SUMMARY_PERIOD_SLOTS
/* Period measured in CALLS to ia_p5g_pf_ul(), i.e. UL scheduling
 * opportunities -- NOT absolute slot numbers. (It was absolute slots,
 * which aliased against the TDD grid and never fired; see the bugfix
 * note at the flush call site.) At numerology 1 with 2 full-UL slots
 * per 2.5ms period there are ~800 UL slots/s, so 800 ≈ one flush per
 * second. Lower it for finer time resolution on short captures.     */
#define IA_P5G_SUMMARY_PERIOD_SLOTS   200
#endif

typedef struct {
    uint16_t rnti;
    bool     used;
    uint32_t grants;             /* successful new-data UL grants since last flush */
    uint64_t bytes;               /* tb_size bytes granted since last flush */
    uint64_t rbsize_sum;          /* Σ rbSize, for mean */
    uint16_t rbsize_max;
    uint32_t retx_grants;         /* successful retransmission grants since last flush */
    uint32_t retx_blocked;        /* allocate_ul_retransmission() returned false */
    uint32_t harq_exhausted;      /* slots UE had no free UL HARQ process at all */
    int      last_bsr;            /* max estimated_ul_buffer_per_lcg across LCGs, most recent slot */
    int32_t  last_deficit_sum;    /* Σ ul_lcg_deficit_bytes across LCGs, most recent slot */

    /* ── [IA-P5G STALL PROBE] Per-exit-path skip accounting ──────────────
     * Motivation: a real, captured failure where a UE sat with
     * est_buf frozen at 8,705,864 bytes for 527 consecutive samples
     * (~2.5s) while receiving ZERO grants. B was huge, avail_rb was
     * plentiful, yet ia_p5g_pf_ul() issued nothing -- meaning the UE was
     * taken out by one of the early `continue` statements before ever
     * reaching allocation. The existing telemetry could not distinguish
     * "not scheduled because nothing to send" from "not scheduled
     * because <specific gate> rejected it", because a skipped UE emits
     * no line at all -- absence of evidence, with ~10 candidate causes.
     *
     * These counters make each exit path individually observable, so
     * "no grant" becomes a NAMED cause. Counted per UE, per window,
     * flushed alongside the rest of [P5G-UL-SUMMARY].
     *
     * Cost: one increment on a path already taking a branch. No
     * formatting, no I/O on the hot path. Safe to leave on.          */
    uint32_t skip_inactive;       /* !nr_mac_ue_is_active()                      */
    uint32_t skip_no_rem_ues;     /* remainUEs budget exhausted across all beams  */
    uint32_t skip_dci_beam;       /* DCI-slot beam allocation failed              */
    uint32_t skip_data_beam;      /* data-slot beam allocation failed             */
    uint32_t skip_empty;          /* B==0 && !do_sched  (genuinely nothing to send) */
    uint32_t skip_transm_intr;    /* transm_interrupt timer active  <-- STALL SUSPECT */
    uint32_t skip_l2_beam;        /* 2nd loop: beam realloc failed                */
    uint32_t skip_l2_budget;      /* 2nd loop: remainUEs==0 or n_rb_sched<min_rb  */
    uint32_t skip_l2_cce;         /* 2nd loop: no free CCE for UL DCI             */
    uint32_t skip_l2_no_prb;      /* 2nd loop: no contiguous PRB run >= min_rb    */
    uint32_t skip_l2_rbzero;      /* 2nd loop: nr_find_nb_rb returned rbSize==0   */
    uint32_t reached_alloc;       /* made it all the way to a real grant attempt  */

    /* ── [IA-P5G FLOOR] Persistent per-RNTI floor state. NOT reset by the
     * window flush (only floor_fires_w is windowed telemetry). Absolute
     * slot numbers wrap at 1024 frames; diffs are computed modulo that. */
    uint64_t floor_rx_lastseen;   /* Σ UL data-LCID mac bytes at last visit       */
    uint32_t floor_last_move_slot;/* abs slot when delivery last observed/attempted */
    uint32_t floor_alive_slot;    /* abs slot of last REAL delivery (arming basis) */
    bool     floor_alive_valid;   /* floor_alive_slot has been set at least once   */
    uint32_t floor_silence_snap;  /* computed silence (slots) at last visit, telemetry */
    uint32_t floor_fruitless;     /* consecutive floor grants that moved no bytes */
    uint32_t floor_fruitless_slot;/* [FIX A] abs slot of last fruitless change    */
    uint32_t floor_adq_slot;      /* [FIX B] abs slot of last adequacy fire       */
    uint32_t floor_adq_backoff;   /* [FIX B] adequacy retry backoff, decays       */
    uint32_t floor_crumb_run;     /* [FIX B] consecutive min_rb grants (trickle)  */
    uint32_t floor_adq_fires_w;   /* [FIX B] adequacy-path fires this window      */
    uint32_t floor_fires_w;       /* floor force-includes this window (telemetry) */
    bool     floor_disarmed;      /* [FIX A] deficit forgiven + in deep backoff;
                                   * NOT a stop -- probing continues at the
                                   * backed-off cadence and the flag clears
                                   * when the fruitless counter decays to 0. */
} ia_p5g_ul_summary_t;

static ia_p5g_ul_summary_t ia_p5g_ul_summary_table[IA_P5G_MAX_UE];

/* Linear-scan get-or-allocate by RNTI. IA_P5G_MAX_UE is small (same bound
 * used for the RNTI-index table above), so O(n) here is negligible next to
 * everything else pf_ul() already does per slot.                        */
static ia_p5g_ul_summary_t *ia_p5g_ul_summary_get(uint16_t rnti)
{
    int free_slot = -1;
    for (int i = 0; i < IA_P5G_MAX_UE; i++) {
        if (ia_p5g_ul_summary_table[i].used && ia_p5g_ul_summary_table[i].rnti == rnti)
            return &ia_p5g_ul_summary_table[i];
        if (free_slot < 0 && !ia_p5g_ul_summary_table[i].used)
            free_slot = i;
    }
    if (free_slot < 0) {
        /* Table full -- should not happen, IA_P5G_MAX_UE bounds real UE
         * count the same way the RNTI-index table does. Fail soft: drop
         * this UE's summary rather than crash a scheduling hot path.    */
        return NULL;
    }
    ia_p5g_ul_summary_table[free_slot].used = true;
    ia_p5g_ul_summary_table[free_slot].rnti = rnti;
    return &ia_p5g_ul_summary_table[free_slot];
}

/* Flush + reset every active UE's accumulated window. Always LOG_I --
 * this is the intended default-on visibility path, independent of
 * IA_P5G_TELEMETRY. One line per UE that had any activity in the window;
 * silent for idle/absent UEs so this stays cheap even with IA_P5G_MAX_UE
 * mostly unused.                                                        */
/* [IA-P5G STALL PROBE] terse accessor for the skip counters. Null-safe:
 * if the summary table is full the increment is simply dropped rather
 * than crashing a scheduling hot path. */
#define IA_P5G_SKIP(rnti_, field_) \
    do { ia_p5g_ul_summary_t *_sk = ia_p5g_ul_summary_get(rnti_); \
         if (_sk) _sk->field_++; } while (0)

static void ia_p5g_ul_summary_flush(int frame, int slot)
{
    for (int i = 0; i < IA_P5G_MAX_UE; i++) {
        ia_p5g_ul_summary_t *s = &ia_p5g_ul_summary_table[i];
        if (!s->used) continue;
        if (s->grants == 0 && s->retx_grants == 0 && s->retx_blocked == 0 && s->harq_exhausted == 0) {
            /* Nothing happened for this UE this window -- still worth one
             * cheap line if it's carrying a nonzero deficit/BSR (a UE that
             * is silent AND backlogged is exactly the stall pattern worth
             * catching), otherwise skip entirely to keep idle UEs free.  */
            if (s->last_bsr <= 0 && s->last_deficit_sum <= 0)
                continue;
        }
        double mean_rbsize = s->grants > 0 ? (double)s->rbsize_sum / (double)s->grants : 0.0;
        if (IA_P5G_TELEMETRY) {
            LOG_I(NR_MAC,
                  "[P5G-UL-SUMMARY][%4d.%2d][UE %04x] grants=%u bytes=%lu mean_rbSize=%.1f max_rbSize=%u "
                  "retx_ok=%u retx_blocked=%u harq_exhausted=%u last_bsr=%d last_deficit=%d "
                  "floor_fires=%u floor_adq=%u floor_sil=%u crumb_run=%u "
                  "fruitless=%u floor_disarmed=%d\n",
                  frame, slot, s->rnti, s->grants, (unsigned long)s->bytes, mean_rbsize, s->rbsize_max,
                  s->retx_grants, s->retx_blocked, s->harq_exhausted, s->last_bsr, s->last_deficit_sum,
                  s->floor_fires_w, s->floor_adq_fires_w, s->floor_silence_snap,
                  s->floor_crumb_run, s->floor_fruitless, (int)s->floor_disarmed);
        }

        /* ── [IA-P5G STALL PROBE] one line per UE per window, naming every
         * reason the UE was skipped. Read this together with last_bsr
         * above: a large last_bsr with grants=0 and a large count in ONE
         * of these buckets is the stall, and that bucket names it.     */
        if (IA_P5G_TELEMETRY) {
        LOG_I(NR_MAC,
              "[P5G-UL-SKIP][%4d.%2d][UE %04x] reached_alloc=%u | inactive=%u no_rem_ues=%u "
              "dci_beam=%u data_beam=%u empty=%u transm_intr=%u | l2_beam=%u l2_budget=%u "
              "l2_cce=%u l2_no_prb=%u l2_rbzero=%u\n",
              frame, slot, s->rnti, s->reached_alloc,
              s->skip_inactive, s->skip_no_rem_ues, s->skip_dci_beam, s->skip_data_beam,
              s->skip_empty, s->skip_transm_intr,
              s->skip_l2_beam, s->skip_l2_budget, s->skip_l2_cce, s->skip_l2_no_prb,
              s->skip_l2_rbzero);
        }
        /* Explicit verdict when the pathological state is present: real
         * backlog, zero grants. Printed at WARNING so it stands out in a
         * long capture without having to diff counters by eye.          */
        if (s->grants == 0 && s->retx_grants == 0 && s->last_bsr > 10000) {
            const char *why = "UNKNOWN (UE never even entered the UL loop this window)";
            uint32_t top = 0;
            if (s->skip_transm_intr  > top) { top = s->skip_transm_intr;  why = "transm_interrupt timer ACTIVE"; }
            if (s->skip_empty        > top) { top = s->skip_empty;        why = "B==0 despite BSR (sched_ul_bytes desync?)"; }
            if (s->harq_exhausted    > top) { top = s->harq_exhausted;    why = "no free UL HARQ process"; }
            if (s->skip_no_rem_ues   > top) { top = s->skip_no_rem_ues;   why = "remainUEs budget exhausted"; }
            if (s->skip_dci_beam     > top) { top = s->skip_dci_beam;     why = "DCI beam allocation failed"; }
            if (s->skip_data_beam    > top) { top = s->skip_data_beam;    why = "data beam allocation failed"; }
            if (s->skip_l2_cce       > top) { top = s->skip_l2_cce;       why = "no free CCE for UL DCI"; }
            if (s->skip_l2_budget    > top) { top = s->skip_l2_budget;    why = "2nd-loop budget/min_rb"; }
            if (s->skip_l2_no_prb    > top) { top = s->skip_l2_no_prb;    why = "no contiguous PRB run >= min_rb"; }
            if (s->skip_l2_rbzero    > top) { top = s->skip_l2_rbzero;    why = "nr_find_nb_rb returned rbSize=0"; }
            if (s->skip_inactive     > top) { top = s->skip_inactive;     why = "UE marked inactive"; }
            IA_P5G_LOG_EXC_W(NR_MAC,
                  "[P5G-UL-STALL][%4d.%2d][UE %04x] BACKLOGGED BUT UNSERVED: bsr=%d bytes pending, "
                  "0 grants this window. Dominant cause: %s (%u hits)\n",
                  frame, slot, s->rnti, s->last_bsr, why, top);
        }

        s->grants = 0;
        s->bytes = 0;
        s->rbsize_sum = 0;
        s->rbsize_max = 0;
        s->retx_grants = 0;
        s->retx_blocked = 0;
        s->harq_exhausted = 0;
        s->skip_inactive = 0;
        s->skip_no_rem_ues = 0;
        s->skip_dci_beam = 0;
        s->skip_data_beam = 0;
        s->skip_empty = 0;
        s->skip_transm_intr = 0;
        s->skip_l2_beam = 0;
        s->skip_l2_budget = 0;
        s->skip_l2_cce = 0;
        s->skip_l2_no_prb = 0;
        s->skip_l2_rbzero = 0;
        s->reached_alloc = 0;
        s->floor_fires_w = 0;
        s->floor_adq_fires_w = 0;
        /* floor_crumb_run / floor_fruitless are persistent state, NOT
         * windowed telemetry -- they must survive the flush or the trickle
         * detector and the backoff would reset every window.            */
        /* last_bsr / last_deficit_sum intentionally NOT reset -- they're a
         * snapshot of current state, not a windowed accumulator. The other
         * floor_* fields are persistent floor state, also NOT reset.    */
    }
}

typedef struct {
    int    dir;          /* 0 = DL, 1 = UL */
    int    idx;           /* rnti_map slot index */
    int    ch;              /* DL: lcid (4..31)   UL: lcg (1..7) */
    double se;               /* bits/PRB/slot, from current adaptive MCS */
    double demand_bps;
    int    is_gbr;
    double gfbr_bps;
    double weight;
} ia_p5g_tier1_flow_t;

/* ── Capacity (PRB-slot-units/sec), per §7.3 ─────────────────────────── */
static void ia_p5g_compute_capacity(const gNB_MAC_INST *mac,
                                     double *cap_dl, double *cap_ul,
                                     int *out_n_rb_ul)
{
    const frame_structure_t *fs = &mac->frame_structure;
    const NR_ServingCellConfigCommon_t *scc =
        mac->common_channels[0].ServingCellConfigCommon;

    const int n_rb_dl = scc->downlinkConfigCommon->frequencyInfoDL
                         ->scs_SpecificCarrierList.list.array[0]->carrierBandwidth;
    const int n_rb_ul = scc->uplinkConfigCommon->frequencyInfoUL
                         ->scs_SpecificCarrierList.list.array[0]->carrierBandwidth;

    const int full_dl = get_full_dl_slots_per_period(fs);
    const int full_ul = get_full_ul_slots_per_period(fs);

    const double slots_per_sec_dl = (double)fs->numb_slots_frame * 100.0
                    * ((double)full_dl / (double)fs->numb_slots_period);
    const double slots_per_sec_ul = (double)fs->numb_slots_frame * 100.0
                    * ((double)full_ul / (double)fs->numb_slots_period);

    *cap_dl = (double)n_rb_dl * slots_per_sec_dl * IA_P5G_TIER1_OVERHEAD_FACTOR;
    *cap_ul = (double)n_rb_ul * slots_per_sec_ul * IA_P5G_TIER1_OVERHEAD_FACTOR;

    /* Export n_rb_ul so callers can compute per-PRB rate for PHR cap.
     * cap_ul / n_rb_ul = slots_per_sec_ul * overhead = rate_per_prb_unit */
    if (out_n_rb_ul)
        *out_n_rb_ul = n_rb_ul;
}

/* ── Spectral efficiency (bits/PRB/slot) from currently-tracked adaptive
 *    MCS — reuses the existing BLER-adaptive MCS state, no new tracking.
 *    1 RB / 14 symbols / no extra DMRS-RE reduction here: the cell-level
 *    overhead_factor above already covers PDCCH/DMRS/CSI-RS, so folding a
 *    second overhead term in per-RB would double-count it.                */
static double ia_p5g_estimate_se_dl(const NR_UE_info_t *UE)
{
    const uint8_t mcs   = UE->UE_sched_ctrl.dl_bler_stats.mcs;
    const uint8_t table = UE->current_DL_BWP.mcsTableIdx;
    const uint8_t  Qm = nr_get_Qm_dl(mcs, table);
    const uint16_t R  = nr_get_code_rate_dl(mcs, table);
    const double se = (double)nr_compute_tbs(Qm, R, 1, 14, 0, 0, 0, 1);
    return se > 1.0 ? se : 1.0;  /* floor: avoid div-by-zero in the LP */
}

static double ia_p5g_estimate_se_ul(const NR_UE_info_t *UE)
{
    const uint8_t mcs   = UE->UE_sched_ctrl.ul_bler_stats.mcs;
    const uint8_t table = UE->current_UL_BWP.mcs_table;
    const uint8_t  Qm = nr_get_Qm_ul(mcs, table);
    const uint16_t R  = nr_get_code_rate_ul(mcs, table);
    const double se = (double)nr_compute_tbs(Qm, R, 1, 14, 0, 0, 0, 1);
    return se > 1.0 ? se : 1.0;
}

/* UL traffic is tracked per-LCG (BSR granularity) but QoS lives on the
 * per-LCID lc_config entry; LCID = LCG + 3 (confirmed mapping, §3).       */
static const nr_lc_config_t *ia_p5g_find_lc_config(const NR_UE_sched_ctrl_t *sc,
                                                     int lcid)
{
    for (int i = 0; i < seq_arr_size(&sc->lc_config); i++) {
        const nr_lc_config_t *c = seq_arr_at(&sc->lc_config, i);
        if (c->lcid == lcid) return c;
    }
    return NULL;
}

/* "Delay" weight boost proxy — no explicit traffic-class field exists in
 * the C struct, so we threshold on 3GPP priority (§7.3 judgment call,
 * flagged as tunable). priority ≤ 20 (URLLC range) → weight 5.0.          */
static inline double ia_p5g_weight_from_priority(int priority)
{
    return (priority > 0 && priority <= IA_P5G_TIER1_DELAY_PRIO_THRESH)
           ? IA_P5G_TIER1_DELAY_WEIGHT : IA_P5G_TIER1_PF_WEIGHT;
}

/* ── SCA outer loop wrapping GLPK's simplex inner solve ──────────────────
 * One LP per call, rebuilt fresh each Tier-1 cycle (flow set/QoS/demand
 * can change between cycles — UEs connect/disconnect, LCIDs activate).
 * On solver failure mid-loop, r_out keeps the last successfully-solved
 * iterate rather than garbage (fail-soft, matches verified testbed
 * behaviour where this path essentially never triggers in practice: the
 * GBR floor is a SOFT constraint via slack s_i, so the LP itself is
 * always feasible by construction — failure here would indicate a
 * genuine numerical/solver problem, not scenario infeasibility).          */
static int ia_p5g_sca_solve(const ia_p5g_tier1_flow_t *flows, int n,
                             double cap_dl, double cap_ul,
                             double *r_out)
{
    if (n <= 0) return 1;

    int n_gbr = 0;
    for (int i = 0; i < n; i++) if (flows[i].is_gbr) n_gbr++;

    const int n_cols = 2 * n;
    const int n_rows = 2 + n_gbr;

    glp_prob *lp = glp_create_prob();
    glp_set_obj_dir(lp, GLP_MAX);
    glp_add_rows(lp, n_rows);
    glp_add_cols(lp, n_cols);

    glp_set_row_bnds(lp, 1, GLP_UP, 0.0, cap_dl);
    glp_set_row_bnds(lp, 2, GLP_UP, 0.0, cap_ul);

    int *gbr_row_of = (int *)calloc((size_t)n, sizeof(int));
    int row = 3;
    for (int i = 0; i < n; i++) {
        if (flows[i].is_gbr) {
            glp_set_row_bnds(lp, row, GLP_LO, flows[i].gfbr_bps, 0.0);
            gbr_row_of[i] = row;
            row++;
        }
    }

    for (int i = 0; i < n; i++) {
        /* [IA-P5G] GLP_DB requires lb < ub. An idle flow with demand_bps==0
         * (legitimate between traffic bursts) makes GLP_DB(0,0) invalid →
         * glp_simplex returns GLP_EBOUND (rc=4) at setup, the whole SCA solve
         * aborts, and Tier-1 silently falls back to stale "last good" targets.
         * Observed failing ~90% of cycles. Pin zero/near-zero-demand flows to
         * a fixed 0 target instead — correct (no demand ⇒ no rate) and valid. */
        if (flows[i].demand_bps > IA_P5G_TIER1_EPSILON)
            glp_set_col_bnds(lp, i + 1, GLP_DB, 0.0, flows[i].demand_bps);
        else
            glp_set_col_bnds(lp, i + 1, GLP_FX, 0.0, 0.0);
        if (flows[i].is_gbr)
            glp_set_col_bnds(lp, n + i + 1, GLP_LO, 0.0, 0.0);
        else
            glp_set_col_bnds(lp, n + i + 1, GLP_FX, 0.0, 0.0);
        glp_set_obj_coef(lp, n + i + 1, -IA_P5G_TIER1_GBR_PENALTY);
    }

    const int max_nz = n + n + 2 * n_gbr;
    int    *ia = (int *)malloc(sizeof(int) * (size_t)(max_nz + 1));
    int    *ja = (int *)malloc(sizeof(int) * (size_t)(max_nz + 1));
    double *ar = (double *)malloc(sizeof(double) * (size_t)(max_nz + 1));
    int nz = 0;

    for (int i = 0; i < n; i++) {
        const int cap_row = (flows[i].dir == 0) ? 1 : 2;
        nz++; ia[nz] = cap_row; ja[nz] = i + 1; ar[nz] = 1.0 / flows[i].se;
    }
    for (int i = 0; i < n; i++) {
        if (flows[i].is_gbr) {
            const int rr = gbr_row_of[i];
            nz++; ia[nz] = rr; ja[nz] = i + 1;     ar[nz] = 1.0;  /* r_i */
            nz++; ia[nz] = rr; ja[nz] = n + i + 1; ar[nz] = 1.0;  /* s_i */
        }
    }
    glp_load_matrix(lp, nz, ia, ja, ar);

    /* [IA-P5G] Silence GLPK's *scaling* output. parm.msg_lev below only
     * controls glp_simplex(); glp_scale_prob() writes straight to GLPK's
     * terminal handler regardless, emitting three lines per solve:
     *     Scaling...
     *      A: min|aij| = ... max|aij| = ... ratio = ...
     *     GM: min|aij| = ... max|aij| = ... ratio = ...
     * At one Tier-1 solve per second that is 3 lines/s of pure noise
     * interleaved into the MAC log, and it was observed dominating long
     * stretches of a capture. glp_term_out() is the only switch that
     * covers it. Disable around scaling, restore after, so any future
     * GLPK diagnostics we DO want are not permanently suppressed.     */
    glp_term_out(GLP_OFF);
    glp_scale_prob(lp, GLP_SF_GM);      /* geometric-mean scaling — the standard default */
    glp_term_out(GLP_ON);

    glp_smcp parm;
    glp_init_smcp(&parm);
    parm.msg_lev = GLP_MSG_OFF;      /* [IA-P5G] silence GLPK's per-solve "OPTIMAL LP
                                      * SOLUTION FOUND / Simplex Optimizer ..." spam --
                                      * useless for diagnosis and floods the log. Solve
                                      * status is already reported via our own
                                      * [IA-P5G] Tier-1 lines below. */

    double *r_prev = (double *)malloc(sizeof(double) * (size_t)n);
    for (int i = 0; i < n; i++) r_prev[i] = IA_P5G_TIER1_EPSILON;

    int ok = 1;
    for (int it = 0; it < IA_P5G_TIER1_SCA_MAXITERS; it++) {
        for (int i = 0; i < n; i++) {
            const double coef = flows[i].weight / (r_prev[i] + IA_P5G_TIER1_EPSILON);
            glp_set_obj_coef(lp, i + 1, coef);
        }

        const int rc = glp_simplex(lp, &parm);
        const int status = glp_get_status(lp);
        if (rc != 0 || status != GLP_OPT) {
            const int prim = glp_get_prim_stat(lp);
            const int dual = glp_get_dual_stat(lp);
            IA_P5G_LOG_EXC_W(NR_MAC, "[IA-P5G] GLPK fail detail: rc=%d status=%d prim=%d dual=%d "
                  "it=%d n=%d n_gbr=%d cap_dl=%.1f cap_ul=%.1f\n",
                  rc, status, prim, dual, it, n, n_gbr, cap_dl, cap_ul);
            ok = 0; break;
        }

        double max_rel_change = 0.0;
        for (int i = 0; i < n; i++) {
            double v = glp_get_col_prim(lp, i + 1);
            if (v < 0.0) v = 0.0;
            const double damped = IA_P5G_TIER1_SCA_ALPHA * v
                          + (1.0 - IA_P5G_TIER1_SCA_ALPHA) * r_prev[i];
            const double rel = fabs(damped - r_prev[i]) / (r_prev[i] + 1.0);
            if (rel > max_rel_change) max_rel_change = rel;
            r_out[i] = damped;
        }
        for (int i = 0; i < n; i++) r_prev[i] = r_out[i];
        if (max_rel_change < IA_P5G_TIER1_SCA_TOL) break;
    }

    glp_delete_prob(lp);
    free(ia); free(ja); free(ar);
    free(gbr_row_of); free(r_prev);
    return ok;
}

void *ia_p5g_tier1_thread(void *arg)
{
    ia_p5g_crash_ctx = "ia_p5g_tier1_thread";
    AssertFatal(arg != NULL, "[IA-P5G] tier1_thread: arg is NULL\n");

    gNB_MAC_INST   *mac   = (gNB_MAC_INST *)arg;
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    AssertFatal(state != NULL,
                "[IA-P5G] tier1_thread: mac->sched_stateful_data is NULL\n");

    IA_P5G_LOG_LIFE(NR_MAC, "[IA-P5G] Tier-1 LP thread started. Period=%.1fs "
          "(SCA+GLPK, damped alpha=%.2f, max_iters=%d, tol=%.0e)\n",
          state->tier1_period_s, IA_P5G_TIER1_SCA_ALPHA,
          IA_P5G_TIER1_SCA_MAXITERS, IA_P5G_TIER1_SCA_TOL);

    static ia_p5g_tier1_flow_t flows[IA_P5G_TIER1_MAX_FLOWS];
    static double              r_out[IA_P5G_TIER1_MAX_FLOWS];

    struct timespec last_solve_ts;
    clock_gettime(CLOCK_MONOTONIC, &last_solve_ts);

    uint32_t iter = 0;
    uint32_t abs_slot_counter = 0;
    const uint32_t slots_per_period =
        (uint32_t)(state->tier1_period_s / IA_P5G_SLOT_DURATION_S + 0.5f);

    while (!atomic_load(&state->stop)) {
        usleep((useconds_t)(state->tier1_period_s * 1e6f));
        iter++;

        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        double elapsed_s = (double)(now.tv_sec - last_solve_ts.tv_sec)
                  + (double)(now.tv_nsec - last_solve_ts.tv_nsec) * 1e-9;
        if (elapsed_s <= 0.0) elapsed_s = (double)state->tier1_period_s;
        last_solve_ts = now;

        double cap_dl = 0.0, cap_ul = 0.0;
        int    n_rb_ul_cap = 1;   /* defensive default; overwritten below */
        ia_p5g_compute_capacity(mac, &cap_dl, &cap_ul, &n_rb_ul_cap);

        int n = 0;

        /* ── Snapshot phase: copy-only, under the existing scheduler lock
         * (same NR_SCHED_LOCK convention nrmac_stats_thread already uses
         * to read UE_info from outside the per-slot thread, main.c).
         * The GLPK solve itself runs unlocked afterwards so a ~1–10ms LP
         * solve never stalls the per-slot scheduler.                      */
        NR_SCHED_LOCK(&mac->sched_lock);
        UE_iterator(mac->UE_info.connected_ue_list, UE) {
            if (!nr_mac_ue_is_active(UE)) continue;

            int idx = ia_p5g_rnti_lookup(state, UE->rnti);
            if (idx < 0) {
                pthread_mutex_lock(&state->state_lock);
                idx = ia_p5g_rnti_get_or_alloc(state, UE->rnti);
                pthread_mutex_unlock(&state->state_lock);
                if (idx < 0) continue;  /* rnti table full — logged inside alloc */
            }

            NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;

            /* ── Change 3: BLER-discounted spectral efficiency ──────────────
             * Raw SE from MCS table assumes every grant delivers bits.  Under
             * high BLER a large fraction of each grant is HARQ retransmission,
             * so net throughput per PRB is lower than the table predicts.
             *
             * effective_se = se_raw × max(1 − BLER, floor)
             *
             * Tier-1 then correctly sizes the rate target to what the channel
             * can actually deliver, preventing over-allocation that cascades
             * into sustained high BLER and eventual RLF.
             *
             * DL and UL are discounted independently — each has its own OLLA.
             * se_ul_raw is kept separately for the PHR cap below, which is a
             * power constraint independent of BLER.                          */
            const double se_dl_raw  = ia_p5g_estimate_se_dl(UE);
            const double se_ul_raw  = ia_p5g_estimate_se_ul(UE);
            const double bler_dl    = (double)sc->dl_bler_stats.bler;
            const double bler_ul    = (double)sc->ul_bler_stats.bler;
            const double se_dl      = se_dl_raw
                                      * fmax(1.0 - bler_dl, IA_P5G_DL_BLER_DISCOUNT_FLOOR);
            const double se_ul      = se_ul_raw
                                      * fmax(1.0 - bler_ul, IA_P5G_UL_BLER_DISCOUNT_FLOOR);

            IA_P5G_LOG_D(NR_MAC,
                  "[IA-P5G][T1][UE %04x] DL bler=%.3f se_raw=%.0f se_eff=%.0f | "
                  "UL bler=%.3f se_raw=%.0f se_eff=%.0f\n",
                  UE->rnti,
                  bler_dl, se_dl_raw, se_dl,
                  bler_ul, se_ul_raw, se_ul);

            /* ── Change 4: PHR-based UL PRB ceiling ─────────────────────────
             * N_max_prb = 10^(ph0/10): the maximum number of PRBs the UE can
             * power at the current MCS without exceeding PCMAX.
             *
             * phr_cap_bps = N_max_prb × (cap_ul / n_rb_ul) × se_ul_raw
             *             = N_max_prb × rate_per_prb_slot × se_per_prb
             *
             * cap_ul / n_rb_ul = (n_rb_ul × sps_ul × overhead) / n_rb_ul
             *                  = slots_per_sec_ul × overhead
             * so phr_cap_bps = N_max_prb × slots_per_sec_ul × overhead × se_ul_raw
             *
             * We use se_ul_raw (not se_ul) because the PHR cap is a power
             * limit, not a quality limit — even a UE with high BLER is still
             * power-limited at N_max_prb PRBs.  The BLER discount is a
             * separate and orthogonal correction.
             *
             * Guard: ph0 == 0 before the first PHR CE is received (startup).
             * In that case disable the cap by setting it to a large sentinel.
             * Also clamp N_max_prb to n_rb_ul as an upper bound — we never
             * need to offer more PRBs than the carrier has.                 */
            double phr_cap_bps;
            if (sc->ph0 > 0) {
                double n_max_prb = IA_P5G_PHR_PRB_SAFETY_FACTOR
                                   * pow(10.0, (double)sc->ph0 / 10.0);
                if (n_max_prb > (double)n_rb_ul_cap)
                    n_max_prb = (double)n_rb_ul_cap;  /* never exceed carrier width */
                /* rate_per_prb_slot = cap_ul / n_rb_ul (PRB-slot-rate normalised) */
                const double rate_per_prb = (n_rb_ul_cap > 0)
                    ? (cap_ul / (double)n_rb_ul_cap) : cap_ul;
                phr_cap_bps = n_max_prb * rate_per_prb * se_ul_raw;
                IA_P5G_LOG_D(NR_MAC,
                      "[IA-P5G][T1][UE %04x] PHR ph0=%d n_max_prb=%.1f "
                      "phr_cap=%.0f bps\n",
                      UE->rnti, sc->ph0, n_max_prb, phr_cap_bps);
            } else {
                /* No PHR yet — sentinel: cap_ul * se_ul_raw is a safe upper bound
                 * (it represents 100% of UL capacity at current MCS, which the LP
                 * capacity constraint will already enforce anyway).            */
                phr_cap_bps = cap_ul * se_ul_raw;
            }

            /* ── DL: one flow per active DRB LCID ────────────────────── */
            for (int i = 0; i < seq_arr_size(&sc->lc_config); i++) {
                const nr_lc_config_t *c = seq_arr_at(&sc->lc_config, i);
                const int lcid = c->lcid;
                if (lcid < 4 || lcid >= IA_P5G_MAX_LCID) continue;
                if (n >= IA_P5G_TIER1_MAX_FLOWS) break;

                const uint64_t del_cum = (uint64_t)UE->mac_stats.dl.lc_bytes[lcid];
                const uint64_t arr_cum = del_cum
                                + (uint64_t)sc->rlc_status[lcid].bytes_in_buffer;
                const uint64_t arr_W = arr_cum - state->dl_arrived_hist[idx][lcid];
                const int prio = c->qos_config[0].priority > 0
                                 ? c->qos_config[0].priority : 90;

                flows[n].dir        = 0;
                flows[n].idx        = idx;
                flows[n].ch         = lcid;
                flows[n].se         = se_dl;
                flows[n].demand_bps = ((double)arr_W * 8.0) / elapsed_s;
                flows[n].is_gbr     = c->gbr_dl_guaranteed > 0;
                flows[n].gfbr_bps   = (double)c->gbr_dl_guaranteed;
                flows[n].weight     = ia_p5g_weight_from_priority(prio);
                n++;

                /* Close out this window for Tier-2's ceiling clamp
                 * (ia_p5g_update_vq_dl()) — next cycle starts fresh.       */
                state->dl_arrived_hist[idx][lcid]   = arr_cum;
                state->dl_delivered_hist[idx][lcid] = del_cum;
            }

            /* ── UL: one flow per active LCG (1–7; LCG 0 = SRB) ────────── */
            for (int lcg = 1; lcg < IA_P5G_MAX_LCG; lcg++) {
                if (n >= IA_P5G_TIER1_MAX_FLOWS) break;
                const int lcid = lcg + 3;
                const nr_lc_config_t *c = ia_p5g_find_lc_config(sc, lcid);
                if (!c) continue;  /* DRB not set up for this LCG yet */

                const uint64_t del_cum = (uint64_t)UE->mac_stats.ul.lc_bytes[lcid];
                const uint64_t arr_cum = del_cum
                                + (uint64_t)sc->estimated_ul_buffer_per_lcg[lcg];
                const uint64_t arr_W = arr_cum - state->ul_arrived_hist[idx][lcg];
                const int prio = c->qos_config[0].priority > 0
                                 ? c->qos_config[0].priority : 90;

                /* ── Change 1: EWMA smoothing on UL demand estimate ──────────
                 * Raw demand from BSR-based window integral oscillates with TCP
                 * congestion control (~1–2 s period), resonant with the 1-s
                 * Tier-1 window.  Apply EWMA with α=IA_P5G_UL_DEMAND_ALPHA
                 * (time constant τ ≈ 2.8 s) to smooth across TCP burst/trough
                 * cycles.  Pass the smoothed value to the LP as demand_bps.
                 *
                 * DL uses raw arr_W directly (reads gNB RLC buffer — exact,
                 * stable) and must NOT be smoothed here.                    */
                double demand_raw = ((double)arr_W * 8.0) / elapsed_s;
                state->ul_demand_smooth[idx][lcg] =
                    IA_P5G_UL_DEMAND_ALPHA * demand_raw
                    + (1.0 - IA_P5G_UL_DEMAND_ALPHA) * state->ul_demand_smooth[idx][lcg];

                /* Guard: if smoothed demand is zero (first cycle after UE attach,
                 * or sustained silence), fall back to raw to avoid starving the
                 * UE on its first active window.                             */
                double demand_use = (state->ul_demand_smooth[idx][lcg] > 0.0)
                                    ? state->ul_demand_smooth[idx][lcg]
                                    : demand_raw;

                /* ── Apply PHR-based demand cap ──────────────────────────────
                 * If the UE is power-limited, cap demand_use to the rate that
                 * corresponds to N_max_prb PRBs.  For non-power-limited UEs
                 * (ph0 >> n_rb_ul, phr_cap_bps >> demand_use) this is a no-op.*/
                if (demand_use > phr_cap_bps) {
                    IA_P5G_LOG_D(NR_MAC,
                          "[IA-P5G][T1][UE %04x][LCG %d] PHR cap applied: "
                          "demand %.0f bps → %.0f bps (ph0=%d)\n",
                          UE->rnti, lcg, demand_use, phr_cap_bps, sc->ph0);
                    demand_use = phr_cap_bps;
                }

                IA_P5G_LOG_D(NR_MAC,
                      "[IA-P5G][T1][UE %04x][LCG %d] UL demand_raw=%.0f bps "
                      "demand_smooth=%.0f bps demand_use=%.0f bps "
                      "arr_W=%"PRIu64" bytes elapsed=%.3fs\n",
                      UE->rnti, lcg, demand_raw, state->ul_demand_smooth[idx][lcg],
                      demand_use, arr_W, elapsed_s);

                flows[n].dir        = 1;
                flows[n].idx        = idx;
                flows[n].ch         = lcg;
                flows[n].se         = se_ul;
                flows[n].demand_bps = demand_use;
                flows[n].is_gbr     = c->gbr_ul_guaranteed > 0;
                flows[n].gfbr_bps   = (double)c->gbr_ul_guaranteed;
                flows[n].weight     = ia_p5g_weight_from_priority(prio);
                n++;

                state->ul_arrived_hist[idx][lcg]   = arr_cum;
                state->ul_delivered_hist[idx][lcg] = del_cum;
            }
        }
        NR_SCHED_UNLOCK(&mac->sched_lock);

        /* ── Solve phase: unlocked SCA+GLPK, damped per VERIFICATION_REPORT.md ── */
        if (n > 0) {
            int ok = ia_p5g_sca_solve(flows, n, cap_dl, cap_ul, r_out);
            if (!ok)
                IA_P5G_LOG_EXC_W(NR_MAC, "[IA-P5G] Tier-1 SCA solve hit a non-optimal "
                      "simplex status (iter=%u, n_flows=%d) — keeping last "
                      "good targets for this cycle\n", iter, n);

            for (int i = 0; i < n; i++) {
                if (flows[i].dir == 0)
                    atomic_store_explicit(
                        &state->t1out.dl_target_bps[flows[i].idx][flows[i].ch],
                        (float)r_out[i], memory_order_relaxed);
                else
                    atomic_store_explicit(
                        &state->t1out.ul_target_bps[flows[i].idx][flows[i].ch],
                        (float)r_out[i], memory_order_relaxed);
            }
        }

        abs_slot_counter += slots_per_period;
        state->window_start_abs_slot = abs_slot_counter;
        atomic_store_explicit(&state->t1out.last_solve_abs_slot,
                               abs_slot_counter, memory_order_relaxed);

        if (iter % 10 == 0)
            IA_P5G_LOG_I(NR_MAC,
                  "[IA-P5G] Tier-1 solved (iter=%u, n_flows=%d, "
                  "cap_dl=%.0f cap_ul=%.0f PRB-slot/s)\n",
                  iter, n, cap_dl, cap_ul);
    }

    IA_P5G_LOG_LIFE(NR_MAC, "[IA-P5G] Tier-1 LP thread exiting cleanly\n");
    return NULL;
}

/* =========================================================================
 * Tier-2 DL functions  
 *
 * ia_p5g_dl_metric() returns 0.0 so the existing qsort comparator in
 * pf_dl() falls back to its has_gbr / pdb_ms tiers for UE ordering.
 * No behavioural regression at Checkpoint 1.
 * ========================================================================= */

/* ─────────────────────────────────────────────────────────────────────────
 * Local UE scheduling candidate struct + comparator for ia_p5g_pf_dl().
 * Structurally identical to UEsched_t/comparator() in gNB_scheduler_dlsch.c
 * (which are static there and not accessible here). Sort behaviour matches
 * exactly when coef == 0 (Tier-1 not yet run): has_gbr tier, then pdb_ms,
 * then coef as final tiebreak.
 * ───────────────────────────────────────────────────────────────────────── */
typedef struct {
    float          coef;
    NR_UE_info_t  *UE;
    int            selected_mcs;
    int            pdb_ms;
    bool           has_gbr;
} ia_p5g_dl_ue_t;

static int ia_p5g_dl_cmp(const void *p, const void *q)
{
    const ia_p5g_dl_ue_t *pp = p;
    const ia_p5g_dl_ue_t *qq = q;

    if (pp->has_gbr && !qq->has_gbr) return -1;
    if (!pp->has_gbr && qq->has_gbr) return  1;

    if (pp->pdb_ms < qq->pdb_ms) return -1;
    if (pp->pdb_ms > qq->pdb_ms) return  1;

    if (pp->coef < qq->coef) return  1;
    if (pp->coef > qq->coef) return -1;
    return 0;
}

void ia_p5g_pf_dl(gNB_MAC_INST *mac,
                  post_process_pdsch_t   *pp_pdsch,
                  NR_UE_info_t          **UE_list,
                  int                    max_num_ue,
                  int                    num_beams,
                  int                    n_rb_sched[])
{
    ia_p5g_crash_ctx = "ia_p5g_pf_dl: entry";

    /* ── Defensive entry checks ──────────────────────────────────────────
     * Required-pointer contract violations — these indicate a caller bug,
     * not a recoverable runtime condition. AssertFatal prints a clear
     * message before terminating, consistent with the rest of OAI.        */
    AssertFatal(mac != NULL,        "[IA-P5G] ia_p5g_pf_dl: mac is NULL\n");
    AssertFatal(pp_pdsch != NULL,   "[IA-P5G] ia_p5g_pf_dl: pp_pdsch is NULL\n");
    AssertFatal(UE_list != NULL,    "[IA-P5G] ia_p5g_pf_dl: UE_list is NULL\n");
    AssertFatal(n_rb_sched != NULL, "[IA-P5G] ia_p5g_pf_dl: n_rb_sched is NULL\n");
    AssertFatal(num_beams > 0,      "[IA-P5G] ia_p5g_pf_dl: num_beams must be > 0 (got %d)\n", num_beams);

    /* ── Runtime condition: state not initialised ────────────────────────
     * Should never happen — the preprocessor only calls us when
     * sched_stateful_data != NULL — but if it does, fail soft: log clearly
     * and skip this slot's DL scheduling rather than crashing the gNB.    */
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    if (state == NULL) {
        IA_P5G_LOG_EXC_E(NR_MAC, "[IA-P5G] ia_p5g_pf_dl called but sched_stateful_data is "
              "NULL (%d.%d) — skipping DL scheduling this slot\n",
              pp_pdsch->frame, pp_pdsch->slot);
        return;
    }

    frame_t frame = pp_pdsch->frame;
    slot_t  slot  = pp_pdsch->slot;

    ia_p5g_crash_ctx = "ia_p5g_pf_dl: setup";

    NR_ServingCellConfigCommon_t *scc = mac->common_channels[0].ServingCellConfigCommon;
    if (scc == NULL) {
        IA_P5G_LOG_EXC_E(NR_MAC, "[IA-P5G] ia_p5g_pf_dl: ServingCellConfigCommon is NULL "
              "(%d.%d) — skipping DL scheduling\n", frame, slot);
        return;
    }

    ia_p5g_dl_ue_t UE_sched[MAX_MOBILES_PER_GNB + 1] = {0};
    int remainUEs[num_beams];
    for (int i = 0; i < num_beams; i++)
        remainUEs[i] = max_num_ue;
    int numUE = 0;
    const int CC_id = 0;
    int slots_per_frame = mac->frame_structure.numb_slots_frame;

    /* ═══════════════════════════════════════════════════════════════════
     * FIRST LOOP — retransmissions + candidate collection
     * ═══════════════════════════════════════════════════════════════════ */
    ia_p5g_crash_ctx = "ia_p5g_pf_dl: first loop";

    UE_iterator(UE_list, UE) {
        if (UE == NULL) continue;  /* defensive: should not happen, guard anyway */

        NR_UE_sched_ctrl_t *sched_ctrl = &UE->UE_sched_ctrl;
        NR_UE_DL_BWP_t *current_BWP = &UE->current_DL_BWP;

        if (!nr_mac_ue_is_active(UE))
            continue;

        NR_mac_dir_stats_t *stats = &UE->mac_stats.dl;
        int harq_pid = sched_ctrl->retrans_dl_harq.head;

        const float a = 0.01f;
        const uint32_t b = stats->current_bytes;
        UE->dl_thr_ue = (1 - a) * UE->dl_thr_ue + a * b;

        stats->current_bytes = 0;
        stats->current_rbs = 0;

        if (frame == sched_ctrl->ta_frame)
            sched_ctrl->ta_apply = true;

        int total_rem_ues = 0;
        for (int i = 0; i < num_beams; i++)
            total_rem_ues += remainUEs[i];
        if (total_rem_ues == 0)
            continue;

        /* retransmission */
        if (harq_pid >= 0) {
            NR_beam_alloc_t beam = beam_allocation_procedure(&mac->beam_info, frame, slot,
                                                               UE->UE_beam_index, slots_per_frame);
            bool sch_ret = beam.idx >= 0;
            if (sch_ret)
                sch_ret = allocate_dl_retransmission(mac, pp_pdsch, &n_rb_sched[beam.idx], UE, beam.idx, harq_pid);
            if (!sch_ret) {
                IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] DL retransmission could not be allocated\n",
                      UE->rnti, frame, slot);
                reset_beam_status(&mac->beam_info, frame, slot, UE->UE_beam_index, slots_per_frame, beam.new_beam);
                continue;
            }
            remainUEs[beam.idx]--;
        } else {
            if (sched_ctrl->available_dl_harq.head < 0) {
                IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] UE has no free DL HARQ process, skipping\n",
                      UE->rnti, frame, slot);
                continue;
            }

            update_dlsch_buffer(pp_pdsch->frame, pp_pdsch->slot, UE);

            if (sched_ctrl->num_total_bytes == 0 && sched_ctrl->ta_apply == false)
                continue;

            /* ── TwoTier hook 1: grow + windowed-clamp virtual queue ──── */
            ia_p5g_update_vq_dl(mac, UE);

            const NR_bler_options_t *bo = &mac->dl_bler;
            const int max_mcs_table = current_BWP->mcsTableIdx == 1 ? 27 : 28;
            const int max_mcs = min(sched_ctrl->dl_max_mcs, max_mcs_table);
            int selected_mcs;
            if (bo->harq_round_max == 1) {
                int new_mcs = min(bo->max_mcs, max_mcs);
                selected_mcs = max(bo->min_mcs, new_mcs);
                sched_ctrl->dl_bler_stats.mcs = selected_mcs;
            } else {
                selected_mcs = get_mcs_from_bler(bo, stats, &sched_ctrl->dl_bler_stats, max_mcs, frame);
            }
            int l = get_dl_nrOfLayers(sched_ctrl, current_BWP->dci_format);
            const uint8_t  Qm = nr_get_Qm_dl(selected_mcs, current_BWP->mcsTableIdx);
            const uint16_t R  = nr_get_code_rate_dl(selected_mcs, current_BWP->mcsTableIdx);
            uint32_t tbs = nr_compute_tbs(Qm, R, 1, 10, 0, 0, 0, l) >> 3;

            /* ── TwoTier hook 2: DPP metric replaces PF coefficient ───── */
            float coeff_ue = ia_p5g_dl_metric(mac, UE, (float)tbs);

            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][DL-QoS] UE %04x b %d thr %.1f tbs %d coef %.4f\n",
                  UE->rnti, b, UE->dl_thr_ue, tbs, coeff_ue);

            /* ── [IA-P5G TELEMETRY] Per-UE DL scheduling snapshot (LOG_I,
             *    gated by IA_P5G_TELEMETRY_DL). Mirror of [P5G-UL] for the
             *    downlink. NOTE the DL scheduler is still LEXICOGRAPHIC
             *    (has_gbr → pdb_ms → coef); coef here is the raw DPP metric
             *    (Σ vq_dl over LCIDs-with-data × SE) used only as the final
             *    tiebreak, NOT the composite (base_q+urg) form the UL path
             *    now uses -- so there is no base_q/urg split to show on DL.
             *    Buffer occupancy is the gNB's own RLC view (num_total_bytes
             *    aggregate; per-LCID rlc_status[].bytes_in_buffer), which is
             *    exact on DL (unlike UL's BSR estimate). `grep P5G-DL <log>`.*/
            if (IA_P5G_TELEMETRY_DL) {
                ia_p5g_state_t *_st = (ia_p5g_state_t *)mac->sched_stateful_data;
                int _idx = _st ? ia_p5g_rnti_lookup(_st, UE->rnti) : -1;
                LOG_I(NR_MAC,
                      "[P5G-DL][%4d.%2d][UE %04x] num_bytes=%d tgt_bytes=%d coef=%.1f "
                      "mcs=%d tbs=%d rem_pdb=%dms has_gbr=%d await_recfg=%d ta_apply=%d thr=%.0f\n",
                      frame, slot, UE->rnti,
                      sched_ctrl->num_total_bytes, sched_ctrl->dl_total_target_bytes, coeff_ue,
                      selected_mcs, tbs, sched_ctrl->dl_best_remaining_pdb_ms,
                      sched_ctrl->dl_has_unfulfilled_gbr, UE->await_reconfig,
                      sched_ctrl->ta_apply, UE->dl_thr_ue);

                for (int _i = 0; _i < seq_arr_size(&sched_ctrl->lc_config); _i++) {
                    const nr_lc_config_t *_c = seq_arr_at(&sched_ctrl->lc_config, _i);
                    const int _lcid = _c->lcid;
                    int   _buf = sched_ctrl->rlc_status[_lcid].bytes_in_buffer;
                    float _vq  = (_idx >= 0 && _lcid < 32) ? _st->vq_dl[_idx][_lcid] : 0.0f;
                    /* show SRBs (control) always if they have data, plus any
                     * DRB with buffer or a live virtual queue */
                    if (_buf <= 0 && _vq <= 0.0f) continue;
                    const char *_kind = (_lcid < 4) ? "SRB/ctrl" : "DRB/data";
                    LOG_I(NR_MAC,
                          "[P5G-DL-LCID][%4d.%2d][UE %04x] lcid=%d kind=%s 5qi=%d prio=%d pdb=%dms "
                          "rlc_buf=%d vq=%.1f gbr_dl=%lu mbr_dl=%lu\n",
                          frame, slot, UE->rnti, _lcid, _kind,
                          _c->qos_config[0].fiveQI, _c->qos_config[0].priority,
                          _c->qos_config[0].pdb_ms, _buf, _vq,
                          (unsigned long)_c->gbr_dl_guaranteed, (unsigned long)_c->gbr_dl_max);
                }
            }

            /* ── Defensive bound: original code sizes UE_sched exactly to
             * MAX_MOBILES_PER_GNB+1 and relies on the connected_ue_list
             * never exceeding that. We add an explicit guard so a future
             * change elsewhere can't silently overflow this array.        */
            if (numUE >= MAX_MOBILES_PER_GNB) {
                IA_P5G_LOG_EXC_E(NR_MAC, "[IA-P5G] ia_p5g_pf_dl: UE_sched array full (%d) "
                      "at (%d.%d) — skipping remaining UEs this slot\n",
                      MAX_MOBILES_PER_GNB, frame, slot);
                break;
            }

            UE_sched[numUE].coef         = coeff_ue;
            UE_sched[numUE].UE           = UE;
            UE_sched[numUE].selected_mcs = selected_mcs;
            UE_sched[numUE].pdb_ms       = sched_ctrl->dl_best_remaining_pdb_ms;
            UE_sched[numUE].has_gbr      = sched_ctrl->dl_has_unfulfilled_gbr;
            numUE++;
        }
    }

    qsort(UE_sched, numUE, sizeof(ia_p5g_dl_ue_t), ia_p5g_dl_cmp);
    ia_p5g_dl_ue_t *iterator = UE_sched;

    /* ── [IA-P5G TELEMETRY] Decided DL ranking after the sort (LOG_I, gated).
     *    ia_p5g_dl_cmp is LEXICOGRAPHIC: has_gbr first, then pdb_ms ascending,
     *    then coef descending as tiebreak. So the served order is decided by
     *    class+deadline, not primarily by coef -- the [gbr] and [pdb] fields
     *    show why each UE sits where it does. Contrast with [P5G-UL-RANK],
     *    which is pure control-plane-then-coef. Only when >1 candidate.     */
    if (IA_P5G_TELEMETRY_DL && numUE > 1) {
        char _rankbuf[320];
        int _off = 0;
        for (int _u = 0; _u < numUE && _off < (int)sizeof(_rankbuf) - 64; _u++) {
            _off += snprintf(_rankbuf + _off, sizeof(_rankbuf) - _off,
                             "%s#%d:UE%04x[gbr=%d pdb=%dms coef=%.1f]",
                             _u ? " > " : "",
                             _u, UE_sched[_u].UE->rnti,
                             UE_sched[_u].has_gbr, UE_sched[_u].pdb_ms,
                             UE_sched[_u].coef);
        }
        LOG_I(NR_MAC, "[P5G-DL-RANK][%4d.%2d] served_order: %s\n", frame, slot, _rankbuf);
    }

    const int min_rbSize = 5;

    /* ═══════════════════════════════════════════════════════════════════
     * SECOND LOOP — allocate granted UEs
     * ═══════════════════════════════════════════════════════════════════ */
    ia_p5g_crash_ctx = "ia_p5g_pf_dl: second loop";

    while (iterator->UE != NULL) {

        NR_UE_sched_ctrl_t *sched_ctrl = &iterator->UE->UE_sched_ctrl;
        const uint16_t rnti = iterator->UE->rnti;

        NR_UE_DL_BWP_t *dl_bwp = &iterator->UE->current_DL_BWP;
        NR_UE_UL_BWP_t *ul_bwp = &iterator->UE->current_UL_BWP;

        if (sched_ctrl->available_dl_harq.head < 0) {
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] UE has no free DL HARQ process, skipping\n",
                  rnti, frame, slot);
            iterator++;
            continue;
        }

        NR_beam_alloc_t beam = beam_allocation_procedure(&mac->beam_info, frame, slot,
                                                           iterator->UE->UE_beam_index, slots_per_frame);
        if (beam.idx < 0) {
            iterator++;
            continue;
        }
        if (remainUEs[beam.idx] == 0 || n_rb_sched[beam.idx] < min_rbSize) {
            reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            iterator++;
            continue;
        }

        int tda = get_dl_tda(mac, slot);
        AssertFatal(tda >= 0, "[IA-P5G] Unable to find PDSCH time domain allocation in list\n");

        const int coresetid = sched_ctrl->coreset->controlResourceSetId;
        NR_tda_info_t tda_info = get_dl_tda_info(dl_bwp,
                                                  sched_ctrl->search_space->searchSpaceType->present,
                                                  tda,
                                                  scc->dmrs_TypeA_Position,
                                                  1,
                                                  TYPE_C_RNTI_,
                                                  coresetid,
                                                  false);
        AssertFatal(tda_info.valid_tda, "[IA-P5G] Invalid TDA from get_dl_tda_info\n");

        const uint16_t slbitmap = SL_to_bitmap(tda_info.startSymbolIndex, tda_info.nrOfSymbols);

        uint16_t *rballoc_mask = mac->common_channels[CC_id].vrb_map[beam.idx];
        bwp_info_t bwp_info = get_pdsch_bwp_start_size(mac, iterator->UE);
        int rbStart = 0;
        int rbStop = bwp_info.bwpSize - 1;
        int bwp_start = bwp_info.bwpStart;

        while (rbStart < rbStop && (rballoc_mask[rbStart + bwp_start] & slbitmap))
            rbStart++;

        uint16_t max_rbSize = 1;
        while (rbStart + max_rbSize <= rbStop && !(rballoc_mask[rbStart + max_rbSize + bwp_start] & slbitmap))
            max_rbSize++;

        if (max_rbSize < min_rbSize) {
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G](%d.%d) Cannot schedule RNTI %04x, rbStart %d, rbSize %d, rbStop %d\n",
                  frame, slot, rnti, rbStart, max_rbSize, rbStop);
            reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            iterator++;
            continue;
        }

        int CCEIndex = get_cce_index(mac, CC_id, slot, rnti,
                                     &sched_ctrl->aggregation_level,
                                     beam.idx,
                                     sched_ctrl->search_space,
                                     sched_ctrl->coreset,
                                     &sched_ctrl->sched_pdcch,
                                     sched_ctrl->pdcch_cl_adjust);
        if (CCEIndex < 0) {
            sched_ctrl->dl_cce_fail++;
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] could not find free CCE for DL DCI\n", rnti, frame, slot);
            reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            iterator++;
            continue;
        }

        int alloc = -1;
        if (!get_FeedbackDisabled(iterator->UE->sc_info.downlinkHARQ_FeedbackDisabled_r17, sched_ctrl->available_dl_harq.head)) {
            int r_pucch = nr_get_pucch_resource(sched_ctrl->coreset, ul_bwp->pucch_Config, CCEIndex);
            alloc = nr_acknack_scheduling(mac, iterator->UE, frame, slot, iterator->UE->UE_beam_index, r_pucch, 0);
            if (alloc < 0) {
                IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] could not find PUCCH for DL DCI\n", rnti, frame, slot);
                reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
                iterator++;
                continue;
            }
        }

        sched_ctrl->cce_index = CCEIndex;
        fill_pdcch_vrb_map(mac, CC_id, &sched_ctrl->sched_pdcch, CCEIndex, sched_ctrl->aggregation_level, beam.idx);

        int l = get_dl_nrOfLayers(sched_ctrl, dl_bwp->dci_format);
        NR_sched_pdsch_t sched_pdsch = {
            .rbStart = rbStart,
            .mcs = iterator->selected_mcs,
            .R = nr_get_code_rate_dl(iterator->selected_mcs, dl_bwp->mcsTableIdx),
            .Qm = nr_get_Qm_dl(iterator->selected_mcs, dl_bwp->mcsTableIdx),
            .dl_harq_pid = sched_ctrl->available_dl_harq.head,
            .pucch_allocation = alloc,
            .pm_index = get_pm_index(mac, iterator->UE, dl_bwp->dci_format, l, mac->radio_config.pdsch_AntennaPorts.XP),
            .nrOfLayers = l,
            .bwp_info = bwp_info,
            .dmrs_parms = get_dl_dmrs_params(scc, dl_bwp, &tda_info, l),
            .time_domain_allocation = tda,
            .tda_info = tda_info,
        };

        sched_pdsch.action = NULL;
        int srb1 = 1;
        if (iterator->UE->await_reconfig && sched_ctrl->rlc_status[srb1].bytes_in_buffer > 10)
            sched_pdsch.action = ack_reconfig;

        const int oh = 3 * 4 + (sched_ctrl->ta_apply ? 2 : 0);
        int dl_target = sched_ctrl->dl_total_target_bytes + oh;
        if (dl_target < sched_ctrl->num_total_bytes + oh)
            dl_target = sched_ctrl->num_total_bytes + oh;

        bool fit_ok = nr_find_nb_rb(sched_pdsch.Qm,
                                    sched_pdsch.R,
                                    1,
                                    sched_pdsch.nrOfLayers,
                                    tda_info.nrOfSymbols,
                                    sched_pdsch.dmrs_parms.N_PRB_DMRS * sched_pdsch.dmrs_parms.N_DMRS_SLOT,
                                    dl_target,
                                    min_rbSize,
                                    max_rbSize,
                                    &sched_pdsch.tb_size,
                                    &sched_pdsch.rbSize);

        /* ── BUG FIX (handoff §6): nr_find_nb_rb() returns false on a
         * *partial* fit — i.e., when the requested bytes exceed what
         * max_rbSize can carry — but it still populates tb_size/rbSize
         * with the best achievable partial allocation.  Skipping on
         * !fit_ok therefore causes permanent UE starvation: the backlog
         * can never drain, so !fit_ok fires every slot forever.
         *
         * Vanilla pf_dl() does not capture the return value at all and
         * proceeds directly to post_process_dlsch() — grant whatever fits,
         * drain the backlog over subsequent slots.  Mirror that here:
         * guard only the rbSize == 0 case (genuinely nothing usable). */
        if (sched_pdsch.rbSize == 0) {
            IA_P5G_LOG_EXC_W(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] nr_find_nb_rb: rbSize=0 "
                  "(dl_target=%d max_rbSize=%d) — skipping this UE this slot\n",
                  rnti, frame, slot, dl_target, max_rbSize);
            reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            iterator++;
            continue;
        }
        /* Log partial-fit at DEBUG level only — not an error. */
        if (!fit_ok)
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] nr_find_nb_rb partial fit: "
                  "dl_target=%d capped to tb_size=%d (rbSize=%d/%d)\n",
                  rnti, frame, slot, dl_target, sched_pdsch.tb_size,
                  sched_pdsch.rbSize, max_rbSize);

        /* ── [IA-P5G TELEMETRY] DL grant RESULT (LOG_I, gated). Allocation
         *    half of [P5G-DL]: rbSize (PRBs), tb_size, mcs, requested
         *    dl_target (bytes; = max of dl_total_target_bytes and
         *    num_total_bytes, plus overhead), and max_rbSize (contention ceiling this slot).
         *    Control-channel: cce=granted CCE index, aggL=PDCCH aggregation
         *    level, pucch=AckNack resource (-1 = HARQ feedback disabled),
         *    cce_fail=cumulative DL DCI CCE-allocation failures,
         *    recfg=1 when this grant carries an RRCReconfiguration ack.     */
        if (IA_P5G_TELEMETRY_DL)
        LOG_I(NR_MAC,
              "[P5G-DL-GRANT][%4d.%2d][UE %04x] rbSize=%d tb_size=%d mcs=%d dl_target=%d "
              "max_rb=%d coef=%.1f cce=%d aggL=%d pucch=%d cce_fail=%d recfg=%d\n",
              frame, slot, rnti,
              sched_pdsch.rbSize, sched_pdsch.tb_size, sched_pdsch.mcs, dl_target,
              max_rbSize, iterator->coef, CCEIndex, sched_ctrl->aggregation_level,
              alloc, sched_ctrl->dl_cce_fail,
              sched_pdsch.action == ack_reconfig ? 1 : 0);

        /* ── TwoTier hook 3a: LCP fill — per-LCID byte budgets for this TB */
        ia_p5g_compute_lcp_budget(mac, iterator->UE, sched_pdsch.tb_size);

        post_process_dlsch(mac, pp_pdsch, iterator->UE, &sched_pdsch);

        /* ── TwoTier hook 3b: drain virtual queues by delivered bits ───── */
        ia_p5g_drain_vq_dl(mac, iterator->UE, sched_ctrl->dl_bler_stats.bler);

        n_rb_sched[beam.idx] -= sched_pdsch.rbSize;

        for (int rb = bwp_start; rb < sched_pdsch.rbSize; rb++)
            rballoc_mask[rb + sched_pdsch.rbStart] |= slbitmap;

        remainUEs[beam.idx]--;
        iterator++;
    }

    ia_p5g_crash_ctx = "ia_p5g_pf_dl: done";
}

void ia_p5g_update_vq_dl(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE)
{
    ia_p5g_crash_ctx = "ia_p5g_update_vq_dl";
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    AssertFatal(state != NULL, "[IA-P5G] update_vq_dl: sched_stateful_data is NULL\n");

    /* Fast lock-free lookup first; allocate under lock only if new UE */
    int idx = ia_p5g_rnti_lookup(state, UE->rnti);
    if (idx < 0) {
        pthread_mutex_lock(&state->state_lock);
        idx = ia_p5g_rnti_get_or_alloc(state, UE->rnti);
        pthread_mutex_unlock(&state->state_lock);
        if (idx < 0) return;  /* table full — logged inside alloc */
    }

    NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;

    for (int i = 0; i < seq_arr_size(&sc->lc_config); i++) {
        const nr_lc_config_t *c = seq_arr_at(&sc->lc_config, i);
        const int lcid = c->lcid;
        if (lcid < 4) continue;  /* skip SRBs (LCID 1-3) */

        /* ── Tier-1 rate target for this LCID (bits/s).
         *    Returns 0.0 when Tier-1 has not yet solved (startup).
         *    VQ stays at 0 until Tier-1 runs — existing ordering applies. */
        float r_bps = atomic_load_explicit(
                &state->t1out.dl_target_bps[idx][lcid],
                memory_order_relaxed);

        /* ── Step 1: grow virtual queue by target inflow this slot ──── */
        state->vq_dl[idx][lcid] += r_bps * IA_P5G_SLOT_DURATION_S;

        /* ── Step 2: windowed ceiling clamp ─────────────────────────────
         * arrived_cum  ≈ bytes delivered + bytes still in RLC queue
         * delivered_cum = bytes delivered (cumulative, non-resetting)
         * Both sampled NOW; difference from hist gives window delta.     */
        uint64_t del_cum  = (uint64_t)UE->mac_stats.dl.lc_bytes[lcid];
        uint64_t arr_cum  = del_cum
                          + (uint64_t)sc->rlc_status[lcid].bytes_in_buffer;

        uint64_t arr_W = arr_cum - state->dl_arrived_hist[idx][lcid];
        uint64_t del_W = del_cum - state->dl_delivered_hist[idx][lcid];

        float target_W_bits  = r_bps * state->tier1_period_s;
        float arr_W_bits     = (float)(arr_W * 8);
        float del_W_bits     = (float)(del_W * 8);

        /* ceiling = max(0, min(target_W, arrived_W) − delivered_W)    */
        float ceiling = (arr_W_bits < target_W_bits ? arr_W_bits : target_W_bits)
                        - del_W_bits;
        if (ceiling < 0.0f) ceiling = 0.0f;

        /* Apply ceiling, then floor at zero */
        if (state->vq_dl[idx][lcid] > ceiling)
            state->vq_dl[idx][lcid] = ceiling;
        if (state->vq_dl[idx][lcid] < 0.0f)
            state->vq_dl[idx][lcid] = 0.0f;
    }
}

float ia_p5g_dl_metric(gNB_MAC_INST *mac,
                        NR_UE_info_t *UE,
                        float         spectral_eff)
{
    ia_p5g_crash_ctx = "ia_p5g_dl_metric";
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    if (!state) return 0.0f;

    int idx = ia_p5g_rnti_lookup(state, UE->rnti);
    if (idx < 0) return 0.0f;  /* unknown UE — fallback to PF tiers */

    NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;
    float sum_q = 0.0f;

    for (int i = 0; i < seq_arr_size(&sc->lc_config); i++) {
        const nr_lc_config_t *c = seq_arr_at(&sc->lc_config, i);
        const int lcid = c->lcid;
        if (lcid < 4) continue;
        /* Only count LCIDs with pending data — idle flows don't drive urgency */
        if (sc->rlc_status[lcid].bytes_in_buffer == 0) continue;
        sum_q += state->vq_dl[idx][lcid];
    }

    /* ue_metric = (Σ Q_f) × spectral_efficiency
     * When sum_q == 0 (Tier-1 not yet run or all flows on-target),
     * returns 0.0 and qsort falls back to has_gbr → pdb_ms tiers.       */
    return sum_q * spectral_eff;
}

/* LCP fill sort: priority ASC (lower 3GPP number = higher priority),
 * then VQ depth DESC (most behind target gets bytes first).              */
typedef struct {
    int      lcid;
    int      priority;
    float    q;       /* vq_dl[idx][lcid] */
    uint32_t backlog; /* rlc_status[lcid].bytes_in_buffer */
} lcp_cand_t;

static int lcp_cmp(const void *a, const void *b)
{
    const lcp_cand_t *x = (const lcp_cand_t *)a;
    const lcp_cand_t *y = (const lcp_cand_t *)b;
    if (x->priority != y->priority)
        return x->priority - y->priority; /* lower value = higher priority */
    if (x->q > y->q) return -1;          /* higher Q = more urgent */
    if (x->q < y->q) return  1;
    return 0;
}

void ia_p5g_compute_lcp_budget(gNB_MAC_INST *mac,
                                NR_UE_info_t *UE,
                                uint32_t      tbs_bytes)
{
    ia_p5g_crash_ctx = "ia_p5g_compute_lcp_budget";
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    if (!state) return;

    int idx = ia_p5g_rnti_lookup(state, UE->rnti);
    if (idx < 0) {
        pthread_mutex_lock(&state->state_lock);
        idx = ia_p5g_rnti_get_or_alloc(state, UE->rnti);
        pthread_mutex_unlock(&state->state_lock);
        if (idx < 0) return;
    }

    /* Reset all budgets to -1 (default pull).
     * SRBs (LCID < 4) keep -1 → nr_generate_dlsch_pdu pulls them freely.
     * DRBs with data are set to 0 below, then filled by greedy loop.     */
    memset(state->dl_lcid_budget[idx], 0xFF,
           sizeof(state->dl_lcid_budget[idx]));

    NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;

    /* Build candidate list — DRBs with pending data only */
    lcp_cand_t cands[IA_P5G_MAX_LCID];
    int n_cands = 0;
    for (int i = 0; i < seq_arr_size(&sc->lc_config); i++) {
        const nr_lc_config_t *c = seq_arr_at(&sc->lc_config, i);
        const int lcid = c->lcid;
        if (lcid < 4) continue;
        if (sc->rlc_status[lcid].bytes_in_buffer == 0) continue;

        cands[n_cands].lcid     = lcid;
        cands[n_cands].priority = c->qos_config[0].priority > 0
                                   ? c->qos_config[0].priority : 90;
        cands[n_cands].q        = state->vq_dl[idx][lcid];
        cands[n_cands].backlog  = sc->rlc_status[lcid].bytes_in_buffer;
        /* Pre-set to 0: this LCID competes but starts with zero allocation */
        state->dl_lcid_budget[idx][lcid] = 0;
        n_cands++;
    }
    if (n_cands == 0) return;

    /* Sort: priority ASC, Q DESC within same priority tier */
    qsort(cands, n_cands, sizeof(lcp_cand_t), lcp_cmp);

    /* Greedy fill: highest-priority, highest-deficit LCID gets bytes first */
    uint32_t remaining = tbs_bytes;
    for (int i = 0; i < n_cands && remaining > 0; i++) {
        uint32_t alloc = (cands[i].backlog < remaining)
                         ? cands[i].backlog : remaining;
        state->dl_lcid_budget[idx][cands[i].lcid] = (int)alloc;
        remaining -= alloc;
    }
}

void ia_p5g_drain_vq_dl(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE,
                          float         bler)
{
    ia_p5g_crash_ctx = "ia_p5g_drain_vq_dl";
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    if (!state) return;

    int idx = ia_p5g_rnti_lookup(state, UE->rnti);
    if (idx < 0) return;

    /* Clamp delivery_rate to [0, 1] */
    float delivery_rate = 1.0f - bler;
    if (delivery_rate < 0.0f) delivery_rate = 0.0f;
    if (delivery_rate > 1.0f) delivery_rate = 1.0f;

    NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;
    for (int i = 0; i < seq_arr_size(&sc->lc_config); i++) {
        const nr_lc_config_t *c = seq_arr_at(&sc->lc_config, i);
        const int lcid = c->lcid;
        if (lcid < 4) continue;

        int budget = state->dl_lcid_budget[idx][lcid];
        /* budget == -1: LCID had no budget (SRB or idle) — don't drain.
         * budget ==  0: LCID lost LCP competition — nothing delivered.
         * budget  >  0: bytes allocated to this LCID this TB.            */
        if (budget <= 0) continue;

        float delivered_bits = (float)budget * 8.0f * delivery_rate;
        state->vq_dl[idx][lcid] -= delivered_bits;
        if (state->vq_dl[idx][lcid] < 0.0f)
            state->vq_dl[idx][lcid] = 0.0f;
    }
}

int ia_p5g_get_lcid_budget(ia_p5g_state_t *state,
                            uint16_t        rnti,
                            int             lcid)
{
    ia_p5g_crash_ctx = "ia_p5g_get_lcid_budget";
    if (!state) return -1;

    /* SRBs bypass LCP budget — always use default pull */
    if (lcid < 4 || lcid >= IA_P5G_MAX_LCID) return -1;

    int idx = ia_p5g_rnti_lookup(state, rnti);
    if (idx < 0) return -1;

    return state->dl_lcid_budget[idx][lcid];
    /* Caller in nr_generate_dlsch_pdu():
     *   -1 → no budget set, use default pull (SRBs / unknown UE)
     *    0 → LCID lost LCP competition this TB, pull 0 bytes
     *   >0 → cap RLC pull to this many bytes                            */
}

/* =========================================================================
 * Tier-2 UL functions  
 *
 * ia_p5g_ul_metric() returns 0.0 so pf_ul()'s existing comparator falls
 * back to sched_inactive / has_gbr / pdb_ms ordering.
 * No behavioural regression at Checkpoint 1.
 * ========================================================================= */
/* ─────────────────────────────────────────────────────────────────────────
 * Local UE scheduling candidate struct + comparator for ia_p5g_pf_ul().
 * Structurally identical to UEsched_t/comparator() in gNB_scheduler_ulsch.c
 * (which are static there and not accessible here). sched_inactive UEs
 * (SR/inactivity keepalive, no data) sort first regardless of coef — this
 * is the existing UL inactive-UE PASS-1 mechanism, fully inherited here.
 * ───────────────────────────────────────────────────────────────────────── */
typedef struct {
    float          coef;            /* composite drift-plus-penalty metric  */
    float          base_q;          /* Σ virtual-queue deficit (pre-urgency)*/
    float          urgency01;       /* worst grant-age/PDB ratio in [0,1]   */
    float          spectral_eff;    /* per-slot TBS proxy for SE            */
    bool           sched_inactive;  /* control-plane class (SR/keepalive/CP)*/
    NR_UE_info_t  *UE;
    int            selected_mcs;
    int            pdb_ms;          /* retained for logging/telemetry only  */
    bool           has_gbr;         /* retained: read by 2nd-loop B_eff     */
    int            gbr_bytes_slot;  /* retained: read by 2nd-loop B_eff     */
    bool           floor_fire;      /* [FLOOR v2] service-interval floor fired
                                     * this slot -> 2nd loop must bypass the
                                     * demand-estimate sizing path.        */
    uint32_t       floor_sil;       /* [FLOOR v2.1] silence (slots) at fire.
                                     * Tie-break when >1 UE fires in the same
                                     * slot: longest-starved served first, so
                                     * the order is deterministic rather than
                                     * left to qsort on equal INF coefs.   */
} ia_p5g_ul_ue_t;

/* ─────────────────────────────────────────────────────────────────────────
 * [IA-P5G] Composite-metric comparator (design revision 2026-07).
 *
 * Previous form was lexicographic: sched_inactive → has_gbr → pdb_ms → coef,
 * which made the drift-plus-penalty metric a mere tiebreaker and let a GBR
 * flow with a 1-byte deficit permanently preempt a non-GBR flow with a huge
 * backlog (observed monopolization). That contradicts the two-tier design:
 * Tier-1 already encodes the GBR guarantee by SETTING the targets, so the
 * Tier-2 virtual-queue deficit already carries the GBR obligation. Enforcing
 * a separate has_gbr class double-counts it and breaks DPP convergence.
 *
 * Revised form has exactly TWO tiers:
 *   1. control plane (sched_inactive): SR / inactivity keepalive / cp_floor.
 *      These carry no Tier-1 target and no virtual queue; they are a
 *      correctness precondition (BSR / RLC STATUS / RRC delivery) and cannot
 *      be arbitrated by a metric they are not part of. Still lexicographic.
 *   2. everything else: sorted by the composite metric `coef` (descending),
 *      where coef = (base_q + delay_w·urgency^delay_exp·max_q)·SE. GBR and
 *      deadline handling now live INSIDE the metric, mirroring two_tier.py.
 * ───────────────────────────────────────────────────────────────────────── */
static int ia_p5g_ul_cmp(const void *p, const void *q)
{
    const ia_p5g_ul_ue_t *pp = p;
    const ia_p5g_ul_ue_t *qq = q;

    /* Tier 1 — control plane sorts ahead of all data UEs. */
    if (pp->sched_inactive && qq->sched_inactive) return 0;
    if (pp->sched_inactive) return -1;
    if (qq->sched_inactive) return  1;

    /* ── Tier 1.5 — [IA-P5G FLOOR v2.1] service-interval floor.
     * A floor-fired UE is in the fault state where BOTH composite inputs are
     * gated on estimated_ul_buffer_per_lcg[] > 0, which reads 0 by definition
     * of the fault: the urgency loop is skipped (urgency01 stays 0, so
     * Phi(0)=0) and vq_ul stops accruing (base_q ~ 0). Its coef is therefore
     * EXACTLY 0 -- the arithmetic minimum -- so under Tier 2 it would sort
     * dead last, behind a saturating flood, and be dropped at
     * `n_rb_sched < min_rb` before ever reaching the grant path. The floor
     * would fire, waste its attempt, increment floor_fruitless, and after
     * FRUITLESS_MAX self-disarm -- misreading "my grants were never issued"
     * as "this flow is idle".
     *
     * Ranking a fired floor above ordinary data UEs makes the rescue land.
     * It only needs to land ONCE: the resulting BSR resets sched_ul_bytes to
     * 0 and repopulates estimated_ul_buffer_per_lcg[], after which both
     * composite inputs are live and Tier 2 governs normally. Control plane
     * still outranks the floor (SRB/reconfig take only min_rb each, so they
     * cost the floor UE almost nothing).
     *
     * Ties (>1 UE firing in the same slot) break on longest silence so the
     * order is deterministic and readable in the A/B logs; the loser simply
     * re-fires after another theta. */
    if (pp->floor_fire && qq->floor_fire) {
        if (pp->floor_sil < qq->floor_sil) return  1;
        if (pp->floor_sil > qq->floor_sil) return -1;
        return 0;
    }
    if (pp->floor_fire) return -1;
    if (qq->floor_fire) return  1;

    /* Tier 2 — composite drift-plus-penalty metric, larger served first. */
    if (pp->coef < qq->coef) return  1;
    if (pp->coef > qq->coef) return -1;
    return 0;
}

int ia_p5g_pf_ul(gNB_MAC_INST            *mac,
                 post_process_pusch_t    *pp_pusch,
                 int                      tda,
                 const NR_tda_info_t     *tda_info,
                 NR_UE_info_t           **UE_list,
                 int                      max_num_ue,
                 int                      num_beams,
                 int                      n_rb_sched[])
{
    ia_p5g_crash_ctx = "ia_p5g_pf_ul: entry";

    /* ── Defensive entry checks ──────────────────────────────────────────
     * Required-pointer contract violations — caller bugs, not recoverable
     * runtime conditions. AssertFatal prints a clear message before
     * terminating, consistent with the rest of OAI.                       */
    AssertFatal(mac != NULL,        "[IA-P5G] ia_p5g_pf_ul: mac is NULL\n");
    AssertFatal(pp_pusch != NULL,   "[IA-P5G] ia_p5g_pf_ul: pp_pusch is NULL\n");
    AssertFatal(tda_info != NULL,   "[IA-P5G] ia_p5g_pf_ul: tda_info is NULL\n");
    AssertFatal(UE_list != NULL,    "[IA-P5G] ia_p5g_pf_ul: UE_list is NULL\n");
    AssertFatal(n_rb_sched != NULL, "[IA-P5G] ia_p5g_pf_ul: n_rb_sched is NULL\n");
    AssertFatal(num_beams > 0,      "[IA-P5G] ia_p5g_pf_ul: num_beams must be > 0 (got %d)\n", num_beams);

    /* ── Runtime condition: state not initialised ────────────────────────
     * Should never happen — the preprocessor only calls us when
     * sched_stateful_data != NULL — but if it does, fail soft: log clearly
     * and schedule nothing this call rather than crashing the gNB.        */
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    if (state == NULL) {
        IA_P5G_LOG_EXC_E(NR_MAC, "[IA-P5G] ia_p5g_pf_ul called but sched_stateful_data is "
              "NULL (%d.%d) — scheduling nothing this call\n",
              pp_pusch->frame, pp_pusch->slot);
        return 0;
    }

    const int CC_id = 0;
    int frame = pp_pusch->frame;
    int slot  = pp_pusch->slot;
    NR_ServingCellConfigCommon_t *scc = mac->common_channels[CC_id].ServingCellConfigCommon;
    if (scc == NULL) {
        IA_P5G_LOG_EXC_E(NR_MAC, "[IA-P5G] ia_p5g_pf_ul: ServingCellConfigCommon is NULL "
              "(%d.%d) — scheduling nothing this call\n", frame, slot);
        return 0;
    }

    int slots_per_frame = mac->frame_structure.numb_slots_frame;
    AssertFatal(tda_info->valid_tda, "[IA-P5G] ia_p5g_pf_ul: tda_info not valid\n");
    const int k2 = tda_info->k2 + get_NTN_Koffset(scc);
    const int sched_frame = (frame + (slot + k2) / slots_per_frame) % MAX_FRAME_NUMBER;
    const int sched_slot  = (slot + k2) % slots_per_frame;
    AssertFatal(is_ul_slot(sched_slot, &mac->frame_structure),
                "[IA-P5G] ia_p5g_pf_ul: sched_slot %d is not a UL slot\n", sched_slot);

    const int min_rb = mac->min_grant_prb;

    ia_p5g_ul_ue_t UE_sched[MAX_MOBILES_PER_GNB + 1] = {0};
    int remainUEs[num_beams];
    for (int i = 0; i < num_beams; i++)
        remainUEs[i] = max_num_ue;
    int numUE = 0;
    bool scheduled_something = false;

    /* ═══════════════════════════════════════════════════════════════════
     * FIRST LOOP — retransmissions (handled inline+committed here) +
     * candidate collection for new transmissions (queued into UE_sched)
     * ═══════════════════════════════════════════════════════════════════ */
    ia_p5g_crash_ctx = "ia_p5g_pf_ul: first loop";

    UE_iterator(UE_list, UE) {
        if (UE == NULL) continue;  /* defensive: should not happen, guard anyway */

        NR_UE_sched_ctrl_t *sched_ctrl = &UE->UE_sched_ctrl;
        if (!nr_mac_ue_is_active(UE)) {
            IA_P5G_SKIP(UE->rnti, skip_inactive);
            continue;
        }

        NR_UE_UL_BWP_t *current_BWP = &UE->current_UL_BWP;
        NR_mac_dir_stats_t *stats = &UE->mac_stats.ul;

        const float a = 0.01f;
        const uint32_t b = stats->current_bytes;
        UE->ul_thr_ue = (1 - a) * UE->ul_thr_ue + a * b;

        stats->current_bytes = 0;
        stats->current_rbs = 0;

        int total_rem_ues = 0;
        for (int i = 0; i < num_beams; i++)
            total_rem_ues += remainUEs[i];
        if (total_rem_ues == 0) {
            IA_P5G_SKIP(UE->rnti, skip_no_rem_ues);
            continue;
        }

        NR_beam_alloc_t dci_beam = beam_allocation_procedure(&mac->beam_info, frame, slot, UE->UE_beam_index, slots_per_frame);
        if (dci_beam.idx < 0) {
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] Beam could not be allocated\n", UE->rnti, frame, slot);
            IA_P5G_SKIP(UE->rnti, skip_dci_beam);
            continue;
        }

        NR_beam_alloc_t beam = beam_allocation_procedure(&mac->beam_info, sched_frame, sched_slot, UE->UE_beam_index, slots_per_frame);
        if (beam.idx < 0) {
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] Beam could not be allocated\n", UE->rnti, frame, slot);
            reset_beam_status(&mac->beam_info, frame, slot, UE->UE_beam_index, slots_per_frame, dci_beam.new_beam);
            IA_P5G_SKIP(UE->rnti, skip_data_beam);
            continue;
        }
        const int index = ul_buffer_index(sched_frame, sched_slot, slots_per_frame, mac->vrb_map_UL_size);
        uint16_t *rballoc_mask = &mac->common_channels[CC_id].vrb_map_UL[beam.idx][index * MAX_BWP_SIZE];

        /* retransmission — handled and committed entirely inline */
        int ul_harq_pid = sched_ctrl->retrans_ul_harq.head;
        if (ul_harq_pid >= 0) {
            bool r = allocate_ul_retransmission(mac, pp_pusch, rballoc_mask,
                                                &n_rb_sched[beam.idx], dci_beam.idx,
                                                UE, ul_harq_pid, scc, tda, tda_info);
            if (!r) {
                IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] UL retransmission could not be allocated\n", UE->rnti, frame, slot);
                { ia_p5g_ul_summary_t *_s = ia_p5g_ul_summary_get(UE->rnti); if (_s) _s->retx_blocked++; }
                reset_beam_status(&mac->beam_info, sched_frame, sched_slot, UE->UE_beam_index, slots_per_frame, beam.new_beam);
                reset_beam_status(&mac->beam_info, frame, slot, UE->UE_beam_index, slots_per_frame, dci_beam.new_beam);
                continue;
            }
            { ia_p5g_ul_summary_t *_s = ia_p5g_ul_summary_get(UE->rnti); if (_s) _s->retx_grants++; }
            remainUEs[beam.idx]--;
            scheduled_something = true;
            continue;
        }
        AssertFatal(ul_harq_pid == -1, "[IA-P5G] ia_p5g_pf_ul: unexpected harq_pid %d\n", ul_harq_pid);

        if (sched_ctrl->available_ul_harq.head < 0) {
            reset_beam_status(&mac->beam_info, sched_frame, sched_slot, UE->UE_beam_index, slots_per_frame, beam.new_beam);
            reset_beam_status(&mac->beam_info, frame, slot, UE->UE_beam_index, slots_per_frame, dci_beam.new_beam);
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] has no free UL HARQ process, skipping\n", UE->rnti, frame, slot);
            { ia_p5g_ul_summary_t *_s = ia_p5g_ul_summary_get(UE->rnti); if (_s) _s->harq_exhausted++; }
            continue;
        }

        const int B = max(0, sched_ctrl->estimated_ul_buffer - sched_ctrl->sched_ul_bytes);

        const bool do_sched = nr_UE_is_to_be_scheduled(&mac->frame_structure, UE, sched_frame, sched_slot,
                                                        mac->ulsch_max_frame_inactivity);

        /* [IA-P5G STALL PROBE] These two conditions were fused in one
         * `if`, so a skip here was ambiguous between "nothing to send"
         * (benign) and "transmission interrupted" (a stall). They are
         * counted separately now: transm_intr firing while last_bsr is
         * large is the signature of the frozen-buffer failure.        */
        /* [IA-P5G FLOOR] ia_floor_fire is read again at the sched_inactive
         * decision below: a fired floor behaves exactly like an arrived SR
         * (do_sched), so the UE takes the existing CTRL-crumb or
         * deficit-sized-DATA path -- no new allocation machinery.       */
        bool ia_floor_fire = false;
        uint32_t ia_floor_sil = 0;   /* [FLOOR v2.1] silence at fire, for tie-break */
        {
            const bool _empty  = (B == 0 && !do_sched);
            const bool _intr   = nr_timer_is_active(&sched_ctrl->transm_interrupt);

#if IA_P5G_UL_FLOOR_ENABLE
            /* ── [IA-P5G FLOOR] Tier-1 service-interval floor. Runs ABOVE
             * the candidacy skip because that skip is precisely where a
             * desynced UE dies (B is DERIVED and can read 0 while the UE
             * holds data; see block comment at the FLOOR defines).
             * Respects transm_interrupt (a legitimate PHY hold) and the
             * HARQ-exhausted skip above (a fired floor still needs a free
             * HARQ process; that gate already ran).                     */
            ia_p5g_ul_summary_t *_fl = ia_p5g_ul_summary_get(UE->rnti);
            if (_fl && sched_ctrl->has_pending_gbr && !_intr) {
                /* Evidence of delivery: total UL MAC bytes on data LCIDs.
                 * lcid = lcg + 3 (project convention, see update_vq_ul). */
                uint64_t _rx = 0;
                for (int _lg = 1; _lg < IA_P5G_MAX_LCG; _lg++)
                    _rx += (uint64_t)UE->mac_stats.ul.lc_bytes[_lg + 3];

                /* Deficit read for TELEMETRY ONLY in v2 -- it is NOT an
                 * arming input. v1 armed on (B>0 || deficit>0 || vq>0),
                 * all estimate-derived: B==0 defines the fault and vq_ul
                 * stops updating once the per-LCG estimate reads 0, so
                 * arming rested entirely on the deficit staying non-zero,
                 * which happens only while GBR is provisioned well above
                 * the offered rate. See the v2 block comment.           */
                int32_t _defsum = 0;
                for (int _lg = 0; _lg < 8; _lg++)
                    _defsum += sched_ctrl->ul_lcg_deficit_bytes[_lg];

                /* Silence measured in absolute slot time (wraps at 1024
                 * frames), NOT in pf_ul visits -- visits are UL-slot paced
                 * and would stretch theta by the TDD UL duty cycle.     */
                const uint32_t _now_abs = (uint32_t)frame * (uint32_t)slots_per_frame
                                        + (uint32_t)slot;
                const uint32_t _wrap    = 1024u * (uint32_t)slots_per_frame;
                const float    _slot_ms_arm = 10.0f / (float)slots_per_frame;
                uint32_t _sil = (_now_abs + _wrap - _fl->floor_last_move_slot) % _wrap;

                if (_rx != _fl->floor_rx_lastseen) {
                    /* Bytes actually moved: the UE is transmitting. Restart
                     * the timer, clear fruitless history, refresh liveness. */
                    _fl->floor_rx_lastseen    = _rx;
                    _fl->floor_last_move_slot = _now_abs;
                    _fl->floor_alive_slot     = _now_abs;
                    _fl->floor_alive_valid    = true;
                    _fl->floor_fruitless      = 0;
                    _fl->floor_disarmed       = false;
                    _sil = 0;
                }
                /* ── ARMING (v2): delivery history only. "This flow moved
                 * bytes within FLOOR_ALIVE_MS" is independent of every
                 * signal the desync corrupts. A UE that has genuinely gone
                 * quiet for longer than the window is treated as idle: the
                 * timer stops accumulating, so no fire and no phantom debt. */
                const uint32_t _alive_age =
                    _fl->floor_alive_valid
                        ? (_now_abs + _wrap - _fl->floor_alive_slot) % _wrap
                        : _wrap;
                const uint32_t _alive_max =
                    (uint32_t)((float)IA_P5G_UL_FLOOR_ALIVE_MS / _slot_ms_arm);
                const bool _armed = _fl->floor_alive_valid && (_alive_age <= _alive_max);

                if (B > 0) {   /* hard evidence of backlog: always re-arm */
                    _fl->floor_disarmed = false;
                    _fl->floor_fruitless = 0;
                }
                if (!_armed) {
                    /* Idle beyond the liveness window: don't accumulate. */
                    _fl->floor_last_move_slot = _now_abs;
                    _sil = 0;
                }
                _fl->floor_silence_snap = _sil;

                int _pdb = sched_ctrl->best_pending_pdb_ms;
                if (_pdb <= 0 || _pdb >= 9999) _pdb = 100;
                const float _slot_ms_fl = 10.0f / (float)slots_per_frame;
                uint32_t _theta = (uint32_t)(((float)_pdb / (float)IA_P5G_UL_FLOOR_PDB_DIV)
                                             / _slot_ms_fl);
                if (_theta < IA_P5G_UL_FLOOR_MIN_SLOTS) _theta = IA_P5G_UL_FLOOR_MIN_SLOTS;

                /* ── [FIX A] Fruitless counter: DECAY, then BACKOFF ───────
                 * v2 latched: FRUITLESS_MAX consecutive fires that moved no
                 * bytes set floor_disarmed, and the only ways out were
                 * _rx movement or B > 0 -- neither of which a desynced UE
                 * on a bad link can produce. So the floor gave up
                 * permanently at exactly the moment it was needed, and it
                 * did so after burning 3 FULL-BWP grants (v2 sizing), not
                 * 3 crumbs. Two changes:
                 *   (i)  the counter decays one step per FRUITLESS_DECAY_MS
                 *        of no further fires, so an isolated probe long ago
                 *        does not pre-penalise a genuine fault later;
                 *   (ii) reaching FRUITLESS_MAX no longer stops the floor.
                 *        It performs the one-time deficit forgiveness and
                 *        then keeps probing at theta << fruitless (capped),
                 *        i.e. cost against a truly idle UE is logarithmic
                 *        in silence rather than a cliff, and a UE whose
                 *        grants are failing to decode still gets retried. */
                if (_fl->floor_fruitless > 0) {
                    const uint32_t _fr_age =
                        (_now_abs + _wrap - _fl->floor_fruitless_slot) % _wrap;
                    uint32_t _fr_decay =
                        (uint32_t)((float)IA_P5G_UL_FLOOR_FRUITLESS_DECAY_MS / _slot_ms_arm);
                    if (_fr_decay == 0) _fr_decay = 1;
                    const uint32_t _steps = _fr_age / _fr_decay;
                    if (_steps > 0) {
                        _fl->floor_fruitless = (_steps >= _fl->floor_fruitless)
                                             ? 0u : (_fl->floor_fruitless - _steps);
                        _fl->floor_fruitless_slot = _now_abs;
                        if (_fl->floor_fruitless == 0)
                            _fl->floor_disarmed = false;   /* backoff fully unwound */
                    }
                }

                uint32_t _shift = _fl->floor_fruitless;
                if (_shift > IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX)
                    _shift = IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX;
                const uint32_t _theta_eff = _theta << _shift;

                /* ── [FIX B] Adequacy trigger ─────────────────────────────
                 * The _empty gate catches total candidacy loss (blackout)
                 * but not the TRICKLE: during it the UE is periodically a
                 * candidate and bytes do move, so the delivery timer keeps
                 * resetting and the floor never fires even though service
                 * is far below the offered rate. Session-4 §5 deferred the
                 * obvious "deficit > 0" trigger because deficit > 0 is
                 * ordinary under congestion and firing there would change
                 * behaviour broadly.
                 * The signature used here is narrower and specific to the
                 * observed fault: a RUN of consecutive min_rb-sized grants.
                 * That is what the measured trickle was (~275 crumbs at
                 * ~0.44 Mbps) and it is not what congestion looks like --
                 * a congested UE gets demand-sized grants that merely
                 * arrive less often, not a monotonic run of min_rb.
                 * Rate-limited, and BACKED OFF geometrically: the blackout
                 * path's fruitless counter cannot bound this one, because a
                 * trickle by definition keeps moving bytes and so keeps
                 * clearing it. Without a separate bound, a UE that is merely
                 * congested -- repeatedly handed min_rb by the FIX-2 reserve
                 * while ranked low -- would draw a full-BWP grant every
                 * theta indefinitely, which is precisely the broad
                 * behaviour change §5 warned about. floor_adq_backoff
                 * doubles the retry period per adequacy fire (capped) and
                 * decays once the trickle stops, so a genuine fault gets a
                 * prompt rescue while a persistent one settles to a bounded
                 * background rate.                                        */
                uint32_t _adq_age =
                    (_now_abs + _wrap - _fl->floor_adq_slot) % _wrap;
                {   /* decay the adequacy backoff on the same clock */
                    uint32_t _fr_decay =
                        (uint32_t)((float)IA_P5G_UL_FLOOR_FRUITLESS_DECAY_MS / _slot_ms_arm);
                    if (_fr_decay == 0) _fr_decay = 1;
                    if (_fl->floor_adq_backoff > 0 && _adq_age >= _fr_decay) {
                        const uint32_t _asteps = _adq_age / _fr_decay;
                        _fl->floor_adq_backoff = (_asteps >= _fl->floor_adq_backoff)
                                               ? 0u : (_fl->floor_adq_backoff - _asteps);
                    }
                }
                uint32_t _adq_shift = _fl->floor_adq_backoff;
                if (_adq_shift > IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX)
                    _adq_shift = IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX;
                const uint32_t _adq_period = _theta_eff << _adq_shift;

                const bool _adq_fire =
                    IA_P5G_UL_FLOOR_ADQ_ENABLE && _armed && !_empty
                    && (_fl->floor_crumb_run >= IA_P5G_UL_FLOOR_ADQ_CRUMB_RUN)
                    && (_adq_age >= _adq_period);

                const bool _empty_fire = _armed && _empty && (_sil >= _theta_eff);

                if (_empty_fire || _adq_fire) {
                    /* One-time evidence-based forgiveness of a stale deficit
                     * once the flow has proved unresponsive. No longer a
                     * stop condition -- see [FIX A] above.               */
                    if (_fl->floor_fruitless >= IA_P5G_UL_FLOOR_FRUITLESS_MAX
                        && !_fl->floor_disarmed) {
                        _fl->floor_disarmed = true;
                        for (int _lg = 0; _lg < 8; _lg++)
                            sched_ctrl->ul_lcg_deficit_bytes[_lg] = 0;
                    }

                    ia_floor_fire = true;
                    ia_floor_sil  = _sil;
                    _fl->floor_fires_w++;
                    _fl->floor_last_move_slot = _now_abs;  /* attempt made */

                    if (_adq_fire) {
                        _fl->floor_adq_fires_w++;
                        _fl->floor_adq_slot  = _now_abs;
                        _fl->floor_crumb_run = 0;   /* need a fresh run to re-fire */
                        if (_fl->floor_adq_backoff
                              <= IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX)
                            _fl->floor_adq_backoff++;
                    } else {
                        /* Blackout path only: no bytes are moving, so this
                         * attempt is provisionally fruitless. The adequacy
                         * path is excluded because bytes ARE moving there,
                         * and _rx movement clears the counter anyway.    */
                        if (_fl->floor_fruitless
                              <= IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX)
                            _fl->floor_fruitless++;
                        _fl->floor_fruitless_slot = _now_abs;
                    }

                    IA_P5G_LOG_EXC_W(NR_MAC,
                          "[P5G-UL-FLOOR][%4d.%2d][UE %04x] service-interval floor FIRED "
                          "(%s): no UL delivery for %u slots (theta=%u eff=%u, pdb=%dms) "
                          "with B=%d deficit=%d alive_age=%u crumb_run=%u -- forcing "
                          "DATA-class grant (fruitless=%u)\n",
                          frame, slot, UE->rnti, _adq_fire ? "adequacy" : "blackout",
                          _sil, _theta, _theta_eff, _pdb,
                          B, _defsum, _alive_age, _fl->floor_crumb_run,
                          _fl->floor_fruitless);
                }
            }
#endif /* IA_P5G_UL_FLOOR_ENABLE */

            if ((_empty && !ia_floor_fire) || _intr) {
                if (_intr) IA_P5G_SKIP(UE->rnti, skip_transm_intr);
                else       IA_P5G_SKIP(UE->rnti, skip_empty);
                reset_beam_status(&mac->beam_info, sched_frame, sched_slot, UE->UE_beam_index, slots_per_frame, beam.new_beam);
                reset_beam_status(&mac->beam_info, frame, slot, UE->UE_beam_index, slots_per_frame, dci_beam.new_beam);
                continue;
            }
        }

        const NR_bler_options_t *bo = &mac->ul_bler;
        const int max_mcs_table = (current_BWP->mcs_table == 0 || current_BWP->mcs_table == 2) ? 28 : 27;
        const int max_mcs = min(bo->max_mcs, max_mcs_table);
        int selected_mcs;
        int nrOfLayers = get_ul_nrOfLayers(sched_ctrl, current_BWP->dci_format);
        if (bo->harq_round_max == 1) {
            selected_mcs = get_mcs_from_SINRx10(current_BWP->mcs_table, sched_ctrl->pusch_snrx10, nrOfLayers);
            selected_mcs = min(max_mcs, selected_mcs);
            selected_mcs = max(bo->min_mcs, selected_mcs);
            sched_ctrl->ul_bler_stats.mcs = selected_mcs;
        } else {
            selected_mcs = get_mcs_from_bler(bo, stats, &sched_ctrl->ul_bler_stats, max_mcs, frame);
        }

        const uint8_t  Qm = nr_get_Qm_ul(selected_mcs, current_BWP->mcs_table);
        const uint16_t R  = nr_get_code_rate_ul(selected_mcs, current_BWP->mcs_table);
        const uint32_t tbs = nr_compute_tbs(Qm, R, 1, 10, 0, 0, 0, nrOfLayers) >> 3;

        int prio = sched_ctrl->best_pending_priority;
        if (prio <= 0 || prio > 900)
            prio = 90;

        /* ── UL per-LCG remaining PDB + deficit + total target ──────────
         * Unchanged from original pf_ul(): mutates persistent per-UE
         * state (ul_lcg_deficit_bytes, ul_gbr_silence_slots) and sets
         * ul_best_remaining_pdb_ms / ul_has_unfulfilled_gbr /
         * ul_total_target_bytes, all read later (sched_inactive flag,
         * UE_sched population, and B_eff in the second loop).            */
        const int      _spf_ul = slots_per_frame;
        const float    _sms_ul = 10.0f / (float)_spf_ul;
        const uint32_t now_ul  = (uint32_t)frame * _spf_ul + slot;

        sched_ctrl->ul_best_remaining_pdb_ms = 9999;
        sched_ctrl->ul_has_unfulfilled_gbr   = false;
        sched_ctrl->ul_total_target_bytes    = 0;

        /* [IA-P5G] Worst deadline-urgency ratio across this UE's flows,
         * in [0,1]. hol is unobservable on UL, so use grant-age as proxy:
         * urgency01 = 1 - rem_pdb/pdb  (0 = just served, 1 = at/over PDB). */
        float ue_worst_urgency01 = 0.0f;

        for (int _lcg = 0; _lcg < 8; _lcg++) {
            if (sched_ctrl->estimated_ul_buffer_per_lcg[_lcg] <= 0) continue;
            int target_lcid = _lcg + 3;
            for (int _i = 0; _i < seq_arr_size(&sched_ctrl->lc_config); _i++) {
                const nr_lc_config_t *_c = seq_arr_at(&sched_ctrl->lc_config, _i);
                if (_c->lcid != target_lcid) continue;
                const NR_QoS_config_t *_qc = &_c->qos_config[0];
                const int _pdb  = _qc->pdb_ms  > 0 ? _qc->pdb_ms  : 300;
                const int _ppri = _qc->priority > 0 ? _qc->priority : 90;

                int _rem_pdb = _pdb;
                if (sched_ctrl->ul_lcg_last_grant_slot[_lcg] > 0) {
                    uint32_t _last = sched_ctrl->ul_lcg_last_grant_slot[_lcg];
                    float    _age  = (float)((now_ul - _last + 1024 * _spf_ul)
                                              % (1024 * _spf_ul)) * _sms_ul;
                    _rem_pdb = _pdb - (int)_age;
                    if (_rem_pdb < 0) _rem_pdb = 0;
                }
                if (_rem_pdb < sched_ctrl->ul_best_remaining_pdb_ms)
                    sched_ctrl->ul_best_remaining_pdb_ms = _rem_pdb;

                /* [IA-P5G] Defect 1 fix — priority-weighted scalarization.
                 * Fold this flow's grant-age lateness into the UE's scalar
                 * urgency as (urgency_ratio · prio_weight), taking the max
                 * over flows. prio_weight rises toward 1 for stronger 3GPP
                 * priority (lower _ppri) and floors at IA_P5G_URG_PRIO_W_MIN
                 * for the weakest, so a late high-priority flow (C2) outranks
                 * a late low-priority flow (video) at equal lateness, instead
                 * of the raw max treating them identically. _pdb >= 1 always. */
                {
                    float _u = 1.0f - ((float)_rem_pdb / (float)_pdb);
                    if (_u < 0.0f) _u = 0.0f;
                    if (_u > 1.0f) _u = 1.0f;

                    float _pw = IA_P5G_URG_PRIO_W_MIN
                              + (1.0f - IA_P5G_URG_PRIO_W_MIN)
                                * (1.0f - ((float)(_ppri - 1)
                                           / (IA_P5G_URG_PRIO_MAX - 1.0f)));
                    if (_pw < IA_P5G_URG_PRIO_W_MIN) _pw = IA_P5G_URG_PRIO_W_MIN;
                    if (_pw > 1.0f)                  _pw = 1.0f;

                    /* GBR-met release: scale urgency by how far this flow is
                     * behind its GUARANTEE, not its backlog. delta in [0,1]:
                     * ~1 when GBR deficit is near its window (far behind), ->
                     * URG_GBR_FLOOR as the deficit collapses (guarantee met),
                     * so a met-GBR flow with leftover backlog stops winning on
                     * the deadline barrier. Non-GBR flows (no gbr_ul_guaranteed)
                     * keep delta=1 — their deadline is ungated. Uses the
                     * deficit as accrued through the previous slot (the update
                     * below is one slot later); the lag is immaterial.        */
                    float _delta = 1.0f;
                    if (_c->gbr_ul_guaranteed > 0) {
                        int _obl_d = (int)(_c->gbr_ul_guaranteed / 8) / (_spf_ul * 100);
                        if (_obl_d < 1) _obl_d = 1;
                        int _win_d = _obl_d * (int)(_pdb / _sms_ul);
                        if (_win_d < 1) _win_d = 1;
                        int _def_d = sched_ctrl->ul_lcg_deficit_bytes[_lcg];
                        if (_def_d < 0) _def_d = 0;
                        float _dr = (float)_def_d / (float)_win_d;
                        if (_dr > 1.0f) _dr = 1.0f;
                        _delta = IA_P5G_URG_GBR_FLOOR
                                 + (1.0f - IA_P5G_URG_GBR_FLOOR) * _dr;
                    }

                    float _uw = _u * _pw * _delta;
                    if (_uw > ue_worst_urgency01) ue_worst_urgency01 = _uw;
                }

                if (_c->gbr_ul_guaranteed > 0) {
                    int _obl = (int)(_c->gbr_ul_guaranteed / 8) / (_spf_ul * 100);
                    if (_obl < 1) _obl = 1;
                    sched_ctrl->ul_lcg_deficit_bytes[_lcg] += _obl;
                    int _window = _obl * (int)(_pdb / _sms_ul);
                    if (sched_ctrl->ul_lcg_deficit_bytes[_lcg] > _window)
                        sched_ctrl->ul_lcg_deficit_bytes[_lcg] = _window;
                    if (sched_ctrl->ul_lcg_deficit_bytes[_lcg] > 0)
                        sched_ctrl->ul_has_unfulfilled_gbr = true;
                    int _rem_slots = (int)(_rem_pdb / _sms_ul);
                    if (_rem_slots < 1) _rem_slots = 1;
                    int _deficit = sched_ctrl->ul_lcg_deficit_bytes[_lcg];
                    int _target  = (_deficit + _obl) / _rem_slots;
                    if (_target < _obl) _target = _obl;
                    int _max_burst = (int)(_c->gbr_ul_max / 8) / (_spf_ul * 100) * 2;
                    if (_max_burst < _obl * 2) _max_burst = _obl * 2;
                    if (_target > _max_burst) _target = _max_burst;
                    sched_ctrl->ul_total_target_bytes += _target;
                } else {
                    sched_ctrl->ul_total_target_bytes +=
                        sched_ctrl->estimated_ul_buffer_per_lcg[_lcg];
                }
                if (_ppri < prio) prio = _ppri;
                break;
            }
        }
        if (B == 0 && sched_ctrl->has_pending_gbr) {
            sched_ctrl->ul_gbr_silence_slots++;
            int _thresh = (int)(sched_ctrl->best_pending_pdb_ms / _sms_ul);
            if ((int)sched_ctrl->ul_gbr_silence_slots > _thresh) {
#if !IA_P5G_UL_FLOOR_ENABLE
                /* Pre-floor behaviour: TIME-based forgiveness. After PDB
                 * worth of silence the deficit was zeroed -- which forgave
                 * the flow's entitlement exactly when it had been starved
                 * longest (the inverse of a floor). Kept only for the
                 * floor-disabled A/B build.                             */
                for (int _lcg = 0; _lcg < 8; _lcg++)
                    sched_ctrl->ul_lcg_deficit_bytes[_lcg] = 0;
#endif
                /* [IA-P5G FLOOR] With the floor enabled, forgiveness is
                 * EVIDENCE-based instead: the floor offers grants, and only
                 * after IA_P5G_UL_FLOOR_FRUITLESS_MAX fruitless ones is
                 * the deficit cleared (see floor disarm above the skip).
                 * The counter itself is kept for telemetry continuity.  */
                sched_ctrl->ul_gbr_silence_slots = 0;
            }
        } else if (B > 0) {
            sched_ctrl->ul_gbr_silence_slots = 0;
        }

        /* ── TwoTier hook 1: grow + windowed-clamp virtual queue ──────── */
        ia_p5g_update_vq_ul(mac, UE);

        /* ── TwoTier hook 2: composite DPP metric.  ia_p5g_ul_metric now
         *    returns the BASE deficit Σ Q_g only; the deadline-urgency term
         *    and the spectral-efficiency factor are folded in after the
         *    first loop, once max_q across all candidates is known (the sim
         *    scales urgency by max_q — see the composite pass below).    */
        const float base_q       = ia_p5g_ul_metric(mac, UE, (float)tbs);
        const float spectral_eff = (float)tbs;

        int gbr_bytes_slot = 0;
        if (sched_ctrl->has_pending_gbr) {
            for (int i = 0; i < seq_arr_size(&sched_ctrl->lc_config); i++) {
                const nr_lc_config_t *c = seq_arr_at(&sched_ctrl->lc_config, i);
                int lcg = c->lcid - 3;
                if (lcg < 0 || lcg > 7) continue;
                if (sched_ctrl->estimated_ul_buffer_per_lcg[lcg] <= 0) continue;
                if (c->gbr_ul_guaranteed == 0) continue;
                int floor = (c->gbr_ul_guaranteed / 8) / (slots_per_frame * 100);
                if (floor > gbr_bytes_slot)
                    gbr_bytes_slot = floor;
            }
        }

        /* ── [IA-P5G FIX-1] Control-plane / detail-less UL floor ──────────
         * If the UE has pending UL bytes (B > 0) but NONE of them are on a
         * data LCG (1-7), the GBR-deficit and remaining-PDB loops above saw
         * nothing: has_gbr = false, pdb_ms = 9999.  This happens when the
         * pending bytes are SRB traffic (LCG 0: RLC STATUS PDUs,
         * RRCReconfigurationComplete, ...) or an SR-derived nominal buffer
         * with no BSR detail yet.  Without this clause such a UE also fails
         * the (B == 0) test for sched_inactive, so it competes in the LOWEST
         * scheduling class.  Under saturation by another UE it then starves
         * indefinitely: no grant → its BSR / RLC STATUS / RRC Complete can
         * never be delivered → the state that demoted it never clears.
         * Observed as a 55 s UL grant freeze with SRB1 max-RETX RLF storm
         * and a stuck RRC reconfiguration (contention-poisoning run,
         * 2026-07: RNTIs 614b/7605).
         *
         * Remedy: schedule it like sched_inactive — first class in the
         * comparator, one min_rb grant — which is exactly enough to carry
         * the BSR and SRB1 PDUs and restore normal QoS classification.
         * Cost while active: min_rb PRBs/slot (control plane must flow).  */
        int data_lcg_bytes = 0;
        for (int _lcg = 1; _lcg < 8; _lcg++)
            if (sched_ctrl->estimated_ul_buffer_per_lcg[_lcg] > 0)
                data_lcg_bytes += sched_ctrl->estimated_ul_buffer_per_lcg[_lcg];
        const bool cp_floor = (B > 0) && (data_lcg_bytes == 0);

        /* [IA-P5G] Reconfig-pending floor. A UE that owes an
         * RRCReconfigurationComplete (UE->await_reconfig, set when the gNB
         * replaces its CellGroupConfig) MUST get UL grants to deliver that
         * SRB1 message, or the whole bearer wedges: no reconfig-complete →
         * stale SRS/TA → the UE stays unschedulable until its peer's traffic
         * happens to stop. Observed as the 55s RA/reconfig freeze
         * (d639 32.0→88.3s). Unlike cp_floor this must fire even when the UE
         * has a data backlog AND unfulfilled GBR, because control-plane
         * recovery gates everything else — so it overrides the GBR-class
         * exclusion below. One min_rb grant/slot carries the complete (and a
         * fresh BSR), after which await_reconfig clears and the UE competes
         * normally again. Self-limiting: the flag clears on delivery. */
        const bool reconfig_floor = UE->await_reconfig && (B > 0);

        /* [IA-P5G] Explicit SRB (control-plane signalling) protection floor.
         * SRBs are LCID 1-3 (SRB1/2/3): RRC signalling, RLC STATUS,
         * measurement reports, reconfiguration -- the control plane. They
         * must NEVER be starved behind data. cp_floor above already promotes
         * a UE whose ONLY backlog is control-plane (data_lcg_bytes == 0), but
         * it does NOT fire when a UE has SRB traffic AND data queued at the
         * same time -- there the SRB PDUs could sit behind the UE's own data
         * under contention. This floor closes that gap: if there are pending
         * SRB bytes at all, force the UE into the top (control-plane) class
         * this slot, regardless of data backlog or unfulfilled GBR. One
         * min_rb grant carries the signalling; SRBs then bypass the LCP byte
         * budget (see ia_p5g_ul_lcp_budget: lcid < 4 -> unlimited pull), so
         * they are filled first within the TB. Net: control-plane always
         * wins, by construction, in both the inter-UE sort and the intra-TB
         * fill. LCG 0 aggregates the SRBs in the UL BSR. */
        int srb_pending_bytes = sched_ctrl->estimated_ul_buffer_per_lcg[0];
        const bool srb_floor = (srb_pending_bytes > 0);

        bool sched_inactive;
        if (reconfig_floor || srb_floor)
            sched_inactive = true;   /* control-plane (reconfig or any SRB) takes precedence */
        else
            /* [IA-P5G FLOOR v2] ia_floor_fire deliberately does NOT appear
             * here. v1 OR-ed it with do_sched, which made sched_inactive
             * true (B==0 and ul_has_unfulfilled_gbr false in this fault)
             * and routed the fire to the control-plane class -- whose
             * grant is a hardcoded min_rb crumb (2nd loop). An SR carries
             * no information, so a probe grant is the right answer to an
             * SR; the floor is the opposite case -- we already know this
             * is a GBR flow overdue by theta, so the need is to move bytes
             * OUT, not to elicit a BSR. Keeping the DATA class gives the
             * fire max_rbSize = bwpSize minus the FIX-2 GBR reserve.    */
            sched_inactive = ((B == 0 && do_sched) || cp_floor)
                             && !sched_ctrl->ul_has_unfulfilled_gbr;

        /* ── [IA-P5G] Always-on BSR/deficit snapshot into the summary table.
         *    Cheap (8-iteration max/sum, no formatting/I/O) and independent
         *    of IA_P5G_TELEMETRY -- this is what lets [P5G-UL-SUMMARY] catch
         *    a UE that's silently backlogged even when the per-slot
         *    telemetry below is compiled OFF for a long run.               */
        {
            ia_p5g_ul_summary_t *_sum = ia_p5g_ul_summary_get(UE->rnti);
            if (_sum) {
                int _max_bsr = 0;
                int32_t _def_sum = 0;
                for (int _lg2 = 0; _lg2 < 8; _lg2++) {
                    if (sched_ctrl->estimated_ul_buffer_per_lcg[_lg2] > _max_bsr)
                        _max_bsr = sched_ctrl->estimated_ul_buffer_per_lcg[_lg2];
                    _def_sum += sched_ctrl->ul_lcg_deficit_bytes[_lg2];
                }
                _sum->last_bsr = _max_bsr;
                _sum->last_deficit_sum = _def_sum;
            }
        }

        /* ── [IA-P5G TELEMETRY] Per-UE UL scheduling snapshot (always on,
         *    LOG_I). One header line with UE-level state, then one line per
         *    active/deficit-bearing LCG with the full QoS + queue detail the
         *    scheduler actually used this slot. Grant RESULT (rbSize/tb_size/
         *    mcs) is logged separately in the second loop (see UL-GRANT).
         *    Prefix [P5G-UL] is grep-friendly: `grep P5G-UL <log>`.        */
        if (IA_P5G_TELEMETRY_UL) {
            ia_p5g_state_t *_st = (ia_p5g_state_t *)mac->sched_stateful_data;
            int _idx = _st ? ia_p5g_rnti_lookup(_st, UE->rnti) : -1;
            LOG_I(NR_MAC,
                  "[P5G-UL][%4d.%2d][UE %04x] class=%s B=%d est_buf=%d sched_ul=%d "
                  "data_lcg=%d tgt_bytes=%d gbr_slot=%d base_q=%.1f urg01=%.2f "
                  "mcs=%d tbs=%d prio=%d rem_pdb=%dms has_gbr=%d cp_floor=%d recfg=%d srb=%d thr=%.0f\n",
                  frame, slot, UE->rnti,
                  reconfig_floor ? "RECFG" : (srb_floor ? "SRBFL" : (cp_floor ? "CPFLR" : (sched_inactive ? "INACT" : "DATA"))),
                  B, sched_ctrl->estimated_ul_buffer, sched_ctrl->sched_ul_bytes,
                  data_lcg_bytes, sched_ctrl->ul_total_target_bytes, gbr_bytes_slot,
                  base_q, ue_worst_urgency01, selected_mcs, tbs, prio,
                  sched_ctrl->ul_best_remaining_pdb_ms, sched_ctrl->ul_has_unfulfilled_gbr,
                  cp_floor, reconfig_floor, srb_floor, UE->ul_thr_ue);

            for (int _lg = 0; _lg < 8; _lg++) {
                int   _bsr = sched_ctrl->estimated_ul_buffer_per_lcg[_lg];
                int   _def = sched_ctrl->ul_lcg_deficit_bytes[_lg];
                float _vq  = (_idx >= 0) ? _st->vq_ul[_idx][_lg] : 0.0f;
                if (_bsr <= 0 && _def <= 0 && _vq <= 0.0f) continue;  /* skip idle LCGs */
                int _fqi = -1, _lcprio = -1, _lpdb = -1;
                uint64_t _ggbr = 0, _gmbr = 0;
                int _tlcid = _lg + 3;
                for (int _i = 0; _i < seq_arr_size(&sched_ctrl->lc_config); _i++) {
                    const nr_lc_config_t *_c = seq_arr_at(&sched_ctrl->lc_config, _i);
                    if (_c->lcid != _tlcid) continue;
                    _fqi    = _c->qos_config[0].fiveQI;
                    _lcprio = _c->qos_config[0].priority;
                    _lpdb   = _c->qos_config[0].pdb_ms;
                    _ggbr   = _c->gbr_ul_guaranteed;
                    _gmbr   = _c->gbr_ul_max;
                    break;
                }
                LOG_I(NR_MAC,
                      "[P5G-UL-LCG][%4d.%2d][UE %04x] lcg=%d lcid=%d 5qi=%d prio=%d pdb=%dms "
                      "bsr=%d vq=%.1f deficit=%d gbr_ul=%lu mbr_ul=%lu last_grant_slot=%u\n",
                      frame, slot, UE->rnti, _lg, _tlcid, _fqi, _lcprio, _lpdb,
                      _bsr, _vq, _def, (unsigned long)_ggbr, (unsigned long)_gmbr,
                      sched_ctrl->ul_lcg_last_grant_slot[_lg]);
            }
        }

        if (numUE >= MAX_MOBILES_PER_GNB) {
            IA_P5G_LOG_EXC_E(NR_MAC, "[IA-P5G] ia_p5g_pf_ul: UE_sched array full (%d) "
                  "at (%d.%d) — skipping remaining UEs this slot\n",
                  MAX_MOBILES_PER_GNB, frame, slot);
            break;
        }

        UE_sched[numUE].coef           = 0.0f;   /* composite filled below  */
        UE_sched[numUE].base_q         = base_q;
        UE_sched[numUE].urgency01      = ue_worst_urgency01;
        UE_sched[numUE].spectral_eff   = spectral_eff;
        UE_sched[numUE].sched_inactive = sched_inactive;
        UE_sched[numUE].UE             = UE;
        UE_sched[numUE].selected_mcs   = selected_mcs;
        UE_sched[numUE].pdb_ms         = sched_ctrl->ul_best_remaining_pdb_ms;
        UE_sched[numUE].has_gbr        = sched_ctrl->ul_has_unfulfilled_gbr;
        UE_sched[numUE].gbr_bytes_slot = gbr_bytes_slot;
        UE_sched[numUE].floor_fire     = ia_floor_fire;
        UE_sched[numUE].floor_sil      = ia_floor_sil;
        numUE++;
    }

    /* ═══════════════════════════════════════════════════════════════════
     * COMPOSITE-METRIC PASS — fold deadline urgency into each candidate's
     * coef, mirroring two_tier.py:
     *     coef = (base_q + W · urgency^EXP · max(max_q,1)) · SE
     * max_q is the largest base deficit among the data candidates, so the
     * urgency bonus is dimensionally commensurate with the deficits it
     * competes against (a maxed-out deadline flow gains up to W·max_q,
     * enough to overtake the largest bulk backlog but not to permanently
     * preempt it once served).  Control-plane (sched_inactive) UEs are
     * exempt — they sort ahead of all data UEs in ia_p5g_ul_cmp and their
     * coef is irrelevant.                                                */
    float max_q = 0.0f;
    for (int _u = 0; _u < numUE; _u++)
        if (!UE_sched[_u].sched_inactive && UE_sched[_u].base_q > max_q)
            max_q = UE_sched[_u].base_q;
    const float _norm = max_q > 1.0f ? max_q : 1.0f;
    for (int _u = 0; _u < numUE; _u++) {
        float u   = UE_sched[_u].urgency01;
        /* [IA-P5G] Defect-3 / functional-form fix — barrier delay term.
         * Phi(u) = u^EXP / (1 - min(u,CAP) + EPS). Tracks the old u^EXP
         * closely below ~0.8 (soft, earned-by-lateness), then diverges as
         * u -> 1 so a flow at/over its PDB dominates; CAP+EPS bound the
         * denominator so it can never overflow or NaN. Rate-deficit base_q
         * remains additive/linear — barrier applies to the deadline side
         * only. Note u here is already priority-weighted (Defect 1).       */
        float _ub  = u < IA_P5G_URG_BARRIER_CAP ? u : IA_P5G_URG_BARRIER_CAP;
        float _phi = powf(u, IA_P5G_DELAY_EXP)
                     / (1.0f - _ub + IA_P5G_URG_BARRIER_EPS);
        float urg = IA_P5G_DELAY_URGENCY_W * _phi * _norm;
        UE_sched[_u].coef = (UE_sched[_u].base_q + urg) * UE_sched[_u].spectral_eff;

        /* ── [IA-P5G FLOOR v2.1] Sentinel coef for a fired floor.
         * During the fault both composite inputs are gated on
         * estimated_ul_buffer_per_lcg[] > 0 (urgency loop skipped ->
         * urgency01 == 0 -> Phi(0) == 0; vq_ul not accruing -> base_q ~ 0),
         * so the computed coef above is exactly 0 and would sort this UE
         * last. INFINITY (not a large finite constant: a legitimate coef
         * reaches ~1e13 under saturation, so any finite sentinel could be
         * silently beaten by a future traffic mix) puts it at the head of
         * the data UEs. The Tier-1.5 comparator branch makes this explicit
         * and handles ties; the sentinel additionally guarantees the order
         * even if that branch is ever removed.
         *
         * Not persistent: UE_sched[] is a local {0}-initialised array and
         * floor_fire is recomputed every slot, so the sentinel lives for
         * exactly one slot. It cannot contaminate other UEs either --
         * _norm/max_q is built from base_q, never from coef. After the
         * grant lands, the BSR zeroes sched_ul_bytes and repopulates the
         * per-LCG estimates, so the very next visit computes an ordinary
         * finite coef. It shows as coef=inf in [P5G-UL-METRIC], which is a
         * deliberate and greppable signature of a floor slot.           */
        if (UE_sched[_u].floor_fire)
            UE_sched[_u].coef = INFINITY;

        /* ── [IA-P5G TELEMETRY] Inner-tier (Tier-2) metric breakdown, always
         *    on (LOG_I). Shows every component of the composite DPP metric
         *    exactly as computed here, so the ranking is fully reconstructible
         *    from the log:
         *        coef = (base_q + urg) * SE,  urg = W * urgency01^EXP * norm
         *    where norm = max(max_q, 1) and max_q is the largest base_q among
         *    data candidates this slot. sched_inactive candidates are shown
         *    too (coef ignored for them — they sort ahead via ia_p5g_ul_cmp),
         *    flagged class=CTRL. Compare base_q vs urg to see whether a UE is
         *    winning on backlog-deficit or on deadline-urgency.            */
        if (IA_P5G_TELEMETRY_UL)
        LOG_I(NR_MAC,
              "[P5G-UL-METRIC][%4d.%2d][UE %04x] class=%s coef=%.1f = (base_q=%.1f + urg=%.1f) * SE=%.0f "
              "| urg: W=%.1f * Phi(u=%.2f)=%.2f * norm=%.1f (max_q=%.1f)\n",
              frame, slot, UE_sched[_u].UE->rnti,
              UE_sched[_u].sched_inactive ? "CTRL" : "DATA",
              UE_sched[_u].coef, UE_sched[_u].base_q, urg, UE_sched[_u].spectral_eff,
              (double)IA_P5G_DELAY_URGENCY_W, UE_sched[_u].urgency01, _phi,
              _norm, max_q);
    }

    qsort(UE_sched, numUE, sizeof(ia_p5g_ul_ue_t), ia_p5g_ul_cmp);
    ia_p5g_ul_ue_t *iterator = UE_sched;

    /* ── [IA-P5G TELEMETRY] Decided inner-tier ranking after the sort, always
     *    on (LOG_I). ia_p5g_ul_cmp sorts control-plane (sched_inactive) first,
     *    then by coef descending. This one line per slot shows the final
     *    served order — rank[i] = the UE that gets PRBs i-th — so you can see
     *    directly which UE won Tier-2 and by how much, without replaying the
     *    comparator by hand. Only emitted when there is >1 candidate (a
     *    ranking of one is uninteresting).                                 */
    if (IA_P5G_TELEMETRY_UL && numUE > 1) {
        char _rankbuf[256];
        int _off = 0;
        for (int _u = 0; _u < numUE && _off < (int)sizeof(_rankbuf) - 48; _u++) {
            _off += snprintf(_rankbuf + _off, sizeof(_rankbuf) - _off,
                             "%s#%d:UE%04x[%s coef=%.1f]",
                             _u ? " > " : "",
                             _u, UE_sched[_u].UE->rnti,
                             UE_sched[_u].sched_inactive ? "CTRL" : "DATA",
                             UE_sched[_u].coef);
        }
        LOG_I(NR_MAC, "[P5G-UL-RANK][%4d.%2d] served_order: %s\n", frame, slot, _rankbuf);
    }

    /* ═══════════════════════════════════════════════════════════════════
     * FIX 2 — per-UE PRB cap to prevent GBR starvation via monopolization.
     *
     * Root cause (captured): a saturating UE was granted rbSize=106 of 106
     * every slot (max_rbSize = bi.bwpSize). n_rb_sched hit 0 before any
     * lower-ranked UE was reached, so a UE holding an UNMET GBR guarantee
     * was rejected at the l2_budget gate (reached_alloc=4, l2_budget=196).
     * Denied all PRBs, its MCS never recovered, its SE stayed pinned low,
     * and the composite metric kept ranking it last — a self-perpetuating
     * lockout. The winner's queue never drained (infinite backlog), so the
     * MaxWeight crossover that would normally rotate service never arrived.
     *
     * Fix: reserve a PRB floor for any GBR UE that (a) ranks BELOW the
     * current UE in the served order and (b) has a live GBR obligation this
     * slot. Each granted UE's max_rbSize is then capped so it cannot
     * consume the PRBs reserved for those still-unserved GBR UEs. This
     * restores the drain-and-yield feedback the Lyapunov formulation
     * depends on WITHOUT touching the metric itself: raw SE and the virtual
     * queue are unchanged. Targeted by design — when no downstream GBR UE
     * is waiting, reserve_rb is 0 and the cap is inert, so aggregate
     * throughput in the uncontended / no-starvation case is unaffected.
     *
     * The reserve is a conservative per-UE floor (min_rb) times the count
     * of still-unserved GBR UEs with a live obligation. min_rb is the
     * smallest grant nr_find_nb_rb will honour, so reserving min_rb per
     * waiting GBR UE guarantees each can clear the l2_budget gate and get a
     * foothold; MCS recovery over subsequent slots does the rest.
     * ═══════════════════════════════════════════════════════════════════ */

    /* gbr_below[i] = number of GBR UEs with a live per-slot obligation that
     * rank strictly AFTER index i in served order. Built by a reverse scan.
     * Control-plane (sched_inactive) UEs are excluded — they already sort
     * first and take only min_rb, so they neither need nor create reserve. */
    int gbr_below[MAX_MOBILES_PER_GNB + 1];
    {
        int running = 0;
        for (int _u = numUE - 1; _u >= 0; _u--) {
            gbr_below[_u] = running;
            if (!UE_sched[_u].sched_inactive
                && UE_sched[_u].has_gbr
                && UE_sched[_u].gbr_bytes_slot > 0)
                running++;
        }
    }
    /* ═══════════════════════════════════════════════════════════════════
     * SECOND LOOP — allocate granted UEs (sched_inactive sorts first,
     * inherited automatically from ia_p5g_ul_cmp — no separate PASS-1
     * code needed for the control-plane keepalive mechanism)
     * ═══════════════════════════════════════════════════════════════════ */
    ia_p5g_crash_ctx = "ia_p5g_pf_ul: second loop";

    while (iterator->UE != NULL) {
        NR_UE_UL_BWP_t     *current_BWP = &iterator->UE->current_UL_BWP;
        NR_UE_sched_ctrl_t *sched_ctrl  = &iterator->UE->UE_sched_ctrl;

        NR_beam_alloc_t beam = beam_allocation_procedure(&mac->beam_info, sched_frame, sched_slot,
                                                          iterator->UE->UE_beam_index, slots_per_frame);
        if (beam.idx < 0) {
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] Beam could not be allocated\n", iterator->UE->rnti, frame, slot);
            IA_P5G_SKIP(iterator->UE->rnti, skip_l2_beam);
            iterator++;
            continue;
        }

        if (remainUEs[beam.idx] == 0 || n_rb_sched[beam.idx] < min_rb) {
            reset_beam_status(&mac->beam_info, sched_frame, sched_slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            IA_P5G_SKIP(iterator->UE->rnti, skip_l2_budget);
            iterator++;
            continue;
        }

        NR_beam_alloc_t dci_beam = beam_allocation_procedure(&mac->beam_info, frame, slot,
                                                              iterator->UE->UE_beam_index, slots_per_frame);
        if (dci_beam.idx < 0) {
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] Beam could not be allocated\n", iterator->UE->rnti, frame, slot);
            reset_beam_status(&mac->beam_info, sched_frame, sched_slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            iterator++;
            continue;
        }

        int CCEIndex = get_cce_index(mac, CC_id, slot, iterator->UE->rnti,
                                     &sched_ctrl->aggregation_level, dci_beam.idx,
                                     sched_ctrl->search_space, sched_ctrl->coreset,
                                     &sched_ctrl->sched_pdcch, sched_ctrl->pdcch_cl_adjust);
        if (CCEIndex < 0) {
            sched_ctrl->ul_cce_fail++;
            reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, dci_beam.new_beam);
            reset_beam_status(&mac->beam_info, sched_frame, sched_slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] no free CCE for UL DCI\n", iterator->UE->rnti, frame, slot);
            IA_P5G_SKIP(iterator->UE->rnti, skip_l2_cce);
            iterator++;
            continue;
        }

        const int index = ul_buffer_index(sched_frame, sched_slot, slots_per_frame, mac->vrb_map_UL_size);
        uint16_t *rballoc_mask = &mac->common_channels[CC_id].vrb_map_UL[beam.idx][index * MAX_BWP_SIZE];

        int rbStart = 0;
        const uint16_t slbitmap = SL_to_bitmap(tda_info->startSymbolIndex, tda_info->nrOfSymbols);
        bwp_info_t bi = get_pusch_bwp_start_size(iterator->UE);
        while (rbStart < bi.bwpSize && (rballoc_mask[rbStart + bi.bwpStart] & slbitmap))
            rbStart++;

        /* ── [FIX C] A floor fire must NOT be capped at min_rb.
         * sched_inactive is forced true whenever reconfig_floor || srb_floor
         * (control plane), independently of floor_fire. So a desynced UE
         * that ALSO has SRB bytes pending -- e.g. an RRC re-establishment,
         * which is precisely what S4 §2c suspects accompanies these stalls
         * -- had max_rbSize clamped to min_rb, and the v2 "full allocation"
         * at `sched.rbSize = available_rb` below silently degraded back to
         * the ~120 B crumb. That regenerates the exact v1 failure through a
         * different door, and would read in the A/B as "v2 fired but did
         * not rescue". The floor keeps the full BWP; the SRB bytes ride out
         * in the same TB (LCG 0 fills first under LCP), so the control
         * plane is served strictly better, not worse.                    */
        uint16_t max_rbSize   = (iterator->sched_inactive && !iterator->floor_fire)
                                ? min_rb : bi.bwpSize;

        /* FIX 2: cap this UE so it cannot consume PRBs reserved for
         * still-unserved GBR UEs ranked below it. rank is the iterator's
         * index into UE_sched (sorted served order). reserve_rb = min_rb
         * per downstream GBR UE with a live obligation this slot. The cap
         * is applied to the DATA class only; control-plane UEs already take
         * exactly min_rb. When no GBR UE waits below, gbr_below is 0, the
         * reserve is 0, and max_rbSize is unchanged (inert in the common
         * case). We never cap below min_rb — a UE that reaches allocation
         * must be able to receive at least the minimum grant.             */
        /* [FIX C] Floor grants now take the DATA-class path above, so they
         * must also respect the FIX-2 reserve -- otherwise a floor fire on
         * a UE that is simultaneously control-plane would skip the cap and
         * could consume PRBs reserved for other waiting GBR UEs.        */
        if (!iterator->sched_inactive || iterator->floor_fire) {
            int rank = (int)(iterator - UE_sched);
            int reserve_rb = gbr_below[rank] * min_rb;
            int cap = n_rb_sched[beam.idx] - reserve_rb;
            if (cap < min_rb) cap = min_rb;
            if (max_rbSize > cap) max_rbSize = cap;
        }

        /* ── [FIX D] PHR-derived PRB ceiling ──────────────────────────────
         * N_max_prb = SAFETY * 10^(ph0/10) is the largest allocation the UE
         * can actually put power behind. The UE spreads a fixed PCMAX over
         * whatever it is granted, so PRBs beyond N_max_prb do not add
         * throughput -- they lower per-PRB SNR and raise BLER.
         *
         * This ceiling was already computed in Tier-1 (see "Change 4") but
         * only ever converted into phr_cap_bps for the LP. It never reached
         * the per-slot grant path, so [FIX C] opening the floor to bwpSize
         * could hand a power-limited UE ~101 PRBs when its headroom
         * supports a handful: at ph0=10 dB, N_max is ~8 PRBs. The grant
         * then fails to decode, no bytes move, floor_fruitless increments
         * and the backoff penalises the floor for a failure its own grant
         * sizing caused. Capping here breaks that loop.
         *
         * Single-BWP deployment makes this the ONLY lever: with one 106-PRB
         * BWP there is no narrow BWP to move a power-limited UE onto, so
         * grant width is the sole control over how thinly power is spread.
         *
         * Applied to every DATA-class grant, not just floor fires -- the
         * physics is identical for an ordinary large grant. Guards mirror
         * Tier-1 exactly: inert when ph0 == 0 (no PHR CE received yet), and
         * never capped below min_rb, which nr_find_nb_rb requires.       */
        if (sched_ctrl->ph0 > 0
            && (!iterator->sched_inactive || iterator->floor_fire)) {
            double _nmax = IA_P5G_PHR_PRB_SAFETY_FACTOR
                           * pow(10.0, (double)sched_ctrl->ph0 / 10.0);
            if (_nmax < (double)min_rb) _nmax = (double)min_rb;
            if (_nmax < (double)max_rbSize) {
                IA_P5G_LOG_D(NR_MAC,
                      "[IA-P5G][UE %04x][%4d.%2d] PHR cap: ph0=%d n_max_prb=%.1f "
                      "max_rbSize %u -> %u%s\n",
                      iterator->UE->rnti, frame, slot, sched_ctrl->ph0, _nmax,
                      max_rbSize, (uint16_t)_nmax,
                      iterator->floor_fire ? " (floor fire)" : "");
                max_rbSize = (uint16_t)_nmax;
            }
        }

        uint16_t available_rb = 1;
        while (rbStart + available_rb < bi.bwpSize
               && !(rballoc_mask[rbStart + bi.bwpStart + available_rb] & slbitmap)
               && available_rb < max_rbSize)
            available_rb++;

        if (rbStart + min_rb > bi.bwpSize || available_rb < min_rb) {
            reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, dci_beam.new_beam);
            reset_beam_status(&mac->beam_info, sched_frame, sched_slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            IA_P5G_SKIP(iterator->UE->rnti, skip_l2_no_prb);
            iterator++;
            continue;
        }

        int nrOfLayers = get_ul_nrOfLayers(sched_ctrl, current_BWP->dci_format);
        NR_sched_pusch_t sched = {
            .frame = sched_frame,
            .slot = sched_slot,
            .rbStart = rbStart,
            .mcs = iterator->selected_mcs,
            .ul_harq_pid = -1,
            .nrOfLayers = nrOfLayers,
            .time_domain_allocation = tda,
            .tda_info = *tda_info,
            .dmrs_info = get_ul_dmrs_params(scc, current_BWP, tda_info, nrOfLayers),
            .bwp_info = bi,
        };

        const int B = cmax(sched_ctrl->estimated_ul_buffer - sched_ctrl->sched_ul_bytes, 0);

        int B_eff = B;
        {
            int ul_target = sched_ctrl->ul_total_target_bytes;
            if (ul_target < B) ul_target = B;
            if (iterator->has_gbr && iterator->gbr_bytes_slot > 0) {
                if (ul_target < iterator->gbr_bytes_slot)
                    ul_target = iterator->gbr_bytes_slot;
            }
            B_eff = ul_target;
        }

        /* [IA-P5G FLOOR v2] The `B > 0` half of this gate is relaxed to
         * include a floor grant. nr_ue_max_mcs_min_rb() is the power-safety
         * loop: it decrements available_rb (then MCS) until the required tx
         * power fits the reported headroom, so a large UL allocation is
         * self-correcting on per-PRB PSD -- which is what makes granting
         * the full available_rb below safe. Under v1 this call was skipped
         * during the fault (B == 0 by definition), i.e. any floor grant
         * would have been issued power-unaware.
         * The (pcmax || ph) half is deliberately KEPT: if the UE has never
         * reported headroom then ph_limit == 0 and the loop would drive Rb
         * all the way down to min_rb, regenerating the crumb from the other
         * direction. Skipping the call in that case is correct.
         * NOTE: the function's `tbs` argument is dead (tbs_bits is
         * immediately recomputed from *Rb), so passing B_eff == 0 on the
         * floor path is harmless -- the adaptation keys off allocation
         * size, not demand.                                             */
        if ((sched_ctrl->pcmax != 0 || sched_ctrl->ph != 0)
            && (B > 0 || iterator->floor_fire))
            nr_ue_max_mcs_min_rb(current_BWP->scs, sched_ctrl->ph, &sched, current_BWP, min_rb, B_eff, &available_rb, &sched.mcs);

        if (sched.mcs < sched_ctrl->ul_bler_stats.mcs)
            sched_ctrl->ul_bler_stats.mcs = sched.mcs;

        update_ul_ue_R_Qm(sched.mcs, current_BWP->mcs_table, current_BWP->pusch_Config, &sched.R, &sched.Qm);

        bool find_ok = true;
        if (iterator->floor_fire) {
            /* ── [IA-P5G FLOOR v2] Floor grant: take the whole allocation
             * that survived power adaptation, bypassing nr_find_nb_rb.
             * Rationale: nr_find_nb_rb sizes the grant to B_eff, and every
             * input to B_eff (ul_total_target_bytes, B, gbr_bytes_slot) is
             * derived from the per-LCG buffer estimate -- which reads 0 in
             * precisely this fault, so demand-based sizing would collapse
             * the rescue back to min_rb. The floor exists because the
             * estimate cannot be trusted, so its grant must not depend on
             * it. available_rb is already bounded by max_rbSize (bwpSize
             * minus the FIX-2 reserve for downstream GBR UEs) and by the
             * PHR loop above, so this is neither unfair nor over-powered.
             * Over-allocation relative to the true backlog is intended:
             * the UE pads the TB, and surplus room is what triggers a
             * padding BSR (38.321) -- the estimate resync a min_rb crumb
             * is too small to elicit. Cost is bounded: at most one such
             * grant per theta per faulted UE.                           */
            sched.rbSize  = available_rb;
            sched.tb_size = nr_compute_tbs(sched.Qm, sched.R, sched.rbSize,
                                           sched.tda_info.nrOfSymbols,
                                           sched.dmrs_info.N_PRB_DMRS * sched.dmrs_info.num_dmrs_symb,
                                           0, 0, sched.nrOfLayers) >> 3;
            IA_P5G_LOG_EXC_W(NR_MAC,
                  "[P5G-UL-FLOOR][%4d.%2d][UE %04x] floor grant: rbSize=%u (avail=%u) "
                  "mcs=%d tbs=%u -- demand-estimate sizing bypassed\n",
                  frame, slot, iterator->UE->rnti, sched.rbSize, available_rb,
                  sched.mcs, sched.tb_size);
        } else if (!iterator->sched_inactive) {
            find_ok = nr_find_nb_rb(sched.Qm, sched.R, current_BWP->transform_precoding, sched.nrOfLayers,
                                    sched.tda_info.nrOfSymbols,
                                    sched.dmrs_info.N_PRB_DMRS * sched.dmrs_info.num_dmrs_symb,
                                    B_eff, min_rb, available_rb, &sched.tb_size, &sched.rbSize);
        } else {
            sched.rbSize = min_rb;
            sched.tb_size = nr_compute_tbs(sched.Qm, sched.R, sched.rbSize, sched.tda_info.nrOfSymbols,
                                           sched.dmrs_info.N_PRB_DMRS * sched.dmrs_info.num_dmrs_symb,
                                           0, 0, sched.nrOfLayers) >> 3;
        }

        /* ── BUG FIX (handoff §6): same root cause as DL fix above.
         * nr_find_nb_rb() returns false on partial fit but still
         * populates tb_size/rbSize.  !find_ok must not cause a skip.
         * For non-GBR UL, ul_total_target_bytes is set from raw BSR
         * occupancy with no per-slot cap, so the first slot a UE's
         * queue grows beyond single-slot capacity at its MCS,
         * nr_find_nb_rb correctly flags partial — and the old check
         * would skip, guaranteeing the backlog never drains (deadlock).
         * Guard only rbSize == 0 (genuinely nothing usable).          */
        if (sched.rbSize == 0) {
            IA_P5G_LOG_EXC_W(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] nr_find_nb_rb: rbSize=0 "
                  "(B_eff=%d available_rb=%d) — skipping this UE this slot\n",
                  iterator->UE->rnti, frame, slot, B_eff, available_rb);
            IA_P5G_SKIP(iterator->UE->rnti, skip_l2_rbzero);
            reset_beam_status(&mac->beam_info, frame, slot, iterator->UE->UE_beam_index, slots_per_frame, dci_beam.new_beam);
            reset_beam_status(&mac->beam_info, sched_frame, sched_slot, iterator->UE->UE_beam_index, slots_per_frame, beam.new_beam);
            iterator++;
            continue;
        }
        if (!find_ok)
            IA_P5G_LOG_D(NR_MAC, "[IA-P5G][UE %04x][%4d.%2d] nr_find_nb_rb partial fit UL: "
                  "B_eff=%d capped to tb_size=%d (rbSize=%d/%d)\n",
                  iterator->UE->rnti, frame, slot, B_eff,
                  sched.tb_size, sched.rbSize, available_rb);

        /* ── [IA-P5G TELEMETRY] UL grant RESULT (always on, LOG_I). This is
         *    the allocation half of the [P5G-UL] header above: what the UE
         *    actually got this slot. rbSize is the PRB count -- comparing it
         *    across UEs is exactly how the 61.5-vs-8.0 NPRB imbalance was
         *    seen. B_eff is the requested size (bytes) that drove it, so
         *    B_eff vs tb_size shows request-vs-served, and available_rb shows
         *    whether the cap was contention (few RBs left) or demand (small
         *    B_eff). partial=1 means nr_find_nb_rb couldn't fit B_eff.
         *    Control-channel: cce=CCE index granted, aggL=PDCCH aggregation
         *    level, cce_fail=cumulative UL DCI CCE-allocation failures.     */
        {
            ia_p5g_ul_summary_t *_sum = ia_p5g_ul_summary_get(iterator->UE->rnti);
            if (_sum) {
                _sum->reached_alloc++;
                _sum->grants++;
                _sum->bytes += (uint64_t)sched.tb_size;
                _sum->rbsize_sum += (uint64_t)sched.rbSize;
                if (sched.rbSize > _sum->rbsize_max) _sum->rbsize_max = sched.rbSize;

                /* [FIX B] Trickle detector feeding the adequacy trigger: a
                 * RUN of consecutive min_rb-sized grants is the crumb
                 * signature. Any larger grant means demand-based sizing is
                 * working, so the run resets. Saturates rather than wraps. */
                if ((int)sched.rbSize <= min_rb) {
                    if (_sum->floor_crumb_run < 0xFFFFu) _sum->floor_crumb_run++;
                } else {
                    _sum->floor_crumb_run = 0;
                }
            }
        }
        if (IA_P5G_TELEMETRY_UL)
        LOG_I(NR_MAC,
              "[P5G-UL-GRANT][%4d.%2d][UE %04x] class=%s rbSize=%d tb_size=%d mcs=%d "
              "B_eff=%d B=%d avail_rb=%d partial=%d coef=%.1f cce=%d aggL=%d cce_fail=%d\n",
              frame, slot, iterator->UE->rnti,
              iterator->floor_fire ? "FLOOR"
                                  : (iterator->sched_inactive ? "INACT" : "DATA"),
              sched.rbSize, sched.tb_size, sched.mcs,
              B_eff, B, available_rb, find_ok ? 0 : 1, iterator->coef,
              CCEIndex, sched_ctrl->aggregation_level, sched_ctrl->ul_cce_fail);

        long *deltaMCS = current_BWP->pusch_Config ? current_BWP->pusch_Config->pusch_PowerControl->deltaMCS : NULL;
        int tbs_bits = sched.tb_size << 3;
        sched.phr_txpower_calc = compute_ph_factor(current_BWP->scs, tbs_bits, sched.rbSize, sched.nrOfLayers,
                                                   sched.tda_info.nrOfSymbols,
                                                   sched.dmrs_info.N_PRB_DMRS * sched.dmrs_info.num_dmrs_symb,
                                                   deltaMCS, false);

        sched_ctrl->cce_index = CCEIndex;
        fill_pdcch_vrb_map(mac, CC_id, &sched_ctrl->sched_pdcch, CCEIndex, sched_ctrl->aggregation_level, dci_beam.idx);

        post_process_ulsch(mac, pp_pusch, iterator->UE, &sched);

        /* ── TwoTier hook 3: drain virtual queues after grant committed ──
         * UE decides actual per-LCG split via its own LCP (black box);
         * this approximates delivery proportional to BSR occupancy.      */
        ia_p5g_drain_vq_ul(mac, iterator->UE, sched.tb_size);

        n_rb_sched[beam.idx] -= sched.rbSize;
        for (int rb = bi.bwpStart; rb < sched.rbSize; rb++)
            rballoc_mask[rb + sched.rbStart] |= slbitmap;

        remainUEs[beam.idx]--;
        iterator++;
        scheduled_something = true;
    }

    int num_ue_sched = num_beams * max_num_ue;
    for (int i = 0; i < num_beams; i++)
        num_ue_sched -= remainUEs[i];
    DevAssert((num_ue_sched == 0 && !scheduled_something) || (num_ue_sched > 0 && scheduled_something));

    /* ── Change 2: Work-conserving UL fill pass ──────────────────────────
     * After the main Tier-1-driven loop, check whether PRBs remain unused
     * and any UE has pending UL data that was not granted.  If so, offer
     * surplus PRBs to the highest-metric UE that:
     *   (a) was NOT already granted in the main loop this slot
     *       (one UL grant per UE per slot — HARQ process constraint), and
     *   (b) has a non-zero BSR (estimated_ul_buffer > 0), and
     *   (c) has a free HARQ process available.
     *
     * This prevents idle PRBs when Tier-1 underestimates demand (e.g.
     * during TCP UL bursts where the smoothed demand_bps has not yet
     * caught up).  The fill grant is bounded by the UE's reported BSR so
     * we never allocate beyond what the UE says it needs.
     *
     * Defensive: only one fill grant total per slot (first eligible UE
     * in metric-sorted order); we do not loop multiple fill grants here
     * to avoid over-committing HARQ processes and CCE budget.             */
    ia_p5g_crash_ctx = "ia_p5g_pf_ul: work-conserving fill";

    /* Find total remaining PRBs across beams */
    int fill_prbs_remaining = 0;
    int fill_beam_idx = -1;
    for (int b = 0; b < num_beams; b++) {
        if (n_rb_sched[b] >= min_rb) {
            fill_prbs_remaining = n_rb_sched[b];
            fill_beam_idx = b;
            break;  /* take first beam with headroom */
        }
    }

    if (fill_prbs_remaining >= min_rb && fill_beam_idx >= 0) {
        /* Walk candidates in metric order (already sorted).
         * Skip any UE that was granted in the main loop (we detect this
         * by checking remainUEs — if remainUEs decreased for this beam,
         * the UE was served.  Since we only track beam-level counts, use
         * the simpler proxy: check if the UE still has sched_ul_bytes == 0
         * after the main loop, meaning no grant was issued this slot.     */
        ia_p5g_ul_ue_t *fill_iter = UE_sched;
        while (fill_iter->UE != NULL) {
            NR_UE_sched_ctrl_t *fill_sc = &fill_iter->UE->UE_sched_ctrl;

            /* Skip UEs with no pending data */
            const int fill_B = cmax(fill_sc->estimated_ul_buffer
                                    - fill_sc->sched_ul_bytes, 0);
            if (fill_B <= 0) { fill_iter++; continue; }

            /* Skip UEs that were already granted this slot
             * (sched_ul_bytes > 0 means a grant was committed).           */
            if (fill_sc->sched_ul_bytes > 0) { fill_iter++; continue; }

            /* Skip UEs with no free HARQ process */
            if (fill_sc->available_ul_harq.head < 0) {
                fill_iter++; continue;
            }

            /* Attempt beam and CCE allocation for fill grant */
            NR_beam_alloc_t fill_beam = beam_allocation_procedure(
                &mac->beam_info, sched_frame, sched_slot,
                fill_iter->UE->UE_beam_index, slots_per_frame);
            if (fill_beam.idx < 0) { fill_iter++; continue; }

            NR_beam_alloc_t fill_dci_beam = beam_allocation_procedure(
                &mac->beam_info, frame, slot,
                fill_iter->UE->UE_beam_index, slots_per_frame);
            if (fill_dci_beam.idx < 0) {
                reset_beam_status(&mac->beam_info, sched_frame, sched_slot,
                                  fill_iter->UE->UE_beam_index, slots_per_frame,
                                  fill_beam.new_beam);
                fill_iter++; continue;
            }

            int fill_CCE = get_cce_index(mac, CC_id, slot, fill_iter->UE->rnti,
                                         &fill_sc->aggregation_level, fill_dci_beam.idx,
                                         fill_sc->search_space, fill_sc->coreset,
                                         &fill_sc->sched_pdcch,
                                         fill_sc->pdcch_cl_adjust);
            if (fill_CCE < 0) {
                /* No CCE available — stop fill pass entirely (CCE budget exhausted) */
                reset_beam_status(&mac->beam_info, frame, slot,
                                  fill_iter->UE->UE_beam_index, slots_per_frame,
                                  fill_dci_beam.new_beam);
                reset_beam_status(&mac->beam_info, sched_frame, sched_slot,
                                  fill_iter->UE->UE_beam_index, slots_per_frame,
                                  fill_beam.new_beam);
                IA_P5G_LOG_D(NR_MAC,
                      "[IA-P5G][UE %04x][%4d.%2d] WC-fill: no CCE — stopping fill pass\n",
                      fill_iter->UE->rnti, frame, slot);
                break;
            }

            /* Compute fill grant size — capped to BSR and available PRBs */
            NR_UE_UL_BWP_t *fill_bwp = &fill_iter->UE->current_UL_BWP;
            bwp_info_t fill_bi = get_pusch_bwp_start_size(fill_iter->UE);
            const int fill_index = ul_buffer_index(sched_frame, sched_slot,
                                                    slots_per_frame, mac->vrb_map_UL_size);
            uint16_t *fill_rballoc = &mac->common_channels[CC_id].vrb_map_UL[fill_beam.idx][fill_index * MAX_BWP_SIZE];
            const uint16_t fill_slbitmap = SL_to_bitmap(tda_info->startSymbolIndex,
                                                         tda_info->nrOfSymbols);

            int fill_rbStart = 0;
            while (fill_rbStart < fill_bi.bwpSize
                   && (fill_rballoc[fill_rbStart + fill_bi.bwpStart] & fill_slbitmap))
                fill_rbStart++;

            uint16_t fill_avail_rb = 1;
            while (fill_rbStart + fill_avail_rb < fill_bi.bwpSize
                   && !(fill_rballoc[fill_rbStart + fill_bi.bwpStart + fill_avail_rb] & fill_slbitmap)
                   && fill_avail_rb < (uint16_t)fill_prbs_remaining)
                fill_avail_rb++;

            if (fill_rbStart + min_rb > fill_bi.bwpSize || fill_avail_rb < (uint16_t)min_rb) {
                reset_beam_status(&mac->beam_info, frame, slot,
                                  fill_iter->UE->UE_beam_index, slots_per_frame,
                                  fill_dci_beam.new_beam);
                reset_beam_status(&mac->beam_info, sched_frame, sched_slot,
                                  fill_iter->UE->UE_beam_index, slots_per_frame,
                                  fill_beam.new_beam);
                fill_iter++; continue;
            }

            int fill_nrOfLayers = get_ul_nrOfLayers(fill_sc, fill_bwp->dci_format);
            NR_sched_pusch_t fill_sched = {
                .frame = sched_frame,
                .slot  = sched_slot,
                .rbStart = fill_rbStart,
                .mcs   = fill_iter->selected_mcs,
                .ul_harq_pid = -1,
                .nrOfLayers  = fill_nrOfLayers,
                .time_domain_allocation = tda,
                .tda_info    = *tda_info,
                .dmrs_info   = get_ul_dmrs_params(scc, fill_bwp, tda_info, fill_nrOfLayers),
                .bwp_info    = fill_bi,
            };

            uint16_t fill_R; uint8_t fill_Qm;
            update_ul_ue_R_Qm(fill_sched.mcs, fill_bwp->mcs_table,
                               fill_bwp->pusch_Config, &fill_R, &fill_Qm);
            fill_sched.R  = fill_R;
            fill_sched.Qm = fill_Qm;

            bool fill_fit = nr_find_nb_rb(fill_Qm, fill_R,
                                          fill_bwp->transform_precoding,
                                          fill_nrOfLayers,
                                          tda_info->nrOfSymbols,
                                          fill_sched.dmrs_info.N_PRB_DMRS
                                              * fill_sched.dmrs_info.num_dmrs_symb,
                                          fill_B, min_rb, fill_avail_rb,
                                          &fill_sched.tb_size, &fill_sched.rbSize);

            if (fill_sched.rbSize == 0) {
                reset_beam_status(&mac->beam_info, frame, slot,
                                  fill_iter->UE->UE_beam_index, slots_per_frame,
                                  fill_dci_beam.new_beam);
                reset_beam_status(&mac->beam_info, sched_frame, sched_slot,
                                  fill_iter->UE->UE_beam_index, slots_per_frame,
                                  fill_beam.new_beam);
                fill_iter++; continue;
            }
            (void)fill_fit;  /* partial fit is acceptable in fill pass */

            IA_P5G_LOG_D(NR_MAC,
                  "[IA-P5G][UE %04x][%4d.%2d] WC-fill grant: rbSize=%d tb_size=%d "
                  "BSR=%d (Tier-1 demand underestimated this cycle)\n",
                  fill_iter->UE->rnti, frame, slot,
                  fill_sched.rbSize, fill_sched.tb_size, fill_B);

            fill_sc->cce_index = fill_CCE;
            fill_pdcch_vrb_map(mac, CC_id, &fill_sc->sched_pdcch,
                               fill_CCE, fill_sc->aggregation_level, fill_dci_beam.idx);

            post_process_ulsch(mac, pp_pusch, fill_iter->UE, &fill_sched);
            ia_p5g_drain_vq_ul(mac, fill_iter->UE, fill_sched.tb_size);

            n_rb_sched[fill_beam.idx] -= fill_sched.rbSize;
            for (int rb = fill_bi.bwpStart; rb < fill_sched.rbSize; rb++)
                fill_rballoc[rb + fill_sched.rbStart] |= fill_slbitmap;

            num_ue_sched++;   /* count the fill grant in return value */
            break;            /* one fill grant per slot — stop here  */
        }
    }

    /* [IA-P5G] Periodic summary flush.
     *
     * BUGFIX: this was `abs_slot(mac, frame, slot) % IA_P5G_SUMMARY_PERIOD_SLOTS == 0`,
     * which NEVER FIRED. abs_slot = frame*slots_per_frame + slot, with
     * slots_per_frame = 20 at numerology 1. Since 1000 % 20 == 0, that
     * condition is only true when slot-in-frame == 0 -- but slot 0 is a
     * DOWNLINK slot, and ia_p5g_pf_ul() is only invoked on UL slots
     * (2, 7, 12, 17 in this TDD pattern). The trigger aliased perfectly
     * against the TDD grid and was unreachable: a 31k-line capture with
     * 5320 grant lines produced zero summary lines.
     *
     * Fixed by counting ACTUAL CALLS to this function instead of deriving
     * the period from the slot number. This cannot alias against any TDD
     * pattern, and the period now means "every N UL scheduling
     * opportunities", which is the quantity actually of interest.
     * At ~800 UL slots/s, 800 ≈ one flush per second.                  */
    {
        static uint32_t _flush_call_count = 0;
        if (++_flush_call_count >= IA_P5G_SUMMARY_PERIOD_SLOTS) {
            _flush_call_count = 0;
            ia_p5g_ul_summary_flush(frame, slot);
        }
    }

    ia_p5g_crash_ctx = "ia_p5g_pf_ul: done";
    return num_ue_sched;
}

void ia_p5g_update_vq_ul(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE)
{
    ia_p5g_crash_ctx = "ia_p5g_update_vq_ul";
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    AssertFatal(state != NULL, "[IA-P5G] update_vq_ul: sched_stateful_data is NULL\n");

    int idx = ia_p5g_rnti_lookup(state, UE->rnti);
    if (idx < 0) {
        pthread_mutex_lock(&state->state_lock);
        idx = ia_p5g_rnti_get_or_alloc(state, UE->rnti);
        pthread_mutex_unlock(&state->state_lock);
        if (idx < 0) return;
    }

    NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;

    /* LCG 0 = SRBs — excluded from virtual queue management.
     * Only LCGs 1-7 carry DRB traffic tracked by Tier-1 targets.        */
    for (int lcg = 1; lcg < IA_P5G_MAX_LCG; lcg++) {
        if (sc->estimated_ul_buffer_per_lcg[lcg] <= 0) continue;

        /* Tier-1 UL rate target for this LCG (bits/s) */
        float r_bps = atomic_load_explicit(
                &state->t1out.ul_target_bps[idx][lcg],
                memory_order_relaxed);

        /* ── Step 1: grow virtual queue ─────────────────────────────── */
        state->vq_ul[idx][lcg] += r_bps * IA_P5G_SLOT_DURATION_S;

        /* ── Step 2: windowed ceiling clamp ─────────────────────────────
         * BUGFIX (starvation inverts the metric):
         *
         * This clamp previously bounded the virtual queue by the ARRIVAL
         * DELTA over the Tier-1 window:
         *     arr_cum = delivered_cum + pending_BSR
         *     arr_W   = arr_cum - ul_arrived_hist        <-- a RATE
         *     ceiling = min(arr_W_bits, target_W_bits) - del_W_bits
         *
         * The intent was "you cannot be owed more than actually arrived."
         * That proxy holds only while the UE's buffer has headroom. Once a
         * flow is starved hard enough that its buffer SATURATES, nothing
         * new can enter it, so arr_W collapses toward zero -- and because
         * the UE is not being served, del_W is ~zero too. Result:
         *     ceiling = min(~0, target) - ~0 = 0
         * and the virtual queue is clamped to 0 exactly when the flow is
         * most starved. The worse the starvation, the smaller the credit:
         * being denied service erases the evidence that you were denied.
         *
         * Measured, this run: UE 5ce4 held 2,901,912 bytes backlogged,
         * received 3 grants / 435 bytes in a 1s window, and its vq_ul read
         * 0.0 -- while its GBR deficit read 290,784. base_q therefore
         * collapsed to 0, the composite metric degenerated to urg*SE with
         * urgency saturated at 1.00 for BOTH UEs, and ranking reduced to
         * pure spectral efficiency (SE=84 vs SE=4). Winner-takes-all.
         *
         * Fix: bound by the BACKLOG LEVEL rather than the arrival delta.
         * "How far behind is this flow" is answered directly by how much
         * it still has queued; that quantity does not vanish when the flow
         * stops being served. It is also dimensionally consistent -- a
         * queue (bits outstanding) compared against target_W_bits (bits
         * owed this window) -- whereas the old form compared a rate.
         *
         * min(backlog, target_W_bits) is retained deliberately: it caps
         * per-window entitlement at what Tier-1 actually promised, so a
         * flow sitting on a 20 MB backlog still cannot claim more than its
         * GBR share in one window. Catch-up is bounded, not unbounded.
         *
         * TRADEOFF, deliberate: the old form also meant a flow whose
         * SOURCE went idle would see its ceiling decay to zero and stop
         * accruing credit. With a backlog-level bound, a flow whose
         * application stalled but whose buffer still holds data keeps its
         * entitlement until that buffer drains. For continuous saturating
         * flows (this workload) the two are equivalent. For very bursty
         * sources the new form is slightly more generous to a stalled
         * sender. That is the intended direction: under-crediting a
         * starved flow is the failure being fixed here.
         *
         * LCID for this LCG: lcid = lcg + 3 (confirmed: LCG = DRB_ID,
         * LCID = DRB_ID + 3; mac_stats.ul.lc_bytes indexed by LCID).    */
        int lcid = lcg + 3;
        uint64_t del_cum = (uint64_t)UE->mac_stats.ul.lc_bytes[lcid];
        uint64_t del_W = del_cum - state->ul_delivered_hist[idx][lcg];

        float target_W_bits = r_bps * state->tier1_period_s;
        float del_W_bits    = (float)(del_W * 8);

        /* Backlog still queued for this LCG, in bits. This is the quantity
         * that survives starvation -- it is what the flow is actually
         * owed, not how fast work happened to arrive recently.          */
        float backlog_bits = (float)((uint64_t)sc->estimated_ul_buffer_per_lcg[lcg] * 8);

        /* Catch-up horizon: the virtual queue may accumulate up to N windows
         * of guaranteed bits (still bounded by real backlog), not just one.
         * N=1 reproduces the original single-window cap; larger N restores
         * the wait-time accumulation MaxWeight needs so a longer-starved
         * flow can overtake a high-SE competitor. Still floored at the
         * backlog: a flow is never credited for data it does not have. */
        float catchup_W_bits = (float)IA_P5G_VQ_UL_CATCHUP_N * target_W_bits;

        float ceiling = (backlog_bits < catchup_W_bits ? backlog_bits : catchup_W_bits)
                        - del_W_bits;
        if (ceiling < 0.0f) ceiling = 0.0f;

        if (state->vq_ul[idx][lcg] > ceiling)
            state->vq_ul[idx][lcg] = ceiling;
        if (state->vq_ul[idx][lcg] < 0.0f)
            state->vq_ul[idx][lcg] = 0.0f;
    }
}

/* [IA-P5G] Returns the UE's BASE virtual-queue deficit Σ_g Q_g (bits),
 * WITHOUT the spectral-efficiency factor. The caller forms the composite
 * metric (base_q + delay urgency) and multiplies by SE once, so that the
 * urgency bonus rides inside the parenthesis exactly as in two_tier.py:
 *     ue_metric = (Σ_g Q_g + delay_urgency) × spectral_efficiency.
 * The `spectral_eff` parameter is retained for signature/ABI stability but
 * is intentionally unused here. */
float ia_p5g_ul_metric(gNB_MAC_INST *mac,
                        NR_UE_info_t *UE,
                        float         spectral_eff)
{
    ia_p5g_crash_ctx = "ia_p5g_ul_metric";
    (void)spectral_eff;
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    if (!state) return 0.0f;

    int idx = ia_p5g_rnti_lookup(state, UE->rnti);
    if (idx < 0) return 0.0f;

    NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;
    float sum_q = 0.0f;

    for (int lcg = 1; lcg < IA_P5G_MAX_LCG; lcg++) {
        /* [IA-P5G] Include this flow's deficit when EITHER the BSR shows
         * pending data OR the virtual queue is still positive. During a grant
         * freeze the UE cannot send a BSR, so estimated_ul_buffer_per_lcg
         * decays to 0 even though data is stuck behind it; the virtual queue
         * is the durable deficit and must keep driving the metric. Without
         * this, base_q collapses to 0 during a freeze, the UE sorts last
         * forever, and the starvation self-perpetuates (the exact failure that
         * left d639 with zero grants for 55s). */
        if (sc->estimated_ul_buffer_per_lcg[lcg] <= 0
            && state->vq_ul[idx][lcg] <= 0.0f) continue;
        sum_q += state->vq_ul[idx][lcg];
    }

    return sum_q;
}

void ia_p5g_drain_vq_ul(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE,
                          uint32_t      tb_size)
{
    ia_p5g_crash_ctx = "ia_p5g_drain_vq_ul";
    ia_p5g_state_t *state = (ia_p5g_state_t *)mac->sched_stateful_data;
    if (!state) return;

    int idx = ia_p5g_rnti_lookup(state, UE->rnti);
    if (idx < 0) return;

    if (tb_size == 0) return;

    NR_UE_sched_ctrl_t *sc = &UE->UE_sched_ctrl;

    /* Compute total BSR buffer across active LCGs for proportional drain.
     * The UE decides per-LCG byte split via its own 3GPP LCP (black box).
     * BSR occupancy is the best available proxy for actual delivery.      */
    uint32_t total_buf = 0;
    int      n_active  = 0;
    for (int lcg = 1; lcg < IA_P5G_MAX_LCG; lcg++) {
        if (sc->estimated_ul_buffer_per_lcg[lcg] > 0) {
            total_buf += (uint32_t)sc->estimated_ul_buffer_per_lcg[lcg];
            n_active++;
        }
    }
    if (n_active == 0) return;

    float grant_bits = (float)tb_size * 8.0f;

    for (int lcg = 1; lcg < IA_P5G_MAX_LCG; lcg++) {
        if (sc->estimated_ul_buffer_per_lcg[lcg] <= 0) continue;

        float fraction = (total_buf > 0)
            ? (float)sc->estimated_ul_buffer_per_lcg[lcg] / (float)total_buf
            : 1.0f / (float)n_active;

        state->vq_ul[idx][lcg] -= grant_bits * fraction;
        if (state->vq_ul[idx][lcg] < 0.0f)
            state->vq_ul[idx][lcg] = 0.0f;
    }
}