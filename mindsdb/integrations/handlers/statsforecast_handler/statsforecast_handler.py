import numpy as np
import dill
from mindsdb.integrations.libs.base import BaseMLEngine
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA

class StatsForecastHandler(BaseMLEngine):
    """
    Integration with the Nixtla StatsForecast library for
    time series forecasting with classical methods.
    """
    name = "statsforecast"


    def create(self, target, df, args, frequency="D"):
        time_settings = args["timeseries_settings"]
        assert time_settings["is_timeseries"], "Specify time series settings in your query"

        # Train model
        sf = StatsForecast(models=[AutoARIMA()], freq=frequency)
        sf.fit(df)

        ###### store model args and time series settings in the model folder
        model_args = sf.fitted_[0][0].model_
        model_args["target"] = target
        model_args["frequency"] = frequency
        model_args["predict_horizon"] = time_settings["horizon"]

        ###### persist changes to handler folder
        self.model_storage.file_set('model', dill.dumps(model_args))
    
    def predict(self, df, args):
        # Load fitted model
        model_args = dill.loads(self.model_storage.file_get('model'))
        fitted_model = AutoARIMA()
        fitted_model.model_ = model_args

        # StatsForecast can't handle extra columns - it assumes they're external regressors
        prediction_df = df[["unique_id", "ds", model_args["target"]]]
        sf = StatsForecast(models=[AutoARIMA()], freq="D", df=prediction_df)
        sf.fitted_ = np.array([[fitted_model]])
        forecast_df = sf.forecast(model_args["predict_horizon"])
        return forecast_df.reset_index(drop=True)