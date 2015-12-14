#!/usr/bin/env python
'''
Usage:
    pip install -r requirements.txt
    ./bridge_filter.py yourname path/to/BridgeComposer.html

Prints out stats on the boards you played and writes out

    path/to/BridgeComposer.filtered.html

Built to parse:
http://clubresults.acbl.org/Results/232132/2015/11/151102E.HTM
'''

import re
import sys

from collections import namedtuple
from itertools import groupby

from bs4 import BeautifulSoup

Result = namedtuple('Result', [
    'board',
    'contract',
    'declarer',
    'making',
    'ns_score',
    'ew_score',
    'ns_matchpoints',
    'ew_matchpoints',
    'pair'
    ])


def matching_boards(pattern, soup):
    return [board for board in soup.select('center > div')
                if re.search(pattern, board.get_text())]


def results_for_pattern(pattern, soup):
    boards = matching_boards(pattern, soup)
    results = []
    for board in boards:
        board_num = re.search(r'Board (\d+)', board.get_text()).group(1)
        result = [tr for tr in board.select('.bcst tr') if re.search(pattern, tr.get_text())][0]
        vals = [board_num] + [td.get_text() for td in result.select('td')]
        results.append(Result._make(vals))
    return results


def remove_section(soup, section):
    def matches_section(row):
        m = re.search(r' vs ([A-Z])\d+', row.get_text())
        return m and m.group(1) == section
    trs = [row for row in soup.select('.bcst tr') if matches_section(row)]
    for tr in trs:
        tr.extract()


def remove_unplayed_boards(pattern, soup):
    boards = [board for board in soup.select('center > div')
                if not re.search(pattern, board.get_text())]
    for board in boards:
        board.extract()


if __name__ == '__main__':
    pattern, htmlpath = sys.argv[1:]
    assert '.html' in htmlpath

    html = open(htmlpath).read()
    soup = BeautifulSoup(html, "html.parser")

    results = results_for_pattern(pattern, soup)
    for declarer, rs in groupby(sorted(results, key=lambda r: r.declarer), lambda r: r.declarer):
        rs = list(rs)
        print '%s (%d)' % (declarer, len(rs))
        for r in rs:
            print '    %2s %s by %s making %s' % (r.board, r.contract, r.declarer, r.making)

    remove_unplayed_boards(pattern, soup)
    remove_section(soup, 'A')
    filterpath = htmlpath.replace('.html', '.filtered.html')
    open(filterpath, 'w').write(str(soup))

    print '\nWrote filtered HTML to %s\n' % filterpath
