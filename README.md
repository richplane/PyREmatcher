# PyREmatcher
A Model Predictive Controller algorithm for load shifting in a district heat network to match local renewables

Model Predictive Control (MPC) is a method of intelligently controlling an unpredictable system to meet multiple objectives. The scheduler module is an MPC algorithm built in Python to control a small district heat network with thermal storage in such as way as to shift load to periods of good local renewable generation.

The characteristics of the heat network and local renewable generation are based on a development at Findhorn, an eco-village on the North Moray coast. Significant variation of the network is possible with the module as presented, but alterations to the heat pump characteristics would require the codebase to be forked.

This system was developed by Richard Lane for my MSc thesis in [Renewable Energy Systems and the Environment at the University of Strathclyde](https://www.strath.ac.uk/courses/postgraduatetaught/sustainableengineeringrenewableenergysystemstheenvironment/). When reviewed, my thesis should be available on the [Energy Systems Research Unit website](https://www.strath.ac.uk/research/energysystemsresearchunit/courses/individualprojects/).


## Requirements

This system requires the pre-installation of [pvlib](https://pypi.org/project/pvlib/) and [windpowerlib](https://pypi.org/project/windpowerlib/0.0.4/), as well as Pandas, SciPy and NumPy. [PyTables](https://pypi.org/project/tables/) is also highly recommended - the system will function without this but the PV generation estimates will be affected.

The system relies on communicating with the [Dark Sky API](https://darksky.net/dev) - an API key is needed to achieve this. The Scheduler will look for this in in a file named `dark_sky_api_key.txt` its current working directory upon instantiation.

## Useage

Two demonstration scripts are provided - findhorn_single.py and findhorn_multiple.py. These show how a template residential demand load can be compiled and local renewable generation capacity can be characterised. Each method is fully commented with parameters.

The following code will instantiate the Scheduler class with three local wind turbines, a PV array, two semi-detatched houses and a 1,000 litre (1m³) hot water tank.

    import scheduler

    sch = scheduler.Scheduler(
        latitude = 57.6568,
        longitude = -3.5818,
        tz = 'Europe/London',
        altitude = 10,
        pv_arrays = [{
            'name' : 'PV array name',
            'surface_tilt' : 30,
            'surface_azimuth' : 163,
            'surface_type' : 'grass',
            'modules_per_string' : 10,
            'strings_per_inverter' : 2,
            'module_name' : '', # name as in CEC/Sandia database
            'inverter_name' : '' # name as in CEC/ADR database
        }],
        tank_characteristics = {
            nodes: 5,
            volume: 1,  # m3
        },
        wind_farm = [{
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
        }],
        roughness_length = 0.15,
        hellman_exp = 0.2,
        housing_stock = [{
            'house_type' : 'Semi-detached',
            'year_built' : 2019,
            'qty' : 2
        }]
    )

