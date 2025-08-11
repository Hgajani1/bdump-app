import io
import re
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="NB Temps (renamed)", layout="wide")

st.title("NB Temps (renamed)")
st.caption("Upload an .lvm → select time window → match local Plotly look & controls.")

# --------- Your label map (edit as needed) ----------
# Map Temperature_i -> Pretty label (match your first screenshot)
TEMP_TO_LABEL = {
    0: "NB Dump TC#1",
    1: "NB Dump TC#2",
    2: "NB Dump TC#3",
    3: "NB Dump TC#4",
    4: "NB Dump TC#5",
    5: "NB Dump TC#6",
    6: "NB Dump TC#7",
    7: "NB Dump TC#8",
    8: "NB Dump TC#9",
    9: "NB Dump TC#10",
    10: "NB Dump TC#11",
    11: "NB Dump TC#12",
    12: "NB Scraper Lower TC#1",
    13: "NB Scraper Lower TC#2",
    14: "NB Scraper Lower TC#3",
    15: "NB Scraper Upper TC#4",
    16: "NB Scraper Upper TC#5",
    17: "NB Scraper Upper TC#6",
}

DUMP_KEYS = {k for k, v in TEMP_TO_LABEL.items() if "Dump" in v}
SCRAPER_KEYS = {k for k, v in TEMP_TO_LABEL.items() if "Scraper" in v}

# --------- Helpers ----------
def find_data_start_from_bytes(file_bytes: bytes):
    text = file_bytes.decode("utf-8", errors="ignore")
    end_idx = -1
    for i, line in enumerate(text.splitlines()):
        if line.strip() == "***End_of_Header***":
            end_idx = i
    if end_idx == -1:
        raise RuntimeError("Couldn't find ***End_of_Header*** in the file.")
    return end_idx + 1, text

@st.cache_data(show_spinner=False)
def load_lvm(uploaded_file) -> pd.DataFrame:
    raw = uploaded_file.read()
    start_row, txt = find_data_start_from_bytes(raw)
    df = pd.read_csv(io.StringIO(txt), sep="\t", skiprows=start_row)
    # Clean headers
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(axis=1, how="all")

    if "X_Value" not in df.columns:
        raise RuntimeError("X_Value column not found in this LVM.")

    # Ensure numerics
    df["X_Value"] = pd.to_numeric(df["X_Value"], errors="coerce")
    df = df.dropna(subset=["X_Value"]).reset_index(drop=True)

    # Convert Temperature_* columns to numeric
    for c in df.columns:
        if c != "X_Value":
            df[c] = pd.to_numeric(df[c], errors="ignore")

    # Rename Temperature_i -> pretty labels if present
    rename_map = {}
    for idx, label in TEMP_TO_LABEL.items():
        col = f"Temperature_{idx}"
        if col in df.columns:
            rename_map[col] = label
    df = df.rename(columns=rename_map)

    return df

def build_figure(df_win: pd.DataFrame, ycols: list[str]) -> go.Figure:
    fig = go.Figure()
    for col in ycols:
        fig.add_trace(go.Scatter(
            x=df_win["X_Value"], y=df_win[col],
            mode="lines", name=col
        ))
    fig.update_layout(
        template="plotly_white",
        height=650,
        margin=dict(l=60, r=20, t=60, b=60),
        legend_title_text="Click to toggle",
        xaxis_title="Time (s)",
        yaxis_title="Temperature (°C)",
    )
    # Show rangeslider at the bottom like your local figure
    fig.update_xaxes(rangeslider=dict(visible=True))
    return fig

# --------- Sidebar controls ----------
with st.sidebar:
    st.header("1) Upload")
    up = st.file_uploader("Choose a .lvm file", type=["lvm"])

    st.header("2) Time window (seconds)")
    # Default to 10–20 s to mirror your screenshot
    tmin = st.number_input("tmin", value=10.0, step=0.5)
    tmax = st.number_input("tmax", value=20.0, step=0.5)
    if tmax < tmin:
        st.warning("tmax < tmin — adjusted to match tmin")
        tmax = tmin

    st.header("3) Plot options")
    downsample = st.checkbox("Downsample for plotting", value=False)
    step = st.number_input("Every Nth point", min_value=1, value=5)

if not up:
    st.info("Upload a `.lvm` file to begin.")
    st.stop()

# --------- Data load + filter ----------
try:
    df = load_lvm(up)
except Exception as e:
    st.error(f"Failed to read LVM: {e}")
    st.stop()

xmin, xmax = float(np.nanmin(df["X_Value"])), float(np.nanmax(df["X_Value"]))
# Clip selected window to data limits
tmin = max(tmin, xmin)
tmax = min(tmax, xmax)

mask = (df["X_Value"] >= tmin) & (df["X_Value"] <= tmax)
df_win = df.loc[mask].copy()

# Choose columns (exclude X_Value)
ycols_all = [c for c in df.columns if c != "X_Value"]
if not ycols_all:
    st.error("No data columns to plot besides X_Value.")
    st.stop()

# Group helpers for buttons
dump_labels    = [TEMP_TO_LABEL[i] for i in sorted(DUMP_KEYS) if TEMP_TO_LABEL.get(i) in ycols_all]
scraper_labels = [TEMP_TO_LABEL[i] for i in sorted(SCRAPER_KEYS) if TEMP_TO_LABEL.get(i) in ycols_all]

st.subheader(f"NB Temps (renamed) — {tmin:g}–{tmax:g} s")

# Quick filters like your local UI
c1, c2, c3 = st.columns([1,1,1])
with c1:
    if st.button("Show All"):
        default_sel = ycols_all
with c2:
    if st.button("Only Dump"):
        default_sel = dump_labels or ycols_all
with c3:
    if st.button("Only Scrapers"):
        default_sel = scraper_labels or ycols_all

# If no quick button pressed this run, default to all
default_sel = locals().get("default_sel", ycols_all)

# Multiselect to fine-tune
sel = st.multiselect("Signals", options=ycols_all, default=default_sel)

# Optional downsample for plotting speed
plot_df = df_win.iloc[::step, :] if (downsample and step > 1) else df_win

fig = build_figure(plot_df, sel if sel else ycols_all)
st.plotly_chart(fig, use_container_width=True)

# Summary + data preview
with st.expander("Summary"):
    st.write(f"Time range in file: {xmin:.3f} → {xmax:.3f} s")
    st.write(f"Selected window: {tmin:.3f} → {tmax:.3f} s")
    st.write(f"Rows in window: {len(df_win):,}")

with st.expander("Table (first 500 rows in window)"):
    st.dataframe(df_win.head(500))
