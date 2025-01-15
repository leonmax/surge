#!/usr/bin/env python
import argparse
import dataclasses
import datetime
import json
import os
import re
import shutil
import time
import tempfile
from urllib import request
from urllib.error import URLError
from pathlib import Path

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
SURGE_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~com~nssurge~inc/Documents"
)
URL_PREFIX = "https://raw.githubusercontent.com/leonmax/rules/master"


@dataclasses.dataclass
class ManagedProfile:
    url: str
    interval: int = 86400  # How often the profile is updated.
    strict: bool = False  # well we basically ignored that

    def download(self, filename):
        try:
            request.urlretrieve(self.url, filename)
        except URLError as e:
            print(f"⚠️  Failed to download: {e.reason}, will use cached version.")

    @staticmethod
    def reload(filename, force_update=False):
        with open(filename, "r") as f:
            line = f.readline()
            if not line.startswith("#!MANAGED-CONFIG"):
                raise Exception(f"⚠️  {filename} is not a managed config!")

        values = line.split(" ")
        profile = ManagedProfile(url=values[1])
        for kv in values[2:]:
            k, v = kv.split("=")
            if k == "interval":
                profile.interval = int(v)
            if k == "strict":
                profile.strict = bool(v)

        mtime = Path(filename).stat().st_mtime
        if force_update:
            print(f"ℹ️  Downloading managed config from {profile.url}. It's forced.")
            profile.download(filename)
        elif time.time() > mtime + profile.interval:
            print(
                f"ℹ️  Downloading managed config from {profile.url}. It's older than {profile.interval} secs."
            )
            profile.download(filename)
        else:
            mdatetime = datetime.datetime.strftime(
                datetime.datetime.fromtimestamp(mtime), "%Y/%m/%m %H:%M:%S"
            )
            print(f"ℹ️  Managed config is as new as {mdatetime}.")


