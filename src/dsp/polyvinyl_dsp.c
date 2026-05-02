/* SPDX-License-Identifier: MIT */
/* strdup, fileno, etc. on glibc with strict standard modes */
#if defined(__linux__) && !defined(_GNU_SOURCE) && !defined(_DEFAULT_SOURCE)
#define _DEFAULT_SOURCE
#endif

#include "polyvinyl_dsp.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void clear_rms(PvDspRmsResult *r) {
    r->rms = NULL;
    r->times_center = NULL;
    r->n = 0;
    r->duration_sec = 0.0;
    r->sample_rate = 0;
    r->error = NULL;
}

static void clear_env(PvDspEnvResult *r) {
    r->envelope = NULL;
    r->n_bins = 0;
    r->duration_sec = 0.0;
    r->error = NULL;
}

void pv_dsp_free_rms_result(PvDspRmsResult *r) {
    if (!r) {
        return;
    }
    free(r->rms);
    free(r->times_center);
    free(r->error);
    clear_rms(r);
}

void pv_dsp_free_env_result(PvDspEnvResult *r) {
    if (!r) {
        return;
    }
    free(r->envelope);
    free(r->error);
    clear_env(r);
}

static uint32_t u32le(const unsigned char *b) {
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}

static uint16_t u16le(const unsigned char *b) {
    return (uint16_t)(b[0] | (b[1] << 8));
}

typedef struct {
    FILE *f;
    int nchannels;
    int sampwidth;
    int framerate;
    uint64_t nframes;
    long data_offset;
} PvWav;

static int read_exact(FILE *f, void *buf, size_t n) {
    return fread(buf, 1, n, f) == n ? 0 : -1;
}

static int wav_open(PvWav *w, const char *path, char **err) {
    memset(w, 0, sizeof(*w));
    w->f = fopen(path, "rb");
    if (!w->f) {
        *err = strdup("Could not open WAV file.");
        return -1;
    }

    unsigned char hdr[12];
    if (read_exact(w->f, hdr, 12) != 0) {
        *err = strdup("WAV file too small.");
        goto fail;
    }
    if (memcmp(hdr, "RIFF", 4) != 0 || memcmp(hdr + 8, "WAVE", 4) != 0) {
        *err = strdup("Not a RIFF/WAVE file.");
        goto fail;
    }

    int have_fmt = 0;
    uint16_t audio_format = 0;
    uint16_t nchannels = 0;
    uint32_t rate = 0;
    uint16_t bits = 0;
    long data_off = 0;
    uint64_t data_bytes = 0;

    for (;;) {
        unsigned char ch[8];
        if (read_exact(w->f, ch, 8) != 0) {
            break;
        }
        uint32_t sz = u32le(ch + 4);

        if (memcmp(ch, "fmt ", 4) == 0) {
            if (sz < 16) {
                *err = strdup("Invalid fmt chunk.");
                goto fail;
            }
            unsigned char fmt[16];
            if (read_exact(w->f, fmt, 16) != 0) {
                *err = strdup("Truncated fmt chunk.");
                goto fail;
            }
            audio_format = u16le(fmt);
            nchannels = u16le(fmt + 2);
            rate = u32le(fmt + 4);
            bits = u16le(fmt + 14);
            long skip = (long)sz - 16;
            if (skip > 0 && fseek(w->f, skip, SEEK_CUR) != 0) {
                *err = strdup("Could not skip fmt extension.");
                goto fail;
            }
            have_fmt = 1;
        } else if (memcmp(ch, "data", 4) == 0) {
            long pos = ftell(w->f);
            if (pos < 0) {
                *err = strdup("ftell failed.");
                goto fail;
            }
            data_off = pos;
            data_bytes = sz;
            if (fseek(w->f, (long)sz + ((sz & 1u) ? 1L : 0L), SEEK_CUR) != 0) {
                *err = strdup("Could not skip data chunk.");
                goto fail;
            }
        } else {
            long skip = (long)sz + ((sz & 1u) ? 1L : 0L);
            if (fseek(w->f, skip, SEEK_CUR) != 0) {
                *err = strdup("Could not skip chunk.");
                goto fail;
            }
        }
    }

    if (!have_fmt) {
        *err = strdup("Missing fmt chunk.");
        goto fail;
    }
    if (audio_format != 1) {
        *err = strdup("Only PCM (format 1) WAV is supported.");
        goto fail;
    }
    if (nchannels < 1 || rate == 0) {
        *err = strdup("Invalid WAV channel or sample rate.");
        goto fail;
    }
    int sw = (int)bits / 8;
    if (sw != 1 && sw != 2 && sw != 3 && sw != 4) {
        *err = strdup("Unsupported sample width.");
        goto fail;
    }
    size_t frame_b = (size_t)sw * (size_t)nchannels;
    if (frame_b == 0 || data_off == 0) {
        *err = strdup("Missing or empty data chunk.");
        goto fail;
    }
    if (data_bytes < frame_b) {
        *err = strdup("WAV data too small.");
        goto fail;
    }
    uint64_t nf = data_bytes / frame_b;

    w->nchannels = (int)nchannels;
    w->sampwidth = sw;
    w->framerate = (int)rate;
    w->nframes = nf;
    w->data_offset = data_off;
    return 0;

fail:
    fclose(w->f);
    w->f = NULL;
    return -1;
}

