"""Tests del gestor de funcionalidades (features.py) — validación y metadatos."""
import os

import pytest

from bass_karaoke import features


@pytest.mark.parametrize(
    "spec",
    [
        "aubio",
        "torch",
        "torchcrepe",
        "onnxruntime",
        "basic-pitch",
        "librosa",
        "numpy==1.26.4",
        "torch>=2.0",
        "pkg[extra]",
        "pkg[extra1,extra2]>=1.0",
    ],
)
def test_validate_spec_accepts_regular_packages(spec):
    assert features._validate_spec(spec) == spec


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "   ",
        "-r requirements.txt",
        "--index-url https://evil",
        "pkg --flag",
        "pkg; rm -rf /",
        "pkg\n--flag",
        "https://example.com/pkg.whl",
        "pkg=",
        "pkg[extra",
    ],
)
def test_validate_spec_rejects_flags_and_injection(spec):
    with pytest.raises(ValueError):
        features._validate_spec(spec)


def test_is_metadata_dir_matches_only_the_same_package():
    assert features._is_metadata_dir("torch-2.1.0.dist-info", "torch")
    assert features._is_metadata_dir("torch.egg-info", "torch")
    assert features._is_metadata_dir("torch-2.1.0.egg-info", "torch")
    assert not features._is_metadata_dir("torchvision-0.15.dist-info", "torch")
    assert not features._is_metadata_dir("torchcrepe-0.0.23.dist-info", "torch")
    assert not features._is_metadata_dir("torch", "torch")


def test_every_registered_package_is_a_valid_spec():
    for feature in features.FEATURES:
        for pkg in feature["packages"]:
            assert features._validate_spec(pkg) == pkg


def test_registry_ids_are_unique_and_requires_resolve():
    ids = [f["id"] for f in features.FEATURES]
    assert len(ids) == len(set(ids))
    known = set(ids)
    for feature in features.FEATURES:
        assert set(feature["requires"]) <= known
        assert feature["category"] in {"pitch", "audio", "score", "core"}


def test_by_id_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        features.by_id("does-not-exist")


def test_features_dir_lives_next_to_the_project():
    path = features.features_dir()
    assert path.endswith("features")
    assert os.path.isabs(path)