@dataclasses.dataclass
class ProxyGroup:
    name: str
    group_type: str  # select, url-test, fallback, load-balance, comment-or-empty-line
    proxies: list[str] = dataclasses.field(default_factory=list)
    properties: dict[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def parse_line(cls, line):
        if line.lstrip().startswith("#") or not line.strip():
            return ProxyGroup(name=line, group_type="comment-or-empty-line")
        m = re.match(r"^(?P<name>[^=]+)=\s*(?P<group_type>[^,]+)(?P<values>.*)", line)
        if m:
            properties = {}
            proxies = []
            for value in m.group("values").split(","):
                value = value.strip()
                if not value:
                    continue
                if "=" in value:
                    k, v = value.split("=", 1)
                    properties[k] = v
                else:
                    proxies.append(value)
            return ProxyGroup(
                name=m.group("name").strip(),
                group_type=m.group("group_type"),
                proxies=proxies,
                properties=properties,
            )
        print("failed to parse line: " + line)
        return None

    def extend(self, proxy_group):
        if self.name != proxy_group.name:
            raise Exception(
                f"⚠️  Cannot extend proxy group {self.name} with {proxy_group.name}"
            )
        self.proxies.extend(proxy_group.proxies)
        self.properties.update(proxy_group.properties)

    def __str__(self):
        if self.group_type == "comment-or-empty-line":
            return self.name
        parts = [f"{self.name} = {self.group_type}"]
        for proxy in self.proxies:
            parts.append(proxy)
        for k, v in self.properties.items():
            parts.append(f"{k}={v}")
        return ", ".join(parts) + "\n"


@dataclasses.dataclass
class Proxy:
    name: str
    proxy_type: (
        str  # direct, reject, ssh, http, snell, trojan, ss, comment-or-empty-line
    )
    host: str | None
    port: int
    properties: dict[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def parse_line(cls, line):
        if line.lstrip().startswith("#") or not line.strip():
            return Proxy(
                name=line, proxy_type="comment-or-empty-line", host=None, port=-1
            )
        m = re.match(
            r"^(?P<name>[^=]+)=\s*(?P<proxy_type>[^,]+),\s*(?P<host>[^,]+),\s*(?P<port>[^,]+),\s*(?P<values>.*)",
            line,
        )
        if m:
            properties = {}
            for value in m.group("values").split(","):
                value = value.strip()
                if not value:
                    continue
                if "=" in value:
                    k, v = value.split("=", 1)
                    properties[k] = v
            return Proxy(
                name=m.group("name").strip(),
                proxy_type=m.group("proxy_type"),
                host=m.group("host"),
                port=int(m.group("port")),
                properties=properties,
            )
        print("failed to parse line: " + line)
        return None

    def __str__(self):
        if self.proxy_type == "comment-or-empty-line":
            return self.name
        parts = [f"{self.name} = {self.proxy_type}, {self.host}, {self.port}"]
        for k, v in self.properties.items():
            parts.append(f"{k}={v}")
        return ", ".join(parts) + "\n"


@dataclasses.dataclass
class Item:
    name: str
    config_type: str  # values, comment-or-empty-line
    values: list[str] | None

    @classmethod
    def parse_line(cls, line: str) -> "Item | None":
        if line.lstrip().startswith("#") or not line.strip():
            return Item(name=line, config_type="comment-or-empty-line", values=None)
        m = re.match(r"^(?P<name>[^=]+)=\s*(?P<values>.*)", line)
        if m:
            return Item(
                name=m.group("name").strip(),
                config_type="values",
                values=m.group("values").split(","),
            )
        print("failed to parse line: " + line)
        return None

    def __str__(self):
        if self.config_type == "comment-or-empty-line":
            return self.name
        return f"{self.name} = {', '.join(self.values)}\n"


class SurgeProfile:
    def __init__(self, file):
        self._file = file
        self._section_names = []
        self._sections = {}
        self._managed_config = None
        self.load()

    def load(self):
        with open(self._file, "r") as f:
            lines = f.readlines()
        cur = []
        self._section_names.append("")
        self._sections[""] = cur
        for line in lines:
            if line.startswith("#!MANAGED-CONFIG"):
                self._managed_config = line
                continue
            m = re.match(r"\[(.*)]\n", line)
            if m:
                section_name = m.group(1)
                cur = []
                self._section_names.append(section_name)
                self._sections[section_name] = cur
            else:
                line = line if line.endswith("\n") else line + "\n"
                cur.append(line)

    def remove_managed_line(self):
        self._managed_config = None

    def add_managed_line(self, url, interval=86400, strict=False):
        self._managed_config = (
            f"#!MANAGED-CONFIG {url} interval={interval} strict={strict}\n"
        )

    def save(self, as_file=None):
        _file = as_file or self._file
        Path(_file).parent.mkdir(parents=True, exist_ok=True)
        with open(_file, "w+") as f:
            if self._managed_config:
                f.write(self._managed_config)

            for section_name in self.section_names:
                if section_name:
                    f.write(f"[{section_name}]\n")
                lines = self.get_section(section_name)
                # print(f"ℹ️  Writing section {section_name}: {len(lines)}")
                f.writelines(lines)

    def get_section(self, section_name):
        return self._sections[section_name] if section_name in self._sections else []

    def merge_items(self, section_name, lines, item_class):
        # Map item name to item
        item_orders = []
        items = {}
        for line in self._sections[section_name]:
            item = item_class.parse_line(line)
            if item:
                item_orders.append(item.name)
                items[item.name] = item

        # Merge customized items
        self._sections[section_name] = ["# region: Customized\n"]
        for line in lines:
            new_item = item_class.parse_line(line)
            if new_item and new_item.name in items:
                if hasattr(new_item, "extend"):
                    new_item.extend(items[new_item.name])
                else:
                    items[new_item.name].values = new_item.values
                del items[new_item.name]
            self._sections[section_name].append(str(new_item))
        self._sections[section_name] += ["# endregion: Customized\n"]

        # Append the rest items
        for item_name in item_orders:
            if item_name in items:
                self._sections[section_name].append(str(items[item_name]))
                del items[item_name]

        # This should not happen
        if items:
            print(f"⚠️  Why there are still {item_class.__name__.lower()}s unmerged?")

    def merge_to_section(self, section_name, lines):
        if section_name == "Proxy Group":
            self.merge_items(section_name, lines, ProxyGroup)
        elif section_name == "General":
            self.merge_items(section_name, lines, Item)
        else:
            self.prepend_to_section(section_name, lines)

    def prepend_to_section(self, section_name, lines):
        if section_name not in self._sections:
            self._section_names.append(section_name)
            self._sections[section_name] = lines
        else:
            self._sections[section_name][0:0] = (
                ["# region: Customized\n"] + lines + ["# endregion: Customized\n"]
            )

    @property
    def section_names(self):
        return self._section_names


def merge(
    source1: str,
    source2: str,
    target: str,
    remote_ruleset=True,
    force_update: bool = False,
    dry_run: bool = False,
):
    if source1.startswith("https://"):
        print(f'ℹ️  Downloading managed profile from "{source1}"')
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
            ManagedProfile(url=source1, interval=0, strict=True).download(tmp.name)
        source1 = tmp.name
    else:
        ManagedProfile.reload(source1, force_update)
    print(f'ℹ️  Loading from "{source1}"')
    profile1 = SurgeProfile(source1)
    print(f'ℹ️  Loading from "{source2}"')
    profile2 = SurgeProfile(source2)

    target_ruleset = Path(target).parent / "ruleset"
    temp_ruleset = Path(source2).parent / "ruleset"

    if not remote_ruleset and not dry_run:
        # 复制 ruleset 文件夹回来，这样 surge 里面手动记录的 rule 不会丢失
        print(f'ℹ️  Copying rulesets back to "{temp_ruleset}"')
        if target_ruleset.is_dir() and target_ruleset.is_dir():
            copy_referenced_files(target_ruleset, temp_ruleset)

    for section_name in profile2.section_names:
        if section_name:
            len1 = len(profile1.get_section(section_name))
            len2 = len(profile2.get_section(section_name))
            print(
                f"ℹ️  Merging section [{section_name}]: {len1} + {len2} => {len1 + len2}"
            )
            lines = profile2.get_section(section_name)
            # 转换本地路径为 HTTPS URL
            if section_name == "Rule" and remote_ruleset:
                print(f"ℹ️️  Converting local path to HTTP URL in {section_name}")
                lines = [convert_local_path_to_http(line) for line in lines]
            profile1.merge_to_section(section_name, lines)

    if not dry_run:
        print(f'ℹ️  Saving to "{target}"')
        profile1.remove_managed_line()
        profile1.save(as_file=target)
        if not remote_ruleset:
            # 复制 ruleset 文件夹到终点
            print(f'ℹ️  Copying rulesets to "{Path(target).parent}"')
            target_ruleset.mkdir(parents=True, exist_ok=True)
            copy_referenced_files(temp_ruleset, target_ruleset)


def convert_local_path_to_http(line):
    if line.startswith("RULE-SET,") and not (
        line.startswith("RULE-SET,https://") or line.startswith("RULE-SET,SYSTEM")
    ):
        parts = line.split(",")
        local_path = parts[1].strip()
        url = f"{URL_PREFIX}/{local_path}"  # 替换为实际的 HTTP URL 前缀
        print(f"ℹ️  {local_path} → {url}")
        parts[1] = url
        return ",".join(parts)
    return line


def copy_referenced_files(source_folder, target_folder):
    source_path = Path(source_folder)
    target_path = Path(target_folder)
    if source_path.exists() and source_path.is_dir():
        for item in source_path.iterdir():
            target_file = target_path / item.name
            if item.is_file():
                if item.resolve() == target_file.resolve():
                    print(f"⚠️  Skipping copy of {item} to itself.")
                else:
                    if target_file.exists():
                        print(
                            f"⚠️  File {target_file} already exists and will be overwritten."
                        )
                    shutil.copy(item, target_file)


def get_path_from_user(path_name: str, default_path: str = None) -> str:
    p = None
    while not p or not os.path.exists(p):
        p = input(f"⌨️  Please input a valid {path_name} [{default_path}]:")
        if not p:
            p = default_path
        p = os.path.expanduser(p)
    return p


def backup(original_path):
    filename = datetime.datetime.now().strftime("bk-%Y-%m-%d.conf")
    backup_path = Path(CURRENT_DIR) / "profiles" / filename
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'ℹ️  Backing up "{original_path}" to "{backup_path}"')
    if os.path.exists(original_path):
        shutil.copyfile(original_path, backup_path, follow_symlinks=True)


@dataclasses.dataclass
class Config:
    source1: str
    source2: str
    target: str


def configure(args):
    if not args.conf_file.exists():
        print(f"ℹ️  No config ({args.conf_file}) exists, let's configure")

        conf = Config(
            source1=args.source1
            or get_path_from_user(
                "source config 1", default_path=f"{ SURGE_DIR }/subs/Dler Cloud.conf"
            ),
            source2=args.source2
            or get_path_from_user(
                "source config 2", default_path=f"{ CURRENT_DIR }/customized.dconf"
            ),
            target=args.target
            or get_path_from_user(
                "target config", default_path=f"{ SURGE_DIR }/all-in-one.conf"
            ),
        )

        print(f"ℹ️  Saving config to {args.conf_file}")
        with args.conf_file.open("w") as fp:
            json.dump(dataclasses.asdict(conf), fp, indent=2)
    else:
        with args.conf_file.open("r") as fp:
            conf = Config(**json.load(fp))
        conf = Config(
            source1=args.source1 or conf.source1,
            source2=args.source2 or conf.source2,
            target=args.target or conf.target,
        )
    return conf


def default_conf_file():
    config_dir = os.getenv("XDG_CONFIG_HOME") or "~/.config"
    conf_path = Path(config_dir).expanduser() / "nssurge" / "config.json"
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    return conf_path


def main():
    conf_file = default_conf_file()

    parser = argparse.ArgumentParser()
    parser.add_argument("source1", nargs="?")
    parser.add_argument("source2", nargs="?")
    parser.add_argument("-t", "--target", nargs="?")
    parser.add_argument("-c", "--conf-file", nargs="?", default=conf_file)
    parser.add_argument("-r", "--remote-ruleset", action="store_true")
    parser.add_argument("-f", "--force-update", action="store_true")
    parser.add_argument("-d", "--duplicate-only", action="store_true")
    parser.add_argument("-n", "--no-backup", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not save the target file"
    )
    args = parser.parse_args()

    conf = configure(args)
    if args.duplicate_only and not args.dry_run:
        shutil.copyfile(conf.source1, conf.target, follow_symlinks=True)
    else:
        merge(
            source1=conf.source1,
            source2=conf.source2,
            target=conf.target,
            remote_ruleset=args.remote_ruleset,
            force_update=args.force_update,
            dry_run=args.dry_run,
        )
    if not args.no_backup and not args.dry_run:
        backup(conf.target)


if __name__ == "__main__":
    main()
