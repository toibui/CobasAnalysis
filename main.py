import streamlit as st
import pandas as pd
import zipfile
import numpy as np
from io import BytesIO
import time
# Điểm bắt đầu

def extract_zip(uploaded_file, encoding='utf-8'):
    """Extract ZIP file and read all CSV files inside it."""
    try:
        with zipfile.ZipFile(uploaded_file, "r") as z:
            # Read all CSV files in the ZIP archive with the specified encoding
            dfs = [pd.read_csv(z.open(f), encoding=encoding) for f in z.namelist() if f.endswith(".csv")]
        # Concatenate all DataFrames into one if there are any
        return pd.concat(dfs, ignore_index=True) if dfs else None
    except Exception as e:
        st.error(f"Lỗi khi giải nén file ZIP: {e}")
        return None
#



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

def calculate_tat_test(df, tat_config):
    """Calculate TAT based on user configuration."""
    df_tat = df.copy()
    tat_results = pd.DataFrame()

    # Chuyển đổi các cột thời gian sang kiểu datetime một lần duy nhất
    datetime_cols = set()
    for config in tat_config.values():
        datetime_cols.add(config["start"])
        datetime_cols.add(config["end"])

    for col in datetime_cols:
        if col in df_tat.columns:
            df_tat[col] = pd.to_datetime(df_tat[col])
        else:
            st.warning(f"Cột '{col}' không tồn tại trong dữ liệu.")

    # Tính toán TAT cho từng cấu hình
    for tat_name, config in tat_config.items():
        col_start = config["start"]
        col_end = config["end"]
        col_name = config["name"]

        # Kiểm tra nếu cột tồn tại
        if col_start not in df_tat.columns or col_end not in df_tat.columns:
            st.warning(f"Cột '{col_start}' hoặc '{col_end}' không tồn tại trong dữ liệu. Bỏ qua {tat_name}.")
            continue

        # Lấy dữ liệu cần thiết
        listCols = ['SampleID', 'TestAbbreviation', col_start, col_end]
        grouped_df = df_tat[listCols].copy()

        # Tính toán thời gian chênh lệch bằng phương thức vectorized
        grouped_df[col_name] = (grouped_df[col_end] - grouped_df[col_start]).dt.total_seconds() / 60

        # Xóa cột thời gian sau khi tính toán
        grouped_df.drop(columns=[col_start, col_end], errors='ignore', inplace=True)

        # Hợp nhất kết quả vào tat_results
        if tat_results.empty:
            tat_results = grouped_df
        else:
            tat_results = tat_results.merge(grouped_df, on=["SampleID", "TestAbbreviation"], how="outer")

    return tat_results

def convert_time(value):
    value = str(value).strip()  # Xóa khoảng trắng đầu/cuối, tránh lỗi do dữ liệu bẩn
    if pd.isna(value) or value in ["", "NaT"]:  # Bỏ qua giá trị NaN hoặc rỗng
        return pd.NaT
    if "AM" in value or "PM" in value:
        return pd.to_datetime(value, format="%I:%M:%S %p", errors="coerce")
    else:
        return pd.to_datetime(value, format="%H:%M:%S", errors="coerce")

