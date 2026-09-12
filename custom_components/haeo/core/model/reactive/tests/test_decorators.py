"""Tests for reactive decorators (constraint, cost, output) and integration tests."""

from collections.abc import Sequence

from highspy import Highs, HighsRanging, HighsSolution
from highspy.highs import highs_linear_expression
import numpy as np
import pytest

from custom_components.haeo.core.model.element import Element
from custom_components.haeo.core.model.elements.battery import Battery
from custom_components.haeo.core.model.reactive import (
    ReactiveConstraint,
    ReactiveCost,
    TrackedParam,
    constraint,
    cost,
    decorators,
)


def create_test_element[T: Element[str]](cls: type[T]) -> T:
    """Create a test element instance with a fresh solver."""
    solver = Highs()
    solver.setOptionValue("output_flag", False)
    return cls(name="test", periods=np.array([1.0]), solver=solver, output_names=frozenset())


# ReactiveConstraint tests


def test_cached_constraint_caches_result() -> None:
    """Test that constraint result is cached."""
    call_count = 0

    class TestElement(Element[str]):
        @constraint
        def my_constraint(self) -> None:
            # Return None to skip solver application
            nonlocal call_count
            call_count += 1

    elem = create_test_element(TestElement)

    # First call
    result1 = elem.my_constraint()
    assert result1 is None
    assert call_count == 1

    # Get the state
    state = getattr(elem, "_reactive_state_my_constraint", None)
    assert state is not None
    assert not state["invalidated"]

    # Second call should use cache
    result2 = elem.my_constraint()
    assert result2 is None
    assert call_count == 1  # Not incremented


def test_cached_constraint_recomputes_when_invalidated() -> None:
    """Test that constraint recomputes when invalidated."""
    call_count = 0

    class TestElement(Element[str]):
        capacity = TrackedParam[float]()

        @constraint
        def my_constraint(self) -> None:
            # Return None to skip solver application
            nonlocal call_count
            call_count += 1
            _ = self.capacity  # Access to establish dependency

    elem = create_test_element(TestElement)
    elem.capacity = 5.0

    # First call
    result1 = elem.my_constraint()
    assert result1 is None
    assert call_count == 1

    # Change capacity (invalidates constraint)
    elem.capacity = 10.0

    # Check state was invalidated
    state = getattr(elem, "_reactive_state_my_constraint", None)
    assert state is not None
    assert state["invalidated"]

    # Next call should recompute
    result2 = elem.my_constraint()
    assert result2 is None
    assert call_count == 2


def test_cached_constraint_tracks_multiple_dependencies() -> None:
    """Test that multiple parameter dependencies are tracked."""

    class TestElement(Element[str]):
        capacity = TrackedParam[float]()
        efficiency = TrackedParam[float]()

        @constraint
        def combined_constraint(self) -> None:
            # Access both parameters to establish dependencies
            _ = self.capacity
            _ = self.efficiency

    elem = create_test_element(TestElement)
    elem.capacity = 10.0
    elem.efficiency = 0.9

    elem.combined_constraint()

    # Check state was created and dependencies tracked
    state = getattr(elem, "_reactive_state_combined_constraint", None)
    assert state is not None
    assert "capacity" in state["deps"]
    assert "efficiency" in state["deps"]


def test_cached_constraint_class_access_returns_descriptor() -> None:
    """Test accessing ReactiveConstraint on class returns the descriptor."""

    class TestElement(Element[str]):
        @constraint
        def my_constraint(self) -> list[int]:
            return []

    assert isinstance(TestElement.my_constraint, ReactiveConstraint)


# ReactiveCost tests


def test_cached_cost_caches_result() -> None:
    """Test that cost result is cached."""
    call_count = 0

    class TestElement(Element[str]):
        @cost
        def my_cost(self) -> Sequence[highs_linear_expression]:
            nonlocal call_count
            call_count += 1
            return []

    elem = create_test_element(TestElement)

    # First call
    elem.my_cost()
    assert call_count == 1

    # Second call should use cache
    elem.my_cost()
    assert call_count == 1  # Not incremented


