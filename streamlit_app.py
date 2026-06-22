import streamlit as st
import os
import tempfile
import warnings
from pathlib import Path

# Workaround for Streamlit Cloud environments that lack Tk
import sys
import types

fake_tk = types.ModuleType("tkinter")
fake_tk.TclError = Exception
sys.modules["tkinter"] = fake_tk

from geomeppy import IDF
warnings.filterwarnings('ignore', category=UserWarning)

# EnergyPlus version mapping
BASE_DIR = Path(__file__).parent

ENERGYPLUS_VERSIONS = {
    "v22.1.0": BASE_DIR / "EnergyPlusV22-1-0" / "Energy+.idd",
    "v23.2.0": BASE_DIR / "EnergyPlusV23-2-0" / "Energy+.idd",
    "v9.5.0": BASE_DIR / "EnergyPlusV9-5-0" / "Energy+.idd",
    "v9.4.0": BASE_DIR / "EnergyPlusV9-4-0" / "Energy+.idd",
}

# Find available versions
def get_available_versions():
    return {
        v: str(path)
        for v, path in ENERGYPLUS_VERSIONS.items()
        if path.exists()
    }

def clean_shading(idf):
    """
    Remove all major shading objects from IDF
    """
    shading_types = [
        "SHADING:ZONE:DETAILED",
        "SHADING:BUILDING:DETAILED",
        "SHADING:SITE:DETAILED"
    ]

    for obj_type in shading_types:
        if obj_type in idf.idfobjects:
            idf.idfobjects[obj_type] = []

    return idf


def standardize_window_constructions(idf):
    """
    Assign the first available window construction to all windows for compatibility
    """
    # Find all window constructions
    window_constructions = []
    if "CONSTRUCTION" in idf.idfobjects:
        # Get any construction name from window objects
        if "FENESTRATIONSURFACE:DETAILED" in idf.idfobjects:
            for win in idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]:
                if hasattr(win, "Construction_Name") and win.Construction_Name:
                    window_constructions.append(win.Construction_Name)
                    break

    # If found a construction, apply it to all windows
    if window_constructions and "FENESTRATIONSURFACE:DETAILED" in idf.idfobjects:
        standard_construction = window_constructions[0]
        for win in idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]:
            win.Construction_Name = standard_construction

    return idf


def modify_wwr(idf, wwr):
    """
    Modify Window-to-Wall Ratio using geomeppy

    Args:
        idf: IDF object
        wwr: Window-to-Wall Ratio (0-1)
    """
    try:
        # Remove shading first, then rebuild windows with geomeppy
        idf = clean_shading(idf)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                idf.set_wwr(
                    wwr=wwr,
                    construction=None,
                    force=True
                )
            except Exception as e:
                error_msg = str(e)
                if "Too many fields" in error_msg or "fields for object" in error_msg:
                    raise Exception(
                        "⚠️ IDF structure is too complex for automatic WWR modification. "
                        "Please simplify the model or verify the IDF before retrying."
                    )
                elif "same construction" in error_msg:
                    idf = standardize_window_constructions(idf)
                    idf.set_wwr(
                        wwr=wwr,
                        construction=None,
                        force=True
                    )
                else:
                    raise

        return idf
    except Exception as e:
        raise Exception(f"Failed to process IDF: {str(e)}")


