import warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.signal import find_peaks

warnings.filterwarnings("ignore")
import math


## Peak valley Extraction
def Peak_Valley_Extarction(signal):
    """
    Extracting the Peak and valleys of signal

    Parameters:
        signal(pd.Series): Signal values

    Returns:
        return the array of peaks and valleys
    """
    # Find peaks
    peaks, _ = find_peaks(signal)
    # Invert the signal to find valleys as peaks
    inverted_signal = -signal
    valleys, _ = find_peaks(inverted_signal)
    return peaks, valleys


def calculate_angle(x1, y1, x2, y2, x3, y3):
    # Vector AB
    AB_x = x2 - x1
    AB_y = y2 - y1

    # Vector BC
    BC_x = x3 - x2
    BC_y = y3 - y2

    # Dot product of AB and BC
    dot_product = AB_x * BC_x + AB_y * BC_y

    # Magnitudes of AB and BC
    magnitude_AB = math.sqrt(AB_x**2 + AB_y**2)
    magnitude_BC = math.sqrt(BC_x**2 + BC_y**2)

    # Calculate the angle in radians
    angle_radians = math.acos(dot_product / (magnitude_AB * magnitude_BC))

    # Convert to degrees
    angle_degrees = 180 - math.degrees(angle_radians)

    return angle_degrees


## Wind parameter extarction
def Wind_Cal(
    One_cycle,
    A_TIME,
    A_Value,
    B_TIME,
    B_Value,
    A1_prime_index,
    A1_prime_TIME,
    A1_prime_value,
):
    ## Time
    AB_Time = np.round(B_TIME - A_TIME, 4)
    BA1_Time = np.round(A1_prime_TIME - B_TIME, 4)
    AA1_Time = np.round(A1_prime_TIME - A_TIME, 4)

    ## Amplitude
    AB_Ampli = np.round(B_Value - A_Value, 4)

    ## Slope
    AB_Slope = np.round((B_Value - A_Value) / (B_TIME - A_TIME), 4)
    BA1_Slope = np.round((A1_prime_value - B_Value) / (A1_prime_TIME - B_TIME), 4)

    ## Area
    A_A1_prime = One_cycle.loc[:A1_prime_index, :]
    AA1_Area = np.round(np.trapz(A_A1_prime["Signal"], x=A_A1_prime["TIME"]), 4)

    ## Angle
    Wind_angle = calculate_angle(
        A_TIME, A_Value, B_TIME, B_Value, A1_prime_TIME, A1_prime_value
    )
    Wind_angle = np.round(Wind_angle, 4)
    ##
    return (
        AB_Time,
        BA1_Time,
        AA1_Time,
        AB_Ampli,
        AB_Slope,
        BA1_Slope,
        AA1_Area,
        Wind_angle,
    )


##
def Cold_Cal(One_cycle, A_TIME, A_Value, B_TIME, B_Value, C_index, C_TIME, C_Value):
    ## Slope
    BC_Slope = np.round((C_Value - B_Value) / (C_TIME - B_TIME), 4)

    ## Time
    BC_Time = np.round(C_TIME - B_TIME, 4)
    AC_Time = np.round(C_TIME - A_TIME, 4)

    ## Amplitude
    BC_Ampli = np.round(B_Value - C_Value, 4)
    AC_Ampli = np.round(A_Value - C_Value, 4)

    ## Area
    AC = One_cycle.loc[:C_index, :]
    AC_Area = np.round(np.trapz(AC["Signal"], x=AC["TIME"]), 4)

    return BC_Slope, BC_Time, AC_Time, BC_Ampli, AC_Ampli, AC_Area


##
def E_F_Extraction(One_cycle, E_index, F_index):
    ## Heat Extraction (E-F)
    E_F = One_cycle.loc[E_index:F_index, :]
    E_F.reset_index(inplace=True)
    return E_F


