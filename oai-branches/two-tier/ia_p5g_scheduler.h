/*
 * ia_p5g_scheduler.h
 * IA-P5G Two-Tier QoS-Aware MAC Scheduler
 *
 * Tier-1: LP-based rate allocation thread (~1 s cadence).
 *         Produces per-flow target rates written atomically to
 *         ia_p5g_tier1_output_t.
 *
 * Tier-2: Drift-plus-penalty (Lyapunov virtual queues), per slot.
 *         Reads Tier-1 targets; maintains per-flow virtual queue Q_f;
 *         computes ue_metric = (Σ Q_f) × spectral_efficiency.
 *         Replaces the PF coefficient inside pf_dl() and pf_ul().
 *
 * Integration:  gNB_MAC_INST->sched_stateful_data
 *   NULL     → pf_dl() / pf_ul() run with original PF coefficient unchanged
 *   non-NULL → TwoTier DPP metric used for UE ranking
 *
 * DL-only items (gNB fills the transport block):
 *   ia_p5g_compute_lcp_budget()  — Phase 1 LCP fill: sort by (priority, Q_f)
 *   ia_p5g_get_lcid_budget()     — called from nr_generate_dlsch_pdu()
 *   ia_p5g_drain_vq_dl()         — drains Q per LCID by delivered bits
 *   Phase 2 D-P2-3               — two-stage 3GPP LCP with PBR wallets
 *
 * UL: gNB grants PRBs only; UE fills TB via its own LCP (TS 38.321 §5.4.3.1).
 *   ia_p5g_drain_vq_ul() approximates delivery proportional to BSR occupancy.
 *   No UL LCP budget control — UE is a black box for intra-TB byte split.
 *
 * Deferred to Phase 2:
 *   D-P2-1: HoL delay urgency (needs hol_us in mac_rlc_status_resp_t)
 *   D-P2-2: SPS / Configured Grants
 *   D-P2-3: Two-stage DL LCP with PBR token buckets (B_j wallets)
 *
 * Save to: openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.h
 */

#ifndef IA_P5G_SCHEDULER_H
#define IA_P5G_SCHEDULER_H

#include <stdint.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <pthread.h>

#include "nr_mac_gNB.h"



/* =========================================================================
 * Crash context tracker
 * Set to a short string literal before each major operation.
 * Appears in backtraces on SIGSEGV / abort without needing a signal handler.
 * ========================================================================= */
extern volatile const char *ia_p5g_crash_ctx;

/* =========================================================================
 * Sizing constants
 * ========================================================================= */
#define IA_P5G_MAX_UE    16   /* headroom above 10-UE deployment           */
#define IA_P5G_MAX_LCID  32   /* NR_MAX_NUM_LCID                           */
#define IA_P5G_MAX_LCG    8   /* LCGs 0-7; LCG 0 = SRBs (excluded from VQ)*/

/* Slot duration at μ=1 (30 kHz SCS), used for VQ target growth per slot.  */
#define IA_P5G_SLOT_DURATION_S  0.5e-3f

/* =========================================================================
 * Tier-1 shared output
 * Written by ia_p5g_tier1_thread (~1 s cadence).
 * Read lock-free by Tier-2 hot path via C11 _Atomic loads.
 * ========================================================================= */
typedef struct {
    /*
     * Per-flow DL rate targets in bits/s.
     * Indexed [ue_slot_index][lcid].
     * Tier-2 converts: per_slot_bits = dl_target_bps[i][l] * SLOT_DURATION_S
     */
    _Atomic float    dl_target_bps[IA_P5G_MAX_UE][IA_P5G_MAX_LCID];

    /*
     * Per-flow UL rate targets in bits/s.
     * Indexed [ue_slot_index][lcg].
     * LCG 0 (SRBs) is excluded from virtual queue management.
     */
    _Atomic float    ul_target_bps[IA_P5G_MAX_UE][IA_P5G_MAX_LCG];

    /*
     * Absolute slot (frame * slots_per_frame + slot) of the last LP solve.
     * Tier-2 uses this to detect stale targets and fall back to PF when
     * Tier-1 has not yet produced a solution (startup / solver failure).
     */
    _Atomic uint32_t last_solve_abs_slot;

} ia_p5g_tier1_output_t;

