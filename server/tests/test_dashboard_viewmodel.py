from __future__ import annotations

from writing_ops.service import WritingOpsService
from writing_ops.state import DAILY_REQUIRED, StateStore


def daily_payload() -> dict[str, object]:
    payload: dict[str, object] = {key: f"value-{key}" for key in DAILY_REQUIRED}
    payload.update(
        {
            "must_happen": ["turning point"],
            "must_not_happen": ["external publication"],
            "forbidden_zones": ["canon rewrite"],
            "word_count": 1800,
            "auto_adopt": False,
            "window_start": "2026-09-02T09:00:00+08:00",
            "window_end": "2026-09-02T11:00:00+08:00",
        }
    )
    return payload


def test_dashboard_view_model_uses_real_three_level_goal_state(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    long_term = store.upsert_goal("long_term", {"objective": "finish the novel"})
    cycle = store.upsert_goal(
        "cycle",
        {"objective": "complete the first arc"},
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
    )
    daily = store.upsert_goal(
        "daily",
        daily_payload(),
        long_term_id=long_term["id"],
        long_term_revision=long_term["revision"],
        cycle_id=cycle["id"],
        cycle_revision=cycle["revision"],
    )

    view_model = WritingOpsService(store=store).dashboard()

    assert view_model.schema_version == 2
    assert [goal.id for goal in view_model.creator.goals.long_term] == [long_term["id"]]
    assert [goal.id for goal in view_model.creator.goals.cycle] == [cycle["id"]]
    assert [goal.id for goal in view_model.creator.goals.daily] == [daily["id"]]
    assert view_model.creator.goals.daily[0].payload["chapter"] == "value-chapter"
    assert view_model.creator.human_review_status == "pending"
    assert view_model.reviewer.human_review_status == "pending"
    assert "创作者模式" in view_model.text_dashboard
    assert "审查模式" in view_model.text_dashboard
