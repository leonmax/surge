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

After running the first time, a config file will be generated under `$XDG_CONFIG_HOME/nssurge/config.json`, so that you don't have to type sources and target if they remain the same. An example is like below:

```json
{
  "source1": "/path_to_this_repo/profiles/managed/managed_profile.conf",
  "source2": "/path_to_this_repo/profiles/customized.conf",
  "target": "/path_to_this_repo/profiles/all-in-one.conf"
}
```

By default, the merge command will merge `managed/managed_profile.conf ` with `conf/customized.conf`, and save the result to `conf/all-in-one.conf`.

```shell
> ./merge.py
> cp profiles/all-in-one.conf ~/Library/Mobile\ Documents/iCloud~com~nssurge~inc/Documents/all-in-one.conf
```

A easier way to merge the profile with docker compose
```shell
docker compose run --rm merge
```

A shell script is also provided for merging the profile with docker
```shell
./merge.sh "https://dler.cloud/subscribe/A57y6psKvMFDxQVRT0IH?surge=smart" all-in-one.conf
```