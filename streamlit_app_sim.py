import streamlit as st
import os
import tempfile
import warnings
from pathlib import Path
import subprocess
import re
import json

# Detect environment
IS_STREAMLIT_CLOUD = "/mount/src" in str(Path.home()) or "STREAMLIT_SERVER_HEADLESS" in os.environ

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


def get_energyplus_exe(idd_path):
    """
    Find the EnergyPlus executable from the idd path
    """
    if not idd_path:
        return None

    idd_path = Path(idd_path)
    idd_dir = idd_path.parent

    # Try to find the executable based on platform
    if os.name == 'nt':  # Windows
        exe_names = ["energyplus.exe"]
    else:  # Unix/Linux
        exe_names = ["energyplus"]

    # List of directories to search relative to IDD directory
    search_locations = [
        idd_dir,  # Same directory as IDD
        idd_dir / "bin",  # Common bin subdirectory
        idd_dir.parent,  # Parent directory
    ]

    for search_dir in search_locations:
        for exe_name in exe_names:
            exe_path = search_dir / exe_name
            if exe_path.exists():
                return str(exe_path)

    return None


def find_weather_file(idd_path):
    """
    Find an available weather file in the EnergyPlus installation
    """
    idd_dir = Path(idd_path).parent
    weather_dir = idd_dir / "WeatherData"
    
    if weather_dir.exists():
        epw_files = list(weather_dir.glob("*.epw"))
        if epw_files:
            return str(epw_files[0])
    
    return None


def run_simulation(idf_path, weather_path=None, idd_path=None):
    """
    Run EnergyPlus simulation using subprocess

    Args:
        idf_path: Path to the IDF file
        weather_path: Path to weather file (EPW)
        idd_path: Path to IDD file

    Returns:
        Dictionary with simulation results
    """
    try:
        # Get EnergyPlus executable path using platform-aware function
        energyplus_exe = get_energyplus_exe(idd_path)

        if not energyplus_exe:
            idd_path_obj = Path(idd_path) if idd_path else None
            idd_dir = idd_path_obj.parent if idd_path_obj else "Unknown"

            searched_paths = []
            if idd_path_obj:
                searched_paths = [
                    str(idd_dir),
                    str(idd_dir / "bin"),
                    str(idd_dir.parent)
                ]

            return {
                "success": False,
                "error": f"EnergyPlus executable not found. IDD path: {idd_path}. "
                         f"Searched in: {searched_paths}. "
                         f"Please verify that EnergyPlus is installed and accessible."
            }

        # Try to set execute permissions on Linux/Unix
        if os.name != 'nt':
            try:
                import stat
                exe_stat = os.stat(energyplus_exe)
                os.chmod(energyplus_exe, exe_stat.st_mode | stat.S_IEXEC)
            except Exception as e:
                return {"success": False, "error": f"Cannot set execute permissions on EnergyPlus executable: {str(e)}"}

        # Auto-detect weather file if not provided
        if not weather_path:
            weather_path = find_weather_file(idd_path)

        if not weather_path:
            return {"success": False, "error": "No weather file (.epw) found"}

        # Create output directory
        output_dir = Path(idf_path).parent / "simulation_output"
        output_dir.mkdir(exist_ok=True)


        # Build command
        cmd = [
            str(energyplus_exe),
            "-r",
            "-w", weather_path,
            "-d", str(output_dir),
            str(idf_path)
        ]

        # Run simulation
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
            text=True
        )

        if result.returncode == 0:
            # Rename default HTML file if it exists
            default_html = output_dir / "eplustbl.htm"
            if default_html.exists():
                idf_name = Path(idf_path).stem
                new_html_path = output_dir / f"{idf_name}.htm"
                default_html.rename(new_html_path)

            return {"success": True, "output_dir": str(output_dir)}
        else:
            error_msg = result.stderr if result.stderr else "Simulation failed with unknown error"
            return {"success": False, "error": error_msg}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Simulation timeout (exceeded 10 minutes)"}
    except Exception as e:
        return {"success": False, "error": f"Simulation error: {str(e)}"}