static double rms_linear_mono(const unsigned char *block, size_t nbytes, int sampwidth, int nchannels) {
    if (nbytes == 0 || nchannels < 1) {
        return 0.0;
    }
    size_t frame_b = (size_t)sampwidth * (size_t)nchannels;
    size_t nframes = nbytes / frame_b;
    if (nframes == 0) {
        return 0.0;
    }

    double acc = 0.0;
    double peak_scale = 1.0;

    if (sampwidth == 1) {
        peak_scale = 128.0;
        for (size_t f = 0; f < nframes; f++) {
            size_t base = f * frame_b;
            for (int c = 0; c < nchannels; c++) {
                int v = (int)block[base + (size_t)c] - 128;
                acc += (double)v * (double)v;
            }
        }
    } else if (sampwidth == 2) {
        peak_scale = 32768.0;
        for (size_t f = 0; f < nframes; f++) {
            size_t base = f * frame_b;
            for (int c = 0; c < nchannels; c++) {
                int16_t v = (int16_t)(block[base + (size_t)c * 2u] | (block[base + (size_t)c * 2u + 1] << 8));
                acc += (double)v * (double)v;
            }
        }
    } else if (sampwidth == 3) {
        peak_scale = 8388608.0;
        for (size_t f = 0; f < nframes; f++) {
            size_t base = f * frame_b;
            for (int c = 0; c < nchannels; c++) {
                size_t off = base + (size_t)c * 3u;
                uint32_t u = (uint32_t)block[off] | ((uint32_t)block[off + 1] << 8) | ((uint32_t)block[off + 2] << 16);
                if (u & 0x800000u) {
                    u -= 0x1000000u;
                }
                int32_t s = (int32_t)u;
                double dv = (double)s;
                acc += dv * dv;
            }
        }
    } else {
        peak_scale = 2147483648.0;
        for (size_t f = 0; f < nframes; f++) {
            size_t base = f * frame_b;
            for (int c = 0; c < nchannels; c++) {
                size_t off = base + (size_t)c * 4u;
                uint32_t lo = u32le(block + off);
                int32_t v = (int32_t)lo;
                double dv = (double)v;
                acc += dv * dv;
            }
        }
    }

    double denom = (double)(nframes * (size_t)nchannels);
    return sqrt(acc / denom) / peak_scale;
}

static double frame_peak_abs(const unsigned char *raw, size_t offset, int sampwidth, int nchannels,
                             double peak_scale) {
    if (sampwidth == 1) {
        double m = 0.0;
        for (int c = 0; c < nchannels; c++) {
            double v = fabs((double)raw[offset + (size_t)c] - 128.0);
            if (v > m) {
                m = v;
            }
        }
        return m / peak_scale;
    }
    if (sampwidth == 2) {
        double m = 0.0;
        for (int c = 0; c < nchannels; c++) {
            size_t off = offset + (size_t)c * 2u;
            int16_t vv = (int16_t)(raw[off] | (raw[off + 1] << 8));
            double v = fabs((double)vv);
            if (v > m) {
                m = v;
            }
        }
        return m / peak_scale;
    }
    if (sampwidth == 3) {
        double m = 0.0;
        for (int c = 0; c < nchannels; c++) {
            size_t off = offset + (size_t)c * 3u;
            uint32_t u = (uint32_t)raw[off] | ((uint32_t)raw[off + 1] << 8) | ((uint32_t)raw[off + 2] << 16);
            if (u & 0x800000u) {
                u -= 0x1000000u;
            }
            double v = fabs((double)(int32_t)u);
            if (v > m) {
                m = v;
            }
        }
        return m / peak_scale;
    }
    double m = 0.0;
    for (int c = 0; c < nchannels; c++) {
        size_t off = offset + (size_t)c * 4u;
        uint32_t lo = u32le(raw + off);
        int32_t vv = (int32_t)lo;
        double v = fabs((double)vv);
        if (v > m) {
            m = v;
        }
    }
    return m / peak_scale;
}

