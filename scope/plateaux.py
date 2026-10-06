"""Extraction des plateaux U/I d'une capture (impulsions PEO), en direct ou en fin de série.

**Source unique** de l'algorithme : la GUI (en direct, :class:`LiveAnalysis`)
et le script d'analyse a posteriori ``tools/extract_plateaux.py`` (simple lanceur
qui lit les CSV) l'importent tous les deux.

Par capture : découpe des impulsions par seuillage à hystérésis (sur I ou sur U,
le plus régulier), statistiques sur le cœur de chaque plateau, fréquence et
rapport cyclique. Sur toute la série : estimation du mode de pilotage (courant
ou tension contrôlé) et synthèse.

- :func:`analyse_arrays` prend des tableaux (``t, U, I``) en V et A ;
  :func:`analyse_waveforms` choisit les voies U/I et convertit leur unité
  (:func:`to_si`) avant.
- Les figures passent par ``matplotlib.figure.Figure`` (pas ``pyplot``) : elles
  sont produites depuis le thread d'acquisition de la GUI, où ``pyplot`` (état
  global, backend Qt possible) n'a pas sa place.

Module Qt-free et testable (cf. ``tests/test_plateaux.py``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# --- Paramètres ---------------------------------------------------------------------
MIN_AMPLITUDE_A = 1.0      # en dessous : capture sans signal
MIN_AMPLITUDE_V = 40.0     # niveau mini pour découper sur la tension
U_ABSENT_V = 20.0          # plateau U sous ce niveau alors que I circule : voie U muette
HYST_HI, HYST_LO = 0.6, 0.4  # seuils d'hystérésis (fraction du niveau haut)
MIN_RUN_S = 0.25e-3        # durée mini d'un plateau (élimine les pointes de coupure)
NEG_MIN_FRACTION = 0.3     # plateau négatif plus court (x plateau positif) : queue de coupure
U_REF_PENALTY = 0.05       # à régularité égale, découper sur I (U est quantifié à 8 V)
EDGE_TRIM = 0.15           # fraction retirée à chaque bord du plateau
MODE_THRESHOLD = np.log(2)  # U ou I doit être 2x plus stable que l'autre pour trancher
MODE_EPS = 0.01            # plancher de bruit relatif (~1 %) du mode de pilotage
MODE_HALF_WINDOW = 3       # fenêtre de captures voisines pour le mode de pilotage
SUMMARY_EDGE = 3           # captures (médiane) pour la synthèse « début -> fin »
JUMP_U_TOL = 0.20          # écart de U à ses voisines au-delà duquel une capture est un saut
JUMP_I_TOL = 0.05          # I considéré inchangé en deçà (sinon : vrai changement de régime)
RUPTURE_U_TOL = 0.25       # saut de U entre captures consécutives = rupture de régime

# Colonnes du CSV de synthèse ``{exp}_plateaux.csv``.
COLUMNS = ["index", "t_s", "flag", "ref", "mode", "mode_score", "freq_Hz", "freq_fft_Hz",
           "t_on_ms", "duty", "n_pulses_pos", "n_pulses_neg"]
for _s in ("pos", "neg"):
    COLUMNS += [f"{q}_{_s}" for q in ("U_med", "U_mean", "U_std", "I_med", "I_mean", "I_std")]

_PREFIXES = {"": 1.0, "m": 1e-3, "k": 1e3, "µ": 1e-6, "u": 1e-6}


# --- conversion d'unités -------------------------------------------------------------
def to_si(values, unit: str):
    """Convertit ``values`` exprimées en ``unit`` (V, mV, kV, A, mA, µA…) vers
    l'unité de base. Retourne ``(valeurs, "V" | "A")`` ; ``ValueError`` si
    l'unité n'est ni une tension ni un courant (ex. W)."""
    unit = unit.strip()
    base, prefix = unit[-1:], unit[:-1]
    if base not in ("V", "A") or prefix not in _PREFIXES:
        raise ValueError(f"unité {unit!r} non convertible en V ou A")
    return np.asarray(values, float) * _PREFIXES[prefix], base


# --- découpage d'une capture -----------------------------------------------------------
def state_level(x, q=0.9):
    """Niveau d'état haut (approche IEEE 181 simplifiée) : médiane des points
    au-dessus du quantile q. Les pointes brèves (< 10 % des points) ne
    suffisent pas à créer un niveau."""
    return max(float(np.median(x[x >= np.quantile(x, q)])), 0.0)


def hysteresis_runs(x, level, dt):
    """Runs où x est au-dessus du seuil (trigger de Schmitt).
    Retourne des (début, fin) en indices, fin exclue."""
    hi_thr, lo_thr = HYST_HI * level, HYST_LO * level
    state = np.zeros(x.size, dtype=bool)
    s = False
    for k, v in enumerate(x):
        if not s and v > hi_thr:
            s = True
        elif s and v < lo_thr:
            s = False
        state[k] = s
    d = np.diff(np.r_[0, state.astype(int), 0])
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    runs = []
    for a, b in zip(starts, ends):
        if a == 0 or b == x.size:  # plateau tronqué par la fenêtre
            continue
        if (b - a) * dt < MIN_RUN_S:
            continue
        runs.append((a, b))
    return runs


def segment(x, dt, min_level):
    """Plateaux positifs et négatifs de x. Un plateau négatif n'est retenu que
    s'il dure au moins ``NEG_MIN_FRACTION`` d'un plateau positif."""
    lp, ln = state_level(x), state_level(-x)
    pos = hysteresis_runs(x, lp, dt) if lp >= min_level else []
    neg = hysteresis_runs(-x, ln, dt) if ln >= min_level else []
    if pos:
        dmin = NEG_MIN_FRACTION * np.median([b - a for a, b in pos])
        neg = [(a, b) for a, b in neg if b - a >= dmin]
    return pos, neg


def regularity(runs):
    """CV des durées et des intervalles entre plateaux : plus c'est bas, plus
    le découpage est régulier."""
    if len(runs) < 2:
        return np.inf
    d = np.array([b - a for a, b in runs], float)
    p = np.diff([a for a, _ in runs]).astype(float)
    return d.std() / d.mean() + p.std() / p.mean()


def best_segmentation(U, I, dt):
    """Découpe sur I et sur U, garde la plus régulière. I est souvent plus
    propre (U quantifié à 8 V), mais en début de PEO les micro-décharges rendent
    I irrégulier alors que U reste un créneau net."""
    cands = {"I": segment(I, dt, MIN_AMPLITUDE_A),
             "U": segment(U, dt, MIN_AMPLITUDE_V)}
    name = min(cands, key=lambda k: regularity(cands[k][0]) + U_REF_PENALTY * (k == "U"))
    return (*cands[name], name)


def core(a, b):
    n = b - a
    cut = int(round(EDGE_TRIM * n))
    return a + cut, b - cut


def plateau_stats(U, I, runs):
    """Statistiques agrégées sur les cœurs des plateaux d'une polarité."""
    if not runs:
        return {}
    meds_U, meds_I, Uc, Ic = [], [], [], []
    for a, b in runs:
        a2, b2 = core(a, b)
        meds_U.append(np.median(U[a2:b2]))
        meds_I.append(np.median(I[a2:b2]))
        Uc.append(U[a2:b2])
        Ic.append(I[a2:b2])
    Uc, Ic = np.concatenate(Uc), np.concatenate(Ic)
    return {
        "U_med": float(np.median(meds_U)),
        "U_mean": float(Uc.mean()),
        "U_std": float(Uc.std()),
        "I_med": float(np.median(meds_I)),
        "I_mean": float(Ic.mean()),
        "I_std": float(Ic.std()),
    }


