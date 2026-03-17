#!/usr/bin/env python3
"""
deploy_morning.py
=================
朝刊HTMLをGitHub Pagesに自動デプロイし、
LINE U&I株倶楽部グループに自動通知するスクリプト。

使い方:
  python3 deploy_morning.py <HTMLファイルパス> <YYYY-MM-DD> "<見出し>"

例:
  python3 deploy_morning.py ~/Desktop/UI_KabuClub_HP/morning_20260318.html 2026-03-18 "NVIDIA GTC効果で反発、本日FOMC"
"""

import sys, os, shutil, subprocess, json
from datetime import datetime
try:
    import urllib.request as urlreq
    import urllib.error
except ImportError:
    pass

GITHUB_USERNAME = "yskzz121"
REPO_NAME       = "ui-kabu-club"
REPO_DIR        = os.path.expanduser("~/ui-kabu-club")
MORNING_DIR     = os.path.join(REPO_DIR, "morning")
PAGES_BASE_URL  = f"https://{GITHUB_USERNAME}.github.io/{REPO_NAME}"
LINE_CONFIG     = os.path.expanduser("~/.line_config")

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

def run(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd or REPO_DIR,
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"コマンド失敗: {cmd}\n{result.stderr}")
    return result.stdout.strip()

def load_line_config():
    config = {}
    if not os.path.exists(LINE_CONFIG):
        return config
    with open(LINE_CONFIG) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    return config

