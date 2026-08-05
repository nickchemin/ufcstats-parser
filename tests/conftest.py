"""
Shared Pytest fixtures for parser testing with mock HTML snippets.
"""

import pytest
from bs4 import BeautifulSoup

EVENTS_HTML = """
<!DOCTYPE html>
<html>
<body>
<table class="b-statistics__table-events">
  <tbody>
    <tr class="b-statistics__table-row">
      <td class="b-statistics__table-col">
        <i class="b-statistics__table-content">
          <a class="b-link b-link_style_black" href="http://www.ufcstats.com/event-details/1a50e734bb54861a">
            UFC 309: Jones vs. Miocic
          </a>
          <span class="b-statistics__date">
            November 16, 2024
          </span>
        </i>
      </td>
      <td class="b-statistics__table-col">
        New York City, New York, USA
      </td>
    </tr>
  </tbody>
</table>
</body>
</html>
"""

FIGHTS_HTML = """
<!DOCTYPE html>
<html>
<body>
<table class="b-fight-details__table js-fight-table">
  <tbody>
    <tr class="b-fight-details__table-row b-fight-details__table-row__hover js-fight-details-click"
        data-link="http://www.ufcstats.com/fight-details/68ae50dbf98dc15f">
      <td class="b-fight-details__table-col">
        <p><a class="b-flag b-flag_style_green">win</a></p>
      </td>
      <td class="b-fight-details__table-col">
        <p><a class="b-link" href="http://www.ufcstats.com/fighter-details/f1_id">Jon Jones</a></p>
        <p><a class="b-link" href="http://www.ufcstats.com/fighter-details/f2_id">Stipe Miocic</a></p>
      </td>
      <td class="b-fight-details__table-col"><p>1</p></td>
      <td class="b-fight-details__table-col"><p>85</p></td>
      <td class="b-fight-details__table-col"><p>2</p></td>
      <td class="b-fight-details__table-col"><p>0</p></td>
      <td class="b-fight-details__table-col"><p>Heavyweight</p></td>
      <td class="b-fight-details__table-col"><p>KO/TKO</p><p>Spinning Back Kick</p></td>
      <td class="b-fight-details__table-col"><p>3</p></td>
      <td class="b-fight-details__table-col"><p>4:29</p></td>
    </tr>
  </tbody>
</table>
</body>
</html>
"""

FIGHT_DETAIL_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="b-fight-details__person">
  <a class="b-link" href="http://www.ufcstats.com/fighter-details/f1_id">Jon Jones</a>
</div>
<div class="b-fight-details__person">
  <a class="b-link" href="http://www.ufcstats.com/fighter-details/f2_id">Stipe Miocic</a>
</div>

<!-- Table 0: Totals -->
<table>
  <tr class="b-fight-details__table-row">
    <td><p class="b-fight-details__table-text">Jon Jones</p><p class="b-fight-details__table-text">Stipe Miocic</p></td>
    <td><p class="b-fight-details__table-text">1</p><p class="b-fight-details__table-text">0</p></td>
    <td><p class="b-fight-details__table-text">85 of 120</p><p class="b-fight-details__table-text">24 of 50</p></td>
    <td><p class="b-fight-details__table-text">70%</p><p class="b-fight-details__table-text">48%</p></td>
    <td><p class="b-fight-details__table-text">95 of 130</p><p class="b-fight-details__table-text">26 of 52</p></td>
    <td><p class="b-fight-details__table-text">2 of 3</p><p class="b-fight-details__table-text">0 of 1</p></td>
    <td><p class="b-fight-details__table-text">66%</p><p class="b-fight-details__table-text">0%</p></td>
    <td><p class="b-fight-details__table-text">0</p><p class="b-fight-details__table-text">0</p></td>
    <td><p class="b-fight-details__table-text">0</p><p class="b-fight-details__table-text">0</p></td>
    <td><p class="b-fight-details__table-text">4:12</p><p class="b-fight-details__table-text">0:15</p></td>
  </tr>
</table>

<!-- Table 1: Totals by Round -->
<table>
  <tr class="b-fight-details__table-row">
    <td><p class="b-fight-details__table-text">Jon Jones</p><p class="b-fight-details__table-text">Stipe Miocic</p></td>
    <td><p class="b-fight-details__table-text">0</p><p class="b-fight-details__table-text">0</p></td>
    <td><p class="b-fight-details__table-text">25 of 35</p><p class="b-fight-details__table-text">8 of 15</p></td>
    <td><p class="b-fight-details__table-text">71%</p><p class="b-fight-details__table-text">53%</p></td>
    <td><p class="b-fight-details__table-text">30 of 40</p><p class="b-fight-details__table-text">9 of 16</p></td>
    <td><p class="b-fight-details__table-text">1 of 1</p><p class="b-fight-details__table-text">0 of 0</p></td>
    <td><p class="b-fight-details__table-text">100%</p><p class="b-fight-details__table-text">0%</p></td>
    <td><p class="b-fight-details__table-text">0</p><p class="b-fight-details__table-text">0</p></td>
    <td><p class="b-fight-details__table-text">0</p><p class="b-fight-details__table-text">0</p></td>
    <td><p class="b-fight-details__table-text">2:30</p><p class="b-fight-details__table-text">0:00</p></td>
  </tr>