def test_cached_cost_recomputes_when_invalidated() -> None:
    """Test that cost recomputes when invalidated."""
    call_count = 0

    class TestElement(Element[str]):
        price = TrackedParam[float]()

        @cost
        def my_cost(self) -> Sequence[highs_linear_expression]:
            nonlocal call_count
            call_count += 1
            _ = self.price  # Access to establish dependency
            return []

    elem = create_test_element(TestElement)
    elem.price = 0.25

    # First call
    elem.my_cost()
    assert call_count == 1

    # Change price (invalidates cost)
    elem.price = 0.50

    # Check state was invalidated
    state = getattr(elem, "_reactive_state_my_cost", None)
    assert state is not None
    assert state["invalidated"]

    # Next call should recompute
    elem.my_cost()
    assert call_count == 2


def test_cached_cost_class_access_returns_descriptor() -> None:
    """Test accessing ReactiveCost on class returns the descriptor."""

    class TestElement(Element[str]):
        @cost
        def my_cost(self) -> Sequence[highs_linear_expression]:
            return []

    assert isinstance(TestElement.my_cost, ReactiveCost)


# Element reactive infrastructure tests


def test_element_reactive_initialization() -> None:
    """Test that Element initializes properly."""
    elem = create_test_element(Element)

    # Element should initialize without errors
    # No reactive state exists until decorators are called
    assert elem.name == "test"
    assert len(elem.periods) == 1


def test_element_reactive_invalidate_dependents_constraints() -> None:
    """Test invalidate_dependents marks correct constraints."""

    class TestElement(Element[str]):
        a = TrackedParam[float]()
        b = TrackedParam[float]()

        @constraint
        def uses_a(self) -> list[int]:
            _ = self.a
            return []

        @constraint
        def uses_b(self) -> list[int]:
            _ = self.b
            return []

        @constraint
        def uses_both(self) -> list[int]:
            _ = self.a
            _ = self.b
            return []

    elem = create_test_element(TestElement)
    elem.a = 1.0
    elem.b = 2.0

    # Call all constraints to establish dependencies
    elem.uses_a()
    elem.uses_b()
    elem.uses_both()

    # Get states
    state_a = getattr(elem, "_reactive_state_uses_a", None)
    state_b = getattr(elem, "_reactive_state_uses_b", None)
    state_both = getattr(elem, "_reactive_state_uses_both", None)
    assert state_a is not None
    assert state_b is not None
    assert state_both is not None

    # Change 'a' - should invalidate uses_a and uses_both but not uses_b
    elem.a = 10.0

    assert state_a["invalidated"]
    assert state_both["invalidated"]
    assert not state_b["invalidated"]


def test_element_reactive_invalidate_dependents_costs() -> None:
    """Test invalidate_dependents marks correct costs."""

    class TestElement(Element[str]):
        price = TrackedParam[float]()

        @cost
        def price_cost(self) -> Sequence[highs_linear_expression]:
            _ = self.price
            return []

    elem = create_test_element(TestElement)
    elem.price = 0.25

    # Call cost to establish dependency
    elem.price_cost()

    # Get state
    state = getattr(elem, "_reactive_state_price_cost", None)
    assert state is not None
    assert not state["invalidated"]

    # Change price
    elem.price = 0.50

    assert state["invalidated"]


# Constraint collection tests


def test_constraints_adds_new_constraint() -> None:
    """Test that constraints() adds constraints to solver on first call."""
    solver = Highs()
    solver.setOptionValue("output_flag", False)
    x = solver.addVariable(lb=0.0, ub=10.0)

    class TestElement(Element[str]):
        @constraint
        def my_constraint(self) -> list[highs_linear_expression]:
            # Constraint methods return expressions, decorator applies to solver
            return [x <= 5.0]

    elem = TestElement(name="test", periods=np.array([1.0]), solver=solver, output_names=frozenset())

    elem.constraints()

    # Constraint should be applied (state should exist with constraint)
    state = getattr(elem, "_reactive_state_my_constraint", None)
    assert state is not None
    assert "constraint" in state


