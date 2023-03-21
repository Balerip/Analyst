import pandas as pd
from sklearn.metrics import r2_score

DEFAULT_FREQUENCY = "D"


def transform_to_nixtla_df(df, settings_dict, exog_vars=[]):
    """Transform dataframes into the specific format required by StatsForecast.

    Nixtla packages require dataframes to have the following columns:
        unique_id -> the grouping column. If multiple groups are specified then
        we join them into one name using a | char.
        ds -> the date series
        y -> the target variable for prediction

    You can optionally include exogenous regressors after these three columns, but
    they must be numeric.
    """
    nixtla_df = df.copy()
    # Transform group columns into single unique_id column
    if len(settings_dict["group_by"]) > 1:
        for col in settings_dict["group_by"]:
            nixtla_df[col] = nixtla_df[col].astype(str)
        nixtla_df["unique_id"] = nixtla_df[settings_dict["group_by"]].agg("|".join, axis=1)
        group_col = "ignore this"
    else:
        group_col = settings_dict["group_by"][0]

    # Rename columns to statsforecast names
    nixtla_df = nixtla_df.rename(
        {settings_dict["target"]: "y", settings_dict["order_by"]: "ds", group_col: "unique_id"}, axis=1
    )

    columns_to_keep = ["unique_id", "ds", "y"] + exog_vars
    return nixtla_df[columns_to_keep]


def get_results_from_nixtla_df(nixtla_df, model_args):
    """Transform dataframes generated by StatsForecast back to their original format.

    This will return the dataframe to the original format supplied by the MindsDB query.
    """
    return_df = nixtla_df.reset_index()
    return_df.columns = ["unique_id", "ds", model_args["target"]]
    if len(model_args["group_by"]) > 1:
        for i, group in enumerate(model_args["group_by"]):
            return_df[group] = return_df["unique_id"].apply(lambda x: x.split("|")[i])
    else:
        group_by_col = model_args["group_by"][0]
        return_df[group_by_col] = return_df["unique_id"]
    return return_df.drop(["unique_id"], axis=1).rename({"ds": model_args["order_by"]}, axis=1)


def infer_frequency(df, time_column, default=DEFAULT_FREQUENCY):
    try:  # infer frequency from time column
        date_series = pd.to_datetime(df[time_column]).unique()
        date_series.sort()
        inferred_freq = pd.infer_freq(date_series)
    except TypeError:
        inferred_freq = default
    return inferred_freq if inferred_freq is not None else default


def get_model_accuracy_dict(nixtla_results_df, metric=r2_score):
    """Calculates accuracy for each model in the nixtla results df."""
    accuracy_dict = {}
    for column in nixtla_results_df.columns:
        if column in ["unique_id", "ds", "y", "cutoff"]:
            continue
        model_error = metric(nixtla_results_df[column], nixtla_results_df["y"])
        accuracy_dict[column] = model_error
    return accuracy_dict


def get_best_model_from_results_df(nixtla_results_df, metric=r2_score):
    """Gets the best model based, on lowest error, from a results df
    with a column for each nixtla model.
    """
    best_model, current_accuracy = None, 0
    accuracy_dict = get_model_accuracy_dict(nixtla_results_df, metric)
    for model, accuracy in accuracy_dict.items():
        if accuracy > current_accuracy:
            best_model, current_accuracy = model, accuracy
    return best_model
