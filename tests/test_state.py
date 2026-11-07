import unittest

from runtime.quant_cn.state import RunState, StateMachine


class StateMachineTests(unittest.TestCase):
    def test_happy_path(self):
        machine = StateMachine()
        for state in (
            RunState.DATA_VALIDATED,
            RunState.BACKTESTED,
            RunState.EVALUATED,
            RunState.COMPLETED,
        ):
            machine.transition(state)
        self.assertEqual(machine.state, RunState.COMPLETED)
        self.assertEqual(len(machine.history), 4)

    def test_rejects_skipping_a_stage(self):
        machine = StateMachine()
        with self.assertRaisesRegex(ValueError, "invalid state transition"):
            machine.transition(RunState.EVALUATED)

    def test_terminal_state_is_immutable(self):
        machine = StateMachine()
        machine.fail("bad input")
        machine.fail("ignored")
        self.assertEqual(machine.state, RunState.FAILED)
        self.assertEqual(len(machine.history), 1)


if __name__ == "__main__":
    unittest.main()
