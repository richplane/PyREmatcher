# Renewable generation at Findhorn
from windpowerlib import WindFarm
from windpowerlib import WindTurbine
from windpowerlib import WindTurbineCluster
from windpowerlib.turbine_cluster_modelchain import TurbineClusterModelChain
import pvlib
from pvlib.pvsystem import PVSystem
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.forecast import GFS
from pvlib.irradiance import disc
import pandas as pd
import numpy as np
import datetime
import scipy
import sys

# University computers can't install tables (bosc needs C++ compiler)
try:
    import tables
except ImportError:
    pass


class RenewablesException(Exception):
    pass


class LocalRE(object):

    forecast_height = 10 # for DarkSky API

    def __init__(
            self,
            wind_turbines: list = [],
            pv_arrays: list = [],
            latitude: float = 57.6568,
            longitude: float = -3.5818,
            altitude: float = 10,
            roughness_length: float = 0.15, # roughness length (bit of a guess)
            hellman_exp: float = 0.2
        ):
        """ Set up the renewable energy generation
        """

        # This needs to be repeated in every forecast
        self.roughness_length = roughness_length

        # Initialise empty forecast dataframe, just so nothing complains
        self.wind_forecast = pd.DataFrame()

        self.pv_forecast = pd.DataFrame()

        # Wind turbine(s)
        turbines = []

        for turbine in wind_turbines:
            turbines.append(
                {
                    'wind_turbine' : WindTurbine(
                        turbine['name'],
                        turbine['hub_height'],
                        nominal_power = turbine['nominal_power'],
                        rotor_diameter = turbine['rotor_diameter'],
                        power_curve = turbine['power_curve']
                    ),
                    'number_of_turbines' : turbine['qty']
                }
            )

        local_wind_farm = WindFarm(
            'Local windfarm',
            turbines,
            [latitude, longitude]
        )

        # TODO - check for learned local data & overwrite power_curve

        self.wind_modelchain = TurbineClusterModelChain(
            local_wind_farm,
            smoothing = False,
            hellman_exp = hellman_exp,
        )

        # Initialise PV models
        self.pv_location = Location(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude
        )

        # Now set up the PV array & system.
        cec_pv_model_params = pvlib.pvsystem.retrieve_sam('CECMod')
        sandia_pv_model_params = pvlib.pvsystem.retrieve_sam('SandiaMod')
        cec_inverter_model_params = pvlib.pvsystem.retrieve_sam('CECInverter')
        adr_inverter_model_params = pvlib.pvsystem.retrieve_sam('ADRInverter')

        self.pv_modelchains = {}

        for pv_array in pv_arrays:

            # Try to find the module names in the libraries
            if pv_array['module_name'] in cec_pv_model_params:
                pv_array['module_parameters'] = cec_pv_model_params[
                    pv_array['module_name']
                ]
            elif pv_array['module_name'] in sandia_pv_model_params:
                pv_array['module_parameters'] = sandia_pv_model_params[
                    pv_array['module_name']
                ]
            else:
                raise RenewablesException('Could not retrieve PV module data')

            # Do the same with the inverter(s)
            if pv_array['inverter_name'] in cec_inverter_model_params:
                pv_array['inverter_parameters'] = cec_inverter_model_params[
                    pv_array['inverter_name']
                ]
            elif pv_array['inverter_name'] in adr_inverter_model_params:
                pv_array['inverter_parameters'] = adr_inverter_model_params[
                    pv_array['inverter_name']
                ]
            else:
                raise RenewablesException('Could not retrieve PV module data')

            self.pv_modelchains[pv_array['name']] = ModelChain(
                PVSystem(**pv_array),
                self.pv_location,
                aoi_model='physical',
                spectral_model='no_loss'
            )


    def make_generation_forecasts(self, forecast):
        """ Makes generation forecast data from the supplied Dark Sky forecast

        Arguments:
            forecast {pandas.DataFrame} -- DarkSky originated forecast
        """

        self.pv_forecast = self._make_pv_forecast(forecast)
        self.wind_forecast = self._make_wind_forecast(forecast)


    def _make_pv_forecast(self, forecast)  -> pd.DataFrame:
        """Compile the forecast required for PV generation prediction

        Uses pvlib to generate solar irradiance predictions.

        Arguments:
            forecast {pandas.DataFrame} -- DarkSky originated forecast
        """

        # Annoyingly, the PV & wind libraries want temperature named differently
        pv_forecast = forecast.rename(
            columns={
                'temperature' : 'air_temp',
                'windSpeed' : 'wind_speed',
            }
        )

        # Use PV lib to get insolation based on the cloud cover reported here

        model = GFS()

        # Next up, we get hourly solar irradiance using interpolated cloud cover
        # We can get this from the clearsky GHI...

        if tables in sys.modules:
            # We can use Ineichen clear sky model (uses pytables for turbidity)
            clearsky = self.pv_location.get_clearsky(pv_forecast.index)

        else:
            # We can't, so use 'Simplified Solis'
            clearsky = self.pv_location.get_clearsky(
                pv_forecast.index, model='simplified_solis'
            )


        # ... and by knowledge of where the sun is
        solpos = self.pv_location.get_solarposition(pv_forecast.index)

        ghi = model.cloud_cover_to_ghi_linear(
            pv_forecast['cloudCover'] * 100, clearsky['ghi']
        )
        dni = disc(ghi, solpos['zenith'], pv_forecast.index)['dni']
        dhi = ghi - dni * np.cos(np.radians(solpos['zenith']))

        # Whump it all together and we have our forecast!
        pv_forecast['dni'] = dni
        pv_forecast['dhi'] = dhi
        pv_forecast['ghi'] = ghi

        return pv_forecast


    def _make_wind_forecast(self, forecast) -> pd.DataFrame:
        """Creates forecast needed for wind generation prediction

        Creates renamed multidimensional columns needed for the windpowerlib
        system.

        Arguments:
            forecast {pandas.DataFrame} -- DarkSky originated forecast
        """

        # Easiest to build multiindexes up one by one.
        columns_index = pd.MultiIndex.from_tuples(
            [
                ('wind_speed', 10), ('temperature', 10),
                ('pressure', 10), ('roughness_length', 0),
                ('wind_bearing', 10)
            ]
        )
        wind_forecast = pd.DataFrame(
            index=forecast.index.copy(),
            columns = columns_index
        )
        wind_forecast.loc[:,('wind_speed',10)] = forecast['windSpeed'].loc[:]
        wind_forecast.loc[:,('temperature',10)] = forecast['temperature'].loc[:]
        wind_forecast.loc[:,('pressure',10)] = forecast['pressure'].loc[:]
        wind_forecast.loc[:,('wind_bearing',10)] = forecast['windBearing'].loc[:]
        wind_forecast.loc[:,('roughness_length', 0)] = self.roughness_length

        return wind_forecast


    def predict_generation(self, reserved_wind_consumption) -> pd.DataFrame:
        """ Predict electricity generated from forecast

        Will use the timestamp index of the forecast property to estimate
        instantaneous electricity generation. Returns table giving amounts in
        kWh.

        Arguments:
            reserved_wind_consumption {float} - constant amount that is assumed
                to be required from wind generation to meet other local need
        """

        prediction = pd.DataFrame(index = self.pv_forecast.index.copy())

        # First up - PV

        # Create a total gen column of zeros
        prediction['PV_AC_TOTAL'] = 0

        for pv_array, pv_model in self.pv_modelchains.items():

            pv_model.run_model(prediction.index, self.pv_forecast)
            output_column_name = 'PV_AC_' + pv_array
            prediction[output_column_name] = pv_model.ac

            # Add to the total column
            prediction['PV_AC_TOTAL'] = prediction['PV_AC_TOTAL'] + pv_model.ac

        # Next - wind power.
        self.wind_modelchain.run_model(
            self.wind_forecast
        )

        prediction['WIND_AC'] = self.wind_modelchain.power_output

        # Convert everything into kWh
        prediction = prediction * 0.001

        prediction['available_wind'] = prediction['WIND_AC'] - reserved_wind_consumption
        prediction['available_wind'][prediction['available_wind']<0] = 0
        prediction['total'] = prediction['WIND_AC'] + prediction['PV_AC_TOTAL']
        prediction['surplus'] = prediction['available_wind'] + prediction['PV_AC_TOTAL']
        prediction['surplus'][prediction['surplus']<0] = 0

        return prediction
