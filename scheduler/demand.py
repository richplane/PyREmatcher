import pandas as pd
import sys
import os
from typing import Union, Tuple

class DemandModel(object):
    """Models the expected demand of one or more dwellings

    Starting with a 'standard' demand pattern this system builds up its own
    dataset, adding data points to build up an average profile of demand
    """

    def __init__(self, houses):
        """ Set up demand profiles based on housing stock

        For now just uses stored stock demand profiles.

        Arguments:
            houses {list} -- list of dicts, each containing house_type,
                year_built and qty. House_type is one of 'Detached',
                'Semi-detached','Mid-terrace','Detached bungalow',
                'Semi-detached bungalow','Ground-floor flat','Mid-floor flat',
                'Top-floor flat'
        """

        self.profiles, self.sigmas = self._get_standard_profile(houses)



    def _get_standard_profile(self, houses: list) -> Tuple[pd.DataFrame, pd.Series]:
        """Create an initial profile from the standard profiles

        Will create a summed profile based on the contents of the houses dict,
        and return this and the standard deviations for all temperatures

        Arguments:
            houses {list} -- list of dicts, each containing house_type,
                year_built and qty. House_type is one of 'Detached',
                'Semi-detached','Mid-terrace','Detached bungalow',
                'Semi-detached bungalow','Ground-floor flat','Mid-floor flat',
                'Top-floor flat'
        """

        profile_pickle = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            'demand-profiles.pkl'
        )
        standard_profiles = pd.read_pickle(profile_pickle)

        year_keys = {
            1983 : 'Pre 1983',
            2003 : '1983-2002',
            2008 : '2003-2007'
        }

        timesteps = [
            '00:00','01:00','02:00','03:00','04:00','05:00','06:00','07:00','08:00',
            '09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00',
            '18:00','19:00','20:00','21:00','22:00','23:00'
        ]

        profiles = pd.DataFrame(
            0.,
            index=timesteps,
            columns=range(-3,15)
        )

        #Go through the housing catalogue and total up the profiles
        for house_group in houses:

            age_key = (lambda x:x[0] if x else 'Post 2007')(
                list(
                    key for year,key in year_keys.items()
                        if house_group['year_built']<year
                )
            )

            profiles = profiles.add(
                standard_profiles.xs(
                    (house_group['house_type'], age_key),
                    axis=1
                ) * house_group['qty']
            )

        # Calculate standard deviations (sigmas)
        sigmas = pd.Series(0., index=profiles.columns)

        for temp in profiles.columns:
            sigmas[temp] = profiles[temp].std()

        return (profiles, sigmas)


    def get_daily_demand(self, average_temp: float) -> pd.Series:
        """Return demand for the given ambient temperature

        Returns the demand timeseries for the day

        Arguments:
            average_temp {temperature} -- average air temperature for the day
        """

        # Round the temperature to nearest integer
        average_temp = int(round(average_temp))

        # If above 14, use the 14 degree series (assumed to be HW only?)
        if average_temp > 14:
            average_temp = 14

        return self.profiles[average_temp]


    def get_hourly_demand(
            self,
            average_temp: float,
            hour: Union[str, int, pd.Timestamp]
        ) -> float:
        """Return demand for the given ambient temperature

        Returns the demand for a specified hour

        Arguments:
            average_temp {temperature} -- average air temperature for the day
            hour {int, string or pd.Timestamp} -- the hour of day
        """

        # Round the temperature to nearest integer
        average_temp = int(round(average_temp))

        # If above 14, use the 14 degree series (assumed to be HW only?)
        if average_temp > 14:
            average_temp = 14

        # Deal with whatever format our hour is in (we have a string index)
        if isinstance(hour, pd.Timestamp):
            hour = hour.strftime('%H:00')
        elif isinstance(hour, int):
            hour = "{:02d}:00".format(hour)

        return self.profiles[average_temp][hour]


    def predict_demand_with_margin(
            self,
            forecast
        ) -> pd.Series:
        """Returns a timeseries based on the current demand profile plus 1SD

        Using the timestamp index of the forecast, create a demand series based
        on the current demand profile.

        Arguments:
            forecast {pd.DataFrame} -- forecast with temperature series &
                datetime index
            scale {float} -- multiple to apply to profile to account for network
                losses & differing performance of building.
        """

        demand_series = pd.Series(0, index = forecast.index)

        for index, row in forecast.iterrows():
            hour = index.hour
            daily_average = row['daily_average']

            demand_series.loc[index] = (
                self.get_hourly_demand(daily_average, hour)
                + self._get_sigma(daily_average)
            )

        return demand_series


    def _get_sigma(self, daily_average: float) -> float:
        """ Get the standard deviation for the demand series

        Returns the stored standard deviation for the demand series for the
        given daily average temperature

        Argumments:
            daily_average {float} -- daily average for selecting the profile
        """

        sigma_index = int(round(daily_average))
        if sigma_index > 14:
            sigma_index = 14
        if sigma_index < -3:
            sigma_index = -3

        return self.sigmas[sigma_index]