def fft_freq(x, dt):
    x = x - x.mean()
    n = 1 << 17  # zéro-padding : résolution native 1/28 ms = 36 Hz seulement
    F = np.abs(np.fft.rfft(x * np.hanning(x.size), n))
    f = np.fft.rfftfreq(n, dt)
    F[f < 20] = 0
    return float(f[np.argmax(F)])


def analyse_arrays(t, U, I):
    """Analyse une capture (temps s, U en V, I en A). Retourne ``(row, traces)``
    où ``traces = (t, U, I, runs_pos, runs_neg)``, ou ``None`` sans signal."""
    t, U, I = (np.asarray(a, float) for a in (t, U, I))
    dt = float(np.median(np.diff(t)))
    row = {"n_pulses_pos": 0, "n_pulses_neg": 0}
    if max(state_level(I), state_level(-I)) < MIN_AMPLITUDE_A:
        row["flag"] = "no_signal"
        return row, None
    runs_pos, runs_neg, ref_name = best_segmentation(U, I, dt)
    for suffix, runs in (("pos", runs_pos), ("neg", runs_neg)):
        row[f"n_pulses_{suffix}"] = len(runs)
        for k, v in plateau_stats(U, I, runs).items():
            row[f"{k}_{suffix}"] = v
    ref = runs_pos if runs_pos else runs_neg
    if len(ref) >= 2:
        period = float(np.median(np.diff([a for a, _ in ref]))) * dt
        row["freq_Hz"] = 1.0 / period
        row["t_on_ms"] = float(np.median([b - a for a, b in ref])) * dt * 1e3
        row["duty"] = row["t_on_ms"] * 1e-3 / period
    row["freq_fft_Hz"] = fft_freq(I, dt)
    row["ref"] = ref_name
    row["flag"] = "ok" if ref else "no_plateau"
    if ref and abs(row.get("U_med_pos", 0)) < U_ABSENT_V:
        row["flag"] = "U_absent"  # voie tension muette alors que I circule
    elif runs_neg and row.get("U_med_pos", 0) < row.get("U_med_neg", 0):
        row["flag"] = "U_dephase"  # U non synchrone de I
    return row, (t, U, I, runs_pos, runs_neg)


