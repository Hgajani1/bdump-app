import io
import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="BDUMP Analysis", layout="wide")
st.title("BDUMP Analysis")
st.caption("Upload a LabVIEW Measurement (.lvm), select a time window, and explore signals interactively.")

# ========= Helpers =========
def find_data_start_from_bytes(file_bytes: bytes):
    """Return (start_row_index, decoded_text) after the last ***End_of_Header*** line."""
    text = file_bytes.decode("utf-8", errors="ignore")
    end_idx = -1
    for i, line in enumerate(text.splitlines()):
        if line.strip() == "***End_of_Header***":
            end_idx = i
    if end_idx == -1:
        raise RuntimeError("Couldn't find ***End_of_Header*** in the file.")
    return end_idx + 1, text

@st.cache_data(show_spinner=False)
def load_lvm(uploaded_file: "UploadedFile") -> pd.DataFrame:
    """Read .lvm into DataFrame, clean columns, ensure X_Value numeric."""
    raw = uploaded_file.read()
    start_row, txt = find_data_start_from_bytes(raw)
    df = pd.read_csv(io.StringIO(txt), sep="\t", skiprows=start_row)
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(axis=1, how="all")

    if "X_Value" not in df.columns:
        raise RuntimeError("X_Value column not found in this LVM.")
    df["X_Value"] = pd.to_numeric(df["X_Value"], errors="coerce")
    df = df.dropna(subset=["X_Value"]).reset_index(drop=True)

    # Try to convert other columns to numeric where possible
    for c in df.columns:
        if c != "X_Value":
            df[c] = pd.to_numeric(df[c], errors="ignore")
    return df

def plot_traces(df_win: pd.DataFrame, ycols: list[str]) -> go.Figure:
    fig = go.Figure()
    for col in ycols:
        fig.add_trace(go.Scatter(
            x=df_win["X_Value"], y=df_win[col],
            mode="lines", name=col
        ))
    fig.update_layout(
        template="plotly_white",
        xaxis_title="Time (s)",
        yaxis_title="Value",
        legend_title="Signals",
        height=650,
        margin=dict(l=60, r=20, t=60, b=60)
    )
    return fig

# ========= Sidebar =========
with st.sidebar:
    st.header("1) Upload")
    up = st.file_uploader("Choose a .lvm file", type=["lvm"])

    st.header("2) Time window (seconds)")
    tmin = st.number_input("tmin", value=0.0, step=0.5)
    tmax = st.number_input("tmax", value=10.0, step=0.5)
    if tmax < tmin:
        st.warning("tmax < tmin — adjusted to match tmin")
        tmax = tmin

    st.header("3) Plot options")
    downsample = st.checkbox("Downsample for plotting", value=True)
    step = st.number_input("Every Nth point", min_value=1, value=5)

# ========= Main =========
if not up:
    st.info("Upload a `.lvm` file to begin.")
    st.stop()

try:
    df = load_lvm(up)
except Exception as e:
    st.error(f"Failed to read LVM: {e}")
    st.stop()

xmin, xmax = float(np.nanmin(df["X_Value"])), float(np.nanmax(df["X_Value"]))
# Set a sensible default window if user left defaults
if (tmin, tmax) == (0.0, 10.0):
    tmin = xmin
    tmax = min(xmin + 0.2*(xmax - xmin), xmax)

# OPTIONAL: apply your custom renaming/mapping here
# Example:
# rename_map = {"Temperature_0": "NB Dump TC#1", ...}
# df = df.rename(columns=rename_map)

# Filter by time
mask = (df["X_Value"] >= tmin) & (df["X_Value"] <= tmax)
df_win = df.loc[mask].copy()

# Select columns to plot (exclude X_Value)
ycols_all = [c for c in df.columns if c != "X_Value"]
if not ycols_all:
    st.error("No data columns to plot besides X_Value.")
    st.stop()

st.subheader("Summary")
c1, c2 = st.columns(2)
with c1:
    st.metric("Total rows", f"{len(df):,}")
    st.metric("Rows in window", f"{len(df_win):,}")
with c2:
    st.write(f"Time range: {xmin:.3f} → {xmax:.3f} s")
    st.write(f"Selected window: {tmin:.3f} → {tmax:.3f} s")

st.subheader("Signals to plot")
default_cols = ycols_all[: min(8, len(ycols_all))]
sel = st.multiselect("Pick columns", options=ycols_all, default=default_cols)
if not sel:
    st.warning("Select at least one signal.")
    st.stop()

plot_df = df_win.iloc[::step, :] if (downsample and step > 1) else df_win
fig = plot_traces(plot_df, sel)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Show filtered data (first 500 rows)"):
    st.dataframe(df_win.head(500))

# Downloads
st.subheader("Download")
st.download_button(
    "Download filtered CSV",
    data=df_win.to_csv(index=False).encode("utf-8"),
    file_name=f"filtered_{tmin:.3f}-{tmax:.3f}s.csv",
    mime="text/csv",
)
st.download_button(
    "Download interactive plot (HTML)",
    data=fig.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8"),
    file_name=f"plot_{tmin:.3f}-{tmax:.3f}s.html",
    mime="text/html",
)