/* =========================================================================
 * RNTI index map entry
 * Maps a UE's RNTI to a slot index in [0, IA_P5G_MAX_UE).
 * The slot index is stable for the lifetime of the UE's connection.
 * ========================================================================= */
typedef struct {
    uint16_t rnti;
    bool     active;
} ia_p5g_rnti_entry_t;

/* =========================================================================
 * Scheduler state  —  stored at gNB_MAC_INST->sched_stateful_data
 *
 * NULL    → all pf_dl() / pf_ul() paths run with original PF coefficient.
 * non-NULL → TwoTier DPP metric activated for UE ranking.
 * ========================================================================= */
typedef struct {

    /* ── Tier-1 output (atomic, written by tier1_thread) ─────────────── */
    ia_p5g_tier1_output_t t1out;

    /* ── RNTI index map (protected by state_lock) ─────────────────────── */
    ia_p5g_rnti_entry_t rnti_map[IA_P5G_MAX_UE];
    pthread_mutex_t     state_lock;

    /* ── DL virtual queues ────────────────────────────────────────────────
     * vq_dl[ue_idx][lcid] — bits owed to this DL flow.
     *
     * Per slot (ia_p5g_update_vq_dl):
     *   Q_f += dl_target_bps[ue_idx][lcid] * SLOT_DURATION_S   (target inflow)
     *   Q_f  = min(Q_f, windowed_ceiling_f)                     (clamp)
     *   After grant: Q_f = max(0, Q_f − delivered_bits_f)       (drain)
     *
     * Only LCID >= 4 (DRBs). SRBs (LCID 1, 2) excluded.
     * Reset to 0.0 when a DRB is released (ia_p5g_rnti_release).          */
    float vq_dl[IA_P5G_MAX_UE][IA_P5G_MAX_LCID];

    /* ── UL virtual queues ────────────────────────────────────────────────
     * vq_ul[ue_idx][lcg] — bits owed to this UL LCG.
     *
     * Per slot (ia_p5g_update_vq_ul):
     *   Q_g += ul_target_bps[ue_idx][lcg] * SLOT_DURATION_S
     *   Q_g  = min(Q_g, windowed_ceiling_g)
     *   After grant: Q_g drained proportional to estimated_ul_buffer_per_lcg
     *   (UE controls actual per-flow split via its own LCP — UE is black box)
     *
     * LCG 0 (SRBs) excluded. Only LCG 1-7 maintained.                    */
    float vq_ul[IA_P5G_MAX_UE][IA_P5G_MAX_LCG];

    /* ── UL demand EWMA smoothing ─────────────────────────────────────────
     * ul_demand_smooth[ue_idx][lcg] — exponentially smoothed UL demand (bps).
     *
     * The raw UL demand estimate (arr_W * 8 / elapsed_s) is computed from
     * BSR-based arrived bytes over a 1-second window.  For TCP UL traffic,
     * this estimate oscillates with the TCP congestion-control timescale
     * (~1–2 s), which is resonant with the Tier-1 window length.  The raw
     * oscillation causes Tier-1 to alternate between over- and under-
     * allocating PRBs each cycle, degrading average UL throughput by ~40%
     * and causing the SCA solver to fail convergence (iter → max_iters).
     *
     * Fix: apply EWMA with IA_P5G_UL_DEMAND_ALPHA = 0.3, giving a smoothing
     * time constant τ ≈ 2.8 s, longer than the TCP oscillation period.
     * Smoothed demand is passed to the LP as the demand_bps upper bound.
     *
     * DL does NOT use smoothing — DL reads directly from the gNB RLC buffer
     * (exact, always current) and does not exhibit this oscillation.
     *
     * Zeroed by calloc at init and by ia_p5g_rnti_release() / _get_or_alloc()
     * so a reconnecting UE always starts from zero (no stale estimate).    */
    double ul_demand_smooth[IA_P5G_MAX_UE][IA_P5G_MAX_LCG];

    /* ── Windowed ceiling tracking ────────────────────────────────────────
     * Snapshotted by ia_p5g_tier1_thread at the start of each Tier-1 window.
     *
     * DL ceiling per LCID:
     *   arrived_cum  ≈ UE->mac_stats.dl.lc_bytes[lcid]
     *                  + sched_ctrl->rlc_status[lcid].bytes_in_buffer
     *   delivered_cum = UE->mac_stats.dl.lc_bytes[lcid]
     *
     * UL ceiling per LCG (LCG g maps to LCID = g + 3):
     *   arrived_cum  ≈ UE->mac_stats.ul.lc_bytes[g+3]
     *                  + sched_ctrl->estimated_ul_buffer_per_lcg[g]
     *   delivered_cum = UE->mac_stats.ul.lc_bytes[g+3]
     *
     * Ceiling formula (applied each slot after VQ growth):
     *   arrived_W    = arrived_cum  − arrived_hist
     *   delivered_W  = delivered_cum − delivered_hist
     *   target_W     = target_bps * tier1_period_s  (bits)
     *   ceiling      = max(0, min(target_W, arrived_W*8) − delivered_W*8)
     *   Q_f          = min(Q_f, ceiling)
     *
     * Using windowed arrival (not instantaneous backlog) is essential for
     * bursty flows whose RLC buffer empties between bursts.               */
    uint64_t dl_arrived_hist[IA_P5G_MAX_UE][IA_P5G_MAX_LCID];   /* bytes */
    uint64_t dl_delivered_hist[IA_P5G_MAX_UE][IA_P5G_MAX_LCID]; /* bytes */
    uint64_t ul_arrived_hist[IA_P5G_MAX_UE][IA_P5G_MAX_LCG];    /* bytes */
    uint64_t ul_delivered_hist[IA_P5G_MAX_UE][IA_P5G_MAX_LCG];  /* bytes */

    /* Absolute slot number when the *_hist arrays were last snapshotted.
     * window_s = (current_abs_slot − window_start_abs_slot) * SLOT_DURATION_S */
    uint32_t window_start_abs_slot;

    /* ── DL MAC LCP fill budgets ──────────────────────────────────────────
     * Written each slot by ia_p5g_compute_lcp_budget() during scheduling.
     * Read by nr_generate_dlsch_pdu() to cap per-LCID RLC pulls.
     *
     * Value -1: TwoTier not active for this LCID; caller uses default pull.
     * Value  0: LCID has no budget this TB (lower priority, TB already full).
     * Value >0: RLC pull capped to this many bytes.
     *
     * DL only — UE controls intra-TB byte split for UL (UE black box).   */
    int dl_lcid_budget[IA_P5G_MAX_UE][IA_P5G_MAX_LCID];

    /* ── Lifecycle ────────────────────────────────────────────────────── */
    gNB_MAC_INST *mac;          /* back-pointer for Tier-1 thread  */
    pthread_t              tier1_thread;

    float         tier1_period_s;  /* LP re-solve cadence, default 1.0 s   */
    _Atomic bool  stop;            /* set true → tier1_thread exits cleanly */

} ia_p5g_state_t;

