import json
import os
import re
import requests
from defusedxml import ElementTree as ET
from app_paths import get_data_dir

RSS_FILE = os.path.join(get_data_dir(), "rss.json")

class RSSManager:
    def __init__(self):
        self.feeds = {} # url -> {'alias': str, 'last_update': float, 'articles': []}
        self.rules = [] # list of {'pattern': str, 'enabled': bool}
        self.load()

    def load(self):
        if os.path.exists(RSS_FILE):
            try:
                with open(RSS_FILE, 'r') as f:
                    data = json.load(f)
                    self.feeds = data.get('feeds', {})
                    self.rules = data.get('rules', [])
            except Exception:
                return

    def save(self):
        data = {'feeds': self.feeds, 'rules': self.rules}
        try:
            with open(RSS_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to save RSS: {e}")

    def add_feed(self, url, alias=""):
        if url not in self.feeds:
            self.feeds[url] = {'alias': alias, 'last_update': 0, 'articles': []}
            self.save()
            return True
        return False

    def remove_feed(self, url):
        if url in self.feeds:
            del self.feeds[url]
            self.save()

    def add_rule(self, pattern, rule_type="accept", scope=None):
        """
        Add a rule.
        scope: None for global, or a list of feed URLs this rule applies to.
        """
        self.rules.append({'pattern': pattern, 'enabled': True, 'type': rule_type, 'scope': scope})
        self.save()

    def remove_rule(self, index):
        if 0 <= index < len(self.rules):
            del self.rules[index]
            self.save()

    def update_rule(self, index, data):
        if 0 <= index < len(self.rules):
            self.rules[index].update(data)
            self.save()

    def reset_all(self):
        self.feeds = {}
        self.rules = []
        self.save()

    def fetch_feed(self, url):
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            
            # Simple RSS/Atom parser
            root = ET.fromstring(r.content)
            articles = []
            
            # Handle RSS 2.0
            for item in root.findall('./channel/item'):
                title = item.find('title')
                link = item.find('link') # usually web link
                enclosure = item.find('enclosure') # usually torrent url
                
                # Torrent link might be in link or enclosure
                t_url = ""
                if enclosure is not None and enclosure.get('type') == 'application/x-bittorrent':
                    t_url = enclosure.get('url')
                elif link is not None:
                    t_url = link.text
                
                if title is not None and t_url:
                    articles.append({
                        'title': title.text,
                        'link': t_url,
                        'uid': t_url # simplified UID
                    })
            
            if url in self.feeds:
                self.feeds[url]['articles'] = articles
                import time
                self.feeds[url]['last_update'] = time.time()
                self.feeds[url]['last_error'] = None # Clear error
            
            return articles
        except Exception as e:
            err_msg = str(e)
            print(f"RSS Fetch Error {url}: {err_msg}")
            if url in self.feeds:
                self.feeds[url]['last_error'] = err_msg
            return []

    def get_matches(self, articles, feed_url=None):
        matches = []
        for a in articles:
            # Filter rules applicable to this feed
            applicable_rules = []
            for r in self.rules:
                if not r.get('enabled', True):
                    continue
                scope = r.get('scope')
                # If scope is None, it's global. If feed_url matches scope, it applies.
                if scope is None or (feed_url and feed_url in scope):
                    applicable_rules.append(r)

            # 1. Reject Check
            rejected = False
            for rule in applicable_rules:
                if rule.get('type') == 'reject':
                    try:
                        if re.search(rule['pattern'], a['title'], re.IGNORECASE):
                            rejected = True
                            break
                    except re.error:
                        continue
            if rejected:
                continue

            # 2. Accept Check
            for rule in applicable_rules:
                if rule.get('type', 'accept') == 'accept':
                    try:
                        if re.search(rule['pattern'], a['title'], re.IGNORECASE):
                            matches.append(a)
                            break
                    except re.error:
                        continue
        return matches

    def import_flexget_config(self, path):
        try:
            import yaml
        except ImportError:
            raise Exception("PyYAML is required to import FlexGet configs.")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            raise Exception(f"Failed to parse YAML: {e}")

        if not config or 'tasks' not in config:
            return 0, 0

        from config_manager import ConfigManager
        cm = ConfigManager()
        existing_profiles = cm.get_profiles()
        
        tasks = config.get('tasks', {})
        count_feeds = 0
        count_rules = 0
        
        # Helper to avoid dupes
        def profile_exists(url, user):
            for pid, p in existing_profiles.items():
                if p['url'] == url and p['user'] == user:
                    return True
            return False

        for task_name, task_config in tasks.items():
            if not isinstance(task_config, dict):
                continue

            # 0. Profile (qBittorrent)
            qbit = task_config.get('qbittorrent')
            if qbit and isinstance(qbit, dict):
                host = qbit.get('host', 'localhost')
                port = qbit.get('port', 8080)
                user = qbit.get('username', '')
                pw = qbit.get('password', '')
                
                url = f"http://{host}:{port}"
                if not profile_exists(url, user):
                    cm.add_profile(f"{task_name} qBit", "qbittorrent", url, user, pw)

            # 1. RSS Feeds (Collect task URLs for scoping)
            task_feed_urls = []
            
            rss_entry = task_config.get('rss')
            if rss_entry:
                url = ""
                if isinstance(rss_entry, str):
                    url = rss_entry
                elif isinstance(rss_entry, dict):
                    url = rss_entry.get('url')
                
                if url:
                    task_feed_urls.append(url)
                    if self.add_feed(url, f"{task_name} RSS"):
                        count_feeds += 1
            
            inputs = task_config.get('inputs', [])
            if isinstance(inputs, list):
                for inp in inputs:
                    if isinstance(inp, dict) and 'rss' in inp:
                        val = inp['rss']
                        url = ""
                        if isinstance(val, str):
                            url = val
                        elif isinstance(val, dict):
                            url = val.get('url')
                        
                        if url:
                            task_feed_urls.append(url)
                            if self.add_feed(url, f"{task_name} RSS"):
                                count_feeds += 1

            # 2. Rules (Regex) - Scope them to task_feed_urls
            regexp = task_config.get('regexp', {})
            if isinstance(regexp, dict):
                # Accept
                accept = regexp.get('accept', [])
                if isinstance(accept, list):
                    for pattern in accept:
                        self.add_rule(str(pattern), "accept", scope=task_feed_urls)
                        count_rules += 1
                # Reject
                reject = regexp.get('reject', [])
                if isinstance(reject, list):
                    for pattern in reject:
                        self.add_rule(str(pattern), "reject", scope=task_feed_urls)
                        count_rules += 1
            
            # 3. Series - Scope them to task_feed_urls
            series = task_config.get('series', [])
            if isinstance(series, list):
                for s in series:
                    name = ""
                    if isinstance(s, str):
                        name = s
                    elif isinstance(s, dict):
                        name = list(s.keys())[0] if s else ""
                    
                    if name:
                        pattern = re.escape(name).replace(r"\ ", ".*")
                        self.add_rule(pattern, "accept", scope=task_feed_urls)
                        count_rules += 1
                        
            # 4. Accept All - Scope them to task_feed_urls
            if task_config.get('accept_all'):
                self.add_rule(".*", "accept", scope=task_feed_urls)
                count_rules += 1
        
        return count_feeds, count_rules