## Heat analysis
def Heat_Cal(
    One_cycle,
    A_Value,
    B_C,
    C_Value,
    D_index,
    D_Time,
    D_Value,
    E_index,
    E_Value,
    F_index,
):
    ## Amplitude
    CE_Ampli = np.round(E_Value - C_Value, 4)
    DE_Ampli = np.round(D_Value - E_Value, 4)
    AE_Ampli = np.round(A_Value - E_Value, 4)

    ##
    C1_prime_index = B_C[B_C["Signal"] < D_Value]["index"].iloc[0]
    C1_prime_TIME = B_C[B_C["Signal"] < D_Value]["TIME"].iloc[0]
    C1_prime_value = B_C[B_C["Signal"] < D_Value]["Signal"].iloc[0]

    E_F = E_F_Extraction(One_cycle, E_index, F_index)

    ## Location D1 prime info.
    D1_prime_index = E_F[E_F["Signal"] > D_Value]["index"].iloc[0]
    D1_prime_TIME = E_F[E_F["Signal"] > D_Value]["TIME"].iloc[0]
    D1_prime_value = E_F[E_F["Signal"] > D_Value]["Signal"].iloc[0]

    ## Time
    D_D1_Time = np.round(D1_prime_TIME - D_Time, 4)

    ## Area
    D_D1_prime = One_cycle.loc[D_index:D1_prime_index, :]
    # Heat_Area=np.round(np.trapz(D_D1_prime['Signal'],x=D_D1_prime['TIME']),4)
    Heat_Area = (D_D1_Time * D_Value) - np.round(
        np.trapz(D_D1_prime["Signal"], x=D_D1_prime["TIME"]), 4
    )

    return CE_Ampli, DE_Ampli, AE_Ampli, D_D1_Time, Heat_Area


## Dryness analysis
def Dryness_Cal(One_cycle, Peak_Valley, E_F, A_Value, F_index, F_Value):
    F_minus_A = np.round(F_Value - A_Value, 4)
    # Count of Peaks
    PV_After_F = Peak_Valley[Peak_Valley["index"] > F_index]
    peak_counts = len(PV_After_F[PV_After_F["Status"] == "Peak"])
    ## TIME from A11 to next cycle start.
    # A11_prime_index=E_F[E_F['Signal']>A_Value]['index'].iloc[0]
    A11_prime_TIME = E_F[E_F["Signal"] > A_Value]["TIME"].iloc[0]
    # A11_prime_value=E_F[E_F['Signal']>A_Value]['Signal'].iloc[0]
    # TIME Calculation
    TIME_delay = One_cycle["TIME"].iloc[-1] - A11_prime_TIME

    return (
        F_minus_A,
        peak_counts,
        TIME_delay,
    )  # ,A11_prime_index,A11_prime_TIME,A11_prime_value


## Humidity Analysis
def Humidity_Cal(
    One_cycle,
    C_TIME,
    C_Value,
    D_index,
    D_TIME,
    D_Value,
    C1_prime_index,
    C1_prime_TIME,
    C1_prime_value,
):
    ## Time
    C1C_Time = np.round(C_TIME - C1_prime_TIME, 4)
    CD_Time = np.round(D_TIME - C_TIME, 4)
    C1D_Time = np.round(D_TIME - C1_prime_TIME, 4)

    ## Slope
    C1C_Slope = np.round((C_Value - C1_prime_value) / (C_TIME - C1_prime_TIME), 4)
    CD_Slope = np.round((D_Value - C_Value) / (D_TIME - C_TIME), 4)

    ## Area
    C1_D = One_cycle.loc[C1_prime_index:D_index, :]
    C1D_Area = np.round(np.trapz(C1_D["Signal"], x=C1_D["TIME"]), 4)

    ## Humidity Angles
    Humidity_angle = calculate_angle(
        C1_prime_TIME, C1_prime_value, C_TIME, C_Value, D_TIME, D_Value
    )
    Humidity_angle = np.round(Humidity_angle, 4)

    return C1C_Time, CD_Time, C1D_Time, C1C_Slope, CD_Slope, C1D_Area, Humidity_angle


