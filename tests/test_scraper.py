"""
Unit tests for proof-of-work challenge resolution logic.
"""

from src.scraper import _is_challenge_page, _solve_pow


def test_is_challenge_page():
    challenge_html = "<html><body><p>Checking your browser…</p><script>xhr.open('POST', '/__c')</script></body></html>"
    normal_html = "<html><body><h1>UFC Stats</h1></body></html>"

    assert _is_challenge_page(challenge_html)
    assert not _is_challenge_page(normal_html)


def test_solve_pow():
    mock_challenge_html = """
    <script>
    var nonce="a1b2c3d4e5f6",
        target=new Array(2+1).join('0');
    </script>
    """

    result = _solve_pow(mock_challenge_html)
    assert result is not None

    nonce, n = result
    assert nonce == "a1b2c3d4e5f6"
    assert isinstance(n, int)
    assert n >= 0