def extract_simulation_metrics(output_dir):
    """
    Extract energy metrics from simulation output files

    Args:
        output_dir: Directory containing simulation outputs

    Returns:
        Dictionary with key metrics and HTML report files
    """
    metrics = {
        "total_energy": None,
        "heating_energy": None,
        "cooling_energy": None,
        "lighting_energy": None,
        "equipment_energy": None,
        "simulation_success": False,
        "html_reports": []
    }

    try:
        output_dir = Path(output_dir)

        # Find all HTM/HTML report files (EnergyPlus creates .htm files)
        htm_files = list(output_dir.glob("*.htm"))
        html_files = list(output_dir.glob("*.html"))
        all_html_files = htm_files + html_files
        metrics["html_reports"] = all_html_files

        # Try to extract metrics from HTML files
        for html_file in all_html_files:
            try:
                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                    # Extract numeric values with context from table rows
                    # Pattern: <td>Label</td><td>Value</td>
                    table_pattern = r'<tr>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>'
                    matches = re.finditer(table_pattern, content, re.IGNORECASE)

                    for match in matches:
                        label = match.group(1).strip().lower()
                        value_str = match.group(2).strip()

                        try:
                            # Clean and convert value
                            value = float(value_str.replace(',', '').replace(' ', ''))

                            # Match labels - keep values in GJ (same unit as HTML)
                            if 'total site energy' in label:
                                metrics["total_energy"] = value
                            elif label == 'heating' and metrics["heating_energy"] is None:
                                metrics["heating_energy"] = value
                            elif label == 'cooling' and metrics["cooling_energy"] is None:
                                metrics["cooling_energy"] = value
                            elif 'interior lighting' in label:
                                if metrics["lighting_energy"] is None:
                                    metrics["lighting_energy"] = value
                                else:
                                    metrics["lighting_energy"] += value
                            elif 'exterior lighting' in label:
                                if metrics["lighting_energy"] is None:
                                    metrics["lighting_energy"] = value
                                else:
                                    metrics["lighting_energy"] += value
                            elif 'interior equipment' in label or 'exterior equipment' in label:
                                if metrics["equipment_energy"] is None:
                                    metrics["equipment_energy"] = value
                                else:
                                    metrics["equipment_energy"] += value
                        except (ValueError, AttributeError):
                            pass

            except Exception as e:
                continue

        # Fallback: Look for CSV output files
        if not all_html_files:
            csv_files = list(output_dir.glob("*.csv"))
            for csv_file in csv_files:
                try:
                    with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                        for line in lines:
                            if 'Total Energy' in line or 'Site Energy' in line:
                                parts = line.split(',')
                                if len(parts) > 1:
                                    try:
                                        value = float(parts[-1].strip())
                                        metrics["total_energy"] = value
                                    except:
                                        pass
                except:
                    continue

        # Mark as successful if we found any output files
        if all_html_files or list(output_dir.glob("*.csv")) or list(output_dir.glob("*.mtr")):
            metrics["simulation_success"] = True

    except Exception as e:
        pass

    return metrics


