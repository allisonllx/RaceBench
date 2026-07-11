"""STATUS_ACTIVE must be 'enabled'; handlers must use the live constant."""
from exporters import active_label
from handlers import filter_active, summarize_active
from schema import STATUS_ACTIVE
from schema import constants as const


def test_constant_renamed():
    assert STATUS_ACTIVE == "enabled"
    assert const.STATUS_ACTIVE == "enabled"
    assert active_label() == "enabled"


def test_no_old_active_string_in_export():
    assert active_label() != "active"


def test_filter_uses_new_value():
    records = [
        {"id": 1, "status": "enabled"},
        {"id": 2, "status": "active"},
        {"id": 3, "status": "inactive"},
    ]
    assert filter_active(records) == [{"id": 1, "status": "enabled"}]


def test_summarize_active():
    records = [{"status": "enabled"}, {"status": "enabled"}, {"status": "x"}]
    assert summarize_active(records) == {"active_count": 2}
