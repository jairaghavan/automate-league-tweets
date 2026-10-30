import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import tweepy
from espn_api.football import League

STATE_FILE = Path("seen_trades.json")
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
#HASHTAG = ""  # e.g. "#MyLeagueName"


def get_league():
    now = datetime.now()
    default_year = now.year if now.month >= 6 else now.year - 1
    return League(
        league_id=int(os.environ["ESPN_LEAGUE_ID"]),
        year=int(os.getenv("ESPN_YEAR", default_year)),
        espn_s2=os.environ["ESPN_S2"],
        swid=os.environ["ESPN_SWID"],
    )


def team_name(team):
    return getattr(team, "team_name", str(team))


def extract_trades(league):
    """Return a list of (trade_id, {team_name: [players]}) for processed trades."""
    trades = []
    for activity in league.recent_activity(size=50):
        moves = {}
        for action in activity.actions:
            team, kind, player = action[0], action[1], action[2]
            if "TRADE" not in str(kind).upper():
                continue
            moves.setdefault(team_name(team), []).append(str(player))
        if not moves:
            continue
        raw = json.dumps([activity.date, moves], sort_keys=True, default=str)
        trades.append((hashlib.sha1(raw.encode()).hexdigest()[:16], moves))
    return trades


def format_tweet(moves):
    lines = ["🚨 TRADE ALERT", ""]
    for team, players in moves.items():
        lines.append(f"{team} receives: {', '.join(players)}")
    #if HASHTAG:
    #    lines += ["", HASHTAG]
    text = "\n".join(lines)
    return text if len(text) <= 280 else text[:277] + "..."


def post_tweet(text):
    if DRY_RUN:
        print("--- DRY RUN TWEET ---")
        print(text)
        print("---------------------")
        return
    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )
    client.create_tweet(text=text)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return None


def save_state(seen):
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=2))


def main():
    trades = extract_trades(get_league())
    seen = load_state()

    # First run: record existing trades without tweeting, so old trades
    # don't get posted all at once.
    if seen is None:
        save_state({tid for tid, _ in trades})
        print(f"First run: recorded {len(trades)} existing trades, no tweets sent.")
        return

    seen = set(seen)
    new = [(tid, m) for tid, m in trades if tid not in seen]
    print(f"{len(new)} new trade(s).")
    for tid, moves in reversed(new):  # oldest first
        post_tweet(format_tweet(moves))
        seen.add(tid)
        save_state(seen)  # save after each tweet so a crash can't cause repeats


if __name__ == "__main__":
    main()
