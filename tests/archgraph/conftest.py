from __future__ import annotations

import pytest


class FakeValidationLayer:
    """Stand-in for PER-317's ValidationLayer.validate_batch."""

    _VALID_METHODS = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}

    def __init__(self) -> None:
        self.accepted: list[object] = []
        self.rejected: list[object] = []

    def validate_batch(self, candidates: list) -> None:
        for candidate in candidates:
            provenance = getattr(candidate, "provenance", [])
            method = getattr(candidate, "extraction_method", "")
            if provenance and method in self._VALID_METHODS:
                self.accepted.append(candidate)
            else:
                self.rejected.append(candidate)


@pytest.fixture
def fake_validation() -> FakeValidationLayer:
    return FakeValidationLayer()
