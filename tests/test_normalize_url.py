import pytest
from main import normalize_url

def test_lever():
    result = normalize_url("https://jobs.lever.co/sarwa/f144708c-61d4-4c29-afd8-49e8c46c0e90")
    assert result == "https://jobs.lever.co/sarwa/f144708c-61d4-4c29-afd8-49e8c46c0e90"

def test_greenhouse():
    result = normalize_url("https://job-boards.greenhouse.io/tegnainc/jobs/4443469007")
    assert result == "https://job-boards.greenhouse.io/tegnainc/jobs/4443469007"

def test_long_url():
    result = normalize_url("https://boards.greenhouse.io/remotecom/jobs/6093880003?utm_source=Logos+Labs+job+board&utm_medium=getro.com&gh_src=Logos+Labs+job+board")
    assert result == "https://boards.greenhouse.io/remotecom/jobs/6093880003"
