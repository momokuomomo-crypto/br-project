import itertools

from br.collect import odds as O


def _tri_html(val):
    head = "<table><thead><tr><th>1</th></tr></thead><tbody>"
    rows = []
    for row in range(20):
        tds = []
        for first in range(1, 7):
            others = [b for b in range(1, 7) if b != first]
            second = others[row // 4]
            third = [b for b in others if b != second][row % 4]
            if row % 4 == 0:
                tds.append(f'<td rowspan="4">{second}</td>')
            tds.append(f"<td>{third}</td><td class=\"oddsPoint \">{val(first, second, third)}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return head + "".join(rows) + "</tbody></table>"


def test_trifecta_mapping():
    html = _tri_html(lambda a, b, c: f"{a}{b}{c}.0")
    got = O.parse_trifecta(html)
    assert len(got) == 120
    for a, b, c in itertools.permutations(range(1, 7), 3):
        assert got[f"{a}-{b}-{c}"] == float(f"{a}{b}{c}")


def test_missing_values_and_deadlines():
    html = _tri_html(lambda a, b, c: "欠場" if 6 in (a, b, c) else "1,234.5")
    got = O.parse_trifecta(html)
    assert got["6-1-2"] is None and got["1-2-3"] == 1234.5
    dl = O.parse_deadlines("<table><tr><th>締切予定時刻</th><td>10:40</td><td>11:07</td></tr></table>")
    assert dl == {1: "10:40", 2: "11:07"}


def test_win():
    html = "<table><tbody>" + "".join(f'<tr><td>{i}</td><td>x</td><td class="oddsPoint">{i}.5</td></tr>' for i in range(1, 7)) + "</tbody></table>"
    assert O.parse_win(html)["3"] == 3.5