def test_constraints_skips_none_result() -> None:
    """Test that constraints() handles None result gracefully."""
    solver = Highs()
    solver.setOptionValue("output_flag", False)

    class TestElement(Element[str]):
        @constraint
        def my_constraint(self) -> None:
            return None

    elem = TestElement(name="test", periods=np.array([1.0]), solver=solver, output_names=frozenset())

    elem.constraints()

    # State should exist but no constraint should be added
    state = getattr(elem, "_reactive_state_my_constraint", None)
    assert state is not None
    assert "constraint" not in state


# Integration tests


def test_reactive_workflow() -> None:
    """Test complete reactive workflow with parameter changes."""

    class Battery(Element[str]):
        capacity = TrackedParam[float]()
        initial_charge = TrackedParam[float]()

        def __init__(
            self,
            capacity: float,
            initial_charge: float,
            **kwargs: object,
        ) -> None:
            super().__init__(**kwargs)  # type: ignore[arg-type]
            self.capacity = capacity
            self.initial_charge = initial_charge
            self._soc_values: list[float] = []

        @constraint
        def test_constraint(self) -> None:
            # Simulated constraint that depends on capacity
            # Return None to skip solver application
            self._soc_values = [self.capacity * 0.9]

    solver = Highs()
    solver.setOptionValue("output_flag", False)
    battery = Battery(
        capacity=10.0,
        initial_charge=5.0,
        name="test",
        periods=np.array([1.0]),
        solver=solver,
        output_names=frozenset(),
    )

    # Initial constraint computation
    result1 = battery.test_constraint()
    assert result1 is None
    assert battery._soc_values == [9.0]

    # Cached access
    result2 = battery.test_constraint()
    assert result2 is None
    assert battery._soc_values == [9.0]

    # Change capacity
    battery.capacity = 20.0

    # Recomputed
    result3 = battery.test_constraint()
    assert result3 is None
    assert battery._soc_values == [18.0]


def test_constraint_without_output_flag() -> None:
    """Test that constraints without output=True don't return OutputData from get_output()."""
    h = Highs()
    h.setOptionValue("output_flag", False)

    # Use 2 periods since battery constraints use slices [1:]
    battery = Battery(
        name="test",
        periods=np.array([1.0, 1.0]),
        solver=h,
        capacity=np.array([10.0, 10.0, 10.0]),
        initial_charge=5.0,
    )

    # Trigger constraint creation
    battery.constraints()

    # Get outputs - should not include constraints without output=True
    outputs = battery.outputs()

    # Battery has @constraint decorators without output=False (energy_balance)
    # These should not appear in outputs because output=False
    assert "energy_balance" not in outputs

    # But should include constraints with output=True
    assert "battery_soc_max" in outputs
    assert "battery_soc_min" in outputs


# Shadow-price ranging extraction


def _solved_battery() -> Battery:
    """Build a two-period battery, create its constraints and solve it."""
    solver = Highs()
    solver.setOptionValue("output_flag", False)
    battery = Battery(
        name="test",
        periods=np.array([1.0, 1.0]),
        solver=solver,
        capacity=np.array([10.0, 10.0, 10.0]),
        initial_charge=5.0,
    )
    battery.constraints()
    # An explicit objective, as every other solve in this file does; the ranging data this
    # test reads is only valid off an optimal solution.
    solver.minimize(battery.power_consumption[0])
    return battery


