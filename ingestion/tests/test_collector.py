from importlib.metadata import files
import pytest
import time
from pathlib import Path
import tarfile

from collectors.lovdata_collector import fetch_lovdata_files
from radon.metrics import mi_visit


# ==================================================
# FIXTURES
# ==================================================

@pytest.fixture
def mock_lovdata_response(mocker):
    list_response = mocker.Mock()
    list_response.status_code = 200
    list_response.json.return_value = [{"filename": "laws_2024.tar.bz2"}]
    list_response.raise_for_status.return_value = None

    download_response = mocker.MagicMock()
    download_response.status_code = 200
    download_response.iter_content.return_value = [b"<xml></xml>"]
    download_response.raise_for_status.return_value = None
    download_response.__enter__.return_value = download_response
    download_response.__exit__.return_value = None

    mocker.patch(
        "collectors.lovdata_collector.requests.get",
        side_effect=lambda url, *a, **k:
            list_response if "list" in url else download_response
    )


@pytest.fixture
def mock_tar_extraction(mocker):
    mock_tar = mocker.MagicMock()

    member = mocker.MagicMock()
    member.isfile.return_value = True
    member.name = "law.xml"

    mock_tar.getmembers.return_value = [member]
    mock_tar.extractfile.return_value.read.return_value = b"<xml></xml>"
    mock_tar.__enter__.return_value = mock_tar
    mock_tar.__exit__.return_value = None

    mocker.patch(
        "collectors.lovdata_collector.tarfile.open",
        return_value=mock_tar
    )


# ==================================================
# METRICS
# ==================================================

def test_ingestion_success_rate_and_latency(
    mock_lovdata_response, mock_tar_extraction, mocker, tmp_path
):
    mocker.patch("collectors.lovdata_collector.RAW_XML_DIR", tmp_path)

    start = time.time()
    files, archive = fetch_lovdata_files(limit=1)
    latency = time.time() - start

    assert len(files) == 1
    assert latency < 2.0
    assert archive.endswith(".tar.bz2")


def test_extraction_accuracy_percentage(
    mock_lovdata_response, mock_tar_extraction, mocker, tmp_path
):
    mocker.patch("collectors.lovdata_collector.RAW_XML_DIR", tmp_path)
    files, _ = fetch_lovdata_files(limit=1)

    assert (len(files) / 1) * 100 == 100.0


def test_schema_validity_accuracy(
    mock_lovdata_response, mock_tar_extraction, mocker, tmp_path
):
    mocker.patch("collectors.lovdata_collector.RAW_XML_DIR", tmp_path)
    files, _ = fetch_lovdata_files(limit=1)

    valid = [f for f in files if f.endswith(".xml")]
    assert (len(valid) / len(files)) * 100 >= 95.0


# ==================================================
# ROBUSTNESS
# ==================================================

def test_idempotency_no_duplicate_extraction(
    mock_lovdata_response, mock_tar_extraction, mocker, tmp_path
):
    mocker.patch("collectors.lovdata_collector.RAW_XML_DIR", tmp_path)

    f1, _ = fetch_lovdata_files(limit=1)
    f2, _ = fetch_lovdata_files(limit=1)

    assert set(f1) == set(f2)


def test_corrupted_xml_rejection(
    mock_lovdata_response, mocker, tmp_path
):
    mocker.patch("collectors.lovdata_collector.RAW_XML_DIR", tmp_path)

    bad = mocker.MagicMock()
    bad.isfile.return_value = True
    bad.name = "bad.xml"

    mock_tar = mocker.MagicMock()
    mock_tar.getmembers.return_value = [bad]
    mock_tar.extractfile.return_value.read.return_value = b"\x00\x00\x00"
    mock_tar.__enter__.return_value = mock_tar
    mock_tar.__exit__.return_value = None

    mocker.patch(
        "collectors.lovdata_collector.tarfile.open",
        return_value=mock_tar
    )

    files, _ = fetch_lovdata_files(limit=1)
    assert files == []


def test_corrupted_tar_handling(mocker):
    mocker.patch(
        "collectors.lovdata_collector.tarfile.open",
        side_effect=tarfile.ReadError("corrupt")
    )

    with pytest.raises(tarfile.ReadError):
        fetch_lovdata_files(limit=1)


# def test_api_schema_change_failure(mocker):
#     mocker.patch(
#         "collectors.lovdata_collector._existing_archive",
#         return_value=None
#     )

#     bad = mocker.Mock()
#     bad.status_code = 200
#     bad.json.return_value = [{"file": "wrong.tar"}]
#     bad.raise_for_status.return_value = None

#     mocker.patch(
#         "collectors.lovdata_collector.requests.get",
#         return_value=bad
#     )

#     with pytest.raises(KeyError):
#         fetch_lovdata_files(limit=1)


def test_tar_path_traversal_protection(
    mock_lovdata_response, mocker, tmp_path
):
    mocker.patch("collectors.lovdata_collector.RAW_XML_DIR", tmp_path)

    evil = mocker.MagicMock()
    evil.isfile.return_value = True
    evil.name = "../../evil.xml"

    mock_tar = mocker.MagicMock()
    mock_tar.getmembers.return_value = [evil]
    mock_tar.__enter__.return_value = mock_tar
    mock_tar.__exit__.return_value = None

    mocker.patch(
        "collectors.lovdata_collector.tarfile.open",
        return_value=mock_tar
    )

    with pytest.raises(ValueError):
        fetch_lovdata_files(limit=1)


def test_error_resilience_score(mocker):
    mocker.patch(
        "collectors.lovdata_collector._existing_archive",
        return_value=None
    )

    error = mocker.Mock()
    error.raise_for_status.side_effect = Exception("API error")

    mocker.patch(
        "collectors.lovdata_collector.requests.get",
        return_value=error
    )

    files, archies = fetch_lovdata_files(limit=10)
    assert len(files) != 0
    assert archies is not None
def test_limit_enforcement(
    mock_lovdata_response, mock_tar_extraction, mocker, tmp_path
):
    mocker.patch("collectors.lovdata_collector.RAW_XML_DIR", tmp_path)
    files, _ = fetch_lovdata_files(limit=0)
    assert files == []


# ==================================================
# MAINTAINABILITY
# ==================================================

def test_maintainability_index():
    src = Path("../collectors/lovdata_collector.py").read_text(encoding="utf-8")
    mi = mi_visit(src, multi=True)
    assert mi >= 55