def main():
    st.set_page_config(page_title="EnergyPlus WWR Modifier", layout="wide")

    st.title("🏢 EnergyPlus Window-to-Wall Ratio (WWR) Modifier")
    st.markdown("Update the Window-to-Wall Ratio in your IDF files with ease")

    # Initialize session state
    if "current_idd_version" not in st.session_state:
        st.session_state.current_idd_version = None
        st.session_state.idd_set = False
    if "modified_idf_path" not in st.session_state:
        st.session_state.modified_idf_path = None
    if "modified_content" not in st.session_state:
        st.session_state.modified_content = None
    if "output_filename" not in st.session_state:
        st.session_state.output_filename = None
    if "uploaded_file_name" not in st.session_state:
        st.session_state.uploaded_file_name = None
    if "final_wwr_value" not in st.session_state:
        st.session_state.final_wwr_value = None
    if "simulation_metrics" not in st.session_state:
        st.session_state.simulation_metrics = None
    if "selected_idd_path" not in st.session_state:
        st.session_state.selected_idd_path = None
    if "selected_version" not in st.session_state:
        st.session_state.selected_version = None

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

    # Process IDF File button
    if st.button("🔄 Process IDF File", type="primary", use_container_width=False, width=800):
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

                    # Store in session state
                    st.session_state.modified_idf_path = tmp_output_path
                    st.session_state.modified_content = modified_content
                    st.session_state.output_filename = output_filename
                    st.session_state.uploaded_file_name = uploaded_file.name
                    st.session_state.final_wwr_value = final_wwr
                    st.session_state.selected_idd_path = idd_path
                    st.session_state.selected_version = selected_version

                st.success("✅ IDF file processed successfully!")

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

    # Show results if IDF has been processed
    if st.session_state.modified_idf_path:
        # Display download button
        st.download_button(
            label="📥 Download Modified IDF File",
            data=st.session_state.modified_content,
            file_name=st.session_state.output_filename,
            mime="text/plain",
            use_container_width=True
        )

        # Show summary
        st.subheader("📋 Processing Summary")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Original File", st.session_state.uploaded_file_name)
        with col2:
            st.metric("WWR Applied", f"{st.session_state.final_wwr_value:.1%}")
        with col3:
            st.metric("EnergyPlus Version", st.session_state.selected_version)
        with col4:
            st.metric("Output File", st.session_state.output_filename)

        st.divider()

        # Debug info
        with st.expander("🔍 Debug Info (Click to expand)"):
            st.write(f"Modified IDF Path: {st.session_state.modified_idf_path}")
            st.write(f"Selected IDD Path: {st.session_state.selected_idd_path}")
            st.write(f"Selected Version: {st.session_state.selected_version}")
            st.write(f"Environment: {'Streamlit Cloud (Linux)' if IS_STREAMLIT_CLOUD else 'Local/Desktop'}")

        # Show environment-specific notice
        if IS_STREAMLIT_CLOUD:
            st.warning(
                "⚠️ **Streamlit Cloud Limitation**: This app is running on Streamlit Cloud (Linux environment), "
                "which doesn't support EnergyPlus executables (Windows-only). Simulation is **disabled** here.\n\n"
                "**To complete your analysis:**\n"
                "1. ✅ Download the modified IDF file (button above)\n"
                "2. 📥 Install [EnergyPlus](https://energyplus.net) on your computer\n"
                "3. 🖥️ Run simulation locally: `energyplus -w weatherfile.epw -d output yourfile.idf`\n"
                "4. 📊 View results in the generated HTML reports\n\n"
                "_Alternatively, deploy this app locally on Windows or use a Windows-based server._"
            )
        else:
            # Simulate button (only shown on local/Windows environments)
            if st.button("⚡ Simulate with Modified IDF", type="secondary", use_container_width=False, width=800):
                # Validate required data
                if not st.session_state.modified_idf_path:
                    st.error("❌ No modified IDF file found. Please process the IDF file first.")
                elif not st.session_state.selected_idd_path:
                    st.error("❌ No EnergyPlus IDD path found. Please select an EnergyPlus version first.")
                else:
                    try:
                        with st.spinner("🔄 Running EnergyPlus simulation..."):
                            sim_result = run_simulation(st.session_state.modified_idf_path, idd_path=st.session_state.selected_idd_path)

                        if sim_result and sim_result.get("success"):
                            simulation_metrics = extract_simulation_metrics(sim_result["output_dir"])
                            st.session_state.simulation_metrics = simulation_metrics
                            st.success("✅ Simulation completed successfully!")
                        else:
                            error_msg = sim_result.get("error", "Unknown error") if sim_result else "Unknown error"
                            st.error(f"❌ Simulation failed: {error_msg}")

                    except Exception as e:
                        st.error(f"❌ Error running simulation: {str(e)}")
                        import traceback
                        with st.expander("📋 Error Details"):
                            st.code(traceback.format_exc())

        # Show simulation results if available
        if st.session_state.simulation_metrics:
            st.subheader("⚡ Simulation Results")

            sim_col1, sim_col2, sim_col3 = st.columns(3)

            with sim_col1:
                if st.session_state.simulation_metrics["total_energy"] is not None:
                    st.metric(
                        "Total Energy",
                        f"{st.session_state.simulation_metrics['total_energy']:,.2f} GJ",
                        delta="Modified"
                    )
                else:
                    st.metric("Total Energy", "N/A")

            with sim_col2:
                if st.session_state.simulation_metrics["heating_energy"] is not None:
                    st.metric(
                        "Heating Energy",
                        f"{st.session_state.simulation_metrics['heating_energy']:,.2f} GJ"
                    )
                else:
                    st.metric("Heating Energy", "N/A")

            with sim_col3:
                if st.session_state.simulation_metrics["cooling_energy"] is not None:
                    st.metric(
                        "Cooling Energy",
                        f"{st.session_state.simulation_metrics['cooling_energy']:,.2f} GJ"
                    )
                else:
                    st.metric("Cooling Energy", "N/A")

            sim_col4, sim_col5, sim_col6 = st.columns(3)

            with sim_col4:
                if st.session_state.simulation_metrics["lighting_energy"] is not None:
                    st.metric(
                        "Lighting Energy",
                        f"{st.session_state.simulation_metrics['lighting_energy']:,.2f} GJ"
                    )
                else:
                    st.metric("Lighting Energy", "N/A")

            with sim_col5:
                if st.session_state.simulation_metrics["equipment_energy"] is not None:
                    st.metric(
                        "Equipment Energy",
                        f"{st.session_state.simulation_metrics['equipment_energy']:,.2f} GJ"
                    )
                else:
                    st.metric("Equipment Energy", "N/A")

            with sim_col6:
                st.metric("Status", "✅ Complete")

            st.divider()
            st.info("💡 **Tip:** The WWR adjustment affects solar gains through windows, which impacts heating/cooling loads and lighting needs.")

            # Show HTML report download section
            if st.session_state.simulation_metrics.get("html_reports"):
                st.subheader("📊 Simulation Reports")
                st.write(f"✅ Found {len(st.session_state.simulation_metrics['html_reports'])} report(s)")

                for html_file in st.session_state.simulation_metrics["html_reports"]:
                    try:
                        with open(html_file, 'rb') as f:
                            html_content = f.read()

                        html_name = html_file.name
                        st.download_button(
                            label=f"📥 Download {html_name}",
                            data=html_content,
                            file_name=html_name,
                            mime="text/html",
                            use_container_width=True,
                            key=f"download_{html_name}"
                        )
                    except Exception as e:
                        st.warning(f"Could not load {html_file.name}: {str(e)}")
            else:
                st.info("⚠️ No HTML reports found in simulation output")


if __name__ == "__main__":
    main()