def test_ranging_output_matches_the_solver_vectors() -> None:
    """Test that range_up and range_dn are bound minus row value, read off the solver."""
    battery = _solved_battery()
    solver = battery._solver

    outputs = battery.outputs()
    soc_max = outputs["battery_soc_max"]

    assert soc_max.range_up is not None
    assert soc_max.range_dn is not None
    assert len(soc_max.range_up) == len(soc_max.values)
    assert len(soc_max.range_dn) == len(soc_max.values)

    # Recompute independently, reading each solver vector exactly once.
    _status, rng = solver.getRanging()
    assert rng.valid
    row_value = solver.getSolution().row_value
    bound_up = rng.row_bound_up.value_
    bound_dn = rng.row_bound_dn.value_

    state = getattr(battery, "_reactive_state_battery_soc_max", None)
    assert state is not None
    arr = np.asarray(state["constraint"], dtype=object)
    expected_up = tuple(float(bound_up[c.index] - row_value[c.index]) for c in arr.flat)
    expected_dn = tuple(float(row_value[c.index] - bound_dn[c.index]) for c in arr.flat)

    assert soc_max.range_up == expected_up
    assert soc_max.range_dn == expected_dn


def test_ranging_vectors_are_copies_rather_than_views() -> None:
    """Test that highspy returns a fresh list per access, which is why the reads are hoisted."""
    battery = _solved_battery()
    solver = battery._solver

    _status, rng = solver.getRanging()
    assert rng.valid
    assert rng.row_bound_up.value_ is not rng.row_bound_up.value_
    assert solver.getSolution().row_value is not solver.getSolution().row_value


class _CountingRecord:
    """Stand-in for HighsRangingRecord that counts reads of value_."""

    def __init__(self, values: list[float], counter: dict[str, int], key: str) -> None:
        """Store the values to hand out and the counter to bump."""
        self._values = values
        self._counter = counter
        self._key = key

    @property
    def value_(self) -> list[float]:
        """Return a fresh copy, as pybind11 does, and count the access."""
        self._counter[self._key] += 1
        return list(self._values)


class _CountingRanging:
    """Stand-in for HighsRanging whose bound records count their reads."""

    def __init__(self, rng: HighsRanging, counter: dict[str, int]) -> None:
        """Snapshot the real ranging vectors behind counting records."""
        self.valid = rng.valid
        self.row_bound_up = _CountingRecord(list(rng.row_bound_up.value_), counter, "up")
        self.row_bound_dn = _CountingRecord(list(rng.row_bound_dn.value_), counter, "dn")


class _CountingSolution:
    """Stand-in for HighsSolution that counts reads of row_value."""

    def __init__(self, solution: HighsSolution, counter: dict[str, int]) -> None:
        """Snapshot the real row values behind a counting property."""
        self._values = list(solution.row_value)
        self._counter = counter

    @property
    def row_value(self) -> list[float]:
        """Return a fresh copy, as pybind11 does, and count the access."""
        self._counter["row"] += 1
        return list(self._values)


def test_ranging_vectors_are_read_once_per_output_not_once_per_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the three solver vectors are read once per output, not once per row.

    This is the regression guard for the quadratic cost. `HighsSolution.row_value` and
    `HighsRangingRecord.value_` are pybind11 properties that return a fresh list on every
    access, so reading them inside the per-row loop copies a whole vector per row. A
    correctness test cannot catch a reintroduction, because the values come out the same
    either way -- only the access count differs.
    """
    battery = _solved_battery()
    solver = battery._solver
    _status, real_rng = solver.getRanging()
    real_solution = solver.getSolution()
    counter = {"up": 0, "dn": 0, "row": 0}

    def fake_get_ranging(_solver: Highs) -> tuple[_CountingRanging, _CountingSolution]:
        return _CountingRanging(real_rng, counter), _CountingSolution(real_solution, counter)

    monkeypatch.setattr(decorators, "_get_ranging", fake_get_ranging)

    outputs = battery.outputs()
    n_rows = len(outputs["battery_soc_max"].values)
    assert n_rows >= 2, "the test needs more than one row to distinguish per-row from per-output"

    n_shadow = sum(1 for output in outputs.values() if output.range_up is not None)
    assert n_shadow >= 1
    for key, count in counter.items():
        assert count <= n_shadow, (
            f"{key} was read {count} times for {n_shadow} shadow-price outputs over {n_rows} rows; "
            "the property is being read inside the per-row loop again"
        )
