import json
import stumpy
import warnings
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
import plotly.express as px

warnings.filterwarnings("ignore")
from pulse_analysis_algo.Parameter_functions_filtered import *


## Motif Extractions
def Motif_Extraction(pulse, window_size, no_of_motif):
    # Sample time series data
    time_series = np.array(pulse)

    # Sample time series data
    time_series = time_series.astype(float)

    # Window size for motif detection
    window_size = window_size

    # Compute the matrix profile
    matrix_profile = stumpy.stump(time_series, m=window_size)

    # Extract the indices of the 5 motifs with the lowest matrix profile values
    motif_indices = np.argsort(matrix_profile[:, 0])[:no_of_motif]

    return motif_indices


## Creating datframes for testing
def create_dataframe(pulse_array):
    """
    Creates a DataFrame with TIME and pulse columns.
    TIME starts from 0 and increments by 0.04 up to the size of the pulse_array.

    Parameters:
    pulse_array (list or np.array): 1D array of pulse values

    Returns:
    pd.DataFrame: DataFrame with TIME and pulse columns
    """
    time_values = np.arange(0, len(pulse_array) * 0.004, 0.004)
    df = pd.DataFrame({"TIME": time_values[: len(pulse_array)], "pulse": pulse_array})
    return df


## One Cycle Extarction
def One_cycle_Extraction(df, Peaks_index, Valley_index, Peak_limit):
    ## Reading only valley points from complete signal
    Valley_df = df.loc[Valley_index]
    Valley_df["Status"] = "Valley"
    ## Reading only peak points from complete signal
    Peaks_df = df.loc[Peaks_index]
    Peaks_df["Status"] = "Peak"

    ## Append peak valleys and sort it
    Peak_Valley = pd.concat([Peaks_df, Valley_df])
    Peak_Valley.sort_index(inplace=True)

    ## Filter only signal above the 0.8 and read the first two peaks
    Peaks_sample = Peak_Valley[Peak_Valley["Signal"] > Peak_limit]
    if Peaks_sample.shape[0] != 0:
        Peak1 = Peaks_sample.index[0]
        Peak2 = Peaks_sample.index[1]
        # Peak_Valley[Peak_Valley.index<Peak1]
        Valley1 = Peak_Valley[Peak_Valley.index < Peak1].index[-1]
        Valley2 = Peak_Valley[Peak_Valley.index < Peak2].index[-1]
        One_cycle = df.loc[Valley1:Valley2, :]
        One_cycle.reset_index(inplace=True)
        return One_cycle


## Saving mupliple plots
def saving_plots(df, pulse_name, cycles, output_path):
    for cycle in cycles:
        fig = px.line(df[cycle], x="TIME", y="Signal", title=pulse_name + "_" + cycle)
        fig.write_image(output_path + "/" + pulse_name + "_" + cycle + ".png")


def Final_Motif_Extarction(df, window_size, no_of_motif):
    motif_indices = Motif_Extraction(df["Signal"], window_size, no_of_motif)
    ## Sort the motif indices
    motif_indices = list(np.sort(motif_indices))

    ## Motif filtering
    final_motif_indices = [motif_indices[0]]
    for i in range(1, len(motif_indices)):
        if (motif_indices[i] - final_motif_indices[-1]) > window_size:
            final_motif_indices.append(motif_indices[i])
    return final_motif_indices


