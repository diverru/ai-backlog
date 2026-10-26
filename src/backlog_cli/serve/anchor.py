"""The ids of the parts of an item card, and the links that point at them."""


class Anchor:
    @staticmethod
    def unit(unit_id: str) -> str:
        return f"u-{unit_id}"

    @staticmethod
    def action(unit_id: str, action_id: str) -> str:
        return f"a-{unit_id}-{action_id}"

    @staticmethod
    def blocker(blocker_id: str) -> str:
        return f"b-{blocker_id.removeprefix('b')}"

    @staticmethod
    def finding(unit_id: str, action_id: str, position: int) -> str:
        return f"f-{unit_id}-{action_id}-{position}"
