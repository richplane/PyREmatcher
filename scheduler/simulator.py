from . import hotwatertank
import pandas as pd
import numpy as np
import copy
from typing import Union, Tuple, TextIO

class Simulator(object):

    def __init__(self,
            heatpump,
            minimum_temperature = 38,
            tank_timestep_multiple = 5
        ):
        """Set up the simulator with things that won't change

        Arguments:
            heatpump {object} -- the heatpump to be used in the simulation
        """
        self.minimum_temperature = minimum_temperature
        self.heatpump = copy.deepcopy(heatpump)
        self.tank_timestep_multiple = tank_timestep_multiple


    def run_simulation(
            self,
            tank: object,
            forecast: pd.DataFrame,
            demand: pd.Series,
            schedule: pd.Series,
            surplus: pd.Series,
            log_file: TextIO = None
        ) -> Tuple[float, float, Union[pd.Timestamp, bool]]:
        """Simulate the current heating schedule

        Run the current heating schedule forward to see if we breach the comfort
        criteria before we run out of forecast road.

        Arguments:
            tank {object} -- the current hot water tank model (for initial
                conditions)
            forecast {pd.DataFrame} -- the forecast weather conditions from
                this time (only temperature is needed)
            demand {pd.Series} -- the anticipated heating demand
            schedule {pd.Series} -- the planned heating schedule
            surplus {pd.Series} -- the anticipated generation surplus
            log_file {typing.TextIO} -- the (open) file to log to (optional)
        """


        # If we're logging, set up the column headers
        if log_file:
            data_columns = []
            for n in range(0,tank.nodes):
                data_columns.append('Tank node #' + str(n))

            data_columns = data_columns + [
                'time', 'temperature', 'demand (kWh)', 'energy stored (kWh)',
                'tank draw to load (kg)', 'heat injected (kWh)',
                'energy surplus (kWh)', 'electricity used (kWh)',
                'tank draw to heatpump (kg)',
                'heatpump active'
            ]

            log_file.write(','.join(str(x) for x in data_columns))
            log_file.write('\n')

        # We don't want to lose the state of the actual tank
        self.tank = copy.deepcopy(tank)

        self.tank.timestep = 1. / self.tank_timestep_multiple
        self.heatpump.timestep = 1. / self.tank_timestep_multiple

        total_elec_in = 0.
        total_elec_imported = 0.

        # Let's set off for the future
        for index, row in forecast.iterrows():

            # Let the tank and the HP know the ambient temp
            self.tank.T_amb = forecast.loc[index,'temperature']
            self.heatpump.T_amb = forecast.loc[index,'temperature']

            # Now run the tank timesteps
            mass_heated_this_timestep = 0.
            elec_this_timestep = 0.
            Q_in_this_timestep = 0.

            tank_substep_demand = demand[index] / self.tank_timestep_multiple

            for substep in range(0,self.tank_timestep_multiple):

                try:
                    # Draw demand from the tank
                    tank_output_mass = self.tank.draw_load(tank_substep_demand)

                    # Are we heating?
                    if schedule[index]:

                        # We'll try to.
                        mass_to_heat = self.heatpump.heatable_mass(
                            self.tank.get_hp_draw_temp()
                        )

                        Q_in = self.tank.inject_heat(
                            mass_to_heat,
                            self.heatpump.T_out
                        )

                        # If we did any heating, add the power
                        if Q_in:
                            Q_in_this_timestep += Q_in

                            # Work out the cost of this
                            elec_in = self.heatpump.deliver_heat(
                                self.tank.get_hp_draw_temp(),
                                mass_to_heat
                            )

                            mass_heated_this_timestep += mass_to_heat
                            elec_this_timestep += elec_in

                    self.tank.process_timestep()

                except HotWaterTank.TankWarning as e:
                    # The tank has entirely circulated in this timestep (bad news)
                    if log_file:
                        log_file.write(str(e) + '\n')
                    return elec_this_timestep, total_elec_imported, index
                except:
                    if log_file:
                        log_file.close
                    raise

            total_elec_in += elec_this_timestep

            # Are we importing energy this timestep?
            if (surplus[index]>0):
                # We have a surplus! Only import if it doesn't cover the need
                if (surplus[index]<elec_this_timestep):
                    total_elec_imported += (elec_this_timestep - surplus[index])
            else:
                # no surplus. Import all
                total_elec_imported += elec_this_timestep


            # If we're loggin, log this timestamp
            if log_file:
                data = self.tank.node_temps.copy()
                data = np.append(
                    data,
                    [
                        str(index),
                        forecast.loc[index,'temperature'],
                        demand[index],
                        self.tank.energy_stored(),
                        tank_output_mass,
                        Q_in_this_timestep,
                        surplus[index],
                        elec_this_timestep,
                        mass_heated_this_timestep,
                        schedule[index]
                    ]
                )
                log_file.write(','.join(str(x) for x in data))
                log_file.write('\n')

            if self.tank.get_outflow_temp() < self.minimum_temperature:
                # We have failed

                if (log_file):
                    log_file.write('COMFORT CONDITION BREACHED\n')

                return total_elec_in, total_elec_imported, index

        # We succeeded.
        return total_elec_in, total_elec_imported, False