## Main Calculation
def new_approach(Final_Report, Cycles, Cycles_index, pulse):
    Keys = list(Cycles.keys())
    for cycle in Keys[-5:]:
        Pulse = pulse + "_" + cycle

        One_cycle = Cycles[cycle][["index", "TIME", "Signal"]].set_index("index")
        Peak_Valley = Cycles_index[cycle][["index", "TIME", "Signal", "Status"]]
        peak_count = Peak_Valley[Peak_Valley["Status"] == "Peak"].shape[0]

        ##
        # Peaks_sample=Peak_Valley[Peak_Valley['Signal']>Peak_limit]
        # Peaks_time=Peaks_sample["TIME"].iloc[-1]-Peaks_sample["TIME"].iloc[-2]
        Peaks_time = 1

        ## Location A info
        A_Value = One_cycle["Signal"].iloc[0]  # Valley
        A_TIME = One_cycle["TIME"].iloc[0]
        L_TIME = One_cycle["TIME"].iloc[-1]
        Cycle_Time = np.round(L_TIME - A_TIME, 2)

        ## Location B,C
        B_index = Peak_Valley["index"].iloc[0]  # Peak
        C_index = Peak_Valley["index"].iloc[1]  # Valley
        D_index = Peak_Valley["index"].iloc[2]  # Peak
        ##
        B_TIME, B_Value = (
            One_cycle.loc[B_index]["TIME"],
            One_cycle.loc[B_index]["Signal"],
        )
        C_TIME, C_Value = (
            One_cycle.loc[C_index]["TIME"],
            One_cycle.loc[C_index]["Signal"],
        )
        D_TIME, D_Value = (
            One_cycle.loc[D_index]["TIME"],
            One_cycle.loc[D_index]["Signal"],
        )
        ##
        if peak_count < 2:
            continue

        elif peak_count < 3:
            Peak_Valley = Cycles_index[cycle][["index", "TIME", "Signal", "Status"]]
            #
            if C_Value < A_Value:
                try:
                    # Wind calculation:
                    B_C = One_cycle.loc[B_index:C_index, :]
                    B_C.reset_index(inplace=True)
                    ## Location A prime info.
                    A1_prime_index = B_C[B_C["Signal"] < A_Value]["index"].iloc[0]
                    A1_prime_TIME = B_C[B_C["Signal"] < A_Value]["TIME"].iloc[0]
                    A1_prime_value = B_C[B_C["Signal"] < A_Value]["Signal"].iloc[0]

                    (
                        AB_Time,
                        BA1_Time,
                        AA1_Time,
                        AB_Ampli,
                        AB_Slope,
                        BA1_Slope,
                        AA1_Area,
                        Wind_angle,
                    ) = Wind_Cal(
                        One_cycle,
                        A_TIME,
                        A_Value,
                        B_TIME,
                        B_Value,
                        A1_prime_index,
                        A1_prime_TIME,
                        A1_prime_value,
                    )
                    ##
                    Final_Report.loc[Pulse, "Wind_AB_Time"] = AB_Time
                    Final_Report.loc[Pulse, "Wind_BA1_Time"] = BA1_Time
                    Final_Report.loc[Pulse, "Wind_AA1_Time"] = AA1_Time
                    Final_Report.loc[Pulse, "Wind_AB_Ampli"] = AB_Ampli
                    Final_Report.loc[Pulse, "Wind_AB_Slope"] = AB_Slope
                    Final_Report.loc[Pulse, "Wind_BA1_Slope"] = BA1_Slope
                    Final_Report.loc[Pulse, "Wind_AA1_Area"] = AA1_Area
                    Final_Report.loc[Pulse, "Wind_angle"] = Wind_angle
                    Final_Report.loc[Pulse, "Cycle_Time"] = Cycle_Time

                    try:
                        ## Cold Calculation
                        BC_Slope, BC_Time, AC_Time, BC_Ampli, AC_Ampli, AC_Area = (
                            Cold_Cal(
                                One_cycle,
                                A_TIME,
                                A_Value,
                                B_TIME,
                                B_Value,
                                C_index,
                                C_TIME,
                                C_Value,
                            )
                        )
                        Humid_Ratio = np.round(AC_Ampli / AB_Ampli, 4)
                        ##
                        Final_Report.loc[Pulse, "Cold_BC_Slope"] = BC_Slope
                        Final_Report.loc[Pulse, "Cold_BC_Time"] = BC_Time
                        Final_Report.loc[Pulse, "Cold_BC_Ampli"] = BC_Ampli
                        Final_Report.loc[Pulse, "Cold_AC_Time"] = AC_Time
                        Final_Report.loc[Pulse, "Cold_AC_Ampli"] = AC_Ampli
                        Final_Report.loc[Pulse, "Cold_AC_Area"] = AC_Area
                        Final_Report.loc[Pulse, "Humid_Ratio"] = Humid_Ratio
                        ##
                        if D_Value < B_Value:
                            C1_prime_index = B_C[B_C["Signal"] < D_Value]["index"].iloc[
                                0
                            ]
                            C1_prime_TIME = B_C[B_C["Signal"] < D_Value]["TIME"].iloc[0]
                            C1_prime_value = B_C[B_C["Signal"] < D_Value][
                                "Signal"
                            ].iloc[0]
                            (
                                C1C_Time,
                                CD_Time,
                                C1D_Time,
                                C1C_Slope,
                                CD_Slope,
                                C1D_Area,
                                Humidity_angle,
                            ) = Humidity_Cal(
                                One_cycle,
                                C_TIME,
                                C_Value,
                                D_index,
                                D_TIME,
                                D_Value,
                                C1_prime_index,
                                C1_prime_TIME,
                                C1_prime_value,
                            )
                            ##
                            Final_Report.loc[Pulse, "Humidity_C1C_Time"] = C1C_Time
                            Final_Report.loc[Pulse, "Humidity_CD_Time"] = CD_Time
                            Final_Report.loc[Pulse, "Humidity_C1D_Time"] = C1D_Time
                            Final_Report.loc[Pulse, "Humidity_C1C_Slope"] = C1C_Slope
                            Final_Report.loc[Pulse, "Humidity_CD_Slope"] = CD_Slope
                            Final_Report.loc[Pulse, "Humidity_C1D_Area"] = C1D_Area
                            Final_Report.loc[Pulse, "Humidity_angle"] = Humidity_angle

                        else:
                            continue
                    except:
                        continue
                except:
                    continue
            else:
                continue

        else:
            if C_Value < A_Value:
                # Wind calculation:
                B_C = One_cycle.loc[B_index:C_index, :]
                B_C.reset_index(inplace=True)
                ## Location A prime info.
                A1_prime_index = B_C[B_C["Signal"] < A_Value]["index"].iloc[0]
                A1_prime_TIME = B_C[B_C["Signal"] < A_Value]["TIME"].iloc[0]
                A1_prime_value = B_C[B_C["Signal"] < A_Value]["Signal"].iloc[0]
                try:
                    (
                        AB_Time,
                        BA1_Time,
                        AA1_Time,
                        AB_Ampli,
                        AB_Slope,
                        BA1_Slope,
                        AA1_Area,
                        Wind_angle,
                    ) = Wind_Cal(
                        One_cycle,
                        A_TIME,
                        A_Value,
                        B_TIME,
                        B_Value,
                        A1_prime_index,
                        A1_prime_TIME,
                        A1_prime_value,
                    )
                    ##
                    Final_Report.loc[Pulse, "Wind_AB_Time"] = AB_Time
                    Final_Report.loc[Pulse, "Wind_BA1_Time"] = BA1_Time
                    Final_Report.loc[Pulse, "Wind_AA1_Time"] = AA1_Time
                    Final_Report.loc[Pulse, "Wind_AB_Ampli"] = AB_Ampli
                    Final_Report.loc[Pulse, "Wind_AB_Slope"] = AB_Slope
                    Final_Report.loc[Pulse, "Wind_BA1_Slope"] = BA1_Slope
                    Final_Report.loc[Pulse, "Wind_AA1_Area"] = AA1_Area
                    Final_Report.loc[Pulse, "Wind_angle"] = Wind_angle
                    Final_Report.loc[Pulse, "Cycle_Time"] = Cycle_Time
                except:
                    continue

                try:
                    ## Cold Calculation
                    BC_Slope, BC_Time, AC_Time, BC_Ampli, AC_Ampli, AC_Area = Cold_Cal(
                        One_cycle,
                        A_TIME,
                        A_Value,
                        B_TIME,
                        B_Value,
                        C_index,
                        C_TIME,
                        C_Value,
                    )
                    Humid_Ratio = np.round(AC_Ampli / AB_Ampli, 4)
                    ##
                    Final_Report.loc[Pulse, "Cold_BC_Slope"] = BC_Slope
                    Final_Report.loc[Pulse, "Cold_BC_Time"] = BC_Time
                    Final_Report.loc[Pulse, "Cold_BC_Ampli"] = BC_Ampli
                    Final_Report.loc[Pulse, "Cold_AC_Time"] = AC_Time
                    Final_Report.loc[Pulse, "Cold_AC_Ampli"] = AC_Ampli
                    Final_Report.loc[Pulse, "Cold_AC_Area"] = AC_Area
                    Final_Report.loc[Pulse, "Humid_Ratio"] = Humid_Ratio
                except:
                    continue

                if D_Value < B_Value:  # Humidity calculation part
                    ##
                    E_index = Peak_Valley["index"].iloc[3]  # Valley
                    F_index = Peak_Valley["index"].iloc[4]  # Peak
                    ##
                    E_TIME, E_Value = (
                        One_cycle.loc[E_index]["TIME"],
                        One_cycle.loc[E_index]["Signal"],
                    )
                    F_TIME, F_Value = (
                        One_cycle.loc[F_index]["TIME"],
                        One_cycle.loc[F_index]["Signal"],
                    )
                    ##
                    C1_prime_index = B_C[B_C["Signal"] < D_Value]["index"].iloc[0]
                    C1_prime_TIME = B_C[B_C["Signal"] < D_Value]["TIME"].iloc[0]
                    C1_prime_value = B_C[B_C["Signal"] < D_Value]["Signal"].iloc[0]
                    try:
                        (
                            C1C_Time,
                            CD_Time,
                            C1D_Time,
                            C1C_Slope,
                            CD_Slope,
                            C1D_Area,
                            Humidity_angle,
                        ) = Humidity_Cal(
                            One_cycle,
                            C_TIME,
                            C_Value,
                            D_index,
                            D_TIME,
                            D_Value,
                            C1_prime_index,
                            C1_prime_TIME,
                            C1_prime_value,
                        )
                        ##
                        Final_Report.loc[Pulse, "Humidity_C1C_Time"] = C1C_Time
                        Final_Report.loc[Pulse, "Humidity_CD_Time"] = CD_Time
                        Final_Report.loc[Pulse, "Humidity_C1D_Time"] = C1D_Time
                        Final_Report.loc[Pulse, "Humidity_C1C_Slope"] = C1C_Slope
                        Final_Report.loc[Pulse, "Humidity_CD_Slope"] = CD_Slope
                        Final_Report.loc[Pulse, "Humidity_C1D_Area"] = C1D_Area
                        Final_Report.loc[Pulse, "Humidity_angle"] = Humidity_angle
                    except Exception as err:
                        continue

                    if D_Value < F_Value:
                        try:
                            CE_Ampli, DE_Ampli, AE_Ampli, D_D1_Time, Heat_Area = (
                                Heat_Cal(
                                    One_cycle,
                                    A_Value,
                                    B_C,
                                    C_Value,
                                    D_index,
                                    D_TIME,
                                    D_Value,
                                    E_index,
                                    E_Value,
                                    F_index,
                                )
                            )
                            Final_Report.loc[Pulse, "Heat_CE_Ampli"] = CE_Ampli
                            Final_Report.loc[Pulse, "Heat_DE_Ampli"] = DE_Ampli
                            Final_Report.loc[Pulse, "Heat_AE_Ampli"] = AE_Ampli
                            Final_Report.loc[Pulse, "Heat_D_D1_Time"] = D_D1_Time
                            Final_Report.loc[Pulse, "Heat_Area"] = Heat_Area
                        except Exception as err:
                            continue
                    else:
                        continue

                    try:
                        E_F = E_F_Extraction(One_cycle, E_index, F_index)
                        F_minus_A, peak_counts, TIME_delay = Dryness_Cal(
                            One_cycle, Peak_Valley, E_F, A_Value, F_index, F_Value
                        )
                        Final_Report.loc[Pulse, "Dryness spike (F-A11)"] = F_minus_A
                        Final_Report.loc[Pulse, "Dryness peak counts"] = peak_counts
                        Final_Report.loc[Pulse, "Dryness delay"] = TIME_delay

                    except Exception as err:
                        continue
            else:
                continue
    return Final_Report


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


