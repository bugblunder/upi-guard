"""Attacker budget, pairing and reproducible evidence checks."""
import numpy as np
import pandas as pd
import pytest

from experiments.poisoning import corrupt_labels, run, verify


def test_targeted_attack_budget_and_immutable_inputs():
    labels = np.array([0] * 90 + [1] * 10)
    before = labels.copy()
    attacked, changed = corrupt_labels(labels, .3, "targeted", 7)
    random, random_changed = corrupt_labels(labels, .3, "random", 7)
    np.testing.assert_array_equal(labels, before)
    assert len(changed) == len(random_changed) == 3
    assert (labels[changed] == 1).all()
    assert (attacked[changed] == 0).all()
    assert np.count_nonzero(random != labels) == 3
    _, larger = corrupt_labels(labels, .5, "targeted", 7)
    assert set(changed) <= set(larger)
    np.testing.assert_array_equal(attacked, corrupt_labels(labels, .3, "targeted", 7)[0])


@pytest.mark.parametrize("fraction", [-.1, 1, float("nan")])
def test_invalid_poisoning_budget(fraction):
    with pytest.raises(ValueError): corrupt_labels([0, 1], fraction, "targeted", 0)


@pytest.fixture(scope="module")
def tiny_study(tmp_path_factory):
    out = tmp_path_factory.mktemp("poisoning") / "run"
    run(out, [100], episodes=40, models=["lr"])
    return out


def test_complete_study_has_paired_arms_and_no_fabricated_single_seed_ci(tiny_study):
    done = verify(tiny_study)
    assert done["weekly_rows"] == 168
    summary = pd.read_csv(tiny_study / "summary.csv")
    assert summary.ci95_low.isna().all()
    assert summary.ci95_high.isna().all()
    rows = pd.read_csv(tiny_study / "weekly.csv")
    pre = rows[rows.week < 14].pivot(index=["seed", "model", "regime", "week"], columns="arm", values="recall")
    pd.testing.assert_series_equal(pre.control, pre.drift, check_names=False)


def test_result_tampering_is_detected(tiny_study, tmp_path):
    import shutil
    out = tmp_path / "tampered"
    shutil.copytree(tiny_study, out)
    with (out / "weekly.csv").open("a") as file: file.write("edited\n")
    with pytest.raises(ValueError, match="checksum"):
        verify(out)


def test_completed_experiment_cannot_be_overwritten(tiny_study):
    with pytest.raises(FileExistsError):
        run(tiny_study, [100], episodes=40, models=["lr"])
