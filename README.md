## Translate surge_config with proxy list to a seperate file
```shell
./translate https://address_to_surge_config_with_proxy_lists > proxy.list
```



## Merge managed profile with your customized portion

```shell
> ./merge.py -h
usage: merge.py [-h] [-t [TARGET]] [-c [CONF_FILE]] [source1] [source2]

positional arguments:
  source1
  source2

options:
  -h, --help            show this help message and exit
  -t [TARGET], --target [TARGET]
  -c [CONF_FILE], --conf_file [CONF_FILE]
```

By default, the merge command will merge `managed/managed_profile.conf ` with `conf/customized.conf`, and save the result to `conf/merged.conf`.

```shell
> ./merge.py
> cp profiles/merged.conf ~/Library/Mobile\ Documents/iCloud~com~nssurge~inc/Documents/merged.conf
```



## Add hard link

make a hard link of the merged file to wherever you sync your surge config to, so that it can also be used anywhere this repo is not present (such as on your iOS devices)

```shell
ln ~/Library/Mobile\ Documents/iCloud~com~nssurge~inc/Documents/backup/Dler\ Cloud.conf profiles/managed/managed_profile.conf
```
