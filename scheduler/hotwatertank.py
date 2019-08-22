# Hot water tank model
# Based on DEVELOPMENT OF AN ENERGY STORAGE TANK MODEL (Buckley, R 2012)

import numpy as np
import math as maths
from typing import Tuple

np.set_printoptions(precision=4)

class TankError(Exception):
    pass

class TankWarning(Exception):
    pass


class Tank(object):

    # Temperature surrounding the tank. Assume indoors, can be changed
    T_amb = 20.0

    # Properties of water - can override for different working fluid
    fluid_specific_heat = 0.0011444     # (4.186 / 3600) # kWh / kgK
    fluid_density = 998                 # kg/m^3
    fluid_conductance = 0.00064         # thermal conductivity of water in kW/mK

    # Our system will be aiming for a fixed flow/return temperature, which is:
    load_supply_temp = 50.0
    load_return_temp = 20.0

    timestep = 1                        # hours

    def __init__(self, nodes, **characteristics):
        """Initialise the tank

        Set the physical characteristics from the supplied dictionary

        Arguments:
            nodes -- the number of nodes to model (at least 3)
            physical_chacteristics {dict} -- as many physical characteristics
            as you feel like supplying out of: diameter, height,
            wall_U_value, volume (litres)
        """
        if nodes<3:
            raise TankError('Cannot model fewer than 3 nodes')

        self.nodes = nodes

        defaults = {
            'wall_U_value'  : 0.00011,      # U-value of tank wall in kW/m2K
            'diameter'      : 0.75,
            'height'        : 1.25,
            'start_node_temps' : [50.0]*nodes,
            'volume'        : 0.55,             # 0.55m3 = 550l
            'outflow_node'  : (nodes-1),        # Defaults to top node
            'heater_draw_node' : 0
        }

        for key, value in defaults.items():
            setattr(self, key, characteristics.get(key, value))

        # If we set a volume, set the dimensions from this
        if 'volume' in characteristics:
            # Aspect ratio of tank - pretty much the higher the better (Armstrong 2015)
            # Using AR = 3 -> H = 3D -> V = 3xD^3*pi / 4
            self.diameter = ( ( 4 * characteristics['volume'] / (3*maths.pi))
                              ** (1/3) )
            self.height = 3 * self.diameter
            self._node_area = ((self.diameter /2 ) ** 2 ) * maths.pi

        else:
            self._node_area = ((self.diameter /2 ) ** 2 ) * maths.pi
            self.volume = self._node_area * self.height

        # Some calculated values
        self._node_volume = self.volume/self.nodes
        self._mass = self.volume * self.fluid_density
        self._node_mass = self._mass / self.nodes
        self._node_surface = self.diameter * maths.pi * self.height / self.nodes
        self._node_height = self.height/self.nodes

        # Initialise temperature array.
        # Nodes are numbered from bottom (0) to top (self.nodes-1)
        self.node_temps = np.array(self.start_node_temps)

        # Mass flows into and out of tank
        self.input_masses = np.array([0.0]*self.nodes)
        self.input_temps = np.array([0.0]*self.nodes)
        self.output_masses = np.array([0.0]*self.nodes)


    def _reinject(self, T_in, mass):
        """Inject fluid into one or more node(s)

        Apportions <mass> kg of fluid at T_in deg C between as many nodes as are
        required. Assumes a perfect low velocity manifold which prevents any
        mixing

        Arguments:
            mass {float} -- mass of inflowing fluid
            T_in {float} -- temperature of inflowing fluid
        """
        T_in = float(T_in)

        if T_in >= self.node_temps[self.nodes-1]:
            # Hotter than the top, inject here!
            target_node = self.nodes-1
        else:
            for i in range(self.nodes-1, 0, -1):
                if (T_in>=self.node_temps[i]):
                    target_node = i
            else:
                # We didn't find any node hot enough to float over our
                # input - inject at bottom
                target_node = 0

        # Distribute the mass!
        injecting_node = target_node

        remaining_mass = mass

        while (remaining_mass>0) :

            # Stick it into this node! But hist - there may be mass already
            # entering this node, so let's mix them and then see how
            # much mass there is left over (on a first-come-first served basis)

            if ( (remaining_mass + self.input_masses[injecting_node])
                 > self._node_mass):
                # Annoyingly we have mass left over. How much can go in here?
                mass_for_this_node = ( self._node_mass
                                        - self.input_masses[injecting_node])
            else:
                # Hooray, we can absorb all the mass here!
                mass_for_this_node = remaining_mass

            # How much left over?
            remaining_mass -= mass_for_this_node

            # Mix the two flows to get the resultant temperature
            self.input_temps[injecting_node] = self._mix_temps(
                [self.input_temps[injecting_node], self.input_masses[injecting_node]],
                [T_in, mass_for_this_node]
            )
            self.input_masses[injecting_node] += mass_for_this_node

            if (remaining_mass>0):

                # Now decide which is our next node
                if (injecting_node>0 and injecting_node <= target_node):
                    # We're iterating downwards & there's still space to go - so
                    # inject to the node below!
                    injecting_node -= 1
                elif (injecting_node == 0 and target_node < self.nodes-1):
                    # we've reached the bottom of the tank, so we're overflowing
                    # above the original injection node now
                    injecting_node = target_node+1
                elif (injecting_node>target_node
                      and injecting_node < self.nodes-1):
                    # We're iterating upwards and there's still space to go - so
                    # inject to the node above!
                    injecting_node += 1
                else:
                    # Uh oh, we've injected the ENTIRE TANK in this timestep.
                    # Where do we go from here?
                    raise TankWarning('Entire tank has circulated within one timestep'
                                       + str(mass) + 'kg ' + str(self.input_masses))


    def _mix_temps(self, *args):
        """Get temperature of mixed fluids

        Given any number of lists (each consisting of temperature,mass),
        calculate the resulting temperatures of the mix

        Arguments:
            *args {array} -- a list of [temperature,mass] for each fluid
        """

        total_notenergy = 0.0    # product of temperature and mass is not energy
        total_mass = 0.0

        for fluid in args :
            total_notenergy += fluid[0]*fluid[1]
            total_mass += fluid[1]

        resultant_T = total_notenergy/total_mass

        return resultant_T


    def inject_heat(self, mass_in: float, T_in: float):
        """Inject heat in this timestemp

        Inject mass_in kg of water at temperature T_in into the tank, drawing
        fluid from the tank's outflow node and reinjecting it in using the
        perfect manifold. Returns the amount of energy thus absorbed.

        Arguments:
            mass_in -- enery being injected (kWh) in this timestep
            T_in -- temperature at which the fluid is returning
        """

        # First up, can we actually heat at all?
        if ((T_in - self.get_hp_draw_temp())<5):
            # We have a smaller than 5 degree difference, so let's not
            return 0

        # Next up, work out how much fluid we need
        delta_T = T_in - self.get_hp_draw_temp()

        Q_in = mass_in * self.fluid_specific_heat * delta_T

        self.output_masses[self.heater_draw_node] += mass_in

        # Reinject this lot back in....
        self._reinject(T_in, mass_in)

        return Q_in


    def draw_load(self, Q_out):
        """Draw out some energy from a node in this timestep

        Returns the amount of mass flowing to provide this load.

        Arguments:
            Q_out {float} -- the energy to extract (kWh)
         """

        if (Q_out == 0):
            # We'll get a divide by zero error if we try this
            return

        delta_T = self.load_supply_temp - self.load_return_temp
        tank_delta = self.get_outflow_temp() - self.load_return_temp

        # Is our top node hot enough?
        if self.get_outflow_temp() > self.load_supply_temp:

            # Yes! So we'll mix with the return to work out the mass
            mass_in_network = float(Q_out) / (delta_T * self.fluid_specific_heat)

            # How do we make the temperature?
            mass_from_tank = (mass_in_network * delta_T / tank_delta)
        else:
            # No! We're supplying below our target temperature (boo!) so we're
            # going to need more mass
            mass_from_tank = float(Q_out) / (tank_delta * self.fluid_specific_heat)

        # Return fluid into whichever node(s) want(s) it
        self._reinject(self.load_return_temp, mass_from_tank)

        self.output_masses[self.outflow_node] += mass_from_tank

        return mass_from_tank


    def energy_stored(self) -> float:
        """Get energy currently in tank

        Returns energy stored in kWh. Not all the energy will be extractable,
        natch.
        """

        energy = 0.0
        for n in range(0,self.nodes):
            energy += ( self.node_temps[n]          # should be in K really
                        * self._node_mass
                        * self.fluid_specific_heat
            )

        return energy


    def process_timestep(self):
        """Perform the timestep, obtaining the next set of temperatures
        """

        # flow up into next node - zero at lowest node
        mass_upflow_in = 0.0

        # Compose our matrices then
        A = np.array([[0.0]*self.nodes]*self.nodes)
        C = np.array([0.0]*self.nodes)

        for n in range(0, self.nodes):

            # Work out how much mass is spilling up out of this node
            mass_upflow_out = ( mass_upflow_in
                                + self.input_masses[n]
                                - self.output_masses[n] )

            # Check: are we injecting more mass into this node than the node
            # can contain?
            if (self.input_masses[n]>self._node_mass):
                print("ALERT: external flow into node {:d} is greater then the node mass".format(n))

            # Exposed node surface (loss to environment) is different for
            # top & bottom nodes
            loss_area = self._node_surface

            # Top and bottom node special cases
            if n==0 or n==(self.nodes-1):
                loss_area += self._node_area

            A[n,n] = ( (self._node_mass * self.fluid_specific_heat / self.timestep)
                       + self.output_masses[n] * self.fluid_specific_heat
                       + ( self.fluid_conductance
                             * self._node_area
                             / self._node_height)
                       + self.wall_U_value * loss_area )

            # Slightly different for top & bottom nodes:
            if n>0 and n<self.nodes-1:
                A[n,n] += ( self.fluid_conductance
                             * self._node_area
                             / self._node_height)

            if (mass_upflow_out > 0):
                A[n,n] += mass_upflow_out * self.fluid_specific_heat

            if (mass_upflow_in < 0):
                A[n,n] -= mass_upflow_in * self.fluid_specific_heat

            if (n>0) :
                A[n,n-1] = -(self.fluid_conductance * self._node_area
                                  / self._node_height )
                if (mass_upflow_in > 0):
                    A[n,n-1] -= mass_upflow_in * self.fluid_specific_heat

            if (n<self.nodes-1):
                A[n,n+1] = - (self.fluid_conductance * self._node_area
                                  / self._node_height )

                if (mass_upflow_out<0):
                    A[n,n+1] += mass_upflow_out * self.fluid_specific_heat

            C[n] = ( ( self._node_mass * self.fluid_specific_heat
                       * self.node_temps[n] / self.timestep )
                     + self.wall_U_value * loss_area * self.T_amb
                     +  ( self.input_masses[n] * self.fluid_specific_heat
                          * self.input_temps[n] )
            )

            # And get ready for the next node
            mass_upflow_in = mass_upflow_out

        # Sanity check!
        if mass_upflow_in>0.0001:
            # (there will be floating point rounding errors)
            raise TankError("Mass imbalance. Inflows: " + str(self.input_masses)
                             + ", outflows: " + str(self.output_masses)
                             + ", remainder: " + str(mass_upflow_in))

        # Let's get our new temperatures then: A T = C
        T = np.linalg.solve(A,C)

        # Write new node temps and reset things ready for next timestep
        self.input_masses = np.array([0.0]*self.nodes)
        self.input_temps = np.array([0.0]*self.nodes)
        self.output_masses = np.array([0.0]*self.nodes)
        self.node_temps = T


    def get_hp_draw_temp(self):
        """Returns the current temperature of the outflow to the heatpump
        """
        return self.node_temps[self.heater_draw_node]


    def get_outflow_temp(self):
        """Return the current temperature at the outflow node
        """
        return self.node_temps[self.outflow_node]