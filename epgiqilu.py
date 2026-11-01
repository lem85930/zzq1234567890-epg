#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
山东网络台全部频道节目表抓取，输出 XMLTV。

用法：
    python3 iqilu_epg.py
    python3 iqilu_epg.py 2026-11-01
    python3 iqilu_epg.py 2026-11-01 epgshandong.xml

依赖：
    pip3 install requests

说明：
    旧接口 module.iqilu.com 已不可用（连接被重置）。
    现改用 sdxw.iqilu.com 公开接口，仅提供当天及少量历史数据。

时间格式：20261101000000 +0800
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from html import escape
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_API = "https://sdxw.iqilu.com/v1/app/play/program/qilu"

# 山东网络台公开直播频道：频道 ID、显示名称
# ID 对应关系来自齐鲁网新接口
CHANNELS = [
    (24, "山东卫视"),
    (31, "山东新闻频道"),
    (25, "齐鲁频道"),
    (29, "山东生活频道"),
    (26, "山东体育休闲频道"),
    (28, "山东综艺频道"),
    (30, "山东农科频道"),
    (27, "山东文旅频道"),
    (32, "山东少儿频道"),
]


def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    })
    return session


def request_programs(session, date_text, cid, name):
    params = {
        "channelID": cid,
        "date": date_text,
    }
    url = BASE_API + "?" + urlencode(params)
    try:
        response = session.get(url, timeout=(15, 45))
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("接口返回不是对象")
        if data.get("code") != 1:
            raise RuntimeError("接口错误：" + json.dumps(data, ensure_ascii=False))
        items = data.get("data", {}).get("infos") or []
        if not items:
            raise RuntimeError("接口返回节目列表为空（该接口通常只有当天数据）")
        return items, url
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def to_timestamp(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def xml_time(timestamp):
    # 接口返回的是 Unix 秒时间戳，按 Asia/Shanghai (+0800) 格式化
    # 不能依赖 time.localtime（机器时区可能是 UTC）
    bj = timezone(timedelta(hours=8))
    dt = datetime.fromtimestamp(timestamp, bj)
    return dt.strftime("%Y%m%d%H%M%S +0800")


def fetch_all(date_text):
    session = create_session()
    result = []
    errors = []

    for cid, name in CHANNELS:
        try:
            programs, api_url = request_programs(session, date_text, cid, name)
            result.append({
                "id": str(name),
                "name": name,
                "cid": cid,
                "programs": programs,
                "api": api_url,
            })
            print(f"OK {name}: {len(programs)} 条", file=sys.stderr)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(f"ERROR {name}: {exc}", file=sys.stderr)

    return result, errors


def build_xml(date_text, channels, errors):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<tv generator-info-name="Python 3 IQILU EPG Fetcher" '
        'generator-info-url="https://v.iqilu.com/live/sdtv/">',
    ]

    for channel in channels:
        channel_id = escape(channel["id"], quote=True)
        channel_name = escape(channel["name"])
        lines.extend([
            f'  <channel id="{channel_id}">',
            f'    <display-name lang="zh">{channel_name}</display-name>',
            "  </channel>",
        ])

    for channel in channels:
        channel_id = escape(channel["id"], quote=True)
        for item in channel["programs"]:
            start = to_timestamp(item.get("begintime"))
            stop = to_timestamp(item.get("endtime"))
            title = str(item.get("name", "")).strip()
            # 接口返回的节目名常带多余空格
            title = " ".join(title.split())
            if not start or not stop or not title:
                continue
            lines.extend([
                f'  <programme start="{xml_time(start)}" '
                f'stop="{xml_time(stop)}" channel="{channel_id}">',
                f'    <title lang="zh">{escape(title)}</title>',
                "  </programme>",
            ])

    for error in errors:
        # XML 注释不能含连续两个连字符
        safe_error = error.replace("--", "- -")
        lines.append(f"  <!-- 频道抓取失败：{escape(safe_error)} -->")

    lines.append("</tv>")
    return "\n".join(lines) + "\n"


def valid_date(date_text):
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def main():
    date_text = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    if not valid_date(date_text):
        raise SystemExit("日期格式必须是 YYYY-MM-DD")

    channels, errors = fetch_all(date_text)
    xml = build_xml(date_text, channels, errors)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as file:
            file.write(xml)
        print(f"已写入 {output_file}，成功频道 {len(channels)} 个，失败频道 {len(errors)} 个")
    else:
        sys.stdout.write(xml)


if __name__ == "__main__":
    main()