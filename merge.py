#!/usr/bin/env python
import argparse
import dataclasses
from datetime import datetime
import json
import os
import re
import shutil
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

dir_path = os.path.dirname(os.path.realpath(__file__))


@dataclass
class ManagedProfile:
    url: str
    interval: int = 86400  # How often the profile is updated.
    strict: bool = False  # well we basically ignored that

    def download(self, filename):
        urllib.request.urlretrieve(self.url, filename)

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

    def prepend_to_section(self, section_name, lines):
        if section_name not in self._sections:
            self._section_names.append(section_name)
            self._sections[section_name] = lines
        else:
            self._sections[section_name][0:0] = ["# region: Customized\n"] + lines + ["# endregion: Customized\n"]

    @property
    def section_names(self):
        return self._section_names


def merge(source1: str, source2: str, target: str, force_update: bool=False):
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
            profile1.prepend_to_section(section_name, lines)

    print(f"ℹ️  Saving to {target}")
    profile1.remove_managed_line()
    profile1.save(as_file=target)


def get_path_from_user(path_name, default_path=None):
    p = None
    while not p or not os.path.exists(p):
        p = input(f"⌨️  Please input a valid {path_name} [{default_path}]:")
        if not p:
            p = default_path
    return p


def backup(original_path):
    os.makedirs(f"{dir_path}/profiles/backup/", exist_ok=True)
    filename = datetime.now().strftime("bk-%Y-%m-%d.conf")
    backup_path = f"{dir_path}/profiles/backup/{filename}"

    print(f"ℹ️  Backing up {original_path} to {backup_path}")
    if os.path.exists(original_path):
        shutil.copyfile(original_path, backup_path, follow_symlinks=True)


@dataclass
class Config:
    source1: str
    source2: str
    target: str


def configure(args):
    if not args.conf_file.exists():
        print(f"ℹ️  No config ({args.conf_file}) exists, let's configure")
        conf = Config(
            source1=args.source1 or get_path_from_user("source config 1", default_path=f"{dir_path}/profiles/managed/managed_profile.conf"),
            source2=args.source2 or get_path_from_user("source config 2", default_path=f"{dir_path}/profiles/customized.conf"),
            target=args.target or get_path_from_user(
                "target config",
                default_path=str(Path('~/Library/Mobile Documents/iCloud~com~nssurge~inc/Documents').expanduser() / "merged.conf")
            )
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
    conf_path = Path(os.getenv('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')) / "nssurge"
    os.makedirs(conf_path, exist_ok=True)
    return conf_path / "config.json"


def main():
    conf_file = default_conf_file()

    parser = argparse.ArgumentParser()
    parser.add_argument("source1", nargs='?')
    parser.add_argument("source2", nargs='?')
    parser.add_argument("-t", "--target", nargs='?')
    parser.add_argument("-c", "--conf_file", nargs='?', default=conf_file)
    parser.add_argument("-f", "--force_update", action="store_true")
    args = parser.parse_args()

    conf = configure(args)
    backup(conf.target)
    merge(conf.source1, conf.source2, conf.target, args.force_update)


if __name__ == "__main__":
    main()
