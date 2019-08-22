import scheduler
import pandas as pd
import numpy as np

# This file is a simulation script that run the Scheduler model repeatedly, simulating
#

# There are two different PV arrays
pv_arrays = [
    {
        'name' : 'Terrace',
        'surface_tilt' : 30,
        'surface_azimuth' : 163,
        'surface_type' : 'grass',
        'modules_per_string' : 10,
        'strings_per_inverter' : 2,
        'module_name' : 'SunPower_SPR_X22_360_COM',
        'inverter_name' : 'SolarEdge_Technologies_Ltd___SE6000__240V__240V__CEC_2018_'
    },
    {
        'name' : 'Studios block',
        'surface_tilt' : 34,
        'surface_azimuth' : 180,
        'surface_type' : 'grass',
        'modules_per_string' : 11,
        'strings_per_inverter' : 1,
        'module_name' : 'SunPower_SPR_X22_360_COM',
        'inverter_name' : 'SolarEdge_Technologies_Ltd___SE3300__240V__240V__CEC_2018_'
    }
]
# Uses SunPower X22 360W panels
# http://spectrum.sunpower.com/sites/default/files/uploads/resources/X22_360DC_RES_UK_AUS.pdf
# and SolarEdge CE3300 inverter
# https://www.solaredge.com/sites/default/files/se_compact_residential_solution_ds.pdf


wind_farm = [
    {
        'name' : 'Vestas V29',
        'hub_height' : 30,          # m
        'nominal_power' : 225e3,    # W
        'rotor_diameter' : 29,      # m
        'power_curve' : pd.DataFrame(
            data={
                'value': [ p * 1000 for p in [
                    0.0, 0.0, 2.1, 7.1, 20.5, 38.3, 61.9, 92.2, 128, 165,
                    196, 216, 223, 225, 225, 0, 0
                ]],  # in W
                'wind_speed': [
                    0.0, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
                    11.0, 12.0, 13.0, 14.0, 25.0, 26, 27
                ] # in m/s
            }
        ),
        'qty' : 3
    }
]

# Power curve source: Vestas V29 specification from
# http://www.orkneywind.co.uk/explore/Skea%20Brae/Vesta%20V29%20225%20Turbine.pdf


housing_stock = [
    {
        'house_type' : 'Semi-detached',
        'year_built' : 2019,
        'qty' : 2
    },
    {
        'house_type' : 'Mid-terrace',
        'year_built' : 2019,
        'qty' : 2
    },
    {
        'house_type' : 'Ground-floor flat',
        'year_built' : 2019,
        'qty' : 2
    },
    {
        'house_type' : 'Top-floor flat',
        'year_built' : 2019,
        'qty' : 2
    }
]

tank_characteristics = {
    'volume' : 1.55,          # 1550l
    'start_node_temps' : [40,43,45,55,57]
}

scale = 1.51 *0.18

# Hours to simulate
hours = 24

# Initialise and run our first hour
sch = scheduler.Scheduler(
    log_filename = 'multi-hour-test-run-' + str(hours) + '.csv',
    start_time = '2019-02-01',
    latitude = 57.6568,
    longitude = -3.5818,
    tz = 'Europe/London',
    altitude = 10,
    pv_arrays = pv_arrays,
    wind_farm = wind_farm,
    tank_characteristics = tank_characteristics,
    network_losses = 0.5,
    pumping_energy = 0.01,
    performance_factor = 0.18,
    reserved_wind_power = 123.4,     # kWh based on local consumption
    roughness_length = 0.15,     # bit of a guess
    hellman_exp = 0.2,
    housing_stock = housing_stock
)


# We'll run the top level tank model at 5 per hour also
tank_timestep_multiple = 5

sch.tank.timestep = 1. / tank_timestep_multiple
sch.heatpump.timestep = 1. / tank_timestep_multiple
debt_carried_forward = 0

# And we'll record the stochastised demands here
drawn_demands = []

time = sch.start_time

while hours>0:

    # It's one hour later.

    # Let's get the stochastised demand for the hour we just had

    # The profiled demand - we'll need the temperature first
    average_temp = sch._forecast.loc[time, 'daily_average']
    profiled_demand = (sch.demands.get_hourly_demand(average_temp, time)
                       * scale)

    # Let's vary this by a random amount with the same standard deviation as the
    # daily profile
    sigma = sch.demands._get_sigma(average_temp) * scale
    randomised_demand = np.random.normal(profiled_demand, sigma)

    # Obviously we can't have a negative demand so in this case we
    # will carry a debt forward
    randomised_demand -= debt_carried_forward
    if randomised_demand<0:
        debt_carried_forward = -randomised_demand
        randomised_demand = 0
    else:
        debt_carried_forward = 0

    # remember this!
    drawn_demands.append(randomised_demand)

    # Were we planning to heat in this timestep?
    heat_pump_active = sch._schedule.iloc[0]

    tank_substep_demand = randomised_demand / tank_timestep_multiple

    # Now let's run the scheduler's own tank model.
    # We aren't fussed about reporting the energy useage as that will already
    # have been simulated
    for substep in range(0,tank_timestep_multiple):

        try:
            # Draw demand from the tank
            tank_output_mass = sch.tank.draw_load(tank_substep_demand)

            # Are we heating?
            if heat_pump_active:

                # We'll try to.
                mass_to_heat = sch.heatpump.heatable_mass(
                    sch.tank.get_hp_draw_temp()
                )

                Q_in = sch.tank.inject_heat(
                    mass_to_heat,
                    sch.heatpump.T_out
                )

            sch.tank.process_timestep()

        except HotWaterTank.TankWarning as e:
            # The tank has entirely circulated in this timestep (bad news)
            log_file.write(str(e) + '\n')
        except:
            log_file.close
            raise


    # Now we should have our tank ready to run another set of simulations at the
    # next timestep
    time = time + pd.Timedelta(hours=1)

    # We have to push forward the hands of time
    hours -= 1

    sch.run_model(time)

# Let's record this in the CSV
log_file = open(sch.log_filename,'a')
log_file.write('DEMANDS SIMULATED\n')
for demand in drawn_demands:
    log_file.write(str(demand)+'\n')
log_file.close()
