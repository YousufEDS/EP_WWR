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


def modify_wwr(idf, wwr, safe_mode=False):
    """
    Modify Window-to-Wall Ratio using geomeppy

    Args:
        idf: IDF object
        wwr: Window-to-Wall Ratio (0-1)
        safe_mode: If True, only removes shading. If False, tries to rebuild windows.
    """
    try:
        # Step 1: remove shading (always recommended)
        idf = clean_shading(idf)

        # Step 2: rebuild windows with geomeppy (if not in safe mode)
        if not safe_mode:
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
                    # Handle specific geomeppy errors
                    if "Too many fields" in error_msg or "fields for object" in error_msg:
                        raise Exception(
                            "⚠️ IDF structure is too complex for automatic WWR modification. "
                            "Try using 'Safe Mode' (Remove shading only) instead."
                        )
                    elif "same construction" in error_msg:
                        # Try to fix construction mismatch
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

    # Sidebar for version selection
    st.sidebar.title("⚙️ Settings")
    selected_version = st.sidebar.selectbox(
        "Select EnergyPlus Version",
        options=list(available_versions.keys()),
        help="Select the EnergyPlus version your IDF file is from"
    )

    idd_path = available_versions[selected_version]

    # Only set IDD if version changed
    if st.session_state.current_idd_version != selected_version:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Try to set the IDD path
                IDF.setiddname(idd_path)
            st.session_state.current_idd_version = selected_version
            st.session_state.idd_set = True
            st.sidebar.success(f"✅ Using EnergyPlus {selected_version}")
            st.sidebar.info(f"📂 IDD File: {idd_path}")
        except Exception as e:
            error_msg = str(e)
            # If error is about IDD already being set, it's okay - just update state
            if "IDD file is set to" in error_msg:
                st.session_state.current_idd_version = selected_version
                st.session_state.idd_set = True
                st.sidebar.info(f"ℹ️ IDD already initialized")
                st.sidebar.success(f"✅ Using EnergyPlus {selected_version}")
                st.sidebar.info(f"📂 IDD File: {idd_path}")
            else:
                st.sidebar.error(f"❌ Error: {error_msg}")
                st.sidebar.info(f"IDD Path: {idd_path}")
    elif st.session_state.idd_set:
        st.sidebar.success(f"✅ Using EnergyPlus {selected_version}")
        st.sidebar.info(f"📂 IDD File: {idd_path}")

    # Create columns for layout
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Input Settings")

        # File uploader
        uploaded_file = st.file_uploader(
            "📁 Upload your IDF file",
            type=["idf"],
            help="Select an EnergyPlus IDF file to modify"
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

        # Alternative: Number input for precise values
        wwr_precise = st.number_input(
            "Or enter WWR as decimal (0-1):",
            min_value=0.0,
            max_value=1.0,
            value=wwr_input,
            step=0.01,
            format="%.2f"
        )

        final_wwr = wwr_precise

        # Processing options
        st.divider()
        st.write("**Processing Options:**")
        processing_mode = st.radio(
            "How to apply WWR changes:",
            options=["Auto (Geomeppy rebuild)", "Safe (Remove shading only)"],
            help="Auto: Rebuilds windows (may fail on complex models). Safe: Only removes shading (compatible with all models)",
            index=1
        )

    with col2:
        st.subheader("Preview")
        st.info(f"📊 Current WWR: **{final_wwr:.1%}**")
        st.metric("Selected WWR Value", f"{final_wwr:.2f}")

    st.divider()

    # Process button
    if st.button("🔄 Process IDF File", type="primary", use_container_width=True):
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

                    # Apply WWR modification based on processing mode
                    safe_mode = processing_mode == "Safe (Remove shading only)"
                    idf = modify_wwr(idf, final_wwr, safe_mode=safe_mode)

                    if safe_mode:
                        st.info(f"✓ Shading removed (Safe mode - Windows not modified)")
                    else:
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
