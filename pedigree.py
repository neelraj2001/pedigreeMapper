"""
File layout expected is an unformatted .csv with 7 columns in the order of
1) individual_id
2) father_id
3) mother_id
4) sex
5) usgs_band_id
6) hatch_year
7) aux_id

Run the program using command 'streamlit run pedigree.py'
"""
from datetime import datetime
import streamlit as st
from graphviz import Digraph
import pandas as pd

st.set_page_config(layout="wide")


def parse_ped_file(ped_file):

    relationships = {}
    file_contents = ped_file.getvalue().decode("utf-8")

    # Deduplication
    seen_lines = set()

    for line in file_contents.split("\n"):
        line = line.strip()
        if not line:
            continue  # Skip empty lines

        if line in seen_lines:
            continue  # Skip duplicates
        seen_lines.add(line)

        parts = line.split(",")
        # Expect at least 7 columns
        if len(parts) < 7:
            continue

        (
            individual_id,
            father_id,
            mother_id,
            sex,
            usgs_band_id,
            hatch_year,
            aux_id,
        ) = parts

        # Convert "0" to "N/A" for optional fields:
        sex_val = sex  # We'll store as-is for determining node shape
        usgs_val = usgs_band_id if usgs_band_id != "0" else "N/A"
        # If 'hatch_year' is blank or None, use 'N/A'; else use the given value
        hatch_val = hatch_year if hatch_year else "N/A"
        aux_val = aux_id if aux_id != "0" else "N/A"

        relationships[individual_id] = {
            "father_id": father_id,
            "mother_id": mother_id,
            "sex": sex_val,
            "usgs_band_id": usgs_val,
            "hatch_year": hatch_val,
            "aux_id": aux_val,
        }

    return relationships


def get_mates(relationships, individual_id):
    """
    Return a set of all mates (partners) of the given individual.
    Two individuals are considered 'mates' if they share at least one child.
    """
    mates = set()
    if individual_id not in relationships:
        return mates

    for iid, info in relationships.items():
        pid = info["father_id"]
        mid = info["mother_id"]
        # If this child has 'individual_id' as father, mother is mate
        if pid == individual_id and mid in relationships and mid != "0":
            mates.add(mid)
        # If this child has 'individual_id' as mother, father is mate
        if mid == individual_id and pid in relationships and pid != "0":
            mates.add(pid)

    return mates


def filter_family(relationships, individual_id, filter_year=None):
    """
    Filter relationships to:
      - The individual
      - Their father & mother
      - Any mates (partners who share a child)
      - Children of the individual or the mates,
        optionally filtered by 'hatch_year' if filter_year is provided.
    """
    if not individual_id or individual_id not in relationships:
        return relationships

    family = {}
    family[individual_id] = relationships[individual_id]

    father_id = relationships[individual_id]["father_id"]
    mother_id = relationships[individual_id]["mother_id"]
    if father_id in relationships and father_id != "0":
        family[father_id] = relationships[father_id]
    if mother_id in relationships and mother_id != "0":
        family[mother_id] = relationships[mother_id]

    mates = get_mates(relationships, individual_id)
    for mate_id in mates:
        family[mate_id] = relationships[mate_id]

    # Children (only include those matching filter_year if specified)
    for iid, info in relationships.items():
        cpid = info["father_id"]
        cmid = info["mother_id"]
        # If child belongs to individual or any of the individual's mates
        if (
            cpid == individual_id
            or cmid == individual_id
            or cpid in mates
            or cmid in mates
        ):
            # If no filter_year specified, or child's hatch_year matches
            if filter_year is None or info["hatch_year"] == filter_year:
                family[iid] = info

    return family