def analyse_waveforms(waveforms: dict, u_channel: str, i_channel: str):
    """Analyse les waveforms d'une capture de série (``{voie: Waveform}``) :
    prend ``u_channel``/``i_channel``, convertit leurs valeurs en V et A, puis
    :func:`analyse_arrays`. ``ValueError`` si une voie manque ou si son unité
    ne correspond pas à la grandeur attendue."""
    arrays = {}
    for role, ch, expected, word in (("U", u_channel, "V", "tension"), ("I", i_channel, "A", "courant")):
        wf = waveforms.get(ch)
        if wf is None:
            raise ValueError(f"voie {role} ({ch}) absente de la capture")
        values, base = to_si(wf.values, wf.unit)
        if base != expected:
            raise ValueError(f"voie {role} ({ch}) en {wf.unit} : une {word} ({expected}) est attendue")
        arrays[role] = (wf.time, values)
    return analyse_arrays(arrays["U"][0], arrays["U"][1], arrays["I"][1])


# --- PNG de vérification du découpage -------------------------------------------------------
def draw_capture(a, t, U, I, runs_pos, runs_neg):
    """Trace U et I (double axe) sur l'axe ``a``, cœurs de plateaux retenus
    surlignés (vert = positifs, rouge = négatifs). Retourne l'axe de I (au-dessus)."""
    a.plot(t * 1e3, U, lw=0.8, color="C0")
    a.set_ylabel("U (V)", color="C0")
    a2 = a.twinx()
    a2.plot(t * 1e3, I, lw=0.8, color="C1")
    a2.set_ylabel("I (A)", color="C1")
    for runs, col in ((runs_pos, "green"), (runs_neg, "red")):
        for s, e in runs:
            s2, e2 = core(s, e)
            a.axvspan(t[s2] * 1e3, t[e2 - 1] * 1e3, color=col, alpha=0.2)
    return a2


