import pandas as pd
import streamlit as st
import seaborn as sns
import matplotlib.pyplot as plt
from io import BytesIO

st.set_page_config(page_title="📞 Agent Performance Dashboard", layout="wide")
st.title("📊 FAI Agent Daily Call Summary with Login Hours")

# Function to convert matplotlib figure to PNG bytes for download
def fig_to_png_bytes(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    return buf

# Upload master data and optional daily incremental data
uploaded_call_master = st.file_uploader("📄 Upload Master Call CSV (e.g. 1st–8th)", type=["csv"], key="call_master")
uploaded_call_daily = st.file_uploader("📄 Upload Today's/Hourly Call CSV (e.g. 9th July)", type=["csv"], key="call_daily")
uploaded_login = st.file_uploader("📅 Upload Login Report (Device On Time)", type=["csv"], key="login")

if uploaded_call_master or uploaded_call_daily:
    if uploaded_call_master:
        df_master = pd.read_csv(uploaded_call_master)
        df_master['source'] = 'master'
    else:
        df_master = pd.DataFrame()

    if uploaded_call_daily:
        df_daily = pd.read_csv(uploaded_call_daily)
        df_daily['source'] = 'daily'
    else:
        df_daily = pd.DataFrame()

    df = pd.concat([df_master, df_daily], ignore_index=True)

    # Preprocess call report
    df['Duration'] = pd.to_numeric(df['Duration'], errors='coerce')
    df['Status'] = df['Status'].str.lower()
    df['Direction'] = df['Direction'].str.lower()
    df['ToName'] = df['ToName'].fillna("N/A").astype(str).str.strip()
    df['FromName'] = df['FromName'].fillna("Not Worked").astype(str).str.strip()
    df['StartTime'] = pd.to_datetime(df['StartTime'], errors='coerce')
    df['StartHour'] = df['StartTime'].dt.hour
    df['Date'] = df['StartTime'].dt.date

    # Date filter
    available_dates = sorted(df['Date'].dropna().unique())
    selected_dates = st.multiselect("📅 Filter by Date", available_dates, default=available_dates)
    df = df[df['Date'].isin(selected_dates)]

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📄 Agent Summary", "⏱ Hourly Completed Calls", "❌ Inbound NA Calls Hourly"])

    with tab1:
        # ✅ Inbound
        inbound_df = df[(df["Direction"] == "inbound") & (df["ToName"].str.contains("FAI", na=False))]
        if not inbound_df.empty:
            inbound_summary = (
                inbound_df.groupby("ToName")
                .agg(
                    Completed_Calls=("Status", lambda x: (x == "completed").sum()),
                    Missed_Calls=("Status", lambda x: (x == "missed-call").sum()),
                    AHT_Min=("Duration", lambda x: round(x.mean() / 60, 2))
                )
                .reset_index()
                .rename(columns={"ToName": "Name"})
            )
        else:
            inbound_summary = pd.DataFrame(columns=["Name", "Completed_Calls", "Missed_Calls", "AHT_Min"])

        # ✅ Outbound
        outbound_df = df[(df["Direction"] == "outbound-dial") & (df["FromName"].str.contains("FAI", na=False))]
        if not outbound_df.empty:
            outbound_summary = (
                outbound_df[outbound_df["Status"] == "completed"]
                .groupby("FromName")
                .agg(Outbound_Calls=("Status", "count"))
                .reset_index()
                .rename(columns={"FromName": "Name"})
            )
            outbound_aht_df = (
                outbound_df.groupby("FromName")["Duration"]
                .mean()
                .apply(lambda x: round(x / 60, 2))
                .reset_index()
                .rename(columns={"FromName": "Name", "Duration": "Outbound_AHT_Min"})
            )
            outbound_summary = pd.merge(outbound_summary, outbound_aht_df, on="Name", how="outer")
        else:
            outbound_summary = pd.DataFrame(columns=["Name", "Outbound_Calls", "Outbound_AHT_Min"])

        summary = pd.merge(inbound_summary, outbound_summary, on="Name", how="outer")

        for col in ["Completed_Calls", "Missed_Calls", "AHT_Min", "Outbound_Calls", "Outbound_AHT_Min"]:
            summary[col] = summary[col].fillna("Not Worked")

        def safe_sum(row):
            try:
                return int(row["Completed_Calls"]) + int(row["Outbound_Calls"])
            except:
                return row["Completed_Calls"] if isinstance(row["Completed_Calls"], int) else row["Outbound_Calls"]

        summary["Grand_Total"] = summary.apply(safe_sum, axis=1)

        if uploaded_login:
            login_df = pd.read_csv(uploaded_login)
            login_df = login_df.rename(columns={
                "Name": "Name",
                "Total Device On Time (Overall)": "RawLoginTime"
            })

            def duration_format(time_str):
                try:
                    h, m, s = map(int, str(time_str).split(":"))
                    return f"{h:02}:{m:02}:{s:02}"
                except:
                    return "N/A"

            login_df["Login_Hours"] = login_df["RawLoginTime"].apply(duration_format)
            login_summary = login_df[["Name", "Login_Hours"]]
            summary = pd.merge(summary, login_summary, on="Name", how="left")
            summary["Login_Hours"] = summary["Login_Hours"].fillna("Not Available")

        st.subheader("📄 Agent-wise Summary Table")
        st.dataframe(summary.sort_values("Name"), use_container_width=True)
        st.download_button("📥 Download Summary CSV", data=summary.to_csv(index=False).encode("utf-8"), file_name="agent_summary.csv", mime="text/csv")

    with tab2:
        st.subheader("⏱ Hourly Completed Calls by Agent")
        agents = sorted(set(df[df["ToName"].str.contains("FAI")]["ToName"]) | set(df[df["FromName"].str.contains("FAI")]["FromName"]))
        selected_agents = st.multiselect("Select Agents", agents, default=agents)

        st.markdown("#### 📞 Inbound Calls (Completed)")
        inbound_heat = df[
            (df["Direction"] == "inbound") &
            (df["Status"] == "completed") &
            (df["ToName"].isin(selected_agents))
        ]
        if not inbound_heat.empty:
            inbound_pivot = inbound_heat.pivot_table(index="ToName", columns="StartHour", values="Status", aggfunc="count").fillna(0)
            fig_in, ax_in = plt.subplots(figsize=(15, len(inbound_pivot)//2 + 2))
            sns.heatmap(inbound_pivot, cmap="Blues", annot=True, fmt=".0f", ax=ax_in, linewidths=0.5, linecolor='gray', cbar_kws={'label': 'Call Count'})
            ax_in.set_title("Inbound Completed Calls by Hour", fontsize=16, weight='bold')
            ax_in.set_xlabel("Hour of Day")
            ax_in.set_ylabel("Agent")
            st.pyplot(fig_in)
            st.download_button("📥 Download Inbound Heatmap", data=fig_to_png_bytes(fig_in), file_name="inbound_heatmap.png", mime="image/png")
        else:
            st.warning("No completed inbound calls for selected agents.")

        st.markdown("#### 🧤 Outbound Calls (Completed)")
        outbound_heat = df[
            (df["Direction"] == "outbound-dial") &
            (df["Status"] == "completed") &
            (df["FromName"].str.contains("FAI", na=False)) &
            (df["FromName"].isin(selected_agents))
        ]
        if not outbound_heat.empty:
            outbound_pivot = outbound_heat.pivot_table(index="FromName", columns="StartHour", values="Status", aggfunc="count").fillna(0)
            fig_out, ax_out = plt.subplots(figsize=(15, len(outbound_pivot)//2 + 2))
            sns.heatmap(outbound_pivot, cmap="Greens", annot=True, fmt=".0f", ax=ax_out, linewidths=0.5, linecolor='gray', cbar_kws={'label': 'Call Count'})
            ax_out.set_title("Outbound Completed Calls by Hour", fontsize=16, weight='bold')
            ax_out.set_xlabel("Hour of Day")
            ax_out.set_ylabel("Agent")
            st.pyplot(fig_out)
            st.download_button("📥 Download Outbound Heatmap", data=fig_to_png_bytes(fig_out), file_name="outbound_heatmap.png", mime="image/png")
        else:
            st.warning("No completed outbound calls for selected agents.")

    with tab3:
        st.subheader("❌ Hourly Inbound NA Calls")
        na_calls = df[
            (df["Direction"] == "inbound") &
            (df["ToName"].str.strip().str.upper().isin(["NA", "N/A"]))
        ]
        st.metric("Total NA Calls", len(na_calls))

        if not na_calls.empty:
            na_pivot = na_calls.pivot_table(index="Status", columns="StartHour", values="ToName", aggfunc="count").fillna(0)
            fig_na, ax_na = plt.subplots(figsize=(15, len(na_pivot)//2 + 2))
            sns.heatmap(na_pivot, cmap="Reds", annot=True, fmt=".0f", ax=ax_na, linewidths=0.5, linecolor='gray', cbar_kws={'label': 'Call Count'})
            ax_na.set_title("Hourly NA Calls by Status", fontsize=16, weight='bold')
            ax_na.set_xlabel("Hour of Day")
            ax_na.set_ylabel("Call Status")
            st.pyplot(fig_na)
            st.download_button("📥 Download NA Calls Heatmap", data=fig_to_png_bytes(fig_na), file_name="na_calls_heatmap.png", mime="image/png")
        else:
            st.warning("No NA calls found.")
else:
    st.info("📌 Please upload the Exotel raw report CSV to generate the summary.")
