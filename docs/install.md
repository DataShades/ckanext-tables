# Installation

## Requirements

**Python 3.10+**

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.9 and earlier | no            |
| 2.10            | yes           |
| 2.11            | yes           |
| master          | not tested    |

## Installation

To install `ckanext-tables`, do the following:

- Activate your CKAN virtualenv and install the extension with `pip`:

    ```sh
    pip install ckanext-tables
    ```

- Add `tables` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).

    ```ini
    ckan.plugins = ... tables ...
    ```

## Developer installation

To install `ckanext-tables` for development, activate your CKAN virtualenv and
do:

```sh
git clone https://github.com/DataShades/ckanext-tables.git
cd ckanext-tables
pip install -e '.[docs,test]'
```