def main():
    st.title("Clean data with web app")

    # Initialize session state variables
    if 'df_selected' not in st.session_state:
        st.session_state.df_selected = None
    if 'excel_file' not in st.session_state:
        st.session_state.excel_file = None
    if 'second_excel_file' not in st.session_state:
        st.session_state.second_excel_file = None
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
    st.write("🚀 **Upload file dữ liệu gốc lên:**")    
    uploaded_file = st.file_uploader("Chọn file .zip hoặc .csv", type=["zip", "csv"])

    if uploaded_file:
        if uploaded_file.name.endswith(".zip"):
            try:
                combined_df = extract_zip(uploaded_file)
            # except UnicodeDecodeError:
            #     combined_df = extract_zip(uploaded_file, encoding="utf-8")
            except Exception as e:
                st.error(f"Lỗi khi đọc file CSV: {e}")
                return
        else:
            try:
                combined_df = pd.read_csv(uploaded_file, encoding="latin1", low_memory=False)
            except UnicodeDecodeError:
                combined_df = pd.read_csv(uploaded_file, encoding="utf-8", low_memory=False)
            except Exception as e:
                st.error(f"Lỗi khi đọc file CSV: {e}")
                return
        
        if combined_df is None or combined_df.empty:
            st.error("Không có dữ liệu hợp lệ.")
            return

        st.write("📌 ***Dữ liệu file gốc:***")
        st.dataframe(combined_df.head())

        st.divider()
        st.write("📌 ***Vui lòng lựa chọn các cột tương ứng:***")
        # Column mapping
        required_group = [
            'SampleID',  'TestAbbreviation', 
            'InstrumentName', 'InstrumentModuleID','FirstInstrumentSeenID', 'FirstInstrumentSeenTime',
            'FirstInstrumentSeenDate']

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
        st.divider()

        st.write("📌 ***Nếu hoàn thành hãy nhấn nút Finished:***")
        if st.button("Finished"):
            list1 = list(selected_columns.values())
            list2 = [col for col in required_columns if col not in selected_columns]

            df_selected = combined_df[list1].copy()
            df_selected.rename(columns={v: k for k, v in selected_columns.items()}, inplace=True)

            for col in list2:
                df_selected[col] = None

            # Process datetime columns
            st.session_state.df_selected = df_selected
            st.session_state.time_cols = [col for col in st.session_state.df_selected.columns if "Time" in col]
            st.write("📌 ***Xem trước dữ liệu sau khi đã thay đổi tên cột:***")
            st.dataframe(df_selected.head())

            if 'InstrumentName' in df_selected.columns and 'InstrumentModuleID' in df_selected.columns:
                excel_file = create_excel_template(df_selected, ['InstrumentName', 'InstrumentModuleID'], 
                                                ['Count', 'Site_Machine', 'Brand', 'System', 'Module', 'Electrode','GroupTest'])
                st.session_state.excel_file = excel_file
            if "FirstInstrumentSeenID" in df_selected.columns:
                second_excel_file = create_excel_template(df_selected, ["FirstInstrumentSeenID"], ["Automation"])
                st.session_state.second_excel_file = second_excel_file

        st.markdown("---")  # Kẻ một dòng ngang
        with st.expander("TẢI TEMPLATE"):

            # Download Excel templates
            if st.session_state.excel_file: 
                st.write("🚀 **Tải xuống file mẫu: Bổ sung thêm các thông tin:**")
                st.download_button(label="Download",
                                data=st.session_state.excel_file,
                                file_name="template_addInformations.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")    
                
            if st.session_state.second_excel_file:
                st.write("🚀 **Tải xuống file mẫu: Bổ sung thông tin chạy hệ hay không:**")    
                st.download_button("Download", data=st.session_state.second_excel_file,
                                file_name="template_TLA.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")    
            st.markdown("---")  # Kẻ một dòng ngang

        # Process uploaded Excel files
        if "df_selected" in st.session_state and st.session_state.df_selected is not None:
            df_selected = st.session_state.df_selected

            st.write("🚀 **Tải lên file: Bổ sung thêm các thông tin:**")
            uploaded_excel = st.file_uploader("Upload", type=["xlsx"], key='excel_uploader')
            if uploaded_excel:
                try:
                    st.session_state.df_uploaded = pd.read_excel(uploaded_excel)
                except Exception as e:
                    st.error(f"Lỗi khi xử lý file Excel: {e}")

                if st.session_state.df_uploaded is not None:
                    st.write(" ***Dữ liệu từ file Excel tải lên:***")
                    st.dataframe(st.session_state.df_uploaded.head())

            st.markdown("---")  # Kẻ một dòng ngang
            st.write("🚀 **Bổ sung thông tin chạy hệ hay không:**")
            uploaded_second_excel = st.file_uploader("Upload", 
                                                        type=["xlsx"], key='second_excel_uploader')
            if uploaded_second_excel:
                try:
                    st.session_state.df_second_updated = pd.read_excel(uploaded_second_excel)
                except Exception as e:
                    st.error(f"Lỗi khi xử lý file Second Excel: {e}")

            if st.session_state.df_second_updated is not None:
                st.write("file Excel: add TLA info:")
                st.dataframe(st.session_state.df_second_updated.head())

            st.markdown("---")  # Kẻ một dòng ngang
            st.write("🚀 **Xác nhận xử lý dữ liệu:**")
            if st.session_state.df_second_updated is not None and st.session_state.df_uploaded is not None:
                if st.button("Analysis: "):
                    start_time = time.time()
                    try:
                        # Merge dataframes
                        merged_df = st.session_state.df_selected \
                            .merge(st.session_state.df_uploaded, on=["InstrumentName", "InstrumentModuleID"], how="left") \
                            .merge(st.session_state.df_second_updated, on=["FirstInstrumentSeenID"], how="left")

                        # Filter valid data
                        filtered_df = merged_df.query("Count == 1 and SampleID.notna()").drop(columns=["Count"], errors="ignore")

                        # Convert time columns
                        for col in st.session_state.time_cols:
                            # filtered_df[col] = filtered_df[col].apply(convert_time)
                            filtered_df[col] = pd.to_datetime(filtered_df[col], errors='coerce')

                        # Process datetime columns
                        if "FirstInstrumentSeenTime" in filtered_df:
                            filtered_df["hour"] = filtered_df["FirstInstrumentSeenTime"].dt.hour

                        if "FirstInstrumentSeenDate" in filtered_df:
                            # filtered_df["date"] = filtered_df["FirstInstrumentSeenDate"]
                            filtered_df["date"] = pd.to_datetime(filtered_df['FirstInstrumentSeenDate'], dayfirst=True, errors='coerce')

                        # Sort data
                        filtered_df.sort_values(by=["FirstInstrumentSeenTime", "Category", "GroupTest"], inplace=True)

                        # Fill NaN and convert to string for grouping columns
                        col_list = ["Department", "Site", "Category", "Site_Machine", "Brand", "System", "GroupTest", "hour"]
                        filtered_df[col_list] = filtered_df[col_list].fillna("1").astype(str)

                        # Group data
                        grouped_df = filtered_df.groupby(["SampleID", "Department", "Site"]).agg({
                            "Category": lambda x: ", ".join(sorted(set(x), key=list(x).index)),
                            "GroupTest": lambda x: ", ".join(sorted(set(x), key=list(x).index)),
                            "Automation": "first",
                            "hour": "first",
                            "date": "min",
                            "Site_Machine": lambda x: ", ".join(sorted(set(x), key=list(x).index)),
                            "Brand": lambda x: ", ".join(sorted(set(x), key=list(x).index)),
                            "System": lambda x: ", ".join(sorted(set(x), key=list(x).index))
                        }).reset_index()

                        # Count unique values
                        for col in ["System", "Brand", "Site_Machine"]:
                            grouped_df[f"count_{col.lower()}"] = grouped_df[col].apply(lambda x: len(str(x).split(",")))

                        # Remove duplicates
                        filtered_df_dedup = filtered_df[["SampleID", "Category", "GroupTest", "Site_Machine", "Brand", "System",
                                                        "InstrumentModuleID", "Module", "Electrode", "TestAbbreviation"]].drop_duplicates()

                        # Save to session state
                        st.session_state.filtered_df = filtered_df
                        st.session_state.grouped_df = grouped_df
                        st.session_state.filtered_df_dedup = filtered_df_dedup

                        # Điểm kết thúc
                        end_time = time.time()
                        # Tính thời gian thực thi
                        elapsed_time = end_time - start_time

                        st.success(f"Thời gian thực thi: {round(elapsed_time,0)} giây")
                        st.success("Xử lý hoàn tất!")

                    except Exception as e:
                        st.error(f"Lỗi khi xử lý dữ liệu: {e}")

                # TAT Configuration
                if "filtered_df" in st.session_state and st.session_state.filtered_df is not None:
                    st.subheader("Tính TAT theo mẫu bệnh phẩm")
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
                    # Sample
                    st.markdown("---")  # Kẻ một dòng ngang
                    st.write("🚀 **Xác nhận tính TAT theo từng sampleID:**")
                    if st.button("Calculate"):
                        start_time = time.time()
                        # Tính thời gian thực thi
                        
                        if 'filtered_df' in st.session_state:
                            tat_results = calculate_tat(st.session_state.filtered_df, st.session_state.tat_config)
                            st.session_state.tat_results = tat_results
                            end_time = time.time()
                            elapsed_time = end_time - start_time
                            st.success(f"Thời gian thực thi: {round(elapsed_time,0)} giây")
                            st.write("Kết quả TAT:")
                            st.dataframe(st.session_state.tat_results)
                        else:
                            st.warning("Vui lòng xử lý dữ liệu trước khi tính TAT")

                st.write("")

                    # TAT Configuration
                if "filtered_df" in st.session_state and st.session_state.filtered_df is not None:
                    st.subheader("Tính TAT theo từng xét nghiệm")
                    tat_names = ["TATTest1", "TATTest2"]

                    if "tat_config_test" not in st.session_state:
                        st.session_state.tat_config_test = {}

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
    
                            st.session_state.tat_config_test[tat] = {
                                "start": col_start,
                                "end": col_end,
                                "name": f"{col_end}-{col_start}"

                            }
                      
                    st.markdown("---")  # Kẻ một dòng ngang
                    st.write("🚀 ***Xác nhận tính TAT theo từng xét nghiệm:***")

                    if st.button("Analysis"):
                        start_time = time.time()
                        if 'filtered_df' in st.session_state:
                            tat_results_test = calculate_tat_test(st.session_state.filtered_df, st.session_state.tat_config_test)
                            st.session_state.tat_results_test = tat_results_test
                            end_time = time.time()
                            elapsed_time = end_time - start_time
                            st.success(f"Thời gian thực thi: {round(elapsed_time,0)} giây")
                            st.write("Kết quả TAT:")
                            st.dataframe(st.session_state.tat_results_test)
                        else:
                            st.warning("Vui lòng xử lý dữ liệu trước khi tính TAT")

            st.markdown("---")  # Kẻ một dòng ngang
            st.write("🚀 **Tải xuống các file hoàn thành:**")
            with st.expander("TẢI TEMPLATE"):
                # Download processed data
                if 'tat_results_test' in st.session_state and st.session_state.tat_results_test is not None:
                    st.download_button(
                        "tbl_tat_test",
                        st.session_state.tat_results_test.to_csv(index=False).encode("utf-8"),
                        "tbl_tat_test.csv"
                    )

                # Download processed data
                if 'tat_results' in st.session_state and st.session_state.tat_results is not None:
                    st.download_button(
                        "tbl_tat",
                        st.session_state.tat_results.to_csv(index=False).encode("utf-8"),
                        "tbl_tat.csv"
                    )

                # Download processed data
                if 'grouped_df' in st.session_state and st.session_state.grouped_df is not None:
                    st.download_button(
                        "tbl_sample",
                        st.session_state.grouped_df.to_csv(index=False).encode("utf-8"),
                        "tbl_sample.csv"
                    )
                
                if 'filtered_df_dedup' in st.session_state and st.session_state.filtered_df_dedup is not None:
                    st.download_button(
                        "tbl_test",
                        st.session_state.filtered_df_dedup.to_csv(index=False).encode("utf-8"),
                        "tbl_test.csv"
                    )

if __name__ == "__main__":
    main()