def generate_graph(relationships, FOCUS_ID=None):
    """
    Generate a DOT graph (PNG) from relationships with:
      - Father & mother on same level (above)
      - Focus individual & mates on same level (middle)
      - Children below
    Node shapes: male=box, female=ellipse, unknown=egg.
    Edge colors: father=blue, mother=red, unknown=gray.
    Returns PNG bytes for display/download.
    """
    if not relationships:
        return None

    dot = Digraph(format="png")
    dot.attr(rankdir="TB", nodesep="0.2", ranksep="0.6", size="8,8!")
    dot.attr("graph", dpi="1000")

    drawn = set()

    def create_node(iid):
        if iid not in drawn and iid in relationships:
            info = relationships[iid]
            label_lines = [f"Individual: {iid}"]

            # Add hatch year if not 'N/A'
            if info["hatch_year"] and info["hatch_year"] != "N/A":
                label_lines.append(f"Hatch Year: {info['hatch_year']}")

            # Add band or aux if not 'N/A'
            if info["usgs_band_id"] != "":
                label_lines.append(f"Primary ID: {info['usgs_band_id']}")
            if info["aux_id"] != "":
                label_lines.append(f"Aux ID: {info['aux_id']}")

            label = "\\n".join(label_lines)

            # Determine shape/fill color from sex
            shape = "egg"
            fillcolor = "gray"
            if info["sex"] == "1":
                shape = "box"
                fillcolor = "lightblue"
            elif info["sex"] == "2":
                shape = "ellipse"
                fillcolor = "lightpink"

            dot.node(iid, label=label, shape=shape, style="filled", fillcolor=fillcolor)
            drawn.add(iid)

    def edge_color(parent_id):
        # Returns 'blue' for male, 'red' for female, else 'gray'.
        color = "gray"
        parent_info = relationships.get(parent_id)
        if parent_info:
            if parent_info["sex"] == "1":
                color = "blue"
            elif parent_info["sex"] == "2":
                color = "red"
        return color

    if FOCUS_ID and FOCUS_ID in relationships:
        father_id = relationships[FOCUS_ID]["father_id"]
        mother_id = relationships[FOCUS_ID]["mother_id"]
        mates = get_mates(relationships, FOCUS_ID)

        # Father & mother side by side
        if (
            father_id in relationships
            and father_id != "0"
            and mother_id in relationships
            and mother_id != "0"
        ):
            with dot.subgraph() as parents_sub:
                parents_sub.attr(rank="same")
                create_node(father_id)
                create_node(mother_id)

            dot.edge(father_id, FOCUS_ID, color=edge_color(father_id))
            dot.edge(mother_id, FOCUS_ID, color=edge_color(mother_id))
        else:
            # If father exists
            if father_id in relationships and father_id != "0":
                create_node(father_id)
                dot.edge(father_id, FOCUS_ID, color=edge_color(father_id))
            # If mother exists
            if mother_id in relationships and mother_id != "0":
                create_node(mother_id)
                dot.edge(mother_id, FOCUS_ID, color=edge_color(mother_id))

        # Individual & mates on same rank
        with dot.subgraph() as main_sub:
            main_sub.attr(rank="same")
            create_node(FOCUS_ID)
            for mate in mates:
                create_node(mate)

        # Children
        for cid, cinfo in relationships.items():
            cpid = cinfo["father_id"]
            cmid = cinfo["mother_id"]
            if (cpid == FOCUS_ID or cpid in mates) or (
                cmid == FOCUS_ID or cmid in mates
            ):
                create_node(cid)
                if cpid == FOCUS_ID or cpid in mates:
                    dot.edge(cpid, cid, color=edge_color(cpid))
                if cmid == FOCUS_ID or cmid in mates:
                    dot.edge(cmid, cid, color=edge_color(cmid))
    else:
        # No focus => entire dataset
        for iid in relationships:
            create_node(iid)
        for iid, info in relationships.items():
            pid = info["father_id"]
            mid = info["mother_id"]
            if pid in relationships and pid != "0":
                dot.edge(pid, iid, color=edge_color(pid))
            if mid in relationships and mid != "0":
                dot.edge(mid, iid, color=edge_color(mid))

    try:
        return dot.pipe(format="png")
    except Exception as error:
        st.error(f"Error generating PNG: {error}")
        return None


# ------------------ STREAMLIT APP ------------------
st.title("🐦 BurrowD Pedigree Grapher")

