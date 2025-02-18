import streamlit as st
import pandas as pd
import zipfile
import numpy as np
from io import BytesIO

def extract_zip(uploaded_file):
    """Extract ZIP file and read all CSV files inside it."""
    try:
        with zipfile.ZipFile(uploaded_file, "r") as z:
            dfs = [pd.read_csv(z.open(f)) for f in z.namelist() if f.endswith(".csv")]
        return pd.concat(dfs, ignore_index=True) if dfs else None
    except Exception as e:
        st.error(f"Lỗi khi giải nén file ZIP: {e}")
        return None

def create_excel_template(df, key_columns, extra_columns):
    """Create an Excel file with key columns and additional headers."""
    df_template = df[key_columns].drop_duplicates().dropna().copy()
    for col in extra_columns:
        df_template[col] = ""
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_template.to_excel(writer, index=False, sheet_name="Sheet1")
    output.seek(0)
    return output

def time_diff_minutes(row, col1, col2):
    """Calculate the time difference in minutes between two columns."""
    if pd.notnull(row[col1]) and pd.notnull(row[col2]):
        time_difference = round((row[col2] - row[col1]).total_seconds() / 60, 0)
        return np.nan if time_difference < 0 else time_difference
    return np.nan

def calculate_tat(df, tat_config):
    """Calculate TAT based on user configuration."""
    df_tat = df.copy()
    tat_results = pd.DataFrame()

    for tat_name, config in tat_config.items():
        col_start, agg_start = config["start"]
        col_end, agg_end = config["end"]
        col_name = config["name"]

        if col_start not in df_tat.columns or col_end not in df_tat.columns:
            st.warning(f"Cột '{col_start}' hoặc '{col_end}' không tồn tại trong dữ liệu. Bỏ qua {tat_name}.")
            continue

        # Convert to datetime
        grouped_df = df_tat.groupby("SampleID").agg({col_start: agg_start, col_end: agg_end}).reset_index()
        grouped_df[col_name] = grouped_df.apply(lambda row: time_diff_minutes(row, col_start, col_end), axis=1)

        if col_start in df_tat.columns and col_end in df_tat.columns:
            grouped_df.drop([col_start, col_end], axis=1, errors='ignore', inplace=True)

        # Merge results
        tat_results = tat_results.merge(grouped_df, on="SampleID", how="outer") if not tat_results.empty else grouped_df

    return tat_results