## Prediction Supporting functions


def calculate_percentage_position(real_df, base_dict):
    for col in base_dict["base_min"].keys():
        real_df[col][0] = np.round(
            (real_df[col][0] - base_dict["base_min"][col])
            / (base_dict["base_max"][col] - base_dict["base_min"][col])
            * 100,
            1,
        )
    return real_df


def rank_columns(row):
    sorted_columns = row.sort_values(ascending=False).index.tolist()
    return pd.Series(
        sorted_columns,
        index=["Primary", "Secondary", "Tertiary", "Quaternary", "Quinary"],
    )


# Function to determine levels for each category
def assign_levels(row):
    row_set = {row["Primary"], row["Secondary"], row["Tertiary"]}

    # Define condition sets
    carb_low = {"Humid", "Cold", "Dry"}
    carb_high = {"Humid", "Heat", "Wind"}

    protein_low = {"Cold", "Humid", "Dry"}
    protein_high = {"Cold", "Heat", "Humid"}

    fat_low = {"Wind", "Dry", "Cold"}
    fat_high = {"Humid", "Heat"}

    # Assign values based on conditions
    carb = (
        "Low"
        if carb_low.issubset(row_set)
        else "High" if carb_high.issubset(row_set) else "Medium"
    )
    protein = (
        "Low"
        if protein_low.issubset(row_set)
        else "High" if protein_high.issubset(row_set) else "Medium"
    )
    fat = (
        "Low"
        if fat_low.issubset(row_set)
        else "High" if fat_high.issubset(row_set) else "Medium"
    )

    return pd.Series([carb, protein, fat])