def main():
    st.set_page_config(page_title="EnergyPlus WWR Modifier", layout="wide")

    st.title("🏢 EnergyPlus Window-to-Wall Ratio (WWR) Modifier")
    st.markdown("Update the Window-to-Wall Ratio in your IDF files with ease")

    # Initialize session state
    if "current_idd_version" not in st.session_state:
        st.session_state.current_idd_version = None
        st.session_state.idd_set = False

    # Get available versions
    available_versions = get_available_versions()

    # Check if any EnergyPlus version is available
    if not available_versions:
        st.error("❌ No EnergyPlus installation found!")
        st.error("Please install EnergyPlus first. Supported versions:")
        for version, path in ENERGYPLUS_VERSIONS.items():
            st.write(f"  • {version}: {path}")
        st.stop()

    # Hide the sidebar and show version selection on the main page
    st.markdown(
        "<style>div[data-testid='stSidebar'] {display: none;} "
        "section[data-testid='stSidebarNav'] {display: none;}</style>",
        unsafe_allow_html=True,
    )

    st.subheader("EnergyPlus Version")
    selected_version = st.selectbox(
        "Select EnergyPlus Version",
        options=list(available_versions.keys()),
        help="Select the EnergyPlus version your IDF file is from",
        width = 200
    )

    idd_path = available_versions[selected_version]

    if st.session_state.current_idd_version != selected_version:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                IDF.setiddname(idd_path)
            st.session_state.current_idd_version = selected_version
            st.session_state.idd_set = True
            st.success(f"✅ Using EnergyPlus {selected_version}", width = 300)
            # st.info(f"📂 IDD File: {idd_path}")
        except Exception as e:
            error_msg = str(e)
            if "IDD file is set to" in error_msg:
                st.session_state.current_idd_version = selected_version
                st.session_state.idd_set = True
                st.info(f"ℹ️ IDD already initialized")
                st.success(f"✅ Using EnergyPlus {selected_version}")
                st.info(f"📂 IDD File: {idd_path}")
            else:
                st.error(f"❌ Error: {error_msg}")
                st.info(f"IDD Path: {idd_path}")
    elif st.session_state.idd_set:
        st.success(f"✅ Using EnergyPlus {selected_version}")
        st.info(f"📂 IDD File: {idd_path}")

    # Create columns for layout
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Input Settings")

        # File uploader
        uploaded_file = st.file_uploader(
            "📁 Upload your IDF file",
            type=["idf"],
            help="Select an EnergyPlus IDF file to modify",
            width = 500
        )

        # WWR input - using slider
        wwr_input = st.slider(
            "Window-to-Wall Ratio (WWR)",
            min_value=0.0,
            max_value=1.0,
            value=0.50,
            step=0.05,
            format="%.2f",
            help="WWR ranges from 0.0 (no windows) to 1.0 (100% windows)"
        )

        final_wwr = wwr_input

        st.divider()
        st.write("**Processing Options:**")
        st.info("The app always uses geomeppy to rebuild window geometry after removing shading.")

    with col2:
        st.subheader("Preview")
        st.info(f"📊 Current WWR: **{final_wwr:.1%}**")
        st.metric("Selected WWR Value", f"{final_wwr:.2f}")

    st.divider()

    # Process button
    if st.button("🔄 Process IDF File", type="primary", use_container_width=False, width = 800):
        if uploaded_file is None:
            st.error("❌ Please upload an IDF file first")
        else:
            try:
                with st.spinner("⏳ Processing your IDF file..."):
                    # Save uploaded file to temp location
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".idf", mode='wb') as tmp_input:
                        tmp_input.write(uploaded_file.getbuffer())
                        tmp_input_path = tmp_input.name

                    st.info(f"📂 Loaded file: {uploaded_file.name} ({uploaded_file.size} bytes)")

                    # Load and modify IDF
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        idf = IDF(tmp_input_path)

                    st.info(f"✓ IDF loaded successfully")

                    # Apply WWR modification with automatic geomeppy rebuilding
                    idf = modify_wwr(idf, final_wwr)
                    st.info(f"✓ WWR modified to {final_wwr:.1%}")

                    # Save to temp output file
                    output_filename = uploaded_file.name.replace(".idf", f"_WWR{int(final_wwr*100)}.idf")
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".idf", mode='w') as tmp_output:
                        tmp_output_path = tmp_output.name

                    # Save with validation
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        idf.saveas(tmp_output_path)

                    # Validate output file
                    if not os.path.exists(tmp_output_path) or os.path.getsize(tmp_output_path) == 0:
                        raise Exception("Output file is empty or was not created")

                    st.info(f"✓ File saved ({os.path.getsize(tmp_output_path)} bytes)")

                    # Read the modified file
                    with open(tmp_output_path, 'rb') as f:
                        modified_content = f.read()

                    # Clean up temp files
                    os.unlink(tmp_input_path)
                    os.unlink(tmp_output_path)

                st.success("✅ IDF file processed successfully!")

                # Display download button
                st.download_button(
                    label="📥 Download Modified IDF File",
                    data=modified_content,
                    file_name=output_filename,
                    mime="text/plain",
                    use_container_width=True
                )

                # Show summary
                st.subheader("📋 Processing Summary")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Original File", uploaded_file.name)
                with col2:
                    st.metric("WWR Applied", f"{final_wwr:.1%}")
                with col3:
                    st.metric("Output File", output_filename)

            except Exception as e:
                st.error(f"❌ Error processing file: {str(e)}")
                st.error("**Troubleshooting:**")
                st.write("• Make sure the IDF file is valid and compatible with EnergyPlus v9.4.0")
                st.write("• The IDF file may have syntax errors (missing semicolons)")
                st.write("• Try opening the original file in EnergyPlus IDF Editor first")
                st.write("• Check that the file is not corrupted")
                import traceback
                with st.expander("📋 Error Details"):
                    st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
