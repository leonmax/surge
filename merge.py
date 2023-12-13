#!/usr/bin/env python
import argparse
import dataclasses
import datetime
import json
import os
import re
import shutil
import time
from urllib import request
from urllib.error import URLError
from pathlib import Path

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
SURGE_DIR = os.path.expanduser('~/Library/Mobile Documents/iCloud~com~nssurge~inc/Documents')


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

        if force_update:
            print(f"ℹ️  Downloading managed config from {profile.url}. It's forced.")
            profile.download(filename)
        elif time.time() > Path(filename).stat().st_mtime + profile.interval:
            print(f"ℹ️  Downloading managed config from {profile.url}. It's older than {profile.interval} secs.")
            profile.download(filename)

@dataclasses.dataclass
class ProxyGroup:
    name: str
    group_type: str  # select, url-test, fallback, load-balance, comment-or-empty-line
    proxies: list[str] = dataclasses.field(default_factory=list)
    properties: dict[str, str] = dataclasses.field(default_factory=dict)

    @staticmethod
    def parse_line(line):
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
                    k, v = value.split("=",1)
                    properties[k] = v
                else:
                    proxies.append(value)
            return ProxyGroup(name=m.group("name").strip(), group_type=m.group("group_type"), proxies=proxies, properties=properties)
        print("failed to parse line: " + line)
        return None

    def extend(self, proxy_group):
        if self.name != proxy_group.name:
            raise Exception(f"⚠️  Cannot extend proxy group {self.name} with {proxy_group.name}")
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

    def save(self, as_file=None):
        _file = as_file or self._file
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

    def merge_to_section(self, section_name, lines):
        if section_name == "Proxy Group":
            # Map group name to group
            group_orders = []
            groups = {}
            for line in self._sections[section_name]:
                group = ProxyGroup.parse_line(line)
                if group:
                    group_orders.append(group.name)
                    groups[group.name] = group

            # Merge customized groups
            self._sections[section_name] = ["# region: Customized\n"]
            for line in lines:
                new_group = ProxyGroup.parse_line(line)
                if new_group and new_group.name in groups:
                    new_group.extend(groups[new_group.name])
                    del groups[new_group.name]
                self._sections[section_name].append(str(new_group))
            self._sections[section_name] += ["# endregion: Customized\n"]

            # Append the rest groups
            for group_name in group_orders:
                if group_name in groups:
                    self._sections[section_name].append(str(groups[group_name]))
                    del groups[group_name]
            # This should not happen
            if groups:
                print("⚠️  Why there are still groups unmerged?")
        else:
            self.prepend_to_section(section_name, lines)


    def prepend_to_section(self, section_name, lines):
        if section_name not in self._sections:
            self._section_names.append(section_name)
            self._sections[section_name] = lines
        else:
            self._sections[section_name][0:0] = ["# region: Customized\n"] + lines + ["# endregion: Customized\n"]

    @property
    def section_names(self):
        return self._section_names


def merge(source1: str, source2: str, target: str, force_update: bool = False, dry_run: bool = False):
    ManagedProfile.reload(source1, force_update)
    print(f'ℹ️  Loading from "{source1}"')
    profile1 = SurgeProfile(source1)
    print(f'ℹ️  Loading from "{source2}"')
    profile2 = SurgeProfile(source2)

    for section_name in profile2.section_names:
        if section_name:
            len1 = len(profile1.get_section(section_name))
            len2 = len(profile2.get_section(section_name))
            print(f"ℹ️  Merging section [{section_name}]: {len1} + {len2} => {len1 + len2}")
            lines = profile2.get_section(section_name)
            profile1.merge_to_section(section_name, lines)

    if not dry_run:
        print(f'ℹ️  Saving to "{target}"')
        profile1.remove_managed_line()
        profile1.save(as_file=target)


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
    backup_path = Path(CURRENT_DIR) / 'profiles' / filename
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
            source1=args.source1 or get_path_from_user(
                "source config 1", default_path=f"{ SURGE_DIR }/subs/Dler Cloud.conf"),
            source2=args.source2 or get_path_from_user(
                "source config 2", default_path=f"{ CURRENT_DIR }/customized.dconf"),
            target=args.target or get_path_from_user(
                "target config", default_path=f"{ SURGE_DIR }/merged.conf")
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
            target=args.target or conf.target)
    return conf


def default_conf_file():
    config_dir = os.getenv('XDG_CONFIG_HOME') or '~/.config'
    conf_path = Path(config_dir).expanduser() / "nssurge" / "config.json"
    conf_path.parent.mkdir(parents=True, exist_ok=True)
    return conf_path


def main():
    conf_file = default_conf_file()

    parser = argparse.ArgumentParser()
    parser.add_argument("source1", nargs='?')
    parser.add_argument("source2", nargs='?')
    parser.add_argument("-t", "--target", nargs='?')
    parser.add_argument("-c", "--conf-file", nargs='?', default=conf_file)
    parser.add_argument("-f", "--force-update", action="store_true")
    parser.add_argument("-d", "--duplicate-only", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Do not save the target file")
    args = parser.parse_args()

    conf = configure(args)
    if args.duplicate_only and not args.dry_run:
        shutil.copyfile(conf.source1, conf.target, follow_symlinks=True)
    else:
        merge(conf.source1, conf.source2, conf.target, args.force_update, args.dry_run)
    if not args.no_backup and not args.dry_run:
        backup(conf.target)

if __name__ == "__main__":
    main()