/* =========================================================================
 * Lifecycle API
 * ========================================================================= */

/*
 * Allocate and zero-initialise scheduler state.
 * Assign the returned pointer to mac->sched_stateful_data.
 * Call AFTER the MAC is fully configured (after mac_rrc_init in main.c).
 * Does NOT start Tier-1 pthread — use threadCreate separately in main.c.
 * Returns NULL on allocation failure (logs with LOG_E).
 */
ia_p5g_state_t *ia_p5g_state_init(gNB_MAC_INST *mac);

/*
 * Stop Tier-1 pthread and free all state.
 * Caller must set state->stop = true and join tier1_thread before calling,
 * or call ia_p5g_state_destroy() which does both.
 */
void ia_p5g_state_destroy(ia_p5g_state_t *state);

/* =========================================================================
 * Tier-1 pthread
 * ========================================================================= */

/*
 * Tier-1 LP thread entry point.
 * arg = (gNB_MAC_INST *).
 * Launch from main.c:
 *   threadCreate(&state->tier1_thread, ia_p5g_tier1_thread,
 *                (void *)RC.nrmac[i], "IA_P5G_TIER1", -1, priority);
 *
 * Loop behaviour:
 *   1. Sleep tier1_period_s.
 *   2. Snapshot windowed ceiling history arrays (under state_lock).
 *   3. Read all active UE QoS configs and throughput EWMAs (under state_lock).
 *   4. Solve LP for per-flow rate targets.
 *   5. Write results atomically to t1out.dl_target_bps / ul_target_bps.
 *   6. Write t1out.last_solve_abs_slot.
 *   Repeat until state->stop == true.
 */
