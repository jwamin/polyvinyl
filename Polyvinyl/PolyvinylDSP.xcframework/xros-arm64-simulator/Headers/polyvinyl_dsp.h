/* SPDX-License-Identifier: MIT */
/* Portable PCM WAV analysis: RMS windows and peak envelope (LP-rip splitting). */

#ifndef POLYVINYL_DSP_H
#define POLYVINYL_DSP_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct PvDspRmsResult {
    double *rms;
    double *times_center;
    size_t n;
    double duration_sec;
    int sample_rate;
    char *error;
} PvDspRmsResult;

typedef struct PvDspEnvResult {
    double *envelope;
    size_t n_bins;
    double duration_sec;
    char *error;
} PvDspEnvResult;

/**
 * Fill @p out with RMS per analysis window (same semantics as Python rms_window_series).
 * Returns 0 on success; on failure sets out->error and leaves arrays NULL.
 */
int pv_dsp_rms_window_series(const char *path, double window_ms, PvDspRmsResult *out);

void pv_dsp_free_rms_result(PvDspRmsResult *r);

/**
 * Peak envelope normalized 0..1 (max bin scaled to 1), one value per bin.
 */
int pv_dsp_waveform_envelope(const char *path, int num_bins, PvDspEnvResult *out);

void pv_dsp_free_env_result(PvDspEnvResult *r);

#ifdef __cplusplus
}
#endif
#endif
