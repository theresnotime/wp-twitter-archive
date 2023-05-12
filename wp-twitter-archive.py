import accounts
import argparse
import config
import difflib
import json
import os
import re
import requests
import time
from pwiki.wiki import Wiki

__version__ = "0.0.1"


def check_available(url: str) -> bool:
    """Check if a URL has been archived on the Internet Archive"""
    result = requests.get(f"{config.IA_URL}/wayback/available?url={url}").json()
    if len(result["archived_snapshots"]) == 0:
        return False
    else:
        return True


def get_latest_snapshot(url: str) -> bool | str:
    """Get the latest snapshot of a URL on the Internet Archive"""
    result = requests.get(f"{config.IA_URL}/wayback/available?url={url}").json()
    if len(result["archived_snapshots"]) == 0:
        return False
    else:
        return (
            result["archived_snapshots"]["closest"]["url"],
            result["archived_snapshots"]["closest"]["timestamp"],
        )


def get_titles() -> list:
    """Get a list of titles from titles.json"""
    with open("titles.json", encoding="utf-8") as f:
        data = json.load(f)
        return data["*"][0]["a"]["*"]


def get_wikitext(title: str) -> str:
    """Get the wikitext of a page"""
    wiki = Wiki(config.SITE, accounts.BOT_USERNAME, accounts.BOT_PASSWORD)
    return wiki.page_text(title)


def save_wikitext(title: str, wikitext: str, summary: str) -> bool:
    """Save the wikitext of a page"""
    wiki = Wiki(config.SITE, accounts.BOT_USERNAME, accounts.BOT_PASSWORD)
    return wiki.edit(title=title, text=wikitext, summary=summary)


def get_cite_tweets(wikitext: str) -> list:
    """Get a list of cited tweets from a page's wikitext"""
    return re.findall(r"{{cite tweet\s?\|(.*?)}}", wikitext, re.IGNORECASE)


def get_tweet_info(cite_params: str) -> list:
    """Get the username and number of a tweet citation"""
    username = re.findall(r"user\s?=\s?(.*?)\s?\|", cite_params, re.IGNORECASE)
    number = re.findall(r"number\s?=\s?(.*?)\s?\|", cite_params, re.IGNORECASE)
    return username, number


def get_tweet_url(username: str, number: str) -> str:
    """Get the URL of a tweet"""
    return f"https://twitter.com/{username}/status/{number}"


def check_already_archived(cite_params: str) -> bool | None:
    """Check if a tweet citation already has an archive-url set"""
    found = re.findall(r"archive-?url\s?=", cite_params, re.IGNORECASE)
    if len(found) == 0:
        return None
    else:
        return found


def iterate_tweets(cited_tweets: list, title: str) -> None:
    """Iterate through a list of cited tweets and work out what to do with them"""
    print(f"[i] Found {len(cited_tweets)} cited tweets")
    wikitext = get_wikitext(title)
    old_wikitext = wikitext
    changes = 0
    for tweet in cited_tweets:
        if check_already_archived(tweet) is None:
            print("[!] Tweet citation does not have an archive-url set")
            tweet_info = get_tweet_info(tweet)
            tweet_url = get_tweet_url(tweet_info[0][0], tweet_info[1][0])
            if check_available(tweet_url):
                latest_snapshot = get_latest_snapshot(tweet_url)
                modified_cite_params = modify_cite_params(
                    tweet, latest_snapshot[0], latest_snapshot[1]
                )
                wikitext = wikitext.replace(tweet, modified_cite_params)
                changes += 1
            else:
                if config.VERBOSE:
                    print(tweet_url)
                print("[!] Tweet has not been archived, let's hope it's still live...")
        else:
            print("[✓] Tweet citation already has an archive-url")
    if wikitext != old_wikitext:
        if config.DIFF_LOG:
            diff = difflib.unified_diff(
                old_wikitext.splitlines(), wikitext.splitlines(), lineterm=""
            )
            with open("logs/diff.log", "a", encoding="utf-8") as f:
                f.write(f"--- {title}\n")
                f.write(f"+++ {title}\n")
                f.write("\n".join(list(diff)))
        add_archive_links(title, wikitext, changes)
    else:
        print("[i] No changes made, skipping")


def modify_cite_params(cite_params: str, archive_url: str, archive_date: str) -> str:
    """Modify the cite params of a tweet citation to include archive-url and archive-date"""
    date = re.sub(r"(\d{4})(\d{2})(\d{2})\d+", r"\1-\2-\3", archive_date)
    cite_params += f"|archive-url={archive_url}|archive-date={date}"
    return cite_params


def add_archive_links(title: str, new_wikitext: str, changes: int) -> None:
    """Add archive-url to tweet citation and save the page"""
    print(f"[+] Adding {changes} archive-url(s) to tweet citation(s) on {title}")
    edit_summary = config.EDIT_SUMMARY.replace("$1", str(changes))
    if config.DRY_RUN is False:
        save_wikitext(title, new_wikitext, edit_summary)
        print(f"[✓] Saved {title}")
    else:
        print(f"[~] Dry run, not saving {title} [{edit_summary}]")


def diff_helper(a: str, b: str, split: str = "\n") -> str:
    """Helper function for diffing strings"""
    for diff in difflib.unified_diff(a.split(split), b.split(split)):
        print(diff)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="WP Twitter Archive",
        description="meow",
        usage="%(prog)s [options]",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-s",
        "--site",
        default=config.SITE,
        help="The wiki to run on",
        type=str,
        metavar=config.SITE,
    )
    parser.add_argument(
        "-l",
        "--limit",
        default=config.RUN_LIMIT,
        help="Limit the number of pages to run on",
        type=int,
        metavar=config.RUN_LIMIT,
    )
    parser.add_argument(
        "-z",
        "--sleep",
        default=config.SLEEP,
        help="Time to sleep between edits",
        type=float,
        metavar=config.SLEEP,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        default=config.VERBOSE,
        help="Be verbose",
        action="store_true",
    )
    parser.add_argument(
        "--diff-log",
        default=config.VERBOSE,
        help="Log diffs to file (in ./logs/)",
        action="store_true",
    )
    parser.add_argument(
        "--dry-run",
        default=config.DRY_RUN,
        help="Don't save anything",
        action="store_true",
    )
    args = parser.parse_args()

    # Merge with defaults
    config.SITE = args.site
    config.RUN_LIMIT = args.limit
    config.SLEEP = args.sleep
    config.VERBOSE = args.verbose
    config.DIFF_LOG = args.diff_log
    config.DRY_RUN = args.dry_run

    # Print some info
    print(f"WP Twitter Archiver thing v{__version__}")
    if config.DRY_RUN:
        print("[!] Doing a dry run")
    if config.DIFF_LOG:
        if not os.path.exists("logs"):
            os.makedirs("logs")
        print("[!] Logging diffs to file")
    print(f"[i] Running on {config.SITE}")
    print(f"[i] Limiting to {config.RUN_LIMIT} pages")
    print(f"[i] Sleeping for {config.SLEEP} seconds between requests")

    count = 0
    titles = get_titles()
    for title in titles:
        if count < config.RUN_LIMIT:
            count += 1
            print(f"\n[{count}/{config.RUN_LIMIT}] {title}")
            wikitext = get_wikitext(title)
            cited_tweets = get_cite_tweets(wikitext)
            iterate_tweets(cited_tweets, title)
            time.sleep(config.SLEEP)