void *ia_p5g_tier1_thread(void *arg);

/* =========================================================================
 * Tier-2 DL functions
 * Called from inside pf_dl() in gNB_scheduler_dlsch.c
 * ========================================================================= */

/*
 * Full DL scheduler replacement — called from nr_dlsch_preprocessor()
 * when mac->sched_stateful_data != NULL.
 * Stub at Checkpoint 1: logs and returns. sched_stateful_data must be
 * NULL in main.c until Checkpoint 2 implementation is complete.
 */
void ia_p5g_pf_dl(gNB_MAC_INST *mac,
                  post_process_pdsch_t   *pp_pdsch,
                  NR_UE_info_t **UE_list,
                  int                    max_num_ue,
                  int                    num_beams,
                  int                    n_rb_sched[]);

/*
 * STEP 1a — Virtual queue update for one UE, DL direction.
 * Call AFTER update_dlsch_buffer() for this UE, BEFORE computing coeff_ue.
 *
 * For each active DL LCID (lcid >= 4, bytes_in_buffer > 0):
 *   Q_f += dl_target_bps[ue_idx][lcid] * SLOT_DURATION_S   (bits)
 *   Apply windowed ceiling clamp.
 *
 * When Tier-1 has not yet produced targets (last_solve_abs_slot == 0),
 * Q_f remains 0 and ia_p5g_dl_metric() returns 0 → existing pf_dl()
 * comparator levels (has_gbr, pdb_ms) still produce valid ordering.
 */
void ia_p5g_update_vq_dl(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE);

/*
 * STEP 1b — DL UE scheduling metric.
 * Call AFTER ia_p5g_update_vq_dl(), as a drop-in replacement for the
 * PF coefficient line in pf_dl().
 *
 * Returns: ( Σ_{active LCIDs} vq_dl[ue_idx][lcid] ) × spectral_eff
 *
 * spectral_eff = tbs (bits per PRB at current MCS), the same local
 * variable already computed by pf_dl() before the coefficient line.
 *
 * Returns 0.0 if ue_idx not found or all targets are 0 (Tier-1 not yet run).
 * The existing qsort comparator's has_gbr and pdb_ms tiers remain active
 * as fallback ordering when all coeff_ue values are 0.
 */
float ia_p5g_dl_metric(gNB_MAC_INST *mac,
                        NR_UE_info_t *UE,
                        float                  spectral_eff);

/*
 * STEP 2a — Phase 1 DL LCP fill budget computation.
 * Call AFTER PRB sizing (nr_find_nb_rb), BEFORE post_process_dlsch().
 *
 * Distributes tbs_bytes across this UE's active DL LCIDs:
 *   1. Build list: LCIDs with rlc_status[lcid].bytes_in_buffer > 0
 *   2. Sort: priority ASC (lower 3GPP number = higher priority),
 *            then vq_dl[ue_idx][lcid] DESC (most behind target first)
 *   3. Greedy fill: dl_lcid_budget[ue_idx][lcid] = min(bytes_in_buffer, remaining)
 *
 * Writes to state->dl_lcid_budget[ue_idx][lcid].
 * Unserved LCIDs get budget = 0.
 * (Phase 2 D-P2-3 replaces this with two-stage 3GPP LCP + PBR wallets.)
 */
void ia_p5g_compute_lcp_budget(gNB_MAC_INST *mac,
                                NR_UE_info_t *UE,
                                uint32_t               tbs_bytes);

/*
 * STEP 2b — DL virtual queue drain after grant committed.
 * Call AFTER post_process_dlsch().
 *
 * For each active DL LCID:
 *   delivered_bits = dl_lcid_budget[ue_idx][lcid] * 8 * (1.0 - bler)
 *   Q_f = max(0, Q_f - delivered_bits)
 *
 * bler = sched_ctrl->dl_bler_stats.bler (from the scheduled UE's BLER tracker).
 */
void ia_p5g_drain_vq_dl(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE,
                          float                  bler);

