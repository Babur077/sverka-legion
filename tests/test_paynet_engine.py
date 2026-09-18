from modules.paynet.engine import PaynetModule


def test_paynet_reconciliation_matches_ids_and_reports_amount_diff():
    module = PaynetModule()
    billing = (
        "id;amount;status\n"
        "A1;1000;SUCCESS\n"
        "A2;2000;SUCCESS\n"
        "A3;3000;SUCCESS\n"
    ).encode("utf-8")
    agent = (
        "txn;sum;state;commission\n"
        "A1;1000;SUCCESS;10\n"
        "A2;2100;SUCCESS;21\n"
        "A4;4000;SUCCESS;40\n"
    ).encode("utf-8")

    result = module.run(
        {"billing_file": billing, "agent_file": agent},
        {
            "billing_file_filename": "billing.csv",
            "agent_file_filename": "agent.csv",
            "billing_id_col": "id",
            "billing_amount_col": "amount",
            "billing_status_col": "status",
            "agent_id_col": "txn",
            "agent_amount_col": "sum",
            "agent_status_col": "state",
            "agent_commission_col": "commission",
            "provider_name": "Paynet",
            "tolerance": "0.01",
        },
    )

    paynet = result.custom_metrics["paynet"]

    assert result.module_id == "paynet"
    assert result.summary.total_records_a == 3
    assert result.summary.total_records_b == 3
    assert result.summary.matched_count == 1
    assert result.summary.discrepancy_count == 3
    assert len(paynet["amount_mismatches"]) == 1
    assert len(paynet["only_billing"]) == 1
    assert len(paynet["only_agent"]) == 1
    assert paynet["total_commission"] == 71.0


def test_paynet_status_mismatch_is_a_problem_even_when_amount_matches():
    module = PaynetModule()
    billing = "id;amount;status\nA1;1000;SUCCESS\n".encode("utf-8")
    agent = "txn;sum;state\nA1;1000;REVERSED\n".encode("utf-8")

    result = module.run(
        {"billing_file": billing, "agent_file": agent},
        {
            "billing_file_filename": "billing.csv",
            "agent_file_filename": "agent.csv",
            "billing_id_col": "id",
            "billing_amount_col": "amount",
            "billing_status_col": "status",
            "agent_id_col": "txn",
            "agent_amount_col": "sum",
            "agent_status_col": "state",
        },
    )

    assert result.summary.matched_count == 0
    assert result.summary.discrepancy_count == 1
    assert len(result.custom_metrics["paynet"]["status_mismatches"]) == 1