## Main Calculation Code
def pulse_predict(pulse_array):
    """
    Reads the array and return the pulse element prediction

    Args:
        pulse_array(array): list of pulse reading

    Returns:
        dataframe of pulse element prediction and scale

    """
    # data = create_dataframe(pulse_array)
    # pulse_array = pulse_array[2000:]  # Reading after 8 sec

    data = create_dataframe(np.convolve(pulse_array, np.ones(8) / 8, mode="valid"))

    ## Configurable inputs
    window_size = 100
    no_of_motif = 20
    Peak_limit = 0.85
    ##

    Final_Report = pd.DataFrame(
        columns=[
            "Pulse name",
            "Wind_AB_Time",
            "Wind_BA1_Time",
            "Wind_AA1_Time",
            "Wind_AB_Slope",
            "Wind_BA1_Slope",
            "Wind_AA1_Area",
            "Wind_angle",
            "Wind_AB_Ampli",
            "Humidity_C1C_Time",
            "Humidity_CD_Time",
            "Humidity_C1D_Time",
            "Humidity_C1C_Slope",
            "Humidity_CD_Slope",
            "Humidity_C1D_Area",
            "Humidity_angle",
            "Humid_Ratio",
            "Cold_BC_Slope",
            "Cold_BC_Time",
            "Cold_AC_Time",
            "Cold_BC_Ampli",
            "Cold_AC_Ampli",
            "Cold_AC_Area",
            "Heat_CE_Ampli",
            "Heat_DE_Ampli",
            "Heat_AE_Ampli",
            "Heat_D_D1_Time",
            "Heat_Area",
            "Dryness spike (F-A11)",
            "Dryness peak counts",
            "Dryness delay",
            "Cycle_Time",
            "Humidity_CD_Ampli",
        ]
    )
    Final_Report.set_index("Pulse name", inplace=True)

    Consolidated_Report = Final_Report.copy()

    ##
    Report = Final_Report.copy()

    ## Main running function
    data.iloc[:, 1:] = (data.iloc[:, 1:] - data.iloc[:, 1:].min()) / (
        data.iloc[:, 1:].max() - data.iloc[:, 1:].min()
    )
    pulse = list(data.columns)[1]
    Cycle_dict = {}
    Cycle_dict_index = {}
    ##
    Report = Final_Report.copy()
    ##
    df = data[["TIME", pulse]]
    df.rename(columns={pulse: "Signal"}, inplace=True)
    ## Extracting motif indicies
    final_motif_indices = Final_Motif_Extarction(df, window_size, no_of_motif)

    for i in range(len(final_motif_indices)):

        if (final_motif_indices[i] - window_size) < 0:
            PULSE = df.iloc[: final_motif_indices[i] + 4 * window_size]
        else:
            PULSE = df.iloc[
                final_motif_indices[i]
                - window_size : final_motif_indices[i]
                + 4 * window_size
            ]

        PULSE.reset_index(inplace=True)
        ## Peak and valley indices
        Peaks_index, Valley_index = Peak_Valley_Extarction(PULSE["Signal"])
        ## Extracting Single Cycle
        # print(f" Cycle {i+1} Peak Valley Extraction Started")

        try:
            cycle = One_cycle_Extraction(PULSE, Peaks_index, Valley_index, Peak_limit)

            Peaks_index, Valley_index = Peak_Valley_Extarction(cycle["Signal"])

            ##
            Valley_df = cycle.loc[Valley_index]
            Valley_df["Status"] = "Valley"
            ## Reading only peak points from complete signal
            Peaks_df = cycle.loc[Peaks_index]
            Peaks_df["Status"] = "Peak"

            ## Append peak valleys and sort it
            Peak_Valley = pd.concat([Peaks_df, Valley_df])  # ignore_index=True
            Peak_Valley.sort_index(inplace=True)

            ##Rejection Based on peaks
            if len(Peaks_index) < 2:
                continue
            elif len(Peaks_index) > 50:
                continue

            else:
                Cycle_dict[f"Cycle_{i + 1}"] = cycle
                Cycle_dict_index[f"Cycle_{i + 1}"] = Peak_Valley

            try:
                Report = new_approach(Report, Cycle_dict, Cycle_dict_index, pulse)
                Consolidated_Report.loc[pulse] = Report.mean()
                Consolidated_Report["Heart_rate"] = np.round(
                    60 / Report["Cycle_Time"].quantile(0.4), 2
                )
                OutputPath = r"../OUTPUT"
                # saving_plots(Cycle_dict,"pulse_name",list(Cycle_dict.keys()),OutputPath)
                # print("plotting saved")
            except Exception as e:
                # print(e)
                continue

        except Exception as e:
            # print(e)
            continue

    ## Additional tags
    Consolidated_Report["Humid_Ratio_Cold"] = Consolidated_Report["Humid_Ratio"]
    Consolidated_Report["Heart_CE_Ampli"] = Consolidated_Report["Heat_CE_Ampli"]
    Consolidated_Report["Heat_BC_Time"] = Consolidated_Report["Cold_BC_Time"]
    Consolidated_Report["Heart_BC_Time"] = Consolidated_Report["Cold_BC_Time"]

    ## Prediction part
    elements = ["Wind", "Humid", "Cold", "Heat", "Dry"]

    Selected_parameters = {
        "Wind": ["Wind_angle", "Wind_AA1_Time"],
        "Humid": ["Humidity_C1D_Area", "Humidity_C1D_Time", "Humidity_CD_Time"],
        "Cold": ["Cold_BC_Time", "Humid_Ratio_Cold"],
        "Heat": ["Heat_DE_Ampli", "Humidity_CD_Ampli", "Heat_BC_Time"],
        "Dry": ["Dryness spike (F-A11)", "Dryness delay"],
    }

    # Open the file and load the content into a dictionary
    with open("pulse_analysis_algo/min_max_values.txt", "r") as file:
        base_dict = json.load(file)  # Read as JSON

    # Vata,Pitta,Kapha and yin and yang
    with open("pulse_analysis_algo/VPT_Yin_Yang.txt", "r") as file:
        VPK = json.load(file)  # Read as JSON

    Consolidated_Report_Copy = Consolidated_Report.copy()

    if Consolidated_Report.empty:
        Mapping = "Retake"
    else:
        Mapping = pd.DataFrame()
        consolidated_result_per = calculate_percentage_position(
            Consolidated_Report, base_dict
        )

        parameter = {
            "Dryness spike (F-A11)": 0.2,
            "Dryness delay": 0.8,
            "Cold_AC_Time": 0.8,
            "Heat_Area": 0.1,
            "Heat_CE_Ampli": 0.05,
            "Heat_AE_Ampli": 0.05,
            "Wind_angle": 0.8,
            "Wind_AA1_Time": 0.2,
            "Heat_BC_Time": 0.2,
            "Heat_DE_Ampli": 0.1,
            "Humidity_CD_Ampli": 0.7,
            "Heart_BC_Time": 0.2,
            "Heart_CE_Ampli": 0.8,
        }

        for key, value in parameter.items():
            consolidated_result_per[key] = consolidated_result_per[key] * value

        ##
        for _ in elements:
            Mapping[_] = consolidated_result_per[Selected_parameters[_]].mean(axis=1)

        # Apply the ranking function row-wise
        ranked_columns = Mapping.apply(rank_columns, axis=1)

        # Concatenate the new columns with the original DataFrame
        Mapping = pd.concat([Mapping, ranked_columns], axis=1)

        ## VPK calculation

        VPK_N = Mapping.copy()
        numeric_cols = ["Wind", "Humid", "Cold", "Heat", "Dry"]
        # Find the minimum value across all numeric columns
        min_val = VPK_N[numeric_cols].min().min()

        # Shift if minimum value is negative
        if min_val < 0:
            VPK_N[numeric_cols] = VPK_N[numeric_cols] + abs(min_val)

        # Concatinating Primary,secondary and Tertiary
        PST = (
            Mapping["Primary"][0]
            + "_"
            + Mapping["Secondary"][0]
            + "_"
            + Mapping["Tertiary"][0]
        )

        vpk_yin_yang = list(VPK[PST].keys())
        for k in vpk_yin_yang:
            Mapping[k] = VPK[PST][k]

        # Apply function and create columns
        Mapping[["Carbohydrate", "Protein", "Fat"]] = Mapping.apply(
            assign_levels, axis=1
        )

        if str(Mapping["Wind"][0]) == "nan" or str(Mapping["Dry"][0]) == "nan":
            Mapping = "Retake"
        else:
            levels = ["Primary", "Secondary", "Tertiary", "Quaternary", "Quinary"]
            for level in levels:
                Mapping[level] = (
                    Mapping[level][0]
                    + "_"
                    + str(np.round(Mapping[Mapping[level][0]][0], 2))
                    + "%"
                )
            Mapping = Mapping[
                levels + ["Carbohydrate", "Protein", "Fat"] + vpk_yin_yang
            ].reset_index()
            Mapping.drop(columns="Pulse name", inplace=True)

            # Mapping[selected_tag]=Consolidated_Report_Copy[selected_tag].iloc[0]
            Mapping["Heart_rate"] = Consolidated_Report["Heart_rate"].iloc[0]

            ## Vata pitta Kapha adding
            vata = np.round((VPK_N["Wind"][0] * 0.4 + VPK_N["Dry"][0] * 0.6), 2)
            pitta = np.round((VPK_N["Heat"][0] * 0.7 + VPK_N["Cold"][0] * 0.3), 2)
            kapha = np.round((VPK_N["Humid"][0] * 0.7 + VPK_N["Cold"][0] * 0.3), 2)
            Total = vata + pitta + kapha
            Mapping["VATA"] = str(np.round(vata / Total * 100, 2)) + "%"
            Mapping["PITTA"] = str(np.round(pitta / Total * 100, 2)) + "%"
            Mapping["KAPHA"] = str(np.round(kapha / Total * 100, 2)) + "%"

            ## heart yin calculation
            Heart_yin_A = consolidated_result_per["Heart_BC_Time"].iloc[0]
            ##
            col = "Heart_CE_Ampli"
            Heart_yin_B = 100 - np.round(
                (Consolidated_Report_Copy["Heart_CE_Ampli"].iloc[0] + 0.15)
                / (base_dict["base_max"][col] - base_dict["base_min"][col])
                * 100,
                1,
            )

            Mapping["Heart_yin"] = (
                str(
                    np.round(
                        Heart_yin_A * parameter["Heart_BC_Time"]
                        + Heart_yin_B * parameter["Heart_CE_Ampli"],
                        2,
                    )
                )
                + "%"
            )
            Mapping = np.round(Mapping, 2)

    return Mapping