def save_selection_png(t, U, I, runs_pos, runs_neg, path, *, title: str = "") -> None:
    """Une capture par fichier (GUI, à chaque capture de série)."""
    from matplotlib.figure import Figure

    fig = Figure(figsize=(10, 3.5))
    a = fig.subplots()
    draw_capture(a, t, U, I, runs_pos, runs_neg)
    a.set_title(title)
    a.set_xlabel("t (ms)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def capture_tag(row) -> str:
    """Numéro de capture sur 4 chiffres, identique au suffixe du fichier
    (``0022`` <-> ``PEO_N_41_0022.csv``)."""
    return f"{row['index']:04d}"


def control_label(row, exp: str) -> str:
    """Titre d'une ligne du PNG de contrôle : nom du fichier de la capture, puis
    anomalie en toutes lettres (pas seulement signalée par la couleur)."""
    label = f"{exp}_{capture_tag(row)}.csv   t = {row['t_s']:.0f} s"
    if row["flag"] != "ok":
        label += f"  —  ANOMALIE {row['flag']}"
    if row.get("U_med_pos") is None or np.isnan(row.get("U_med_pos")):  # pas de plateau mesuré
        return label
    return f"{label}  —  U = {row['U_med_pos']:.0f} V, I = {row['I_med_pos']:.1f} A, f = {row['freq_Hz']:.0f} Hz"


def save_control_png(captures, path, *, title: str = "", row_height=1.8) -> None:
    """Toutes les captures d'un essai dans un seul PNG, une ligne par capture dans
    l'ordre (contrôle rapide du découpage en faisant défiler l'image).
    ``captures`` : liste de ``(row, (t, U, I, runs_pos, runs_neg))``, captures sans
    signal comprises (runs vides) ; ``title`` = id de l'essai (préfixe des fichiers).
    Chaque ligne porte en marge gauche son numéro en grand (cartouche rouge si anomalie)."""
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle

    # "constrained" réserve la place du titre général (tight_layout le superpose à la 1re ligne)
    fig = Figure(figsize=(10, 0.6 + row_height * len(captures)), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.12)  # marge (pouces) : le cartouche du numéro n'est pas rogné
    axes = fig.subplots(len(captures), 1, squeeze=False)[:, 0]
    for a, (row, trace) in zip(axes, captures):
        top = draw_capture(a, *trace)
        anomaly = row["flag"] != "ok"
        a.set_title(control_label(row, title), loc="left", fontsize=9, color="red" if anomaly else "black")
        # numéro en grand dans la marge gauche, à gauche de l'axe U
        a.text(-0.09, 0.5, capture_tag(row), transform=a.transAxes, ha="right", va="center",
               fontsize=22, fontweight="bold", color="white" if anomaly else "black",
               bbox=dict(boxstyle="round,pad=0.3", fc="red" if anomaly else "#e6e6e6", ec="none"))
        if anomaly:  # voile rouge pâle sur toute la capture : repérable au défilement
            top.add_patch(Rectangle((0, 0), 1, 1, transform=top.transAxes, color="red",
                                    alpha=0.15, zorder=10, lw=0))
    axes[-1].set_xlabel("t (ms)")
    fig.suptitle(f"{title} — contrôle du découpage (vert : plateaux +, rouge : plateaux −)")
    fig.savefig(path, dpi=80)


# --- fin de série : mode de pilotage + synthèse ------------------------------------------
def roughness_drift(t, s, center):
    """Rugosité (écart-type autour de la droite ajustée) et dérive (pente x durée)
    de la série ``s`` sur la fenêtre, relatives à son niveau. Le point le plus
    éloigné de la droite est écarté (capture aberrante isolée), sauf ``center``,
    la capture qu'on classe."""
    m = np.median(np.abs(s))
    if len(s) < 3 or not m:
        return np.nan, np.nan
    keep = np.ones(len(s), bool)
    if len(s) >= 5:
        r = np.abs(s - np.polyval(np.polyfit(t, s, 1), t))
        r[center] = -1
        keep[np.argmax(r)] = False
    p = np.polyfit(t[keep], s[keep], 1)
    return np.std(s[keep] - np.polyval(p, t[keep])) / m, abs(p[0] * (t[-1] - t[0])) / m


def window_stats(df, w, center):
    """(rugosité U, dérive U, rugosité I, dérive I) sur les captures ``w``."""
    t = df.loc[w, "t_s"].to_numpy()
    ru, du = roughness_drift(t, df.loc[w, "U_mean_pos"].to_numpy(), center)
    ri, di = roughness_drift(t, df.loc[w, "I_mean_pos"].to_numpy(), center)
    return ru, du, ri, di


def mode_score(ru, du, ri, di):
    """log(I / U) : > 0 -> U plus stable (tension contrôlée), < 0 -> courant.
    La grandeur pilotée suit sa consigne (constante ou rampe) : elle est la
    moins rugueuse. Si U et I sont aussi lisses l'un que l'autre, c'est celle
    qui ne dérive pas (l'autre suit la croissance de la couche d'oxyde)."""
    score = np.log((ri + MODE_EPS) / (ru + MODE_EPS))
    if abs(score) <= MODE_THRESHOLD:
        score = np.log((di + MODE_EPS) / (du + MODE_EPS))
    return score


def estimate_mode(df, half_window=MODE_HALF_WINDOW):
    """Mode de pilotage capture par capture, sur des fenêtres de captures voisines.
    Parmi les fenêtres gauche, centrée et droite, on garde la plus homogène (filtre
    de Kuwahara) pour ne pas étaler les changements de régime. Ajoute les colonnes
    'mode' et 'mode_score' ; retourne le mode majoritaire et les phases."""
    ok = df.index[df["flag"] == "ok"]
    df["mode"], df["mode_score"] = "", np.nan
    for k, i in enumerate(ok):
        spans = [(max(0, lo), hi) for lo, hi in
                 ((k - 2 * half_window, k), (k - half_window, k + half_window), (k, k + 2 * half_window))]
        stats = [window_stats(df, ok[lo:hi + 1], k - lo) for lo, hi in spans if len(ok[lo:hi + 1]) >= 3]
        if not stats:
            continue
        score = mode_score(*min(stats, key=lambda st: st[0] + st[2]))
        df.loc[i, "mode_score"] = score
        df.loc[i, "mode"] = ("tension contrôlée" if score > MODE_THRESHOLD else
                             "courant contrôlé" if score < -MODE_THRESHOLD else
                             "indéterminé")
    # résumé en phases successives
    m = df.loc[ok, ["index", "mode"]]
    phases = []
    for _, g in m.groupby((m["mode"] != m["mode"].shift()).cumsum()):
        phases.append(f"{g['mode'].iloc[0]} (#{g['index'].iloc[0]}–#{g['index'].iloc[-1]})")
    main = m["mode"].mode().iloc[0] if len(m) else "indéterminé"
    return {"mode_majoritaire": main, "phases": " → ".join(phases)}


def plot_series(df, exp, out):
    from matplotlib.figure import Figure

    ok = df[df["flag"] == "ok"]
    bip = ok["n_pulses_neg"].sum() > 0
    fig = Figure(figsize=(9, 9))
    ax = fig.subplots(3, 1, sharex=True)
    # fond coloré selon le mode de pilotage estimé
    colors = {"courant contrôlé": "tab:orange", "tension contrôlée": "tab:blue"}
    tt = ok["t_s"].to_numpy()
    half = np.median(np.diff(tt)) / 2 if len(tt) > 1 else 15
    for t_c, m in zip(tt, ok["mode"]):
        if m in colors:
            for a in ax:
                a.axvspan(t_c - half, t_c + half, color=colors[m], alpha=0.08, lw=0)
    for k, (q, unit) in enumerate((("U", "V"), ("I", "A"))):
        ax[k].errorbar(ok["t_s"], ok[f"{q}_med_pos"], yerr=ok[f"{q}_std_pos"],
                       fmt="o-", ms=4, capsize=2, label="plateau +")
        if bip:
            ax[k].errorbar(ok["t_s"], ok[f"{q}_med_neg"], yerr=ok[f"{q}_std_neg"],
                           fmt="s-", ms=4, capsize=2, label="plateau −")
        ax[k].set_ylabel(f"{q} ({unit})")
        ax[k].grid(alpha=0.3)
        ax[k].legend()
    ax[2].plot(ok["t_s"], ok["freq_Hz"], "o-", ms=4, label="fronts")
    ax[2].plot(ok["t_s"], ok["freq_fft_Hz"], "x", label="FFT")
    ax[2].set_ylabel("f (Hz)")
    ax[2].set_xlabel("t (s)")
    ax[2].grid(alpha=0.3)
    ax[2].legend()
    fig.suptitle(f"{exp} — médiane des plateaux (±σ)\n"
                 "fond : orange = courant contrôlé, bleu = tension contrôlée (estimé)")
    fig.tight_layout()
    fig.savefig(Path(out) / f"{exp}_UI_vs_t.png", dpi=120)


def finalize_series(series_dir, exp: str, rows: list[dict]):
    """Fin de série : estime le mode de pilotage sur les lignes accumulées
    (une par capture : ``{"index", "t_s", **row}``), écrit ``{exp}_plateaux.csv``
    et ``{exp}_UI_vs_t.png`` dans ``series_dir`` et retourne la synthèse (dict).
    Aucune ligne -> rien d'écrit, ``None``."""
    if not rows:
        return None
    import pandas as pd

    out = Path(series_dir)
    df = pd.DataFrame(rows).reindex(columns=COLUMNS)
    ruptures = flag_jumps(df)
    for row, flag in zip(rows, df["flag"]):  # les sauts de U ne se voient qu'en fin de série
        row["flag"] = flag
    mode_summary = estimate_mode(df)
    df.to_csv(out / f"{exp}_plateaux.csv", index=False, float_format="%.4g", encoding="utf-8-sig")
    plot_series(df, exp, out)
    ok = df[df["flag"] == "ok"]
    return {
        "experiment": exp,
        "n_captures": len(df),
        "n_ok": len(ok),
        "bipolaire": bool(ok["n_pulses_neg"].sum() > 0),
        "freq_Hz": ok["freq_Hz"].median(),
        "duty": ok["duty"].median(),
        "U_pos_debut_fin": start_end(ok["U_med_pos"], "{:.0f}"),
        "I_pos_debut_fin": start_end(ok["I_med_pos"], "{:.1f}"),
        "ruptures_U": ruptures,
        **mode_summary,
    }


def flag_jumps(df):
    """Anomalies visibles seulement en comparant une capture à ses voisines (« ok »),
    quand I ne bouge pas (< ``JUMP_I_TOL``) :

    - saut isolé de U : la capture s'écarte de plus de ``JUMP_U_TOL`` de la droite
      passant par ses voisines (jusqu'à 2 de chaque côté, sans saut entre elles) ->
      flag ``U_saut`` (exclue de U(t) et du mode de pilotage) ;
    - rupture durable : U change de plus de ``RUPTURE_U_TOL`` d'une capture à la
      suivante et reste au nouveau niveau -> signalée (chaîne retournée), pas exclue.
    """
    ok = np.flatnonzero(df["flag"].to_numpy() == "ok").tolist()  # positions
    t, U, I = (df[c].to_numpy(float) for c in ("t_s", "U_med_pos", "I_med_pos"))
    for k, i in enumerate(ok):
        nb = ok[max(0, k - 2):k] + ok[k + 1:k + 3]
        if len(nb) < 2:
            continue
        # voisines sans saut entre elles (sinon pas de référence fiable, ex. rupture)
        coherent = np.all(np.abs(np.diff(U[nb])) <= JUMP_U_TOL * np.abs(U[nb][1:]))
        pu, pi = (np.polyfit(t[nb], v[nb], 1) for v in (U, I))
        u_pred, i_pred = np.polyval(pu, t[i]), np.polyval(pi, t[i])
        if (coherent and abs(U[i] - u_pred) > JUMP_U_TOL * abs(u_pred)
                and abs(I[i] - i_pred) <= JUMP_I_TOL * abs(i_pred)):
            df.loc[df.index[i], "flag"] = "U_saut"
    # ruptures : sauts entre captures « ok » consécutives, même sens fusionnés
    ok = np.flatnonzero(df["flag"].to_numpy() == "ok").tolist()
    events = []
    for a, b in zip(ok, ok[1:]):
        if (abs(U[b] - U[a]) > RUPTURE_U_TOL * max(abs(U[a]), abs(U[b]))
                and abs(I[b] - I[a]) <= JUMP_I_TOL * abs(I[a])):
            if events and events[-1][1] == a and np.sign(U[b] - U[a]) == np.sign(U[a] - U[events[-1][0]]):
                events[-1][1] = b
            else:
                events.append([a, b])
    idx = df["index"].to_numpy()
    return " ; ".join(f"U {U[a]:.0f} -> {U[b]:.0f} V (#{idx[a]} -> #{idx[b]})" for a, b in events)


def start_end(values, fmt):
    """« début -> fin » : médianes des ``SUMMARY_EDGE`` premières et dernières
    valeurs (une capture aberrante en bout de série ne fausse pas la synthèse)."""
    if values.empty:
        return ""
    v = values.to_numpy()
    return f"{fmt.format(np.median(v[:SUMMARY_EDGE]))} -> {fmt.format(np.median(v[-SUMMARY_EDGE:]))}"


# --- accumulation en direct (GUI) -------------------------------------------------------
class LiveAnalysis:
    """Analyse capture par capture pendant une série, puis synthèse à la fin.

    :meth:`add` analyse une capture et écrit ``{exp}_{index:04d}_plateaux.png``
    (si des plateaux existent) ; :meth:`finish` estime le mode de pilotage sur
    toutes les lignes et écrit CSV + ``_UI_vs_t.png`` (:func:`finalize_series`).
    Qt-free : appelé depuis le thread d'acquisition de la GUI."""

    def __init__(self, series_dir, exp: str, u_channel: str, i_channel: str) -> None:
        self.series_dir = Path(series_dir)
        self.exp = exp
        self.u_channel = u_channel
        self.i_channel = i_channel
        self.rows: list[dict] = []
        self._t0: float | None = None

    def add(self, index: int, timestamp: float, waveforms: dict) -> dict:
        """Retourne ``{"row", "traces", "png"}`` ; ``ValueError`` si les voies U/I
        sont absentes ou d'unité incompatible (la ligne n'est alors pas gardée)."""
        row, traces = analyse_waveforms(waveforms, self.u_channel, self.i_channel)
        if self._t0 is None:
            self._t0 = timestamp
        row = {"index": index, "t_s": timestamp - self._t0, **row}
        self.rows.append(row)
        png = None
        if traces is not None:
            png = self.series_dir / f"{self.exp}_{index:04d}_plateaux.png"
            save_selection_png(*traces, png, title=f"{self.exp} — capture {index} ({row['flag']})")
        return {"row": row, "traces": traces, "png": png}

    def finish(self):
        return finalize_series(self.series_dir, self.exp, self.rows)
