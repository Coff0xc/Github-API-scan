"""终端表格展示发现，不展示余额或高价值。"""

from rich.console import Console

from ui import Dashboard


def test_terminal_table_is_a_finding_list():
    dashboard = Dashboard()
    dashboard.add_valid_key(
        platform="openai",
        masked_key="sk-pro...k9Q2",
        source="acme-labs/billing-api/.env",
    )

    console = Console(record=True, width=120)
    console.print(dashboard._render_table())
    text = console.export_text()

    assert "发现记录" in text
    assert "sk-pro...k9Q2" in text
    assert "openai" in text
    assert "valid" in text
    assert "acme-labs/billing-api/.env" in text
    assert "Treasure" not in text
    assert "高价值" not in text
    assert "余额" not in text
    assert "$100" not in text
    assert "⭐" not in text
    joined_logs = " ".join(dashboard.logs)
    assert "高价值" not in joined_logs


def test_valid_key_record_has_no_retired_value_fields():
    from dataclasses import fields
    from ui import ValidKeyRecord

    names = {f.name for f in fields(ValidKeyRecord)}
    for retired in ("is_high_value", "balance", "balance_usd", "value_score"):
        assert retired not in names


if __name__ == "__main__":
    test_terminal_table_is_a_finding_list()
    test_valid_key_record_has_no_retired_value_fields()
    print("ui findings ok")
