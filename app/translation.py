from __future__ import annotations

import re
from typing import Optional


SPORT_NAMES = {
    "mlb": "MLB",
    "nba": "NBA",
    "nhl": "NHL",
    "nfl": "NFL",
    "ncaamb": "NCAA 男篮",
    "ncaafb": "NCAA 橄榄球",
}

TEAM_NAMES = {
    "ari": "亚利桑那响尾蛇",
    "atl": "亚特兰大勇士",
    "bal": "巴尔的摩金莺",
    "bos": "波士顿红袜",
    "chc": "芝加哥小熊",
    "cws": "芝加哥白袜",
    "cin": "辛辛那提红人",
    "cle": "克利夫兰守护者",
    "col": "科罗拉多洛矶",
    "det": "底特律老虎",
    "hou": "休斯敦太空人",
    "kc": "堪萨斯城皇家",
    "laa": "洛杉矶天使",
    "lad": "洛杉矶道奇",
    "mia": "迈阿密马林鱼",
    "mil": "密尔沃基酿酒人",
    "min": "明尼苏达双城",
    "nym": "纽约大都会",
    "nyy": "纽约扬基",
    "oak": "奥克兰运动家",
    "ath": "运动家",
    "phi": "费城费城人",
    "pit": "匹兹堡海盗",
    "sd": "圣迭戈教士",
    "sea": "西雅图水手",
    "sf": "旧金山巨人",
    "stl": "圣路易斯红雀",
    "tb": "坦帕湾光芒",
    "tex": "得州游骑兵",
    "tor": "多伦多蓝鸟",
    "wsh": "华盛顿国民",
    "car": "卡罗莱纳飓风",
    "las": "拉斯维加斯金骑士",
    "vgk": "拉斯维加斯金骑士",
    "edm": "埃德蒙顿油人",
    "fla": "佛罗里达美洲豹",
    "dal": "达拉斯星",
    "nyr": "纽约游骑兵",
    "nyi": "纽约岛人",
    "nj": "新泽西魔鬼",
    "njd": "新泽西魔鬼",
    "tor-maple": "多伦多枫叶",
}

OUTCOME_NAMES = {
    "over": "大分",
    "under": "小分",
    "yes": "是",
    "no": "否",
    "draw": "平局",
    "boston red sox": "波士顿红袜",
    "new york yankees": "纽约扬基",
    "new york mets": "纽约大都会",
    "pittsburgh pirates": "匹兹堡海盗",
    "atlanta braves": "亚特兰大勇士",
    "washington nationals": "华盛顿国民",
    "arizona diamondbacks": "亚利桑那响尾蛇",
    "los angeles angels": "洛杉矶天使",
    "los angeles dodgers": "洛杉矶道奇",
    "milwaukee brewers": "密尔沃基酿酒人",
    "colorado rockies": "科罗拉多洛矶",
    "carolina hurricanes": "卡罗莱纳飓风",
    "hurricanes": "卡罗莱纳飓风",
}


def _line(value: Optional[str]) -> str:
    text = str(value or "").strip()
    return text.replace("pt", ".")


def _date(parts: list[str]) -> str:
    if len(parts) < 3:
        return ""
    try:
        year, month, day = [int(item) for item in parts[:3]]
    except ValueError:
        return ""
    return f"{year}/{month:02d}/{day:02d}"


def _team(code: str) -> str:
    return TEAM_NAMES.get(code.lower(), code.upper())


def _humanize_title(text: str) -> str:
    title = str(text or "").strip()
    if not title:
        return ""
    replacements = {
        "Will ": "",
        " win the NBA game?": " 赢下 NBA 比赛？",
        " win the MLB game?": " 赢下 MLB 比赛？",
        " win the NHL game?": " 赢下 NHL 比赛？",
        " total over ": " 总分大于 ",
        " total under ": " 总分小于 ",
    }
    for source, target in replacements.items():
        title = title.replace(source, target)
    return title


def translate_market(slug: str = "", title: str = "") -> str:
    slug = str(slug or "").strip().lower()
    parts = slug.split("-") if slug else []
    if len(parts) >= 7 and parts[0] in SPORT_NAMES and re.fullmatch(r"\d{4}", parts[3] or ""):
        sport = SPORT_NAMES[parts[0]]
        away = _team(parts[1])
        home = _team(parts[2])
        date_text = _date(parts[3:6])
        market_parts = parts[6:]
        market_text = "市场"
        if market_parts[:1] == ["total"] and len(market_parts) >= 2:
            market_text = f"总分 { _line(market_parts[1]) }"
        elif market_parts[:1] == ["spread"] and len(market_parts) >= 3:
            side = "主队" if market_parts[1] == "home" else "客队" if market_parts[1] == "away" else market_parts[1]
            market_text = f"{side}让分 {_line(market_parts[2])}"
        elif market_parts[:1] in (["moneyline"], ["winner"]):
            market_text = "胜负盘"
        prefix = f"{sport} {away} vs {home}"
        return "｜".join(item for item in (prefix, market_text, date_text) if item)
    return _humanize_title(title) or slug or "-"


def translate_outcome(outcome: str = "") -> str:
    text = str(outcome or "").strip()
    if not text:
        return "-"
    key = text.lower()
    if key in OUTCOME_NAMES:
        return OUTCOME_NAMES[key]
    slug_key = key.replace(" ", "-")
    if slug_key in TEAM_NAMES:
        return TEAM_NAMES[slug_key]
    return text
