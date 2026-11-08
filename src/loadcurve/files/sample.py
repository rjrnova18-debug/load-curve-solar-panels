"""The sample Load table offered as a downloadable template."""

from loadcurve.domain.models import HOURS_PER_DAY, Load, LoadTable
from loadcurve.files.load_table_io import FileFormat, write_load_table


def _hours_on(*hours: int) -> tuple[int, ...]:
    return tuple(1 if hour in hours else 0 for hour in range(HOURS_PER_DAY))


# A small office, adapted from the legacy app's template. Usage factors reflect
# thermostat-driven equipment: compressors and pumps do not run the whole hour.
SAMPLE_LOAD_TABLE = LoadTable(
    loads=(
        Load(name="Server rack", rated_power_w=1500, schedule=_hours_on(*range(8, 19))),
        Load(name="Kitchen fridge", rated_power_w=350, usage_factor=0.4, schedule=(1,) * 24),
        Load(name="Projector", rated_power_w=300, schedule=_hours_on(9, 10, 11, 15, 16, 17)),
        Load(
            name="AC office",
            rated_power_w=3514,
            usage_factor=0.7,
            schedule=_hours_on(9, 10, 13, 14, 23),
        ),
        Load(
            name="AC principal",
            rated_power_w=3514,
            usage_factor=0.7,
            schedule=_hours_on(10, 11, 20, 21, 22, 23),
        ),
        Load(
            name="AC coordination",
            rated_power_w=3514.4,
            usage_factor=0.7,
            schedule=_hours_on(5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 22, 23),
        ),
        Load(
            name="Water pump",
            rated_power_w=1491.6,
            usage_factor=0.5,
            schedule=_hours_on(6, 8, 11, 20, 21, 22, 23),
        ),
        Load(
            name="Refrigerator",
            rated_power_w=1000,
            usage_factor=0.4,
            schedule=_hours_on(0, 1, 2, 3, 4, 5, 6, 12, 13, 14, 15, 16, 21, 22),
        ),
        Load(
            name="Fans",
            rated_power_w=5400,
            schedule=_hours_on(0, 1, 2, 3, 4, 11, 13, 15, 17, 22),
        ),
        Load(
            name="LED lighting",
            rated_power_w=1200,
            schedule=_hours_on(4, 5, 6, 10, 12, 14, 16, 21),
        ),
    )
)


def template(fmt: FileFormat) -> bytes:
    """The sample Load table as a file the user can fill in."""
    return write_load_table(SAMPLE_LOAD_TABLE, fmt)
