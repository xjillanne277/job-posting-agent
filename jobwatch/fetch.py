"""
meta's servers are picky about request headers. the first real run got a
400 Bad Request on the sitemap even though it loads fine in a browser, so
instead of guessing the one magic combo i just try a few "profiles" in order
and stick with whichever one works first.
"""

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

PROFILES = [
    # 1. look like a real chrome tab, including the sec-fetch stuff chrome sends
    ("full browser", {
        "User-Agent": CHROME_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "sec-ch-ua": '"Chromium";v="129", "Not=A?Brand";v="8", "Google Chrome";v="129"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }),
    # 2. just be honest about being a script (sitemaps are meant for bots anyway)
    ("plain script", {
        "User-Agent": "job-posting-agent/1.0 (+https://github.com/xjillanne277/job-posting-agent)",
        "Accept": "*/*",
    }),
    # 3. whatever requests sends by default
    ("requests default", {}),
]

_working = None  # index of the profile that worked last, so i dont retry the bad ones every page


def get(session, url, timeout=30):
    """session.get but tries each header profile until one isnt rejected.
    404s get returned right away (that just means the posting is gone)"""
    global _working
    order = list(range(len(PROFILES)))
    if _working is not None:
        order.remove(_working)
        order.insert(0, _working)

    resp = None
    for i in order:
        name, headers = PROFILES[i]
        resp = session.get(url, headers=headers, timeout=timeout)
        if resp.status_code < 400 or resp.status_code == 404:
            if _working != i:
                print(f"  ({name} headers worked for {url})")
            _working = i
            return resp
        print(f"  {name} headers got {resp.status_code} from {url}")
    return resp  # everything failed, caller will raise_for_status on this
