#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Setup:
    pip install -r requirements.txt

Run:
    ./bridge_filter.py yourname path/to/BridgeComposer.html

Or:
    ./bridge_filter.py yourname http://clubresults.acbl.org/...

This will print out stats on the boards you played, write out

    path/to/BridgeComposer.filtered.html

and post it to gist.github.com.

Built to parse:
http://clubresults.acbl.org/Results/232132/2015/11/151102E.HTM
'''

import os
# TODO: determine whether partnership is EW or NS from the page
# TODO: determine partnership's section from the page

import re
import sys
import json

from collections import namedtuple
from itertools import groupby

from bs4 import BeautifulSoup
import requests

DDS_URL = 'http://www.danvk.org/bridge/'
#DDS_URL = 'http://localhost:8080/'

Result = namedtuple('Result', [
    'board',
    'contract',
    'declarer',
    'making',
    'ns_score',
    'ew_score',
    'ns_matchpoints',
    'ew_matchpoints',
    'ns_pair',
    'ew_pair'
    ])


def get_all_boards(soup):
    return soup.select('.bcboard > .bchd')


def matching_boards(pattern, soup):
    boards = get_all_boards(soup)
    print 'Found %d total boards on page' % len(boards)
    return [board for board in boards
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


def filter_section(soup, ok_section):
    def matches_section(row):
        nspair = row.select_one('.bcstpairns')
        if not nspair:
            return True
        return nspair.text[0] == ok_section
    trs = [row for row in soup.select('.bcst tr') if not matches_section(row)]
    for tr in trs:
        tr.extract()


def remove_unplayed_boards(pattern, soup):
    boards = [board for board in get_all_boards(soup)
              if not re.search(pattern, board.get_text())]
    for board in boards:
        board.extract()


def add_stats(soup, stats):
    '''Add in a preamble with stats.'''
    pre = soup.new_tag('pre')
    pre.string = stats
    soup.body.insert(0, pre)


def add_links(soup, source):
    # Convert all the double dummy results into links.
    for i, board in enumerate(get_all_boards(soup)):
        bchd = board.select('.bchd')[0]
        pbn = extract_pbn(bchd)
        dda_el = board.select('.bcdda')[0]
        dda = dda_el.get_text()
        # e.g. 'EW 3♠; EW 3♥; EW 3♣; W 1N'
        contracts = []
        for contract in re.sub('; Par.*', '', ascii_suit(dda)).split(';')[:-1]:
            contract = contract.replace('\n', '').strip()
            declarer = contract[0]
            c = contract.split(u' ')[1]  # non-breaking space
            num = int(c[0])
            strain = c[1]
            contracts.append((declarer, strain))
        count = [0]
        def make_link(match):
            if count[0] >= len(contracts):
                return match.group(0)
            c = contracts[count[0]]
            count[0] += 1
            return u'<a target="_blank" href="%s?deal=%s&declarer=%s&strain=%s">%s</a>; ' % (DDS_URL, pbn, c[0], c[1], match.group(1))
        new_html = re.sub(r'([EWNS]{1,2}\xa0[1-7].*?); ', make_link, unicode(dda_el))
        dda_el.replaceWith(BeautifulSoup(new_html, 'html.parser'))

    # Add a link back to the original source.
    soup.body.insert(0, BeautifulSoup('<p><a href="%s">View Original</a></p>\n' % source, 'html.parser'))


def extract_hand(bchand):
    '''Given a 'table.bchand' element, return PBN for that hand.'''
    holdings = []
    for suit_td in bchand.select('td'):
        txt = suit_td.get_text()
        if any((suit in txt) for suit in {u'♠', u'♥', u'♦', u'♣'}):
            continue  # this is the suit label td, not the holding td
        if txt == u'—':
            holding = ''
        else:
            holding = txt.replace('10', 'T').replace(' ', '')
        holdings.append(holding)
    return '.'.join(holdings)


def extract_pbn(bchd):
    '''Given a 'table.bchd' element, return PBN for the board.'''
    player = ['N', 'W', 'E', 'S']  # order of hands in HTML
    hands = {
        player[i]: extract_hand(bchand)
        for (i, bchand) in enumerate(bchd.select('table.bchand'))
    } 
    return 'N:' + ' '.join((hands[p] for p in ['N', 'E', 'S', 'W']))

SUIT_MAP = {u'♠': u'S', u'♥': u'H', u'♦': u'D', u'♣': u'C'}
def ascii_suit(txt):
    for k, v in SUIT_MAP.iteritems():
        txt = txt.replace(k, v)
    return txt


def gist_file(path):
    '''Posts a file to GitHub gists and returns the rawgit.com URL.'''
    basename = os.path.basename(path)
    obj = {
      'files': {
          basename: {
              'content': open(path).read()
          }
      },
      'description': 'Filtered BridgeComposer output',
      'public': True
    }
    r = requests.post('https://api.github.com/gists', json=obj)
    r.raise_for_status()
    raw_url = r.json()['files'][basename]['raw_url']
    assert 'gist.githubusercontent.com' in raw_url
    return raw_url.replace('gist.githubusercontent.com', 'cdn.rawgit.com')


def read_html(arg):
    '''Returns HTML for the argument, which is either a URL or a file.'''
    if os.path.exists(arg):
        return open(arg).read()
    r = requests.get(arg)
    r.raise_for_status()
    return r.text


if __name__ == '__main__':
    try:
        pattern, source = sys.argv[1:]
    except ValueError:
        sys.stderr.write('Usage: %s [your name] path/to/results\n' % sys.argv[0])
        sys.exit(1)

    html = read_html(source)
    htmlpath = os.path.basename(source)
    soup = BeautifulSoup(html, "html.parser")

    stats = 'By player:\n'

    results = results_for_pattern(pattern, soup)
    if not results:
        raise ValueError('No boards matched %s' % pattern)

    for declarer, rs in groupby(sorted(results, key=lambda r: r.declarer), lambda r: r.declarer):
        rs = list(rs)
        avg = 1. * sum((float(r.ew_matchpoints) for r in rs)) / len(rs)
        stats += '%s (%d, avg=%f)\n' % (declarer, len(rs), avg)
        for r in rs:
            stats += '    %2s %s by %s making %s (%s)\n' % (
                    r.board, r.contract, r.declarer, r.making, r.ew_matchpoints)

    stats += '\nBy board:\n'
    for r in results:
        stats += '%2s\t%s\t%s\t%s\t%s\n' % (r.board, r.contract, r.declarer, r.making, r.ew_matchpoints)

    print stats

    remove_unplayed_boards(pattern, soup)
    filter_section(soup, 'A')
    add_stats(soup, stats)
    add_links(soup, source)
    filterpath = htmlpath.replace('.html', '.filtered.html')
    open(filterpath, 'w').write(str(soup))

    print '\nWrote filtered HTML to %s\n' % filterpath
    # attempt to gist the file
    rawgit_url = gist_file(filterpath)
    print '\nView results at %s\n' % rawgit_url
