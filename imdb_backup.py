#!/usr/bin/env python3

import re
import time
import zipfile
from pathlib import Path
from typing import Dict, Generator, Iterable

import requests
import unidecode
from bs4 import BeautifulSoup

COOKIE_FNAME = 'imdb_cookie.txt'
ZIP_FNAME = 'imdb_exported_lists.zip'

MList = Dict[str, str]


def slugify(s: str) -> str:
    """
    Convert to lowercase ASCII with hyphens instead of underscores or spaces.
    Remove all non-alphanumeric characters and strip leading and trailing whitespace.
    """
    s = unidecode.unidecode(s)
    s = re.sub(r'[^\w\s-]', '', s).strip().lower()
    s = re.sub(r'[-_\s]+', '-', s)
    return s


def load_imdb_cookies():
    script_path = Path(__file__).resolve().parent
    cookie_path = script_path / COOKIE_FNAME

    if cookie_path.exists():
        return {'id': cookie_path.read_text().strip()}
    else:
        raise FileNotFoundError(f'\n\nCreate a file "{COOKIE_FNAME}" in the script directory\n'
                                'and put your IMDb cookie inside.\nFor more info see README.md.')


def fetch_userid(cookies: dict) -> str:
    """User ID is required for exporting any lists. Cookie validity will also be checked here."""
    r = requests.head('http://www.imdb.com/profile', cookies=cookies)
    r.raise_for_status()
    m = re.search(r'ur\d+', r.headers['Location'])
    if not m:
        raise Exception("\n\nCan't log into IMDb.\n"
                        f"Make sure that your IMDb cookie in {COOKIE_FNAME} is correct.\n"
                        'For more info see README.md.')
    return m.group()


def get_fname(url: str, title: str) -> str:
    """Turn an IMDb list into {LIST_OR_USER_ID}_{TITLE_SLUG}.csv."""
    match = re.search(r"..\d{6,}", url, re.MULTILINE)
    if not match:
        raise Exception(f'Can\'t extract list/user ID from {url} for the list "{title}"')
    return match.group() + '_' + slugify(title) + '.csv'


def fetch_lists_info(userid: str, cookies: dict) -> Generator[Dict, None, None]:
    r = requests.get(f'http://www.imdb.com/user/{userid}/lists', cookies=cookies)
    r.raise_for_status()

    # Fetch two special lists: ratings and watchlist
    # /lists has an old link for ratings; easier to hardcode it
    yield {'url': f'/user/{userid}/ratings/',
           'fname': get_fname(userid, 'ratings'),
           'title': 'Ratings'}
    # /lists doesn't have a link for watchlist that can be used for exporting at all
    r_wl = requests.get(f'http://www.imdb.com/user/{userid}/watchlist', cookies=cookies)
    listid = BeautifulSoup(r_wl.text, 'html.parser').find('meta', property='pageId').get('content')
    yield {'url': f'/list/{listid}/',
           'fname': get_fname(userid, 'watchlist'),
           'title': 'Watchlist'}

    # Fetch the rest of user's lists
    links = BeautifulSoup(r.text, 'html.parser').select('a.list-name')
    for link in links:
        url = link.get('href')
        title = link.string
        yield {'url': url,
               'fname': get_fname(url, title),
               'title': title}


def export(mlist: MList, cookies: dict) -> MList:
    """All requests are throttled just in case."""
    time.sleep(0.2)
    print('Downloading:', mlist['title'].replace('\n', ' '))
    r = requests.get(f'http://www.imdb.com{mlist["url"]}export', cookies=cookies)
    r.raise_for_status()
    mlist['content'] = r.content
    return mlist


def zip_all(mlists: Iterable[MList], zip_fname=ZIP_FNAME):
    """Write all downloaded movielists into a zip archive.

    A file with original list names (quoted if multi-line) is also added to the archive.
    """
    with zipfile.ZipFile(zip_fname, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        titles = ''
        for ml in mlists:
            print('  ->', ml['fname'])
            zf.writestr(ml['fname'], ml['content'])
            # new list system allows list titles to be multi-line
            title = f'"{ml["title"]}"' if '\n' in ml['title'] else ml['title']
            titles += f'{ml["fname"]}: {title}\n'
        zf.writestr('lists.txt', titles)


def backup():
    cookies = load_imdb_cookies()
    userid = fetch_userid(cookies)
    print(f'Successfully logged in as user {userid}')
    mlists = fetch_lists_info(userid, cookies)
    zip_all(export(ml, cookies) for ml in mlists)


def pause_before_exit_if_run_with_dblclick_on_win():
    """Pause before exiting if a script is launched with a double click on Windows.

    This will cause the script to show a standard "Press any key" prompt even if it crashes,
    keeping a console window visible.
    Works only on Python 3.3+, older versions have "explorer.exe" as a parent process.
    """
    def prompt():
        try:
            import psutil
            if psutil.Process().parent().name() == 'py.exe':
                print()
                os.system('pause')
        except ImportError:
            pass

    import os
    if os.name == 'nt':
        import atexit
        atexit.register(prompt)


if __name__ == '__main__':
    pause_before_exit_if_run_with_dblclick_on_win()
    backup()
