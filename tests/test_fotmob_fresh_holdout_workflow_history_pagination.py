from pathlib import Path


def test_fresh_holdout_workflow_paginates_past_first_hundred_runs():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    ).read_text(encoding="utf-8")

    assert '"--paginate", "--slurp"' in workflow
    assert "fotmob-utc-native-xg-fresh-holdout.yml/runs?per_page=100" in workflow
    assert 'runs_pages = json.loads(runs_out)' in workflow
    assert 'prior_runs.extend(runs_data["workflow_runs"])' in workflow
    assert 'type(runs_pages) is not list' in workflow


def test_fresh_holdout_workflow_does_not_return_to_single_page_history():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    ).read_text(encoding="utf-8")

    old_single_page = '''runs_data = json.loads(runs_out)\n              if type(runs_data) is not dict or type(runs_data.get("workflow_runs")) is not list:\n                  raise RuntimeError("malformed workflow_runs response")\n              prior_runs = runs_data["workflow_runs"]'''
    assert old_single_page not in workflow
