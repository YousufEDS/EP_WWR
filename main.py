from geomeppy import IDF



IDD_PATH = r"C:\EnergyPlusV22-1-0\Energy+.idd"

IDF.setiddname(IDD_PATH)
# Load IDF
idf_path = input("Enter the path to your IDF file: ")
idf = IDF(idf_path)

WWR = 0.50


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


def modify_wwr(idf, wwr):
    """
    Modify Window-to-Wall Ratio using geomeppy
    """
    # Step 1: remove shading (optional but recommended)
    idf = clean_shading(idf)

    # Step 2: let geomeppy rebuild windows
    idf.set_wwr(
        wwr=wwr,
        construction=None,   # you can replace with a real construction name if needed
        force=True
    )

    return idf


# Apply WWR modification
idf = modify_wwr(idf, WWR)
# Generate output filename with WWR suffix
output_path = idf_path.replace(".idf", f"_WWR{int(WWR*100)}.idf")
# Save output
idf.saveas(output_path)

print("IDF successfully updated and saved!")
