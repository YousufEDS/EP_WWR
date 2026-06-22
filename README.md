# EnergyPlus WWR Modifier

A tool to modify Window-to-Wall Ratio (WWR) in EnergyPlus IDF files.

## Features

- **GUI Interface**: User-friendly Streamlit web interface
- **Easy File Upload**: Drag-and-drop IDF file upload
- **Flexible WWR Input**: Slider or precise decimal input
- **Auto-Clean Shading**: Automatically removes shading objects before WWR modification
- **Direct Download**: Download the modified IDF file immediately

## Installation

### Prerequisites
- Python 3.8+
- EnergyPlus (v22.1.0 or compatible) installed with IDD file

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Update the IDD path in `streamlit_app.py` if needed:
```python
IDD_PATH = r"C:\EnergyPlusV22-1-0\Energy+.idd"
```

## Usage

### Option 1: Streamlit Web UI (Recommended)

```bash
streamlit run streamlit_app.py
```

Then:
1. Open your browser to the URL shown (typically `http://localhost:8501`)
2. Upload your IDF file
3. Set the desired WWR (0.0 to 1.0)
4. Click "Process IDF File"
5. Download the modified file

### Option 2: Command Line

```bash
python main.py
```

Then follow the prompts to enter file paths and WWR value.

## File Structure

- `streamlit_app.py` - Web UI (Recommended)
- `main.py` - Command-line version
- `requirements.txt` - Python dependencies

## How It Works

1. **Loads IDF**: Reads your EnergyPlus IDF file
2. **Cleans Shading**: Removes existing shading objects
3. **Sets WWR**: Updates window-to-wall ratio using geomeppy
4. **Saves Output**: Saves modified file with `_WWR{percentage}` suffix

## WWR Values

- **0.0**: No windows
- **0.25**: 25% windows
- **0.50**: 50% windows (default)
- **0.75**: 75% windows
- **1.0**: 100% windows (full window coverage)

## Troubleshooting

### IDD File Not Found
Make sure EnergyPlus is installed and update the `IDD_PATH` in the code to point to your `Energy+.idd` file.

### Invalid IDF File
Ensure the file is a valid EnergyPlus IDF file. The file should have a `.idf` extension.

### Geometry Issues
Some complex geometries may have issues with WWR modification. Try reducing the WWR value or cleaning the IDF file manually.

## License

Use freely for EnergyPlus simulations and building energy analysis.