int pv_dsp_rms_window_series(const char *path, double window_ms, PvDspRmsResult *out) {
    clear_rms(out);
    if (window_ms <= 0.0) {
        out->error = strdup("window_ms must be positive.");
        return -1;
    }

    PvWav w;
    if (wav_open(&w, path, &out->error) != 0) {
        return -1;
    }

    int window_frames = (int)(w.framerate * window_ms / 1000.0);
    if (window_frames < 1) {
        window_frames = 1;
    }
    size_t frame_b = (size_t)w.sampwidth * (size_t)w.nchannels;

    size_t nwin = 0;
    uint64_t pos = 0;
    while (pos < w.nframes) {
        nwin++;
        uint64_t take = (uint64_t)window_frames;
        if (pos + take > w.nframes) {
            take = w.nframes - pos;
        }
        pos += take;
    }

    out->rms = (double *)calloc(nwin, sizeof(double));
    out->times_center = (double *)calloc(nwin, sizeof(double));
    if (!out->rms || !out->times_center) {
        out->error = strdup("Out of memory.");
        goto fail;
    }
    out->n = nwin;
    out->duration_sec = (double)w.nframes / (double)w.framerate;
    out->sample_rate = w.framerate;

    if (fseek(w.f, w.data_offset, SEEK_SET) != 0) {
        out->error = strdup("Could not seek to PCM data.");
        goto fail;
    }

    pos = 0;
    size_t wi = 0;
    while (pos < w.nframes) {
        uint64_t take = (uint64_t)window_frames;
        if (pos + take > w.nframes) {
            take = w.nframes - pos;
        }
        size_t nbytes = (size_t)take * frame_b;
        unsigned char *buf = (unsigned char *)malloc(nbytes);
        if (!buf) {
            out->error = strdup("Out of memory.");
            goto fail;
        }
        if (fread(buf, 1, nbytes, w.f) != nbytes) {
            free(buf);
            out->error = strdup("Short read in WAV data.");
            goto fail;
        }
        out->rms[wi] = rms_linear_mono(buf, nbytes, w.sampwidth, w.nchannels);
        free(buf);

        pos += take;
        double t_end = (double)pos / (double)w.framerate;
        double t_start = ((double)pos - (double)take) / (double)w.framerate;
        out->times_center[wi] = (t_start + t_end) / 2.0;
        wi++;
    }

    fclose(w.f);
    w.f = NULL;
    return 0;

fail:
    if (w.f) {
        fclose(w.f);
    }
    free(out->rms);
    free(out->times_center);
    out->rms = NULL;
    out->times_center = NULL;
    out->n = 0;
    return -1;
}

int pv_dsp_waveform_envelope(const char *path, int num_bins, PvDspEnvResult *out) {
    clear_env(out);
    if (num_bins < 8) {
        out->error = strdup("num_bins too small.");
        return -1;
    }

    PvWav w;
    if (wav_open(&w, path, &out->error) != 0) {
        return -1;
    }

    double peak_scale = 128.0;
    if (w.sampwidth == 2) {
        peak_scale = 32768.0;
    } else if (w.sampwidth == 3) {
        peak_scale = 8388608.0;
    } else if (w.sampwidth == 4) {
        peak_scale = 2147483648.0;
    }

    size_t frame_b = (size_t)w.sampwidth * (size_t)w.nchannels;
    uint64_t nframes = w.nframes;
    uint64_t frames_per_bin = nframes / (uint64_t)num_bins;
    if (frames_per_bin < 1u) {
        frames_per_bin = 1u;
    }

    out->envelope = (double *)calloc((size_t)num_bins, sizeof(double));
    if (!out->envelope) {
        out->error = strdup("Out of memory.");
        fclose(w.f);
        return -1;
    }
    out->n_bins = (size_t)num_bins;
    out->duration_sec = (double)nframes / (double)w.framerate;

    if (fseek(w.f, w.data_offset, SEEK_SET) != 0) {
        out->error = strdup("Could not seek to PCM data.");
        fclose(w.f);
        free(out->envelope);
        out->envelope = NULL;
        return -1;
    }

    uint64_t chunk_frames = frames_per_bin;
    if (chunk_frames < 4096u) {
        chunk_frames = 4096u;
    }

    int bin_idx = 0;
    uint64_t frames_in_bin = 0;
    uint64_t pos = 0;

    while (pos < nframes) {
        uint64_t take = chunk_frames;
        if (pos + take > nframes) {
            take = nframes - pos;
        }
        size_t nbytes = (size_t)take * frame_b;
        unsigned char *raw = (unsigned char *)malloc(nbytes);
        if (!raw) {
            out->error = strdup("Out of memory.");
            goto env_fail;
        }
        if (fread(raw, 1, nbytes, w.f) != nbytes) {
            free(raw);
            out->error = strdup("Short read in WAV data.");
            goto env_fail;
        }
        for (uint64_t f = 0; f < take; f++) {
            size_t off = (size_t)f * frame_b;
            double pk = frame_peak_abs(raw, off, w.sampwidth, w.nchannels, peak_scale);
            if (pk > out->envelope[bin_idx]) {
                out->envelope[bin_idx] = pk;
            }
            frames_in_bin++;
            pos++;
            if (frames_in_bin >= frames_per_bin && bin_idx < num_bins - 1) {
                frames_in_bin = 0;
                bin_idx++;
            }
        }
        free(raw);
    }

    double m = 0.0;
    for (int i = 0; i < num_bins; i++) {
        if (out->envelope[i] > m) {
            m = out->envelope[i];
        }
    }
    if (m < 1e-12) {
        m = 1e-12;
    }
    for (int i = 0; i < num_bins; i++) {
        double v = out->envelope[i] / m;
        if (v > 1.0) {
            v = 1.0;
        }
        out->envelope[i] = v;
    }

    fclose(w.f);
    return 0;

env_fail:
    fclose(w.f);
    free(out->envelope);
    out->envelope = NULL;
    out->n_bins = 0;
    return -1;
}