def send_line(token, group_id, message, max_retries=3):
    import time
    data = json.dumps({
        "to": group_id,
        "messages": [{"type": "text", "text": message}]
    }).encode("utf-8")
    for attempt in range(1, max_retries + 1):
        req = urlreq.Request(
            "https://api.line.me/v2/bot/message/push",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urlreq.urlopen(req, timeout=10) as res:
                return res.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                wait = int(e.headers.get("Retry-After", 5 * attempt))
                print(f"  ⏳ レート制限（429）。{wait}秒後にリトライ ({attempt}/{max_retries})...")
                time.sleep(wait)
            else:
                print(f"⚠️  LINE送信エラー: {e}")
                return False
        except Exception as e:
            print(f"⚠️  LINE送信エラー: {e}")
            return False
    return False

def update_latest_html(date_obj):
    """latest.html を最新号へのリダイレクトに更新"""
    y = date_obj.strftime("%Y")
    m = date_obj.strftime("%m")
    d = date_obj.strftime("%d").lstrip("0")
    rel_path = f"{y}/{m}/{int(d)}.html"
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url={rel_path}">
<title>U&amp;I株倶楽部 朝刊 - 最新号</title>
</head>
<body>
<p>最新号にリダイレクトしています... <a href="{rel_path}">こちらをクリック</a></p>
</body>
</html>
"""
    with open(os.path.join(MORNING_DIR, "latest.html"), "w", encoding="utf-8") as f:
        f.write(html)

def get_existing_editions():
    """既存の朝刊一覧を取得（日付降順）"""
    editions = []
    for root, dirs, files in os.walk(MORNING_DIR):
        for fname in files:
            if fname.endswith(".html") and fname not in ("index.html", "latest.html"):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, MORNING_DIR)
                # 2026/03/13.html -> parse date
                parts = rel.replace("\\", "/").split("/")
                if len(parts) == 3:
                    try:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2].replace(".html", ""))
                        dt = datetime(y, m, d)
                        editions.append((dt, rel))
                    except ValueError:
                        pass
    editions.sort(key=lambda x: x[0], reverse=True)
    return editions

def extract_headline(html_path):
    """HTMLファイルからTOP STORYのタイトルを抽出"""
    import re
    try:
        with open(html_path, encoding="utf-8") as f:
            content = f.read(20000)
        # summary-topic を探す
        m = re.search(r'class="summary-topic[^"]*">(.*?)</span>', content)
        if m:
            return re.sub(r'<[^>]+>', '', m.group(1)).strip()
    except Exception:
        pass
    return ""

def rebuild_archive_index(editions):
    """アーカイブindex.htmlを再構築"""
    # 月別にグループ化
    months = {}
    for dt, rel in editions:
        key = dt.strftime("%Y年%-m月")
        if key not in months:
            months[key] = []
        weekday = WEEKDAYS[dt.weekday()]
        day_str = f"{dt.month}月{dt.day}日（{weekday}）"

        # 見出しをHTMLから抽出
        fpath = os.path.join(MORNING_DIR, rel)
        headline = extract_headline(fpath)

        vol = len(editions) - editions.index((dt, rel))
        subtitle = f"Vol.{vol}"
        if headline:
            subtitle += f" — {headline}"

        months[key].append((dt, rel, day_str, subtitle))

    month_html = ""
    for month_key in sorted(months.keys(), reverse=True):
        items = months[month_key]
        items.sort(key=lambda x: x[0], reverse=True)
        li_html = ""
        for dt, rel, day_str, subtitle in items:
            li_html += f'      <li><a href="{rel}"><span class="edition-date">{day_str}</span><span class="edition-day">{subtitle}</span></a></li>\n'
        month_html += f"""
  <div class="month-group">
    <div class="month-label">{month_key}</div>
    <ul class="edition-list">
{li_html}    </ul>
  </div>
"""

    index_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>U&amp;I株倶楽部 朝刊アーカイブ</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&family=Noto+Serif+JP:wght@700;900&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #0d1117;
  --surface: #161b22;
  --border: #30363d;
  --text: #e6edf3;
  --text-sub: #8b949e;
  --accent: #58a6ff;
  --green: #2ea043;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Noto Sans JP', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  padding: 40px 20px;
}}
.container {{ max-width: 800px; margin: 0 auto; }}
.header {{
  text-align: center;
  margin-bottom: 40px;
  padding-bottom: 24px;
  border-bottom: 2px solid var(--border);
}}
.header h1 {{
  font-family: 'Noto Serif JP', serif;
  font-size: 2em;
  font-weight: 900;
  margin-bottom: 8px;
}}
.header p {{ color: var(--text-sub); font-size: 0.95em; }}
.month-group {{ margin-bottom: 32px; }}
.month-label {{
  font-size: 1.1em;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}}
.edition-list {{ list-style: none; }}
.edition-list li {{ margin-bottom: 4px; }}
.edition-list a {{
  display: block;
  padding: 12px 16px;
  border-radius: 8px;
  color: var(--text);
  text-decoration: none;
  transition: background 0.15s;
  font-size: 0.95em;
}}
.edition-list a:hover {{ background: var(--surface); }}
.edition-date {{ font-weight: 700; margin-right: 12px; }}
.edition-day {{ color: var(--text-sub); font-size: 0.85em; }}
.back-link {{
  display: inline-block;
  margin-top: 24px;
  color: var(--accent);
  text-decoration: none;
  font-size: 0.9em;
}}
.back-link:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📰 朝刊アーカイブ</h1>
    <p>U&amp;I株倶楽部 マーケット朝刊のバックナンバー</p>
  </div>
{month_html}
  <a class="back-link" href="/ui-kabu-club/">← ポータルに戻る</a>
</div>
</body>
</html>
"""
    with open(os.path.join(MORNING_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

def main():
    if len(sys.argv) < 3:
        print("使い方: python3 deploy_morning.py <HTMLパス> <YYYY-MM-DD> [見出し]")
        sys.exit(1)

    html_path = os.path.abspath(sys.argv[1])
    date_str = sys.argv[2]
    headline = sys.argv[3] if len(sys.argv) > 3 else ""

    if not os.path.exists(html_path):
        print(f"❌ ファイルが見つかりません: {html_path}")
        sys.exit(1)

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    y = date_obj.strftime("%Y")
    m = date_obj.strftime("%m")
    d = str(date_obj.day)
    weekday = WEEKDAYS[date_obj.weekday()]

    print(f"📰 U&I株倶楽部 朝刊デプロイ")
    print(f"   日付: {y}年{int(m)}月{d}日（{weekday}）")
    print()

    # 1. git pull
    print("1️⃣  リポジトリを最新化...")
    run("git pull --rebase", cwd=REPO_DIR)

    # 2. HTMLをコピー
    dest_dir = os.path.join(MORNING_DIR, y, m)
    os.makedirs(dest_dir, exist_ok=True)
    dest_file = os.path.join(dest_dir, f"{d}.html")
    shutil.copy2(html_path, dest_file)
    print(f"2️⃣  HTMLをコピー → morning/{y}/{m}/{d}.html")

    # 3. latest.html 更新
    update_latest_html(date_obj)
    print("3️⃣  latest.html を更新")

    # 4. アーカイブindex.html 再構築
    editions = get_existing_editions()
    rebuild_archive_index(editions)
    print("4️⃣  アーカイブ index.html を再構築")

    # 5. git add → commit → push
    print("5️⃣  Git コミット & プッシュ...")
    run("git add -A", cwd=REPO_DIR)
    commit_msg = f"📰 朝刊 {y}/{int(m)}/{d}（{weekday}）"
    run(f'git commit -m "{commit_msg}"', cwd=REPO_DIR)
    run("git push", cwd=REPO_DIR)
    print("   ✅ GitHub Pages にプッシュ完了")

    # 6. LINE通知
    print("6️⃣  LINE通知...")
    line_cfg = load_line_config()
    token = line_cfg.get("LINE_TOKEN")
    group_id = line_cfg.get("LINE_GROUP_ID")

    if token and group_id:
        url = f"{PAGES_BASE_URL}/morning/{y}/{m}/{d}.html"
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
        msg = (
            f"📰 【U&I株倶楽部 朝刊】{y}年{int(m)}月{d}日（{weekday}）\n"
        )
        if headline:
            msg += f"💬 {headline}\n"
        msg += (
            f"\n"
            f"🔗 朝刊はこちら:\n"
            f"{url}\n"
            f"\n"
            f"📚 バックナンバー:\n"
            f"{PAGES_BASE_URL}/morning/\n"
            f"\n"
            f"({now_str} 自動配信)"
        )
        ok = send_line(token, group_id, msg)
        if ok:
            print("   ✅ LINE通知 送信完了")
        else:
            print("   ⚠️  LINE通知 送信失敗（レポートは公開済み）")
    else:
        print("   ⚠️  LINE設定が見つかりません（スキップ）")

    print()
    url = f"{PAGES_BASE_URL}/morning/{y}/{m}/{d}.html"
    print(f"🎉 デプロイ完了!")
    print(f"   📎 {url}")

if __name__ == "__main__":
    main()