st.markdown(
    """
    This application takes a CSV file describing individuals, their parents, and
    other identifying information. Once uploaded, it constructs a simple pedigree
    graph to visualize family relationships and allows filtering by individual ID
    or band ID, as well as optionally filtering children by hatch year.

    This application was developed by Neel Raj while a fellow with the CTL at SDZWA.
    It takes data from the Burrowing Owl recovery project but may be used for other
    conservation/breeding projects.

    The CSV file should be formatted in order of: Individual_ID, Father_ID, Mother_ID, Sex, USGS_Band_ID, Hatch_Year, Aux_ID
    """
)

uploaded_file = st.file_uploader("Upload CSV file")

if uploaded_file:
    # 1. Parse relationships
    relationships = parse_ped_file(uploaded_file)

    # 2. Convert dict to DataFrame for display
    df = pd.DataFrame.from_dict(relationships, orient="index")
    df.index.name = "Individual ID"
    df.reset_index(inplace=True)

    df.rename(
        columns={
            "father_id": "Father ID",
            "mother_id": "Mother ID",
            "sex": "Sex",
            "usgs_band_id": "USGS Band ID",
            "hatch_year": "Hatch Year",
            "aux_id": "Aux ID",
        },
        inplace=True,
    )

    # Show the data
    st.subheader("Parsed Pedigree Data")
    st.dataframe(df, use_container_width=True, height=600)

    # 3. Inputs for focusing the graph
    st.write("### Focus Filters")
    individual_id = st.text_input("Enter an Individual ID (leave blank to skip)")
    band_id = st.text_input("Enter a USGS Band ID (leave blank to skip)")

    # 4. Determine which individual to focus on
    FOCUS_ID = None
    # If user gave an Individual ID, we use that first
    if individual_id.strip():
        if individual_id in relationships:
            FOCUS_ID = individual_id
        else:
            st.warning(f"No match found for Individual ID: {individual_id}")
    else:
        # Otherwise, if user gave a band ID, find the matching individual(s)
        if band_id.strip():
            # Collect all individuals who match this band (some data sets might have 1 or more)
            found_ids = [
                iid
                for iid, info in relationships.items()
                if info["usgs_band_id"] == band_id
            ]
            if len(found_ids) == 1:
                FOCUS_ID = found_ids[0]
                st.info(f"Found Individual ID {FOCUS_ID} for Band {band_id}")
            elif len(found_ids) > 1:
                st.warning(
                    f"Multiple Individuals found with band {band_id}: {found_ids}. "
                    "Using the first one."
                )
                FOCUS_ID = found_ids[0]
            else:
                st.warning(f"No individual found with Band ID: {band_id}")

    # 5. Optionally filter children by hatch year
    filter_year = st.text_input(
        "Enter a Hatch Year to Filter Children (optional):"
    ).strip()
    filter_year = filter_year if filter_year else None

    # 6. Filter relationships to the family around the focus individual (if any)
    filtered_relationships = (
        filter_family(relationships, FOCUS_ID, filter_year)
        if FOCUS_ID
        else relationships
    )

    # 7. Generate and display the graph
    png_bytes = generate_graph(filtered_relationships, FOCUS_ID=FOCUS_ID)
    if png_bytes:
        st.image(png_bytes, caption="Pedigree Graph", use_container_width=True)
        # Build a filename that reflects the filters
        prefix = (
            FOCUS_ID
            if FOCUS_ID
            else ("band_" + band_id if band_id else "all_individuals")
        )
        suffix = f"_{filter_year}" if filter_year else ""
        file_name = f"{prefix}_pedigree{suffix}.png"
        st.download_button(
            label="Download PNG", data=png_bytes, file_name=file_name, mime="image/png"
        )
    else:
        st.error("No valid data to generate a PNG graph.")
else:
    st.info("Please upload a CSV file to begin.")

current_year = datetime.now().year
CR_STATEMENT = (
    "Copyright (c) " 
    + str(current_year)
    + " Conservation Tech Lab at the San Diego Zoo Wildlife Alliance"
)
st.write("Github - https://")
st.write(CR_STATEMENT)