from app.models import WorkspacePlan
from app.plans import plan_allows


class _WS:
    def __init__(self, plan):
        self.plan = plan


def test_basic_plan_blocks_scheduled_reports():
    assert plan_allows(_WS(WorkspacePlan.basic), "scheduled_reports") is False


def test_advanced_plan_allows_scheduled_reports():
    assert plan_allows(_WS(WorkspacePlan.advanced), "scheduled_reports") is True
