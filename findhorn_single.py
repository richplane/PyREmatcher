import scheduler
import pandas as pd

# This file contains all the parameters needed to characterise Findhorn.

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

sch = scheduler.Scheduler(
    log_filename = 'jun-test-run.csv',
    start_time = '2019-06-01',
    latitude = 57.6568,
    longitude = -3.5818,
    tz = 'Europe/London',
    baseline_scenario = [0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
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