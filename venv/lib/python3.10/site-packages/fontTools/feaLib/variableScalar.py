from fontTools.varLib.models import VariationModel, normalizeValue, piecewiseLinearMap


def Location(loc):
    return tuple(sorted(loc.items()))


class VariableScalar:
    """A scalar with different values at different points in the designspace."""

    def __init__(self, location_value={}):
        self.values = {}
        self.axes = {}
        for location, value in location_value.items():
            self.add_value(location, value)

    def __repr__(self):
        items = []
        for location, value in self.values.items():
            loc = ",".join(
                [
                    f"{ax}={int(coord) if float(coord).is_integer() else coord}"
                    for ax, coord in location
                ]
            )
            items.append("%s:%i" % (loc, value))
        return "(" + (" ".join(items)) + ")"

    @property
    def does_vary(self):
        values = list(self.values.values())
        return any(v != values[0] for v in values[1:])

    @property
    def axes_dict(self):
        if not self.axes:
            raise ValueError(
                ".axes must be defined on variable scalar before interpolating"
            )
        return {ax.axisTag: ax for ax in self.axes}

    def _normalized_location(self, location):
        location = self.fix_location(location)
        normalized_location = {}
        for axtag in location.keys():
            if axtag not in self.axes_dict:
                raise ValueError("Unknown axis %s in %s" % (axtag, location))
            axis = self.axes_dict[axtag]
            normalized_location[axtag] = normalizeValue(
                location[axtag], (axis.minValue, axis.defaultValue, axis.maxValue)
            )

        return Location(normalized_location)

    def fix_location(self, location):
        location = dict(location)
        for tag, axis in self.axes_dict.items():
            if tag not in location:
                location[tag] = axis.defaultValue
        return location

    def add_value(self, location, value):
        if self.axes:
            location = self.fix_location(location)

        self.values[Location(location)] = value

    def fix_all_locations(self):
        self.values = {
            Location(self.fix_location(l)): v for l, v in self.values.items()
        }

    @property
    def default(self):
        self.fix_all_locations()
        key = Location({ax.axisTag: ax.defaultValue for ax in self.axes})
        if key not in self.values:
            raise ValueError("Default value could not be found")
            # I *guess* we could interpolate one, but I don't know how.
        return self.values[key]

    def value_at_location(self, location, model_cache=None, avar=None):
        loc = Location(location)
        if loc in self.values.keys():
            return self.values[loc]
        values = list(self.values.values())
        loc = dict(self._normalized_location(loc))
        return self.model(model_cache, avar).interpolateFromMasters(loc, values)

    def model(self, model_cache=None, avar=None):
        if model_cache is not None:
            key = tuple(self.values.keys())
            if key in model_cache:
                return model_cache[key]
        locations = [dict(self._normalized_location(k)) for k in self.values.keys()]
        if avar is not None:
            mapping = avar.segments
            locations = [
                {
                    k: piecewiseLinearMap(v, mapping[k]) if k in mapping else v
                    for k, v in location.items()
                }
                for location in locations
            ]
        m = VariationModel(locations)
        if model_cache is not None:
            model_cache[key] = m
        return m

    def get_deltas_and_supports(self, model_cache=None, avar=None):
        values = list(self.values.values())
        return self.model(model_cache, avar).getDeltasAndSupports(values)

    def add_to_variation_store(self, store_builder, model_cache=None, avar=None):
        deltas, supports = self.get_deltas_and_supports(model_cache, avar)
        store_builder.setSupports(supports)
        index = store_builder.storeDeltas(deltas)
        return int(self.default), index
