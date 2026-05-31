"""
scripts/scrape.py
每月自动抓取 @aleabitoreddit 最新推文，追加到 data/latest_tweets.csv
"""
import asyncio
import csv
import os
import pandas as pd
from pathlib import Path
from twscrape import API

USERNAME = os.environ["X_USERNAME"]
PASSWORD = os.environ["X_PASSWORD"]
EMAIL    = os.environ["X_EMAIL"]
COOKIES  = os.environ.get("X_COOKIES", "")
TARGET   = "aleabitoreddit"
OUT_FILE = Path("data/latest_tweets.csv")


async def main():
    api = API()

    if COOKIES:
        await api.pool.add_account(
            username=USERNAME,
            password=PASSWORD,
            email=EMAIL,
            email_password=PASSWORD,
            cookies=COOKIES
        )
    else:
        await api.pool.add_account(USERNAME, PASSWORD, EMAIL, EMAIL)

    await api.pool.login_all()

    user = await api.user_by_login(TARGET)
    if not user:
        print(f"Could not find @{TARGET}")
        return

    print(f"Found: {user.displayname} — scraping tweets...")

    # 读取已有数据，避免重复
    existing_ids = set()
    if OUT_FILE.exists():
        existing = pd.read_csv(OUT_FILE)
        existing_ids = set(existing["id"].astype(str).tolist())
        print(f"Existing tweets: {len(existing_ids)}")

    new_rows = []
    async for tweet in api.user_tweets_and_replies(user.id, limit=200):
        if str(tweet.id) in existing_ids:
            continue
        new_rows.append({
            "id":           tweet.id,
            "date":         tweet.date.strftime("%Y-%m-%d %H:%M:%S"),
            "content":      tweet.rawContent,
            "likeCount":    tweet.likeCount,
            "retweetCount": tweet.retweetCount,
            "url":          tweet.url,
        })

    if not new_rows:
        print("No new tweets found.")
        return

    print(f"New tweets: {len(new_rows)}")

    # 追加写入
    write_header = not OUT_FILE.exists()
    with open(OUT_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["id","date","content","likeCount","retweetCount","url"])
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)

    print(f"Saved to {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
