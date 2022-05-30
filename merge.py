#!/usr/bin/env python
from datetime import datetime
from shutil import copyfile
from pathlib import Path
import os
import re
import argparse


class SurgeProfile:
    def __init__(self, file):
        self._file = file
        self._section_names = []
        self._sections = {}
        self._maanaged_config = None
        self.load()

    def load(self):
        with open(self._file, "r") as f:
            lines = f.readlines()
        cur = []
        self._section_names.append("")
        self._sections[""] = cur
        for l in lines:
            if l.startswith("#!MANAGED-CONFIG"):
                self._managed_config = l
                continue
            m = re.match("\[(.*)\]\n", l)
            if m:
                section_name = m.group(1)
                cur = []
                self._section_names.append(section_name)
                self._sections[section_name] = cur
            else:
                l = l if l.endswith("\n") else l + "\n"
                cur.append(l)

    def remove_managed_line(self):
        self._managed_config = None

    def save(self, as_file=None):
        file = as_file or self._file
        with open(file, "w+") as f:
            if self._managed_config:
                f.write(self._managed_config)

            for section_name in self.section_names:
                if section_name:
                    f.write(f"[{section_name}]\n")
                lines = self.get_section(section_name)
                #print(f"Writing section {section_name}: {len(lines)}")
                f.writelines(lines)

    def get_section(self, section_name):
        return self._sections[section_name] if section_name in self._sections else []

    def prepend_to_section(self, section_name, lines):
        if section_name not in self._sections:
            self._section_names.append(section_name)
            self._sections[section_name] = lines
        else:
            self._sections[section_name][0:0] = ["#region: Leonmax\n"] + lines + ["#endregion: Leonmax\n"]

    @property
    def section_names(self):
        return self._section_names


def merge(source1: str, source2: str, target: str, backup: str):

    print(f'Loading from "{source1}"')
    profile1 = SurgeProfile(source1)
    print(f'Loading from "{source2}"')
    profile2 = SurgeProfile(source2)

    for section_name in profile2.section_names:
        if section_name:
            len1 = len(profile1.get_section(section_name))
            len2 = len(profile2.get_section(section_name))
            print(f"Merging section {section_name}: {len1} + {len2} => {len1+len2}")
            lines = profile2.get_section(section_name)
            profile1.prepend_to_section(section_name, lines)

    if not backup:
        backup = datetime.today().strftime('backup/%Y-%m-%d.conf')
    print(f"Backing up {target} to {backup}")
    copyfile(target, backup)

    print(f"Saving to {target}")
    profile1.remove_managed_line()
    profile1.save(as_file=target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source1", nargs='?', default="Dler Cloud (Yujing).conf")
    parser.add_argument("source2", nargs='?', default="rules/merge.conf")
    parser.add_argument("target", nargs='?', default="Yangming.conf")
    parser.add_argument("backup", nargs='?')
    args = parser.parse_args()

    target = args.target or args.source2
    merge(args.source1, args.source2, target, args.backup)

