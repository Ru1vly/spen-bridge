"""Resource-guard checks only; never launch a compiler or service."""

import unittest

from audit.limited_android_compile import validate_limits


class ResourceGuardTests(unittest.TestCase):
    def limits(self, **extra):
        result = {
            "cpu.max": "1000 20000",
            "memory.max": str(768 * 1024**2),
            "memory.high": str(512 * 1024**2),
            "memory.swap.max": "0",
        }
        result.update(extra)
        return result

    def test_verified_budget_is_accepted(self):
        validate_limits(self.limits(), 19)

    def test_unlimited_or_excess_cpu_is_refused(self):
        for value in ["max 100000", "10000 100000", "0 100000", "1000 0"]:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                validate_limits(self.limits(**{"cpu.max": value}), 19)

    def test_unlimited_or_excess_memory_is_refused(self):
        for value in ["max", str(769 * 1024**2)]:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                validate_limits(self.limits(**{"memory.max": value}), 19)

    def test_swap_and_priority_must_be_restricted(self):
        with self.assertRaises(RuntimeError):
            validate_limits(self.limits(**{"memory.swap.max": "max"}), 19)
        with self.assertRaises(RuntimeError):
            validate_limits(self.limits(), 0)
