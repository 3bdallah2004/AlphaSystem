"""Repeatable latency checks with synthetic provider delay; never call live AI."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import analysis
import chat


def test_extraction_cache_is_scoped_and_coalesces_requests(database, case):
    analysis._suggest_cache.clear()
    calls = []
    def provider(*args, **kwargs):
        calls.append(args)
        time.sleep(.08)
        return True, json.dumps({"case_name": "Warehouse theft", "case_type": "سرقة", "date": "2026-02-30"})
    with patch.object(analysis, "send_to_n8n", side_effect=provider):
        started = time.perf_counter()
        analysis.suggest_details("source", "en")
        baseline = time.perf_counter() - started
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: analysis.suggest_details("source", "en", case), range(3)))
        assert len(calls) == 2  # baseline + one shared cold request
        assert all("date" not in result for result in results)
        started = time.perf_counter()
        analysis.suggest_details("source", "en", case)
        cached = time.perf_counter() - started
        assert len(calls) == 2
        analysis.suggest_details("changed source", "en", case)
        analysis.suggest_details("source", "en", case + 1)
        assert len(calls) == 4
    print(f"extraction synthetic uncached={baseline:.6f}s warm_cache={cached:.6f}s")


def test_ready_analysis_does_not_wait_for_geocode(database, case):
    database.update_case(case, location="Test location")
    completed = threading.Event()
    release = threading.Event()
    gated = False
    def locate(*args):
        if gated:
            release.wait(5)
        else:
            time.sleep(.25)
        completed.set()
    def provider(*args, **kwargs):
        time.sleep(.05)
        return True, '{"summary":"Test result"}'
    with patch.object(analysis, "locate", side_effect=locate), patch.object(analysis, "send_to_n8n", side_effect=provider):
        # Old pipeline: concurrent work followed by a blocking location join.
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=1) as pool:
            location = pool.submit(locate)
            provider()
            location.result()
        baseline = time.perf_counter() - started
        completed.clear()
        gated = True
        started = time.perf_counter()
        analysis._analyze(case, "en")
        improved = time.perf_counter() - started
        try:
            assert database.get_case(case)["status"] == "analyzed"
            assert not completed.is_set()
        finally:
            release.set()
            assert completed.wait(2)
    print(f"analysis synthetic old_join={baseline:.6f}s ready_report={improved:.6f}s")


def test_duplicate_analysis_does_not_launch_two_workers(database, case):
    analysis._analysis_generations.clear()
    analysis._analysis_inputs.clear()
    with patch.object(analysis.threading, "Thread") as worker:
        assert analysis.start_analysis(case, "en")
        assert not analysis.start_analysis(case, "en")
        assert worker.call_count == 1
        database.update_case(case, case_text="Changed source")
        assert analysis.start_analysis(case, "en")
        assert worker.call_count == 2
    analysis._analysis_generations.clear()
    analysis._analysis_inputs.clear()


def test_chat_context_uses_one_overview_query_and_excludes_future_messages(database, case):
    for index in range(120):
        database.create_draft(f"Synthetic complaint {index}")
    old = database.add_message(0, "user", "Earlier fact")
    current = database.add_message(0, "user", "Current question")
    database.add_message(0, "user", "Future question")
    started = time.perf_counter()
    rows = database.list_cases()
    for row in rows:
        database.get_case(row["id"])
    baseline = time.perf_counter() - started
    started = time.perf_counter()
    with patch.object(database, "get_case", wraps=database.get_case) as lookup:
        chat.cases_overview("en")
        assert lookup.call_count == 0
    improved = time.perf_counter() - started
    assert chat.history(before_id=current) == [{"role": "user", "content": "Earlier fact"}]
    assert old < current
    print(f"chat DB/context 121 cases old_Nplus1={baseline:.6f}s new_overview={improved:.6f}s queries=122->1")


def test_chat_transport_retry_reuses_turn_and_rejects_different_content(database):
    with patch.object(chat.threading, "Thread") as worker:
        first = chat.ask("Question", "en", request_id="transport-1")
        second = chat.ask("Question", "en", request_id="transport-1")
        assert first[:2] == second[:2]
        assert worker.call_count == 1
        import pytest
        with pytest.raises(ValueError):
            chat.ask("Different question", "en", request_id="transport-1")
        chat.ask("Question", "en", request_id="transport-2")
        assert worker.call_count == 2
