import pandas as pd
import requests
import os
import time
from requests.exceptions import HTTPError


class ForecastException(Exception):
    pass


class Forecaster(object):
    """Class for interacting with the DarkSky forecast API.

    For details on the API see
    """

    def __init__(
        self, API_key, latitude = 57.6568, longitude = -3.5818, tz='Europe/London'
    ):
        """Instantiate class with API key and lat/long (if used somewhere other
        than Findhorn)

        Arguments:
            API_key {string} -- active API key for communicating with DarkSky
            latitude {float or string} -- latitude
            longitude {float or string} -- longitude
        """

        self._API_key = API_key
        self.tz = tz

        if latitude:
            self.latitude = latitude

        if latitude:
            self.longitude = longitude



    def get_forecast(self, sim_start_time: pd.Timestamp = None) -> pd.DataFrame:
        """Get 48 hour forecast

        Combine API calls to DarkSky to make one DataFrame with
        meteorological data starting at the start of today and ending 48 hours
        time. If a start_time is supplied works from the start of that day
        to 48 hours after start_time

        Arguments:
            sim_start_time {pd.Timestamp} -- simulation start time; if not
                supplied start time is the current hour.
        """

        # First up - check we haven't already pulled one this hour

        start_time = sim_start_time or pd.Timestamp.now(tz=self.tz)

        # We can't get a forecast for a date in the future
        if (start_time>pd.Timestamp.now(tz=self.tz)):
            raise ForecastException('Cannot get forecast for future date')

        start_time = start_time.replace(minute=0, second=0)

        filename = ('forecasts/forecast-'
                    + start_time.strftime('%Y-%m-%d-%H%M')
                    + '.csv')

        if os.path.exists(filename):
            forecast = pd.read_csv(
                filename,
                index_col='datetime',
                parse_dates=['datetime'],
                dayfirst = True
            )

        # First call - start of today until end of tomorrow
        unixtime = int(time.mktime(start_time.timetuple()))

        try:
            json_response = self._call_darksky(str(unixtime))
        except Exception as err:
            raise ForecastException(f'Communication error occurred: {err}')

        past_data = pd.DataFrame.from_dict(json_response['hourly']['data'])

        past_data['datetime'] = pd.to_datetime(
            past_data['time'],
            unit = 's'
        )
        past_data.set_index(
            'datetime',
            inplace = True
        )
        past_data.index = past_data.index.tz_localize('UTC').tz_convert(self.tz)

        # Second call - might be another historical one...
        if not sim_start_time:

            # No, this is the standard forecast
            try:
                json_response = self._call_darksky()
            except Exception as err:
                raise ForecastException(f'Communication error occurred: {err}')

            # We have to do this differently for historic data as the DarkSky
            # API doesn't appear to be returning 2 day forecasts for historical
            # data as the docs indicate it should.

            future_data = pd.DataFrame.from_dict(json_response['hourly']['data'])
            future_data['datetime'] = pd.to_datetime(
                future_data['time'],
                unit = 's'
            )

            future_data.set_index(
                'datetime',
                inplace = True
            )

        else:

            # We need to do two more calls then.
            # We'll trim it later.

            second_day = (sim_start_time+pd.Timedelta(days=1))

            unixtime = int(time.mktime(second_day.timetuple()))
            try:
                json_response = self._call_darksky(str(unixtime))
            except Exception as err:
                raise ForecastException(f'Communication error occurred: {err}')

            day_2_data = pd.DataFrame.from_dict(json_response['hourly']['data'])
            day_2_data['datetime'] = pd.to_datetime(
                day_2_data['time'],
                unit = 's'
            )

            day_2_data.set_index(
                'datetime',
                inplace = True
            )

            third_day =  (sim_start_time+pd.Timedelta(days=2))

            unixtime = int(time.mktime(third_day.timetuple()))
            try:
                json_response = self._call_darksky(str(unixtime))
            except Exception as err:
                raise ForecastException(f'Communication error occurred: {err}')

            day_3_data = pd.DataFrame.from_dict(json_response['hourly']['data'])
            day_3_data['datetime'] = pd.to_datetime(
                day_3_data['time'],
                unit = 's'
            )

            day_3_data.set_index(
                'datetime',
                inplace = True
            )

            future_data = day_2_data.combine_first(day_3_data)

        future_data.index = future_data.index.tz_localize('UTC').tz_convert(self.tz)

        # Combine them together overwriting any rows that appear in both
        forecast = past_data.combine_first(future_data)

        # Add a daily average
        forecast['daily_average'] = 0

        # This only kicks in after today, so add today's in
        daily_average_col = forecast.columns.get_loc('daily_average')
        forecast.iloc[0:24, daily_average_col] = forecast['temperature'][0:24].mean()
        forecast.iloc[24:48, daily_average_col] = forecast['temperature'][24:48].mean()

        # Our data will be spanning 3 days. If we've used a forecast API call,
        # the last one will be incomplete so work that out on the average of
        # the last 24 hours in the forecast.
        forecast.iloc[48:, daily_average_col] = forecast['temperature'][-24:].mean()

        # Truncate the second forecast at the 48 hour mark
        two_days_later = start_time+pd.Timedelta(days=2)
        forecast = forecast.truncate(after = two_days_later)

        # Now lose the past - we only needed it for the daily averages.
        forecast = forecast.truncate(
            before=start_time
        )

        # Save our forecast to the local file that we looked for before
        forecast.to_csv(filename, float_format='%.3f')

        return forecast


    def _call_darksky(self, url_suffix: str = '') -> object:
        """Make call to DarkSky API

        Attempts a call to the API to retrieve a JSON object.

        Arguments:
            url_suffix {string} -- additional parameter to add to URL call
        """


        url = ( 'https://api.darksky.net/forecast/' + self._API_key
                      + '/' + str(self.latitude) + ',' + str(self.longitude)
                      + url_suffix
        );

        if url_suffix:
            url = url + ',' + url_suffix

        params = {
            'exclude' : 'currently,minutely,daily,alerts,flags',
            'units' : 'si'
        }

        response = requests.get(url = url, params = params)

        if response.status_code != 200 :
            # We couldn't communicate with the API - return the previous forecast
            raise ForecastException("DarkSky API did not respond. Check API key")

        return response.json()