</table>

<!-- Table 2: Sig Strikes -->
<table>
  <tr class="b-fight-details__table-row">
    <td><p class="b-fight-details__table-text">Jon Jones</p><p class="b-fight-details__table-text">Stipe Miocic</p></td>
    <td><p class="b-fight-details__table-text">85 of 120</p><p class="b-fight-details__table-text">24 of 50</p></td>
    <td><p class="b-fight-details__table-text">70%</p><p class="b-fight-details__table-text">48%</p></td>
    <td><p class="b-fight-details__table-text">50 of 80</p><p class="b-fight-details__table-text">15 of 35</p></td>
    <td><p class="b-fight-details__table-text">20 of 25</p><p class="b-fight-details__table-text">5 of 10</p></td>
    <td><p class="b-fight-details__table-text">15 of 15</p><p class="b-fight-details__table-text">4 of 5</p></td>
    <td><p class="b-fight-details__table-text">40 of 60</p><p class="b-fight-details__table-text">20 of 42</p></td>
    <td><p class="b-fight-details__table-text">10 of 12</p><p class="b-fight-details__table-text">2 of 4</p></td>
    <td><p class="b-fight-details__table-text">35 of 48</p><p class="b-fight-details__table-text">2 of 4</p></td>
  </tr>
</table>

<!-- Table 3: Sig Strikes by Round -->
<table>
  <tr class="b-fight-details__table-row">
    <td><p class="b-fight-details__table-text">Jon Jones</p><p class="b-fight-details__table-text">Stipe Miocic</p></td>
    <td><p class="b-fight-details__table-text">25 of 35</p><p class="b-fight-details__table-text">8 of 15</p></td>
    <td><p class="b-fight-details__table-text">71%</p><p class="b-fight-details__table-text">53%</p></td>
    <td><p class="b-fight-details__table-text">15 of 20</p><p class="b-fight-details__table-text">5 of 10</p></td>
    <td><p class="b-fight-details__table-text">5 of 8</p><p class="b-fight-details__table-text">2 of 3</p></td>
    <td><p class="b-fight-details__table-text">5 of 7</p><p class="b-fight-details__table-text">1 of 2</p></td>
    <td><p class="b-fight-details__table-text">10 of 15</p><p class="b-fight-details__table-text">6 of 12</p></td>
    <td><p class="b-fight-details__table-text">3 of 4</p><p class="b-fight-details__table-text">1 of 1</p></td>
    <td><p class="b-fight-details__table-text">12 of 16</p><p class="b-fight-details__table-text">1 of 2</p></td>
  </tr>
</table>
</body>
</html>
"""

FIGHTER_PROFILE_HTML = """
<!DOCTYPE html>
<html>
<body>
<span class="b-content__title-highlight">Jon Jones</span>
<p class="b-content__Nickname">"Bones"</p>
<span class="b-content__title-record">Record: 28-1-0 (1 NC)</span>
<ul class="b-list__box-list">
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">Height:</i> 6' 4"</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">Weight:</i> 248 lbs.</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">Reach:</i> 84"</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">STANCE:</i> Orthodox</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">DOB:</i> Jul 19, 1987</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">SLpM:</i> 4.30</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">Str. Acc.:</i> 58%</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">SApM:</i> 2.20</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">Str. Def:</i> 64%</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">TD Avg.:</i> 1.85</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">TD Acc.:</i> 45%</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">TD Def.:</i> 95%</li>
  <li class="b-list__box-list-item"><i class="b-list__box-item-title">Sub. Avg.:</i> 0.4</li>
</ul>
</body>
</html>
"""


@pytest.fixture
def events_soup():
    return BeautifulSoup(EVENTS_HTML, "lxml")


@pytest.fixture
def fights_soup():
    return BeautifulSoup(FIGHTS_HTML, "lxml")


@pytest.fixture
def fight_detail_soup():
    return BeautifulSoup(FIGHT_DETAIL_HTML, "lxml")


@pytest.fixture
def fighter_profile_soup():
    return BeautifulSoup(FIGHTER_PROFILE_HTML, "lxml")
