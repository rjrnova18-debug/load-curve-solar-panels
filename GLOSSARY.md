# Load Curve & Solar Sizing

Estimates how much electricity a home, business or building consumes over a day and a year, and sizes the solar PV systems that could supply it.

## Consumption

**Load**:
A single piece of electrical equipment, described by its name, rated power, usage factor and schedule.
_Avoid_: Appliance, device, equipment, carga

**Rated power**:
The power a Load draws while it is running, in watts, as stated on its nameplate.
_Avoid_: Wattage, nominal load

**Schedule**:
The 24 on/off flags of a Load, one per hour of the day (0 to 23), where 1 means the Load is switched on during that hour.
_Avoid_: Timetable, active hours

**Usage factor**:
The fraction of each switched-on hour in which a Load actually draws its rated power, from 0 to 1 (a fridge compressor cycling 40% of the time has 0.4).
_Avoid_: Duty cycle, utilization, demand factor

**Load table**:
The full set of Loads a user enters for one site; Load names are unique within it.
_Avoid_: Load list, inventory, cuadro de carga

## Daily profile

**Hourly profile**:
The average power drawn by the whole Load table in each of the 24 hours of the day, in watts.
_Avoid_: Load curve, demand profile

**Daytime window**:
The range of hours, from a start hour to an end hour, that counts as day; every other hour counts as night.
_Avoid_: Day period, solar window

**Load duration curve**:
The Hourly profile sorted from the highest to the lowest power.
_Avoid_: LDC chart, sorted profile

**Peak power**:
The highest value of the Hourly profile (overall, daytime or night-time).
_Avoid_: Max demand

**Base power**:
The lowest value of the Hourly profile.
_Avoid_: Minimum load

**Load factor**:
Average power divided by Peak power over the same set of hours, as a percentage.
_Avoid_: Utilization factor

## Year projection

**Seasonal multipliers**:
Twelve factors, one per month, that scale the daily consumption of that month (1.0 means no change).
_Avoid_: Seasonal adjustments, monthly factors

**Monthly energy**:
The energy consumed in one month: daily energy × days in the month × that month's Seasonal multiplier.
_Avoid_: Monthly consumption

## Solar

**Peak sun hours**:
The daily solar irradiation of a place expressed as equivalent hours at 1000 W/m², for one month.
_Avoid_: PSH value, sun hours, HSP, irradiance

**Solar resource**:
The twelve monthly Peak sun hours of one location, either looked up from PVGIS or entered by the user.
_Avoid_: Weather data, irradiation data

**System type**:
How a PV system relates to the grid: on-grid (no batteries), hybrid (grid plus batteries for night-time) or off-grid (batteries only, no grid).
_Avoid_: Topology, configuration

**Sizing assumptions**:
The user-editable parameters of the sizing method: performance ratio, panel power, battery depth of discharge, battery efficiency, inverter safety factor, days of autonomy and on-grid coverage.
_Avoid_: Settings, parameters, config

**System sizing**:
The result of sizing one System type: array peak power (kWp), number of panels, battery capacity (kWh) and inverter power (kW).
_Avoid_: Design, quote, solution
