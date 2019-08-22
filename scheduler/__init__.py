from . import generation
from . import heatpump
from . import hotwatertank
from . import demand
from . import simulator
from . import forecast
import warnings
import pandas as pd
import numpy as np
from typing import Union, Tuple


class SchedulerError(Exception):
    pass

class Scheduler(object):
    """Class to perform the scheduling of heat pump operation

    Should be instantiated with keyword arguments setting the following
    local conditions: latitude, longitude, tz (timezone),
    altitude, housing_stock, minimum_temperature

    Optionally also include baseline_scenario, network_losses, pumping_energy,
    performance_factor, reserved_wind_power, pv_arrays, wind_farm,
    tank_characteristics, roughness_length, hellman_exp,
    roughness_length
    """

    # Everything we need to know about our setup should be set here:
    latitude = 57.6568
    longitude = -3.5818
    tz = 'Europe/London'
    altitude = 10

    # Baseline daily heating schedule for comparison: 3am-5am every morning
    baseline_scenario = None

    # Characteristics of DHS (as proportion of demand)
    network_losses = 0.5
    pumping_energy = 0.01
    performance_factor = 1

    housing_stock = []

    # Renewable energy generation
    wind_farm = []
    reserved_wind_power = 0     # kWh based on local consumption
    pv_arrays = []
    roughness_length = 0.15
    hellman_exp = 0.2

    # Comfort condition - minimum network temperature
    minimum_temperature = 38

    tank_characteristics = {

    }

    # That's all the local condition data we want.


    # This will hold our on/off schedule
    _schedule = []

    # This will hold our forecast, but keep it empty for now
    _forecast = None

    # This is where we will output our logs (set by constructor)
    log_filename = None

    # If this is set in the constructor then we aren't living in the present
    start_time = None


    def __init__(
            self,
            **kwargs
        ) :
        """Set up the generation resources and demand model

        Keyword arguments::
            log_filename {string} -- a filename to log the simulation to
            start_time {string} -- start time for the simulation
            'latitude' {float}
            'longitude' {float}
            'tz' {string} -- (timezone)
            'altitude' {float}
            'housing_stock' {list} -- see Demand module
            'minimum_temperature' {float} -- the comfort condition
            'baseline_scenario' {list} -- daily schedule for comparison, if
                desired
            'network_losses' {float} -- network losses as multiple of demand
            'pumping_energy' {float} -- as multiple of demand
            'performance_factor' {float} -- as multiple of template demand profile
            'reserved_wind_power' {float} -- absolute constant value for margin
                to determine surplus
                'pv_arrays', 'wind_farm', 'hellman_exp', 'roughness_length',
                 (see generation module),
                'tank_characteristics' (see Tank module)
        """

        # Load all the local conditions into the class
        kwargs_to_load = ['latitude', 'longitude', 'tz',
            'altitude', 'housing_stock', 'minimum_temperature',
            'baseline_scenario', 'network_losses', 'start_time',
            'pumping_energy', 'performance_factor', 'reserved_wind_power',
            'pv_arrays', 'wind_farm', 'tank_characteristics', 'hellman_exp',
            'roughness_length', 'log_filename']

        for key in kwargs_to_load:
            if kwargs.get(key):
                setattr(self, key, kwargs.get(key))

        # Look for our API key
        try:
            with open('darksky_api_key.txt', 'r') as f:
                API_key = f.read()
                f.close()
        except Exception as err:
            # And that's pretty much the end of that.
            raise SchedulerError('DarkSky API key could not be loaded')

        self.weatherman = forecast.Forecaster(
            API_key, self.latitude, self.longitude, self.tz
        )
        self.demands = demand.DemandModel(self.housing_stock)

        # Create a five node, 750L tank
        self.tank = hotwatertank.Tank(5, **self.tank_characteristics)

        # Instantiate our heat pump
        self.heatpump = heatpump.HeatPump()

        # Instantiate our renewable energy sources
        self.renewables = generation.LocalRE(
            wind_turbines = self.wind_farm,
            pv_arrays = self.pv_arrays,
            latitude = self.latitude,
            longitude = self.longitude,
            altitude = self.altitude,
            roughness_length = self.roughness_length,
            hellman_exp = self.hellman_exp,
        )

        # Did we get given a start time for this simulation using
        # historic/future data?
        if self.start_time:
            if isinstance(self.start_time, str):
                self.start_time = pd.Timestamp(self.start_time, tz=self.tz)
        else:
            self.start_time = pd.Timestamp.now(tz=self.tz)

        self.simulator = simulator.Simulator(self.heatpump)

        # Clear the logfile
        if self.log_filename:
            logfile = open(self.log_filename, 'w')
            logfile.write('Scheduler instantiated at '+str(pd.Timestamp.now()) + '\n')
            logfile.close()


        # Plan our first hour!
        self.run_model(self.start_time)


    def _signal_heatpump(self, active, time:pd.Timestamp):
        """Send control signal to heatpump

        To be run every control timestep. Reads schedule and sends signal

        Arguments:
            active {bool} -- whether the heatpump is active or not
            time {pd.Timestamp} -- the time we're acting for
        """

        if active:
            print(f"At time {time} the heatpump is ON")
        else:
            print(f"At time {time} the heatpump is OFF")



    def run_model(self, start_time: pd.Timestamp = None):
        """Create schedule

        Updates forecast, predicts surplus from generation and demand and runs
        scenarios to find best way of meeting comfort criteria.

        Arguments:
            start_time {pd.Timestamp} -- start time if running on historical
                data or a future time within current data set
        """

        # Open our log file (we reopen it every hour so we can read it between)
        log_file = open(self.log_filename,'a+') if self.log_filename else None

        if log_file:
            log_file.write('Simulation starting ' +
                (str(start_time) if start_time else 'for current hour') + '\n')

        # 1. Get forecast

        try:
            forecast = self.weatherman.get_forecast(start_time)
            self._forecast = forecast
        except Exception as err:
            if not self._forecast:
                # We don't have a forecast from last time.
                # - so We can't operate at this timestep
                raise SchedulerError('Cannot get first forecast.')
            else:
                # Shave an hour off the previous forecast and run using
                # shortened horizon
                warnings.warn('Could not retrieve forecast at this timestamp, using previous')
                self._forecast = self._forecast.drop(self._forecast.index[0])

        # 2. (in future work:) Determine demand used since previous timestep
        #    & learn from it

        # 3. Predict surplus

        self.renewables.make_generation_forecasts(self._forecast)

        self.generation = self.renewables.predict_generation(
            self.reserved_wind_power
        )

        scale = ( (1+self.network_losses + self.pumping_energy)
                  * self.performance_factor)

        self._demand = (
            self.demands.predict_demand_with_margin(self._forecast) * scale
        )

        # Pull out the surplus/shortfall series here (on the same index)
        self._surplus = self.generation['surplus']

        # Repeat the following until we meet comfort criteria

        # 4. Generate scenario - at first 'no heating'
        self._schedule = pd.Series(0, index=self._surplus.index)

        comfort_conditions_met = False

        # Repeat until we have an outcome
        while True:

            print("Running scenario: "
                  + str(self._schedule[self._schedule==1].size)
                  + "hours of heating")

            # 5. Simulate next 48 hours with the current schedule
            elec_used, elec_imported, failure_time = self.simulator.run_simulation(
                self.tank,
                forecast,
                self._demand,
                self._schedule,
                self._surplus,
                log_file
            )

            # Two ways out of this endless loop - either we succeeded...
            if not failure_time:
                break

            # ...or we ran out of hours to add heating in
            print("Scenario has failed at ", str(failure_time))

            # Repeat 4 - generate new schedule by adding an hour's heating
            added_another_hour = self._add_hour(failure_time)

            if not added_another_hour:
                # We had no more hours to add - time to give up!
                break

        # If we are heating all the time, that's gotta be worth a warning.
        if failure_time:
            warnings.warn('Could not maintain comfort conditions even with continuous heating')

        # Report scenario
        time = start_time or pd.Timestamp.now(tz=self.tz)

        import_percent = (100 * (elec_imported / elec_used)) if elec_used else 100

        run_notice = (f"At time {time} the optimal scenario has "
                      + f"{self._schedule.sum()} hours of heating, requiring "
                      + f"{elec_used}kWh of electricity of which "
                      + f"{elec_imported}kWh ({import_percent}%) was imported")
        print(run_notice)
        print(self._schedule)

        if self.baseline_scenario:

            if log_file:
                log_file.write(run_notice + '\n')
                log_file.write('--- Baseline scenario ---\n')

            # Calculate baseline scenario for the current scenario timeseries... IN ONE LINE!
            baseline_scenario = pd.Series(
                [ self.baseline_scenario[time.hour] for time in forecast.index],
                index=forecast.index
            )

            # Simulate baseline scenario
            elec_used, elec_imported, failure_time = self.simulator.run_simulation(
                self.tank,
                forecast,
                self._demand,
                baseline_scenario,
                self._surplus,
                log_file
            )

            if failure_time:
                print("Basline scenario has failed at ", str(failure_time))

            import_percent = (100 * (elec_imported / elec_used)) if elec_used else 100

            baseline_notice = (f"At time {time} the baseline scenario has "
                               + f"{baseline_scenario.sum()} hours of "
                               + f"heating, requiring {elec_used} kWh of "
                               + f"electricity of which {elec_imported}kWh "
                               + f"({import_percent}%) was imported")

            print(baseline_notice)

            if log_file:
                log_file.write(baseline_notice + '\n')

        if log_file:
            log_file.close()

        # Now send the signal to the heatpump for the first hour
        self._signal_heatpump(self._schedule.iloc[0], time)



    def _add_hour(
            self,
            failure_time: pd.Timestamp = None
        ) -> bool:
        """Add an hour to the schedule that isn't already in it.

        Looks for the hour with the highest surplus before the current failure
        time that isn't in the schedule already. Returns True on success, False
        if there are no more hours to add.

        Arguments:
            priority_hours {pd.Series} -- Descending sorted
        """

        # Order our surplus descendingly
        priority_hours = self._surplus.truncate(
            after=failure_time
        ).sort_values(
            ascending = False
        ).index.to_series(
            keep_tz = True
        )

        # Get a list of 'on' hours:
        on_hours = self._schedule[self._schedule==1].index.to_series(
            keep_tz = True
        )

        remaining_hours = priority_hours[~priority_hours.isin(on_hours)]

        if remaining_hours.size == 0:
            return False

        # Find our highest priority hour that isn't in the on_hours series.
        to_add = remaining_hours.iloc[0]

        self._schedule[to_add] = 1

        return to_add
