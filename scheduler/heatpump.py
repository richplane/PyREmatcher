# Heat pump model
# Based on regression analysis from Mitsubishi data
import numpy as np
import warnings

np.set_printoptions(precision=4)

class HeatPumpWarning(UserWarning):
    pass

class HeatPump(object):
    """ Models heat pump characteristics

    Uses COP to determining electricity consumption for a given heat output in a
    timestep. Hardcoded to characterise the Mitsubishi Ecodan PUHZ-HW140V
    monobloc system.
    """

    # Properties of water - could override for different working fluid!
    fluid_specific_heat = 0.0011444     # (4.186 / 3600) kWh / kgK
    timestep = 1.                       # hours

    # These may be adjusted according
    T_amb = 8.2 # External temperature (this is average)
    T_out = 60  # Target flow temperature

    # Mitsubishi provided max/nominal outputs, medium and minimum.
    nominal_power = 14    # 14kW
    max_flow_rate = 40    # kg/minute

    def _COP_coefficients(self) -> list:
        """ Get regression coefficients for current situation
        """

        # If ambient temperature is 2 degrees or below we will use defrost mode
        if (self.T_amb <= 2):
            return [
                3.254509975, 0.055426116, 0.007181906, -0.001549673,
                -0.000509163, -0.00051864
            ]
        else:
            return [
                5.526028912, 0.1251938, -0.000714286, -0.054584426,
                -3.17198e-05, -0.001400534
            ]



    def deliver_heat(self, T_in, mass) -> float:
        """ Determine electricity required to deliver heat for this timestep

        Calculates amount of heat required from input temperature (assumed
        constant throughout this timestep) and then determines electrical
        consumption from COP regression.

        Returns the amount of electrical energy used.

        Arguments:
            T_in {float} -- return temperature from thermal store
            mass {float} -- mass of water being heated (kg)
        """

        if (mass>(self.max_flow_rate*self.timestep*60)):
            warnings.warn('Mass flow exceeds specified range', HeatPumpWarning)


        # Calculate COP for these temperatures
        coefficients = self._COP_coefficients()

        COP = ( coefficients[0]
                + coefficients[1] * self.T_amb + coefficients[2] * self.T_amb**2
                + coefficients[3] * self.T_out + coefficients[4] * self.T_out**2
                + coefficients[5] * self.T_amb * self.T_out )

        heat_required = ( (self.T_out - T_in ) * mass * self.fluid_specific_heat)

        # 14kW is rated capacity (above -2degC)
        max_heat_deliverable = self.nominal_power * self.timestep  # kWh

        # Cope with floating point rounding errors here
        if ((heat_required - max_heat_deliverable) > 0.01):
            warnings.warn('Heat demand (' + str(heat_required)
                          + ' exceeds capacity', HeatPumpWarning)
            heat_required = max_heat_deliverable

        return heat_required / COP


    def heatable_mass(self, T_in) -> float:
        """Get the amount of mass we can process in this timestep

        Given a T_in, how much mass can we heat to T_out?

        Arguments:
            T_in {float} -- inflowing temperature
        """

        delta_T = self.T_out - T_in

        mass = ( self.nominal_power * self.timestep
                 / (self.fluid_specific_heat * delta_T))

        max_mass = self.max_flow_rate * 60 * self.timestep

        if mass>max_mass:
            return max_mass

        return mass
