[![Tests](https://github.com/DataShades/ckanext-tables/actions/workflows/Tests/badge.svg)](https://github.com/DataShades/ckanext-tables/actions/workflows/test.yml)

# ckanext-tables

A CKAN extension to display tabular data in a nice way using [Tabulator](http://tabulator.info/).

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

1. Activate your CKAN virtualenv and install the extension with `pip`:
```sh
pip install ckanext-tables
```

1. Add `tables` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).



## Developer installation

To install `ckanext-tables` for development, activate your CKAN virtualenv and
do:

```sh
git clone https://github.com/DataShades/ckanext-tables.git
cd ckanext-tables
pip install -e .
```

## Tests

To run the tests, do:
```sh
pytest --ckan-ini=test.ini
```


## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