def main():
    st.title("Phân tích dữ liệu CSV với Streamlit")

    # Initialize session state variables
    if 'df_selected' not in st.session_state:
        st.session_state.df_selected = None
    if 'df_uploaded' not in st.session_state:
        st.session_state.df_uploaded = None
    if 'df_second_updated' not in st.session_state:
        st.session_state.df_second_updated = None
    if 'tat_config' not in st.session_state:
        st.session_state.tat_config = {}
    if 'filtered_df' not in st.session_state:
        st.session_state.filtered_df = None
    if 'grouped_df' not in st.session_state:
        st.session_state.grouped_df = None
    if 'filtered_df_dedup' not in st.session_state:
        st.session_state.filtered_df_dedup = None

    # File uploader for ZIP or CSV
    uploaded_file = st.file_uploader("Chọn file ZIP hoặc CSV", type=["zip", "csv"])

    if uploaded_file:
        if uploaded_file.name.endswith(".zip"):
            combined_df = extract_zip(uploaded_file)
        else:
            try:
                combined_df = pd.read_csv(uploaded_file)
            except Exception as e:
                st.error(f"Lỗi khi đọc file CSV: {e}")
                return
        
        if combined_df is None or combined_df.empty:
            st.error("Không có dữ liệu hợp lệ.")
            return

        st.write("Dữ liệu tải lên:")
        st.dataframe(combined_df.head())

        # Column mapping
        required_group = [
            'SampleID',  'TestAbbreviation', 
            'InstrumentName', 'InstrumentModuleID', 'FirstInstrumentSeenTime','FirstInstrumentSeenID']

        option_columns = ['Site', 'Department','Category','ReceivedTime','InstrumentResultTime',
                        'TechnicalValidationTime', 'MedicalValidationTime', 'Priorityorder']
        
        required_columns = required_group + option_columns
        available_columns = sorted(combined_df.columns.tolist())
        selected_columns = {}
        used_columns = set()

        for col in required_columns:
            choices = ["(Không chọn)"] + [c for c in available_columns if c not in used_columns]
            if col in required_group:
                rq = "(bắt buộc)"
            else:
                rq = "(không bắt buộc)"
            selected_value = st.selectbox(f"Chọn {col} {rq}", choices, key=col)
            if selected_value != "(Không chọn)":
                selected_columns[col] = selected_value
                used_columns.add(selected_value)

        if st.button("Xác nhận chuyển đổi"):
            list1 = list(selected_columns.values())
            list2 = [col for col in required_columns if col not in selected_columns]

            df_selected = combined_df[list1].copy()
            df_selected.rename(columns={v: k for k, v in selected_columns.items()}, inplace=True)

            for col in list2:
                df_selected[col] = None
            if "Site" in list2:
                df_selected["Site"] = 1

            # Process datetime columns
            
            st.session_state.df_selected = df_selected
            st.session_state.time_cols = [col for col in st.session_state.df_selected.columns if "Time" in col]
            st.write("📌 **Dữ liệu sau khi chuyển đổi:**")
            st.dataframe(df_selected.head())

            # Download Excel templates
            if 'InstrumentName' in df_selected.columns and 'InstrumentModuleID' in df_selected.columns:
                excel_file = create_excel_template(df_selected, ['InstrumentName', 'InstrumentModuleID'], 
                                                ['Count', 'Site_Machine', 'Brand', 'System', 'Module', 'Electrode'])
                st.download_button(label="Tải xuống file Excel add informations",
                                data=excel_file,
                                file_name="template_addInformations.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")    
            
            if "FirstInstrumentSeenID" in df_selected.columns:
                second_excel_file = create_excel_template(df_selected, ["FirstInstrumentSeenID"], ["Automation"])
                st.download_button("Tải xuống file mẫu cho add automation info", data=second_excel_file,
                                file_name="template_TLA.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")    

        # Process uploaded Excel files
        if "df_selected" in st.session_state and st.session_state.df_selected is not None:
            df_selected = st.session_state.df_selected

            uploaded_excel = st.file_uploader("Tải lên file Excel đã chỉnh sửa", type=["xlsx"], key='excel_uploader')
            if uploaded_excel:
                try:
                    st.session_state.df_uploaded = pd.read_excel(uploaded_excel)
                except Exception as e:
                    st.error(f"Lỗi khi xử lý file Excel: {e}")

            if st.session_state.df_uploaded is not None:
                st.write("📌 **Dữ liệu từ file Excel tải lên:**")
                st.dataframe(st.session_state.df_uploaded.head())

                uploaded_second_excel = st.file_uploader("Tải lên file Excel cho FirstInstrumentSeenID", 
                                                        type=["xlsx"], key='second_excel_uploader')
                if uploaded_second_excel:
                    try:
                        st.session_state.df_second_updated = pd.read_excel(uploaded_second_excel)
                    except Exception as e:
                        st.error(f"Lỗi khi xử lý file Second Excel: {e}")

                if st.session_state.df_second_updated is not None:
                    st.write("Dữ liệu đã chỉnh sửa (FirstInstrumentSeenID):")
                    st.dataframe(st.session_state.df_second_updated.head())

                    if st.button("Xử lý và hợp nhất dữ liệu"):
                        try:
                            merged_df = st.session_state.df_selected \
                                .merge(st.session_state.df_uploaded, on=["InstrumentName", "InstrumentModuleID"], how="left") \
                                .merge(st.session_state.df_second_updated, on=["FirstInstrumentSeenID"], how="left")

                            # Filter valid data
                            filtered_df = merged_df.query("TechnicalValidationTime.notna() & FirstInstrumentSeenTime.notna() & Count == 1") \
                                                .drop(columns=["Count"], errors="ignore")

                            for col in st.session_state.time_cols:
                                # Replace the datetime conversion line with this:
                                # filtered_df[col] = pd.to_datetime(filtered_df[col], format='%Y-%m-%d %H:%M:%S', errors="coerce")
                                filtered_df[col] = pd.to_datetime(filtered_df[col], format='%H:%M:%S', errors="coerce")
                            
                            # Create additional hour and date columns
                            if "FirstInstrumentSeenTime" in filtered_df:
                                filtered_df["hour"] = filtered_df["FirstInstrumentSeenTime"].dt.hour
                                filtered_df["date"] = filtered_df["FirstInstrumentSeenTime"].dt.date

                            # Sort data
                            filtered_df.sort_values(by=["FirstInstrumentSeenTime", "Category"], inplace=True)

                            # Convert the specified columns to strings
                            filtered_df["Category"] = filtered_df["Category"].astype(str)
                            filtered_df["Site_Machine"] = filtered_df["Site_Machine"].astype(str)
                            filtered_df["Brand"] = filtered_df["Brand"].astype(str)
                            filtered_df["System"] = filtered_df["System"].astype(str)

                            # Group data
                            grouped_df = (
                                filtered_df.groupby(["SampleID", "Department", "Site"])
                                .agg({
                                    "Category": lambda x: ", ".join(sorted(set(x), key=list(x).index)),
                                    "Automation": "first",
                                    "Site_Machine": lambda x: ", ".join(sorted(set(x), key=list(x).index)),
                                    "Brand": lambda x: ", ".join(sorted(set(x), key=list(x).index)),
                                    "System": lambda x: ", ".join(sorted(set(x), key=list(x).index))
                                })
                                .reset_index()
                            )

                            # Count unique values
                            for col in ["System", "Brand", "Site_Machine"]:
                                grouped_df[f"count_{col.lower()}"] = grouped_df[col].apply(lambda x: len(str(x).split(",")))

                            # Remove duplicates
                            filtered_df_dedup = filtered_df[["SampleID", "Category", "Site_Machine", "Brand", "System",
                                                              "InstrumentModuleID", "Module", "Electrode", "TestAbbreviation"]].drop_duplicates()

                            # Save to session state
                            st.session_state.filtered_df = filtered_df
                            st.session_state.grouped_df = grouped_df
                            st.session_state.filtered_df_dedup = filtered_df_dedup

                            st.success("Xử lý hoàn tất!")

                        except Exception as e:
                            st.error(f"Lỗi khi xử lý dữ liệu: {e}")

                # TAT Configuration
                st.subheader("Cấu hình TAT")
                tat_names = ["TAT1", "TAT2", "TAT3", "TAT4"]
                if st.session_state.time_cols:
                    for tat in tat_names:
                        st.markdown(f"**{tat}**")
                        col_start = st.selectbox(
                            f"Chọn cột bắt đầu ({tat})",
                            options=["(Không chọn)"] + list(st.session_state.time_cols),
                            key=f"start_{tat}"
                        )
                        col_end = st.selectbox(
                            f"Chọn cột kết thúc ({tat})",
                            options=["(Không chọn)"] + list(st.session_state.time_cols),
                            key=f"end_{tat}"
                        )
                        agg_start = st.selectbox(
                            f"Chọn cách tính cho thời gian {col_start}",
                            options=["max", "min"],
                            key=f"agg_start_{tat}"
                        )
                        agg_end = st.selectbox(
                            f"Chọn cách tính cho thời gian {col_end}",
                            options=["max", "min"],
                            key=f"agg_end_{tat}"
                        )
                        
                        st.session_state.tat_config[tat] = {
                            "start": (col_start, agg_start),
                            "end": (col_end, agg_end),
                            "name": f"{col_end}-{col_start}"
                        }

            if st.button("Tính TAT"):
                if 'filtered_df' in st.session_state:
                    tat_results = calculate_tat(st.session_state.filtered_df, st.session_state.tat_config)
                    st.session_state.tat_results = tat_results
                    st.write("Kết quả TAT:")
                    st.dataframe(st.session_state.tat_results)
                else:
                    st.warning("Vui lòng xử lý dữ liệu trước khi tính TAT")

            # Download processed data
            if 'tat_results' in st.session_state and st.session_state.tat_results is not None:
                st.download_button(
                    "Tải xuống tbl_tat",
                    st.session_state.tat_results.to_csv(index=False).encode("utf-8"),
                    "tbl_tat.csv"
                )
            else:
                st.warning("Không có dữ liệu tbl_tat để tải xuống.")

            # Download processed data
            if 'grouped_df' in st.session_state and st.session_state.grouped_df is not None:
                st.download_button(
                    "Tải xuống tbl_sample",
                    st.session_state.grouped_df.to_csv(index=False).encode("utf-8"),
                    "tbl_sample.csv"
                )
            else:
                st.warning("Không có dữ liệu tbl_sample để tải xuống.")
            
            if 'filtered_df_dedup' in st.session_state and st.session_state.filtered_df_dedup is not None:
                st.download_button(
                    "Tải xuống tbl_test",
                    st.session_state.filtered_df_dedup.to_csv(index=False).encode("utf-8"),
                    "tbl_test.csv"
                )
            else:
                st.warning("Không có dữ liệu tbl_test để tải xuống.")

if __name__ == "__main__":
    main()