/*
 * DL LCP budget lookup — called from nr_generate_dlsch_pdu().
 * O(1): rnti → ue_idx lookup → return dl_lcid_budget[ue_idx][lcid].
 *
 * Returns:
 *   -1   TwoTier not active or RNTI not in map; caller uses default RLC pull
 *    0   This LCID has no budget this TB; caller should skip (pull 0 bytes)
 *   >0   Caller caps RLC pull to this many bytes
 */
int ia_p5g_get_lcid_budget(ia_p5g_state_t *state,
                            uint16_t        rnti,
                            int             lcid);

/* =========================================================================
 * Tier-2 UL functions
 * Called from inside pf_ul() in gNB_scheduler_ulsch.c
 * ========================================================================= */

/*
 * Full UL scheduler replacement — called from nr_ulsch_preprocessor()
 * while loop when mac->sched_stateful_data != NULL.
 * Returns count of UEs scheduled (used by caller to decrement max_dci).
 * Stub at Checkpoint 1: returns 0. sched_stateful_data must be NULL
 * in main.c until Checkpoint 2 implementation is complete.
 */
int ia_p5g_pf_ul(gNB_MAC_INST          *mac,
                 post_process_pusch_t    *pp_pusch,
                 int                     tda,
                 const NR_tda_info_t    *tda_info,
                 NR_UE_info_t **UE_list,
                 int                     max_num_ue,
                 int                     num_beams,
                 int                     n_rb_sched[]);
/*
 * STEP 1a UL — Virtual queue update for one UE, UL direction.
 * Call in pf_ul()'s first loop (candidate collection), per UE.
 *
 * For each active LCG g (estimated_ul_buffer_per_lcg[g] > 0, g >= 1):
 *   Q_g += ul_target_bps[ue_idx][g] * SLOT_DURATION_S   (bits)
 *   Apply windowed ceiling clamp.
 *
 * LCG 0 (SRBs) is excluded — SRB traffic is not subject to rate targets.
 */
void ia_p5g_update_vq_ul(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE);

/*
 * STEP 1b UL — UL UE scheduling metric.
 * Drop-in replacement for the PF coefficient line in pf_ul().
 *
 * Returns: ( Σ_{active LCGs g>=1} vq_ul[ue_idx][g] ) × spectral_eff
 *
 * sched_inactive UEs (SR / inactivity timer, no data) are handled by the
 * existing qsort comparator — they sort before all data UEs regardless of
 * coeff_ue. No separate PASS 1 code needed.
 */
float ia_p5g_ul_metric(gNB_MAC_INST *mac,
                        NR_UE_info_t *UE,
                        float                  spectral_eff);

/*
 * STEP 2 UL — UL virtual queue drain after grant committed.
 * Call in pf_ul()'s second loop, after the grant sizing is finalised.
 *
 * The UE decides internally how to split tb_size bytes across its LCGs
 * (via its own 3GPP LCP — UE is a black box). The gNB approximates
 * per-LCG delivery proportional to BSR occupancy:
 *
 *   total_buf = Σ_g estimated_ul_buffer_per_lcg[g]
 *   for each active LCG g:
 *     fraction_g = estimated_ul_buffer_per_lcg[g] / total_buf
 *     drain_bits = tb_size * 8 * fraction_g
 *     Q_g = max(0, Q_g - drain_bits)
 *
 * This approximation self-corrects within a few slots: if the gNB
 * over-drains a LCG's VQ, Q_g grows faster in subsequent slots and
 * that UE's metric increases, re-prioritising it correctly.
 */
void ia_p5g_drain_vq_ul(gNB_MAC_INST *mac,
                          NR_UE_info_t *UE,
                          uint32_t               tb_size);

/* =========================================================================
 * RNTI index helpers
 * Must be called under state_lock.
 * ========================================================================= */

/*
 * Returns the slot index (0..IA_P5G_MAX_UE-1) for rnti.
 * Allocates a new slot if this rnti is not yet known.
 * Returns -1 with LOG_E if the table is full (> IA_P5G_MAX_UE active UEs).
 */
int ia_p5g_rnti_get_or_alloc(ia_p5g_state_t *state, uint16_t rnti);

/*
 * Marks the slot for rnti as inactive and zeroes its VQ state.
 * Call on UE release (ue_context_release_command handler).
 */
void ia_p5g_rnti_release(ia_p5g_state_t *state, uint16_t rnti);

#endif /* IA_P5G_SCHEDULER_H */